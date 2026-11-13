"""Configuração de logging estruturado com mascaramento de segredos."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

_PADRAO_SEGREDOS = re.compile(
    r"(Bearer\s+[A-Za-z0-9\-_\.]+|gAAAA[A-Za-z0-9\-_=]+)",
    re.IGNORECASE,
)


class FiltroMascaraSegredos(logging.Filter):
    """Mascara tokens Bearer e Fernet em mensagens de log."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _PADRAO_SEGREDOS.sub("[REDIGIDO]", record.msg)
        return True


class FormatadorJsonSeguro(logging.Formatter):
    """Serializa registros de log em JSON enxuto para observabilidade em VPS."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "nivel": record.levelname,
            "logger": record.name,
            "mensagem": record.getMessage(),
        }
        if record.exc_info:
            payload["excecao"] = self.formatException(record.exc_info)
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
