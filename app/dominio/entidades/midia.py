"""Entidade de mídia armazenada em nuvem com proteção de favoritas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_conteudo import PastaMidia


@dataclass(slots=True)
class MidiaBiblioteca:
    """Ativo de imagem ou vídeo pertencente a uma conta Instagram específica."""

    empresa_id: UUID
    conta_ig_id: UUID
    pasta: PastaMidia
    chave_storage: str
    tipo_arquivo: str
    tamanho_bytes: int
    curtida_favorita: bool = False
    resumo_visual: str = ""
    id: UUID = field(default_factory=uuid4)
    criado_em: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.chave_storage.strip():
            raise ErroValidacaoDominio("Chave de storage da mídia é obrigatória.")
        if self.tamanho_bytes <= 0:
            raise ErroValidacaoDominio("Tamanho do arquivo deve ser maior que zero.")

    @staticmethod
    def montar_chave_storage(
        empresa_id: UUID,
        conta_ig_id: UUID,
        pasta: PastaMidia,
        nome_arquivo: str,
    ) -> str:
        """Padroniza o prefixo multi-tenant exigido pelo R2/S3."""
        nome_limpo = nome_arquivo.strip().lstrip("/")
        if not nome_limpo or ".." in nome_limpo:
            raise ErroValidacaoDominio("Nome de arquivo inválido para storage.")
        return f"{empresa_id}/{conta_ig_id}/{pasta.value}/{nome_limpo}"

    def alternar_curtida(self, favorita: bool) -> None:
        """Define se a mídia é âncora visual protegida contra limpeza."""
        self.curtida_favorita = favorita

    def pode_ser_limpa(self, vinculada_a_post_ativo: bool) -> bool:
        """Protege mídias curtidas ou usadas em posts RASCUNHO/AGENDADO/PUBLICANDO."""
        return not self.curtida_favorita and not vinculada_a_post_ativo
