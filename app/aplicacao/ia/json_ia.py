"""Parser seguro para saídas JSON estruturadas retornadas por LLMs."""

from __future__ import annotations

import json
import re
from typing import Any

from app.dominio.excecoes import ErroIntegracaoIA

_PADRAO_CERCA = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def extrair_objeto_json(texto_bruto: str) -> dict[str, Any]:
    """Remove cercas markdown opcionais e decodifica um objeto JSON válido."""
    limpo = texto_bruto.strip()
    match = _PADRAO_CERCA.match(limpo)
    if match:
        limpo = match.group(1).strip()

    try:
        dados = json.loads(limpo)
    except ValueError:
        inicio = limpo.find("{")
        fim = limpo.rfind("}")
        if inicio == -1 or fim <= inicio:
            raise ErroIntegracaoIA(
                "Modelo de IA não retornou JSON estruturado válido."
            ) from None
        try:
            dados = json.loads(limpo[inicio : fim + 1])
        except ValueError as exc:
            raise ErroIntegracaoIA("Falha ao decodificar JSON retornado pela IA.") from exc

    if not isinstance(dados, dict):
        raise ErroIntegracaoIA("Resposta JSON da IA deve ser um objeto na raiz.")
    return dados
