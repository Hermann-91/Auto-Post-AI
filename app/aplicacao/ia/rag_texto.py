"""Utilitários puros de chunking e ranqueamento lexical para RAG por conta."""

from __future__ import annotations

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


def ranquear_trechos_rag(
    fontes: list[FonteRAG],
    consulta: str,
    top_k: int = 4,
    max_chars: int = 1800,
) -> list[str]:
    """Ordena chunks por correspondência com tema e título respeitando max_chars."""
    termos_consulta = set(_tokenizar(consulta))
    candidatos: list[tuple[float, str]] = []
    for fonte in fontes:
        tokens_titulo = set(_tokenizar(fonte.titulo))
        for chunk in fonte.chunks:
            tokens_chunk = _tokenizar(chunk)
            if not tokens_chunk:
                continue
            intersecao = len(termos_consulta & set(tokens_chunk))
            bonus_titulo = 1.5 * len(termos_consulta & tokens_titulo)
            freq = sum(tokens_chunk.count(t) for t in termos_consulta)
            score = (intersecao * 2.0) + bonus_titulo + (0.25 * freq)
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
