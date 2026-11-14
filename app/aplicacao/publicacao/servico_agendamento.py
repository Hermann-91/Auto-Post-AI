"""Casos de uso de agendamento, listagem e publicação oficial Meta."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.aplicacao.publicacao.dtos import (
    AgendarPostagemCmd,
    CriarPostagemCmd,
    ResultadoPublicacaoDTO,
)
from app.aplicacao.publicacao.validadores_postagem import (
    exigir_conta_ativa,
    normalizar_agendamento_utc,
    resolver_chaves_midias,
)
from app.dominio.entidades.publicacao import Postagem
from app.dominio.excecoes import ErroDominio, ErroLimitePublicacaoMeta, ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import StatusPostagem, TipoMidia
from app.dominio.objetos_valor.maquina_estados import validar_transicao_postagem
from app.dominio.portas.ia_meta import PublicadorMidiaStrategyPort
from app.dominio.portas.midia_storage import StorageMidiaPort
from app.dominio.portas.repositorios_conteudo import MidiaRepositoryPort, PostagemRepositoryPort
from app.dominio.portas.repositorios_tenant import ContaIGRepositoryPort
from app.dominio.portas.seguranca import CriptografiaPort

logger = logging.getLogger(__name__)


class FabricaPublicadoresPort(Protocol):
    """Porta para resolver estratégia de publicação oficial por TipoMidia."""

    def obter(self, tipo_midia: TipoMidia) -> PublicadorMidiaStrategyPort: ...


class LockPublicacaoPort(Protocol):
    """Porta de lock distribuído para impedir publicação concorrente."""

    async def adquirir(self, chave: str, ttl_segundos: int) -> str | None: ...
    async def liberar(self, chave: str, token_lock: str) -> None: ...


class ServicoAgendamentoUseCase:
    """Orquestra ciclo de vida de Postagem até a publicação oficial na Meta."""

    def __init__(
        self,
        conta_repo: ContaIGRepositoryPort,
        midia_repo: MidiaRepositoryPort,
        post_repo: PostagemRepositoryPort,
        storage: StorageMidiaPort,
        cripto: CriptografiaPort,
        fabrica_publicadores: FabricaPublicadoresPort,
        lock_distribuido: LockPublicacaoPort | None = None,
        lock_ttl_segundos: int = 300,
        reagendar_cota_minutos: int = 60,
    ) -> None:
        self._conta_repo = conta_repo
        self._midia_repo = midia_repo
        self._post_repo = post_repo
        self._storage = storage
        self._cripto = cripto
        self._fabrica = fabrica_publicadores
        self._lock = lock_distribuido
        self._lock_ttl = lock_ttl_segundos
        self._reagendar_minutos = reagendar_cota_minutos

    async def criar_postagem(self, cmd: CriarPostagemCmd) -> Postagem:
        """Cria rascunho validado contra IDOR e agenda se agendado_para for enviado."""
        await exigir_conta_ativa(
            self._conta_repo, cmd.empresa_id, cmd.conta_ig_id, cmd.agendado_para is not None
        )
        post = Postagem(
            empresa_id=cmd.empresa_id,
            conta_ig_id=cmd.conta_ig_id,
            tipo_midia=cmd.tipo_midia,
            midias_chaves=await resolver_chaves_midias(self._midia_repo, cmd),
            legenda=cmd.legenda,
            planejamento_id=cmd.planejamento_id,
        )
        if cmd.agendado_para is not None:
            post.agendar(normalizar_agendamento_utc(cmd.agendado_para))
        return await self._post_repo.salvar(post)

    async def agendar_postagem(self, cmd: AgendarPostagemCmd) -> Postagem:
        """Agenda, reagenda ou programa repostagem de post existente."""
        await exigir_conta_ativa(self._conta_repo, cmd.empresa_id, cmd.conta_ig_id, True)
        post = await self.obter_postagem(cmd.empresa_id, cmd.conta_ig_id, cmd.postagem_id)
        if post.status in {
            StatusPostagem.PUBLICADO, StatusPostagem.CANCELADO, StatusPostagem.FALHA
        }:
            post.status = StatusPostagem.RASCUNHO
            post.meta_container_id = None
        post.agendar(normalizar_agendamento_utc(cmd.agendado_para))
        return await self._post_repo.salvar(post)

    async def cancelar_postagem(
        self, empresa_id: UUID, conta_ig_id: UUID, postagem_id: UUID
    ) -> Postagem:
        """Cancela postagem que ainda não entrou em publicação ou conclusão."""
        await exigir_conta_ativa(self._conta_repo, empresa_id, conta_ig_id)
        post = await self.obter_postagem(empresa_id, conta_ig_id, postagem_id)
        validar_transicao_postagem(post.status, StatusPostagem.CANCELADO)
        post.status = StatusPostagem.CANCELADO
        return await self._post_repo.salvar(post)

    async def obter_postagem(
        self, empresa_id: UUID, conta_ig_id: UUID, postagem_id: UUID
    ) -> Postagem:
        post = await self._post_repo.buscar_por_id(empresa_id, conta_ig_id, postagem_id)
        if post is None:
            raise ErroValidacaoDominio("Postagem não encontrada para esta conta.")
        return post

    async def listar_postagens(
        self, empresa_id: UUID, conta_ig_id: UUID, status: StatusPostagem | None = None
    ) -> list[Postagem]:
        await exigir_conta_ativa(self._conta_repo, empresa_id, conta_ig_id)
        return await self._post_repo.listar_por_conta(empresa_id, conta_ig_id, status=status)

    async def publicar_postagem(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        postagem_id: UUID,
        permitir_imediata: bool = False,
    ) -> ResultadoPublicacaoDTO:
        """Executa publicação oficial sob lock distribuído e máquina de estados."""
        chave_lock = f"post:{postagem_id}"
        token_lock = (
            await self._lock.adquirir(chave_lock, self._lock_ttl) if self._lock else "local"
        )
        if token_lock is None:
            post_atual = await self.obter_postagem(empresa_id, conta_ig_id, postagem_id)
            return ResultadoPublicacaoDTO(
                postagem=post_atual,
                publicada=False,
                motivo="Publicação já está em execução por outro worker.",
            )
        try:
            return await self._executar_publicacao_protegida(
                empresa_id, conta_ig_id, postagem_id, permitir_imediata
            )
        finally:
            if self._lock is not None:
                await self._lock.liberar(chave_lock, token_lock)

    async def _executar_publicacao_protegida(
        self, empresa_id: UUID, conta_ig_id: UUID, postagem_id: UUID, permitir_imediata: bool
    ) -> ResultadoPublicacaoDTO:
        post = await self.obter_postagem(empresa_id, conta_ig_id, postagem_id)
        if permitir_imediata and post.status in {
            StatusPostagem.RASCUNHO, StatusPostagem.FALHA, StatusPostagem.PUBLICADO
        }:
            post.status = StatusPostagem.RASCUNHO
            post.meta_container_id = None
            post.agendar(datetime.now(UTC))
        elif post.status != StatusPostagem.AGENDADO:
            return ResultadoPublicacaoDTO(
                postagem=post,
                publicada=False,
                motivo=f"Status '{post.status.value}' não é elegível para publicação.",
            )

        post.iniciar_publicacao()
        await self._post_repo.salvar(post)
        try:
            conta = await exigir_conta_ativa(self._conta_repo, empresa_id, conta_ig_id, True)
            bruto = self._cripto.descriptografar(conta.access_token_enc).strip().strip("\"'")
            token_plano = bruto[7:].strip() if bruto.lower().startswith("bearer ") else bruto
            urls = [await self._storage.obter_url_publica(c) for c in post.midias_chaves]
            meta_media_id, meta_container_id = await self._fabrica.obter(
                post.tipo_midia
            ).publicar(conta, token_plano, post, urls)
            post.marcar_publicado(meta_media_id=meta_media_id, meta_container_id=meta_container_id)
            return ResultadoPublicacaoDTO(
                postagem=await self._post_repo.salvar(post), publicada=True
            )
        except ErroLimitePublicacaoMeta as exc:
            post.marcar_falha(str(exc))
            post.agendar(datetime.now(UTC) + timedelta(minutes=self._reagendar_minutos))
            salva = await self._post_repo.salvar(post)
            return ResultadoPublicacaoDTO(
                postagem=salva, publicada=False, reagendada=True, motivo=str(exc)
            )
        except ErroDominio as exc:
            post.marcar_falha(str(exc))
            return ResultadoPublicacaoDTO(
                postagem=await self._post_repo.salvar(post), publicada=False, motivo=str(exc)
            )
        except Exception as exc:
            logger.exception("Erro inesperado ao publicar postagem %s", postagem_id)
            post.marcar_falha(f"Erro interno na publicação: {type(exc).__name__}")
            salva = await self._post_repo.salvar(post)
            return ResultadoPublicacaoDTO(
                postagem=salva, publicada=False, motivo=post.erro_detalhe or "Erro interno."
            )
