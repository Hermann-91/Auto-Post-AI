"""Configuração de logging estruturado com mascaramento de segredos."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

_PADRAO_SEGREDOS = re.compile(
    r"(Bearer\s+[A-Za-z0-9\-_\.=]+"
    r"|gAAAA[A-Za-z0-9\-_=]+"
    r"|eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
    r"|sk-or-v1-[A-Za-z0-9\-_]+"
    r"|(?:access_token|refresh_token|client_secret|api_key|secret|password|senha)"
    r"\s*[=:]\s*['\"]?[^\s&'\",}]+['\"]?"
    r"|(?:postgresql(?:\+asyncpg)?|redis|rediss)://[^:\s/]*:[^@\s]+@)",
    re.IGNORECASE,
)


def mascarar_segredos(texto: str) -> str:
    """Redige tokens Bearer, JWT, Fernet, chaves de API e senhas de conexão."""
    return _PADRAO_SEGREDOS.sub("[REDIGIDO]", texto)


class FiltroMascaraSegredos(logging.Filter):
    """Mascara segredos tanto na mensagem base quanto nos argumentos do LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mascarar_segredos(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                mascarar_segredos(arg) if isinstance(arg, str) else arg for arg in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                k: mascarar_segredos(v) if isinstance(v, str) else v
                for k, v in record.args.items()
            }
        return True


class FormatadorJsonSeguro(logging.Formatter):
    """Serializa registros de log em JSON enxuto para observabilidade em VPS."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "nivel": record.levelname,
            "logger": record.name,
            "mensagem": mascarar_segredos(record.getMessage()),
        }
        if record.exc_info:
            payload["excecao"] = mascarar_segredos(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configurar_logging(nivel: int = logging.INFO) -> None:
    """Configura handler raiz com formato JSON e filtro anti-vazamento."""
    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    raiz.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(FormatadorJsonSeguro())
    handler.addFilter(FiltroMascaraSegredos())
    raiz.addHandler(handler)
