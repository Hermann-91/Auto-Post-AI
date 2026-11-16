"""Helpers puros de parsing, validação e extração de custos do OpenRouter."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from app.dominio.excecoes import ErroIntegracaoIA, ErroValidacaoDominio

_QUANTUM_CUSTO = Decimal("0.000001")
_MAX_IMAGEM_BYTES = 20 * 1024 * 1024


def modelo_eh_gratuito(modelo: str) -> bool:
    """Identifica modelos OpenRouter gratuitos para evitar fallback pago."""
    return modelo == "openrouter/free" or modelo.endswith(":free")


def validar_url_imagem(url: str) -> str:
    """Aceita apenas data URI de imagem ou URL HTTPS válida contra SSRF."""
    limpa = url.strip()
    if limpa.startswith("data:image/"):
        return limpa
    analisada = urlparse(limpa)
    if analisada.scheme == "https" and analisada.netloc:
        return limpa
    raise ErroValidacaoDominio("Imagem deve ser data URI (data:image/*) ou URL HTTPS válida.")


def extrair_usage(dados: dict[str, Any], modelo_solicitado: str) -> dict[str, Any]:
    """Extrai gen_id, tokens e usage.cost em Decimal seguro da resposta OpenRouter."""
    usage = dados.get("usage")
    uso = usage if isinstance(usage, dict) else {}
    bruto_custo = uso.get("cost")
    try:
        custo = Decimal(str(bruto_custo if bruto_custo is not None else "0"))
    except (InvalidOperation, ValueError, TypeError):
        custo = Decimal("0")
    custo_seguro = max(Decimal("0"), custo).quantize(_QUANTUM_CUSTO)

    detalhes = uso.get("prompt_tokens_details")
    cached = detalhes.get("cached_tokens", 0) if isinstance(detalhes, dict) else 0
    return {
        "openrouter_gen_id": str(dados.get("id") or ""),
        "modelo": str(dados.get("model") or modelo_solicitado),
        "tokens_in": max(0, int(uso.get("prompt_tokens") or 0)),
        "tokens_out": max(0, int(uso.get("completion_tokens") or 0)),
        "tokens_cached": max(0, int(cached or 0)),
        "custo_usd": custo_seguro,
    }


def extrair_mensagem(dados: dict[str, Any]) -> dict[str, Any]:
    """Valida e retorna o objeto message principal de choices[0]."""
    escolhas = dados.get("choices")
    if not isinstance(escolhas, list) or not escolhas:
        raise ErroIntegracaoIA("Resposta do OpenRouter sem escolhas válidas.")
    msg = escolhas[0].get("message") if isinstance(escolhas[0], dict) else None
    if not isinstance(msg, dict):
        raise ErroIntegracaoIA("Resposta do OpenRouter sem objeto de mensagem.")
    return msg


def extrair_texto_mensagem(msg: dict[str, Any]) -> str:
    """Extrai resposta textual ou JSON bruto da mensagem retornada."""
    conteudo = msg.get("content")
    if isinstance(conteudo, str) and conteudo.strip():
        return conteudo
    if isinstance(conteudo, list):
        partes = [
            str(item.get("text", ""))
            for item in conteudo
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        junto = "\n".join(p for p in partes if p).strip()
        if junto:
            return junto
    raise ErroIntegracaoIA("Resposta textual vazia retornada pelo OpenRouter.")


def extrair_url_imagem_gerada(msg: dict[str, Any]) -> str:
    """Lê choices[0].message.images[0].image_url.url (Nano Banana) ou fallback content."""
    imagens = msg.get("images")
    if isinstance(imagens, list) and imagens:
        primeiro = imagens[0]
        img_obj = primeiro.get("image_url") if isinstance(primeiro, dict) else None
        if isinstance(img_obj, dict) and isinstance(img_obj.get("url"), str):
            return str(img_obj["url"])
    conteudo = msg.get("content")
    if isinstance(conteudo, list):
        for item in conteudo:
            if isinstance(item, dict) and item.get("type") == "image_url":
                obj = item.get("image_url")
                if isinstance(obj, dict) and isinstance(obj.get("url"), str):
                    return str(obj["url"])
    raise ErroIntegracaoIA("Resposta do modelo de imagem não retornou URL/base64 de saída.")


def decodificar_data_uri(uri: str) -> bytes:
    """Decodifica data URI base64 validando formato e limite de tamanho."""
    if not uri.startswith("data:image/") or ";base64," not in uri:
        raise ErroIntegracaoIA("Formato de data URI inválido retornado pelo modelo de imagem.")
    _, payload_b64 = uri.split(";base64,", 1)
    try:
        dados = base64.b64decode(payload_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ErroIntegracaoIA("Falha ao decodificar imagem base64 do OpenRouter.") from exc
    if not dados or len(dados) > _MAX_IMAGEM_BYTES:
        raise ErroIntegracaoIA("Imagem gerada vazia ou excede limite máximo permitido.")
    return dados


def montar_payload_texto(
    system_prompt: str, user_prompt: str, modelo: str, formato_json: bool
) -> dict[str, Any]:
    """Monta payload OpenRouter para chat textual ou JSON estruturado."""
    msgs = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    payload: dict[str, Any] = {"model": modelo, "messages": msgs}
    if formato_json:
        payload["response_format"] = {"type": "json_object"}
    return payload


def montar_payload_visao(
    system_prompt: str, user_prompt: str, imagem_data_url: str, modelo: str
) -> dict[str, Any]:
    """Monta payload multimodal validando esquema da imagem contra SSRF."""
    url_segura = validar_url_imagem(imagem_data_url)
    conteudo = [
        {"type": "text", "text": user_prompt},
        {"type": "image_url", "image_url": {"url": url_segura}},
    ]
    return {
        "model": modelo,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": conteudo},
        ],
    }


def montar_payload_imagem(
    prompt: str, modelo: str, imagem_base_url: str | None = None,
    imagens_referencia_urls: Sequence[str] = (),
) -> dict[str, Any]:
    """Monta payload Nano Banana (modalities=['image', 'text']) com 0..N referências."""
    prompt_limpo = prompt.strip()
    if not prompt_limpo:
        raise ErroValidacaoDominio("Prompt visual não pode ser vazio.")
    base = [imagem_base_url] if imagem_base_url is not None else []
    brutas = [*base, *imagens_referencia_urls]
    urls = list(dict.fromkeys(validar_url_imagem(u) for u in brutas))
    conteudo_user: str | list[dict[str, Any]] = prompt_limpo
    if urls:
        conteudo_user = [
            {"type": "text", "text": prompt_limpo},
            *({"type": "image_url", "image_url": {"url": u}} for u in urls),
        ]
    return {"model": modelo, "modalities": ["image", "text"],
            "messages": [{"role": "user", "content": conteudo_user}]}


def montar_payload_embeddings(textos: list[str], modelo: str) -> dict[str, Any]:
    """Monta payload para OpenRouter /embeddings validando textos não vazios."""
    limpos = [t.strip() for t in textos if t.strip()]
    if not limpos or len(limpos) != len(textos):
        raise ErroValidacaoDominio("Textos para embeddings não podem ser vazios.")
    return {"model": modelo, "input": limpos}


def extrair_embeddings(dados: dict[str, Any], esperado: int) -> list[list[float]]:
    """Extrai e ordena vetores de embeddings garantindo integridade dimensional."""
    itens = dados.get("data")
    if not isinstance(itens, list) or len(itens) != esperado:
        raise ErroIntegracaoIA("Resposta de embeddings incompatível com os chunks enviados.")
    ordenados = sorted(
        (i for i in itens if isinstance(i, dict)),
        key=lambda i: int(i.get("index", 0)),
    )
    vetores: list[list[float]] = []
    for item in ordenados:
        bruto = item.get("embedding")
        if not isinstance(bruto, list) or not bruto:
            raise ErroIntegracaoIA("Vetor de embedding ausente ou vazio na resposta.")
        vetores.append([float(v) for v in bruto])
    if len(vetores) != esperado:
        raise ErroIntegracaoIA("Quantidade de embeddings inválida retornada pelo OpenRouter.")
    return vetores
