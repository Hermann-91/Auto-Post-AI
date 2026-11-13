"""Exceções puras da camada de domínio."""

from __future__ import annotations


class ErroDominio(Exception):
    """Classe base para erros de regra de negócio e invariantes."""


class ErroValidacaoDominio(ErroDominio):
    """Violação de invariante estrutural ou regra de formato."""


class ErroTransicaoEstado(ErroDominio):
    """Tentativa de transição ilegal na máquina de estados."""


class ErroCotaExcedida(ErroDominio):
    """Limite de quantidade ou bytes da biblioteca de mídia atingido."""


class ErroOrcamentoExcedido(ErroDominio):
    """Teto mensal ou diário de gastos com IA atingido."""


class ErroCredenciaisInvalidas(ErroDominio):
    """Falha de autenticação ou sessão inválida."""


class ErroRateLimitExcedido(ErroDominio):
    """Limite de requisições excedido; carrega segundos para retry."""

    def __init__(self, mensagem: str, retry_after_segundos: int) -> None:
        super().__init__(mensagem)
        self.retry_after_segundos = max(1, retry_after_segundos)


class ErroCaptchaInvalido(ErroDominio):
    """Falha na validação anti-bot (Turnstile)."""


class ErroTokenReutilizado(ErroDominio):
    """Reuso suspeito de refresh token já rotacionado."""


class ErroConflitoDados(ErroDominio):
    """Conflito de unicidade (ex.: e-mail já cadastrado)."""


class ErroSegurancaInterna(ErroDominio):
    """Erro crítico de integridade criptográfica."""


class ErroIntegracaoIA(ErroDominio):
    """Falha de comunicação ou resposta inválida do provedor de IA."""


class ErroIntegracaoMeta(ErroDominio):
    """Falha de autenticação OAuth, container ou publicação na Meta Graph API."""


class ErroLimitePublicacaoMeta(ErroIntegracaoMeta):
    """Teto móvel de 24h de publicações (content_publishing_limit) atingido."""
