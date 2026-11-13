"""Objeto de valor para controle de cotas da biblioteca de mídia."""

from __future__ import annotations

from dataclasses import dataclass

from app.dominio.excecoes import ErroCotaExcedida, ErroValidacaoDominio

UM_GIGABYTE = 1024 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class CotaMidia:
    """Define e valida os tetos de quantidade de arquivos e volume em bytes."""

    max_itens: int = 250
    max_bytes: int = UM_GIGABYTE

    def __post_init__(self) -> None:
        if self.max_itens <= 0 or self.max_bytes <= 0:
            raise ErroValidacaoDominio("Limites de cota devem ser maiores que zero.")

    def validar_novo_arquivo(
        self,
        qtd_atual: int,
        bytes_atuais: int,
        novo_tamanho_bytes: int,
        novos_itens: int = 1,
    ) -> None:
        """Lança ErroCotaExcedida se o novo ativo ultrapassar itens ou espaço."""
        if novo_tamanho_bytes < 0 or novos_itens <= 0:
            raise ErroValidacaoDominio("Parâmetros de mídia inválidos para cálculo de cota.")
        if qtd_atual + novos_itens > self.max_itens:
            raise ErroCotaExcedida(
                f"Limite de {self.max_itens} mídias na biblioteca atingido."
            )
        if bytes_atuais + novo_tamanho_bytes > self.max_bytes:
            raise ErroCotaExcedida(
                f"Limite de armazenamento ({self.max_bytes} bytes) da biblioteca atingido."
            )

    def percentual_itens(self, qtd_atual: int) -> float:
        """Retorna percentual utilizado da cota por contagem de mídias."""
        return round(min(100.0, (qtd_atual / self.max_itens) * 100.0), 2)

    def percentual_bytes(self, bytes_atuais: int) -> float:
        """Retorna percentual utilizado da cota por volume em bytes."""
        return round(min(100.0, (bytes_atuais / self.max_bytes) * 100.0), 2)
