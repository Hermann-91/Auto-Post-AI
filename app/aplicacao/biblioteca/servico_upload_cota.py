"""Casos de uso para upload na biblioteca, validação de cota e curtidas."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID, uuid4

from app.aplicacao.biblioteca.dtos import MidiaComUrlDTO, ResumoCotaDTO, UploadMidiaCmd
from app.dominio.entidades.midia import MidiaBiblioteca
from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.cota_midia import CotaMidia
from app.dominio.portas.midia_storage import StorageMidiaPort
from app.dominio.portas.repositorios_conteudo import MidiaRepositoryPort

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
    """Orquestra validação, cálculo de cota, upload em nuvem e curtidas."""

    def __init__(
        self,
        midia_repo: MidiaRepositoryPort,
        storage: StorageMidiaPort,
        cota: CotaMidia | None = None,
        tamanho_max_arquivo_bytes: int = TAMANHO_MAX_ARQUIVO_BYTES,
    ) -> None:
        self._midia_repo = midia_repo
        self._storage = storage
        self._cota = cota or CotaMidia()
        self._tamanho_max = tamanho_max_arquivo_bytes

    async def registrar_upload(self, cmd: UploadMidiaCmd) -> MidiaComUrlDTO:
        """Valida formato e cota, envia ao storage e persiste metadados com rollback."""
        content_type = cmd.content_type.strip().lower()
        extensao = TIPOS_MIDIA_EXTENSOES.get(content_type)
        if extensao is None:
            raise ErroValidacaoDominio(f"Tipo de mídia não suportado: {cmd.content_type}")

        tamanho = len(cmd.conteudo)
        if tamanho <= 0:
            raise ErroValidacaoDominio("Arquivo de mídia vazio não é permitido.")
        if tamanho > self._tamanho_max:
            raise ErroValidacaoDominio("Arquivo excede o limite individual permitido.")

        nome_seguro = _sanitizar_nome_arquivo(cmd.nome_arquivo, extensao)
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

        url = await self._storage.enviar_bytes(chave, cmd.conteudo, content_type)
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

    async def alternar_curtida(
        self,
        empresa_id: UUID,
        conta_ig_id: UUID,
        midia_id: UUID,
        favorita: bool,
    ) -> MidiaBiblioteca:
        """Marca ou desmarca mídia como favorita protegida contra limpeza."""
        midia = await self._midia_repo.buscar_por_id(empresa_id, conta_ig_id, midia_id)
        if midia is None:
            raise ErroValidacaoDominio("Mídia não encontrada para esta conta.")
        midia.alternar_curtida(favorita)
        return await self._midia_repo.salvar(midia)

    async def obter_resumo_cota(self, empresa_id: UUID, conta_ig_id: UUID) -> ResumoCotaDTO:
        """Retorna estatísticas atuais de consumo de itens e bytes da conta."""
        qtd, bytes_usados = await self._midia_repo.calcular_uso_cota(empresa_id, conta_ig_id)
        return ResumoCotaDTO(
            itens_usados=qtd,
            max_itens=self._cota.max_itens,
            percentual_itens=self._cota.percentual_itens(qtd),
            bytes_usados=bytes_usados,
            max_bytes=self._cota.max_bytes,
            percentual_bytes=self._cota.percentual_bytes(bytes_usados),
        )
