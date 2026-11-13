"""Validações de conta, anti-IDOR de mídias e datas para postagens."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.aplicacao.publicacao.dtos import CriarPostagemCmd
from app.dominio.entidades.tenant import ContaInstagram
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.portas.repositorios_conteudo import MidiaRepositoryPort
from app.dominio.portas.repositorios_tenant import ContaIGRepositoryPort


async def exigir_conta_ativa(
    conta_repo: ContaIGRepositoryPort,
    empresa_id: UUID,
    conta_ig_id: UUID,
    validar_token: bool = False,
) -> ContaInstagram:
    """Garante existência, isolamento por empresa_id, ativação e validade do token."""
    conta = await conta_repo.buscar_por_id(empresa_id, conta_ig_id)
    if conta is None:
        raise ErroValidacaoDominio("Conta Instagram não encontrada para esta empresa.")
    if not conta.ativa:
        raise ErroValidacaoDominio("Conta Instagram desativada.")
    if validar_token and conta.token_expirado():
        raise ErroValidacaoDominio("Token OAuth da conta Instagram expirou; reconecte.")
    return conta


async def resolver_chaves_midias(
    midia_repo: MidiaRepositoryPort,
    cmd: CriarPostagemCmd,
) -> list[str]:
    """Resolve e valida que todas as mídias pertencem à conta do tenant (anti-IDOR)."""
    chaves: list[str] = []
    for midia_id in cmd.midia_ids:
        midia = await midia_repo.buscar_por_id(cmd.empresa_id, cmd.conta_ig_id, midia_id)
        if midia is None:
            raise ErroValidacaoDominio("Mídia informada não pertence a esta conta.")
        chaves.append(midia.chave_storage)

    if cmd.midias_chaves:
        midias_conta = await midia_repo.listar_por_conta(cmd.empresa_id, cmd.conta_ig_id)
        validas = {m.chave_storage for m in midias_conta}
        for chave in cmd.midias_chaves:
            limpa = chave.strip()
            if limpa not in validas:
                raise ErroValidacaoDominio("Chave de mídia não pertence a esta conta.")
            chaves.append(limpa)

    if not chaves:
        raise ErroValidacaoDominio("Informe ao menos uma mídia válida da biblioteca.")
    return chaves


def normalizar_agendamento_utc(dt: datetime) -> datetime:
    """Exige datetime com timezone e converte para UTC."""
    if dt.tzinfo is None:
        raise ErroValidacaoDominio("Data de agendamento deve conter fuso horário (UTC).")
    return dt.astimezone(UTC)
