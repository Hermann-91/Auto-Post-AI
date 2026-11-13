"""Modelos, exceções internas HTTP e helpers de validação da Meta Graph API."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.dominio.excecoes import ErroIntegracaoMeta, ErroValidacaoDominio

_EXTENSOES_VIDEO = (".mp4", ".mov", ".m4v")


@dataclass(frozen=True, slots=True)
class LimitePublicacaoMeta:
    """Uso atual e teto móvel de 24h retornado por content_publishing_limit."""

    quota_usage: int
    quota_total: int

    @property
    def atingido(self) -> bool:
        return self.quota_usage >= self.quota_total


@dataclass(frozen=True, slots=True)
class StatusContainerMeta:
    """Estado de processamento de um container na Meta."""

    status_code: str
    status_detalhe: str = ""


class ErroHttpMeta(ErroIntegracaoMeta):
    """Erro HTTP 4xx/5xx retornado pela Meta Graph API."""

    def __init__(self, status_code: int, mensagem: str) -> None:
        super().__init__(mensagem)
        self.status_code = status_code


class ErroTransitorioMeta(ErroIntegracaoMeta):
    """Erro de timeout ou rede durante requisição Meta."""


def extrair_erro_meta(resp: httpx.Response) -> str:
    """Extrai mensagem e código de erro da resposta JSON da Meta."""
    try:
        dados = resp.json()
        erro = dados.get("error") if isinstance(dados, dict) else None
        if isinstance(erro, dict):
            msg = str(erro.get("message") or "").strip()
            cod = erro.get("code")
            if msg:
                return f"{msg} (code={cod})" if cod is not None else msg
    except ValueError:
        pass
    return f"HTTP {resp.status_code}"


def validar_urls_publicas(urls_publicas: list[str], exigir_https: bool = False) -> list[str]:
    """Valida esquema e formato das URLs públicas antes de enviar à Meta."""
    limpas: list[str] = []
    for url in urls_publicas:
        u = url.strip()
        analisada = urlparse(u)
        esquema = analisada.scheme.lower()
        if not u or not analisada.netloc or esquema not in {"http", "https"}:
            raise ErroValidacaoDominio("URL pública de mídia inválida para publicação Meta.")
        if exigir_https and esquema != "https":
            raise ErroValidacaoDominio("Meta Graph API em produção exige URL pública HTTPS.")
        limpas.append(u)
    return limpas


def eh_video_midia(chave_ou_url: str) -> bool:
    """Detecta se a chave de storage ou URL aponta para arquivo de vídeo."""
    caminho = urlparse(chave_ou_url.strip()).path.lower()
    return caminho.endswith(_EXTENSOES_VIDEO)
