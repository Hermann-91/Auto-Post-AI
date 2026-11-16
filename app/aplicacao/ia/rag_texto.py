"""Utilitários puros de chunking, resumo factual e ranqueamento híbrido RAG."""

from __future__ import annotations

import math
import re
import unicodedata

from app.dominio.entidades.ia_rag import FonteRAG
from app.dominio.excecoes import ErroValidacaoDominio

_STOPWORDS_PT = frozenset(
    {
        "para", "como", "com", "que", "uma", "uns", "umas", "dos", "das", "por",
        "nao", "mais", "sua", "seu", "suas", "seus", "nos", "nas", "sobre", "entre",
        "isso", "esta", "este", "pela", "pelo", "muito", "sem", "ate",
    }
)
_PADRAO_PALAVRA = re.compile(r"[a-z0-9]{2,}")


def _tokenizar(texto: str) -> list[str]:
    nfkd = unicodedata.normalize("NFKD", texto)
    sem_acentos = "".join(ch for ch in nfkd if not unicodedata.combining(ch)).lower()
    return [tok for tok in _PADRAO_PALAVRA.findall(sem_acentos) if tok not in _STOPWORDS_PT]


def _quebrar_bloco_longo(bloco: str, max_chars: int, overlap: int) -> list[str]:
    palavras = bloco.split()
    partes: list[str] = []
    atual: list[str] = []
    tam_atual = 0
    for palavra in palavras:
        acrescimo = len(palavra) + (1 if atual else 0)
        if atual and tam_atual + acrescimo > max_chars:
            trecho = " ".join(atual)
            partes.append(trecho)
            cauda = trecho[-overlap:].strip() if overlap > 0 else ""
            atual = cauda.split() if cauda else []
            tam_atual = sum(len(p) for p in atual) + max(0, len(atual) - 1)
        atual.append(palavra)
        tam_atual += acrescimo
    if atual:
        partes.append(" ".join(atual))
    return partes


def segmentar_em_chunks(conteudo: str, max_chars: int = 500, overlap: int = 80) -> list[str]:
    """Segmenta texto em chunks coesos por parágrafo/palavras sem corte bruto."""
    texto = re.sub(r"\n{3,}", "\n\n", conteudo.strip())
    if not texto:
        raise ErroValidacaoDominio("Conteúdo da fonte RAG não pode ser vazio.")
    chunks: list[str] = []
    buffer = ""
    for paragrafo in [p.strip() for p in texto.split("\n\n") if p.strip()]:
        if len(paragrafo) > max_chars:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.extend(_quebrar_bloco_longo(paragrafo, max_chars, overlap))
            continue
        candidato = f"{buffer}\n\n{paragrafo}".strip() if buffer else paragrafo
        if len(candidato) <= max_chars:
            buffer = candidato
        else:
            chunks.append(buffer)
            buffer = paragrafo
    if buffer:
        chunks.append(buffer)
    return chunks


def gerar_resumo_fatos(titulo: str, conteudo: str, max_chars: int = 600) -> str:
    """Extrai síntese factual determinística ($0) para indexação e Brand Bible."""
    linhas = [" ".join(ln.split()) for ln in conteudo.splitlines() if ln.strip()]
    unicas: list[str] = []
    vistas: set[str] = set()
    for ln in linhas:
        chave = ln.lower()
        if chave not in vistas:
            vistas.add(chave)
            unicas.append(ln)
    corpo = " | ".join(unicas)
    prefixo = f"{titulo.strip()}: " if titulo.strip() else ""
    return f"{prefixo}{corpo}"[:max_chars].strip()


def similaridade_cosseno(vetor_a: list[float], vetor_b: list[float]) -> float:
    """Calcula similaridade de cosseno segura entre dois vetores numéricos."""
    if not vetor_a or len(vetor_a) != len(vetor_b):
        return 0.0
    produto = sum(a * b for a, b in zip(vetor_a, vetor_b, strict=True))
    norma_a = math.sqrt(sum(a * a for a in vetor_a))
    norma_b = math.sqrt(sum(b * b for b in vetor_b))
    if norma_a == 0.0 or norma_b == 0.0:
        return 0.0
    return max(-1.0, min(1.0, produto / (norma_a * norma_b)))


def ranquear_trechos_rag(
    fontes: list[FonteRAG],
    consulta: str,
    embedding_consulta: list[float] | None = None,
    top_k: int = 4,
    max_chars: int = 1800,
    limiar_semantico: float = 0.25,
) -> list[str]:
    """Ordena chunks por BM25 lexical + cosseno de embeddings descartando irrelevantes."""
    termos_consulta = set(_tokenizar(consulta))
    docs: list[tuple[FonteRAG, int, str, list[str]]] = []
    for fonte in fontes:
        for idx, chunk in enumerate(fonte.chunks):
            tokens = _tokenizar(chunk)
            if tokens:
                docs.append((fonte, idx, chunk, tokens))
    if not docs:
        return []

    n_docs = len(docs)
    avgdl = sum(len(d[3]) for d in docs) / n_docs
    df = {t: sum(1 for d in docs if t in d[3]) for t in termos_consulta}
    candidatos: list[tuple[float, str]] = []

    for fonte, idx, chunk, tokens_chunk in docs:
        tokens_titulo = set(_tokenizar(fonte.titulo))
        bm25 = 0.0
        for t in termos_consulta:
            tf = tokens_chunk.count(t)
            if tf == 0:
                continue
            idf = math.log(1.0 + (n_docs - df[t] + 0.5) / (df[t] + 0.5))
            denom = tf + 1.2 * (0.25 + 0.75 * (len(tokens_chunk) / avgdl))
            bm25 += idf * (tf * 2.2) / denom
        bonus_titulo = 1.2 * len(termos_consulta & tokens_titulo)
        score_lex = bm25 + bonus_titulo
        lex_norm = (score_lex / (score_lex + 2.0)) if score_lex > 0.0 else 0.0

        tem_emb = embedding_consulta is not None and idx < len(fonte.embeddings_chunks)
        sim_sem = (
            max(0.0, similaridade_cosseno(embedding_consulta, fonte.embeddings_chunks[idx]))
            if tem_emb and embedding_consulta is not None
            else 0.0
        )
        if score_lex <= 0.0 and (not tem_emb or sim_sem < limiar_semantico):
            continue
        score = (0.45 * lex_norm + 0.55 * sim_sem) if tem_emb and sim_sem > 0.0 else lex_norm
        if score > 0.0:
            candidatos.append((score, f"[{fonte.titulo}] {chunk}"))

    candidatos.sort(key=lambda item: item[0], reverse=True)
    selecionados: list[str] = []
    acumulado = 0
    for _, texto in candidatos[:top_k]:
        if acumulado + len(texto) > max_chars and selecionados:
            break
        selecionados.append(texto)
        acumulado += len(texto)
    return selecionados
