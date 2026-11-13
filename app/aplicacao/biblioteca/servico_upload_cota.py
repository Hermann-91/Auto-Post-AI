"""Casos de uso para upload na biblioteca, validação de cota e curtidas."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from app.aplicacao.biblioteca.dtos import MidiaComUrlDTO, ResumoCotaDTO, UploadMidiaCmd
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.cota_midia import CotaMidia
from app.dominio.objetos_valor.enums_conteudo import PastaMidia
from app.dominio.portas.midia_storage import StorageMidiaPort
from app.dominio.portas.repositorios_conteudo import MidiaRepositoryPort
from app.dominio.portas.repositorios_tenant import ContaIGRepositoryPort


class CompactadorImagemPort(Protocol):
    """Contrato estrutural para normalização de fotos na entrada da biblioteca."""

    def __call__(self, dados: bytes, max_lado: int = 2048, qualidade: int = 85) -> bytes: ...


TIPOS_MIDIA_EXTENSOES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
}
TAMANHO_MAX_ARQUIVO_BYTES = 100 * 1024 * 1024
_PADRAO_NOME_SEGURO = re.compile(r"[^a-zA-Z0-9._-]+")


def _sanitizar_nome_arquivo(nome_original: str, extensao_padrao: str) -> str:
    nome_base = Path(nome_original.strip()).name
    if not nome_base or ".." in nome_original:
        raise ErroValidacaoDominio("Nome de arquivo inválido.")
    stem = _PADRAO_NOME_SEGURO.sub("_", Path(nome_base).stem).strip("._-") or "midia"
    ext = Path(nome_base).suffix.lower()
    if ext not in TIPOS_MIDIA_EXTENSOES.values():
        ext = extensao_padrao
    return f"{uuid4().hex[:12]}_{stem[:60]}{ext}"


class ServicoUploadCotaUseCase:
    """Orquestra validação, cálculo de cota, upload em nuvem/VPS e curtidas."""

    def __init__(
        self,
        midia_repo: MidiaRepositoryPort,
        storage: StorageMidiaPort,
        cota: CotaMidia | None = None,
        tamanho_max_arquivo_bytes: int = TAMANHO_MAX_ARQUIVO_BYTES,
        compactador: CompactadorImagemPort | None = None,
        conta_repo: ContaIGRepositoryPort | None = None,
    ) -> None:
        self._midia_repo = midia_repo
        self._storage = storage
        self._cota = cota or CotaMidia()
        self._tamanho_max = tamanho_max_arquivo_bytes
        self._compactador = compactador
        self._conta_repo = conta_repo

    async def _exigir_conta(self, empresa_id: UUID, conta_ig_id: UUID) -> None:
        if self._conta_repo is None:
            return
        conta = await self._conta_repo.buscar_por_id(empresa_id, conta_ig_id)
        if conta is None:
            raise ErroValidacaoDominio("Conta Instagram não encontrada para esta empresa.")

    async def registrar_upload(self, cmd: UploadMidiaCmd) -> MidiaComUrlDTO:
        """Valida formato e cota, envia ao storage e persiste metadados com rollback."""
        await self._exigir_conta(cmd.empresa_id, cmd.conta_ig_id)
        content_type = cmd.content_type.strip().lower()
        extensao = TIPOS_MIDIA_EXTENSOES.get(content_type)
        if extensao is None:
            raise ErroValidacaoDominio(f"Tipo de mídia não suportado: {cmd.content_type}")

        if not cmd.conteudo:
            raise ErroValidacaoDominio("Arquivo de mídia vazio não é permitido.")
        if len(cmd.conteudo) > self._tamanho_max:
            raise ErroValidacaoDominio("Arquivo excede o limite individual permitido.")

        nome_seguro = _sanitizar_nome_arquivo(cmd.nome_arquivo, extensao)
        conteudo_final = cmd.conteudo
        if self._compactador is not None and content_type.startswith("image/"):
            conteudo_final = await asyncio.to_thread(
                self._compactador, cmd.conteudo, max_lado=2048, qualidade=85
            )
            content_type = "image/jpeg"
            nome_seguro = f"{Path(nome_seguro).stem}.jpg"

        tamanho = len(conteudo_final)
        chave = MidiaBiblioteca.montar_chave_storage(
            cmd.empresa_id,
            cmd.conta_ig_id,
            cmd.pasta,
            nome_seguro,
        )

        qtd_atual, bytes_atuais = await self._midia_repo.calcular_uso_cota(
            cmd.empresa_id,
            cmd.conta_ig_id,
        )
        self._cota.validar_novo_arquivo(qtd_atual, bytes_atuais, tamanho)

        url = await self._storage.enviar_bytes(chave, conteudo_final, content_type)
        entidade = MidiaBiblioteca(
            empresa_id=cmd.empresa_id,
            conta_ig_id=cmd.conta_ig_id,
            pasta=cmd.pasta,
            chave_storage=chave,
            tipo_arquivo=content_type,
            tamanho_bytes=tamanho,
            resumo_visual=cmd.resumo_visual,
        )
        try:
            salva = await self._midia_repo.salvar(entidade)
        except Exception:
            await self._storage.remover_objeto(chave)
            raise
        return MidiaComUrlDTO(midia=salva, url_publica=url)

    async def listar_midias(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        pasta: PastaMidia | None = None,
    ) -> list[MidiaComUrlDTO]:
        """Lista mídias da conta (opcionalmente filtradas por pasta) com URLs públicas."""
        await self._exigir_conta(empresa_id, conta_ig_id)
        midias = await self._midia_repo.listar_por_conta(empresa_id, conta_ig_id, pasta=pasta)
        saida: list[MidiaComUrlDTO] = []
        for midia in midias:
            url = await self._storage.obter_url_publica(midia.chave_storage)
            saida.append(MidiaComUrlDTO(midia=midia, url_publica=url))
        return saida

    async def obter_conteudo_midia(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        midia_id: UUID,
    ) -> tuple[MidiaBiblioteca, bytes]:
        """Recupera metadados e bytes da mídia validando propriedade da conta."""
        await self._exigir_conta(empresa_id, conta_ig_id)
        midia = await self._midia_repo.buscar_por_id(empresa_id, conta_ig_id, midia_id)
        if midia is None:
            raise ErroValidacaoDominio("Mídia não encontrada para esta conta.")
        dados = await self._storage.baixar_bytes(midia.chave_storage)
        return midia, dados

    async def alternar_curtida(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        midia_id: UUID,
        favorita: bool,
    ) -> MidiaBiblioteca:
        """Marca ou desmarca mídia como favorita protegida contra limpeza."""
        await self._exigir_conta(empresa_id, conta_ig_id)
        midia = await self._midia_repo.buscar_por_id(empresa_id, conta_ig_id, midia_id)
        if midia is None:
            raise ErroValidacaoDominio("Mídia não encontrada para esta conta.")
        midia.alternar_curtida(favorita)
        return await self._midia_repo.salvar(midia)

    async def obter_resumo_cota(self, empresa_id: UUID, conta_ig_id: UUID) -> ResumoCotaDTO:
        """Retorna estatísticas atuais de consumo de itens e bytes da conta."""
        await self._exigir_conta(empresa_id, conta_ig_id)
        qtd, bytes_usados = await self._midia_repo.calcular_uso_cota(empresa_id, conta_ig_id)
        return ResumoCotaDTO(
            itens_usados=qtd,
            max_itens=self._cota.max_itens,
            percentual_itens=self._cota.percentual_itens(qtd),
            bytes_usados=bytes_usados,
            max_bytes=self._cota.max_bytes,
            percentual_bytes=self._cota.percentual_bytes(bytes_usados),
        )
