"""Compositor determinístico de capas com gradiente e logotipo opcionais."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from app.dominio.excecoes import ErroValidacaoDominio
from app.infra.midia.processador_imagem import (
    ProcessadorImagem,
    abrir_imagem_segura,
    serializar_jpeg,
)


@dataclass(frozen=True, slots=True)
class ConfiguracaoCapa:
    """Parâmetros visuais por conta para composição de capas e slides."""

    aplicar_gradiente: bool = True
    altura_gradiente_topo: float = 0.28
    opacidade_topo: int = 190
    altura_gradiente_base: float = 0.0
    opacidade_base: int = 0
    cor_gradiente: tuple[int, int, int] = (12, 8, 4)
    tamanho_max_logo: tuple[int, int] = (450, 220)
    margem_topo_logo: int = 55
    qualidade_jpeg: int = 95

    def __post_init__(self) -> None:
        if not 0.0 <= self.altura_gradiente_topo <= 1.0:
            raise ErroValidacaoDominio("Altura do gradiente de topo deve estar entre 0 e 1.")
        if not 0.0 <= self.altura_gradiente_base <= 1.0:
            raise ErroValidacaoDominio("Altura do gradiente de base deve estar entre 0 e 1.")
        if self.altura_gradiente_topo + self.altura_gradiente_base > 1.0:
            raise ErroValidacaoDominio("Gradientes de topo e base não podem se sobrepor.")
        if not 0 <= self.opacidade_topo <= 255 or not 0 <= self.opacidade_base <= 255:
            raise ErroValidacaoDominio("Opacidade do gradiente deve estar entre 0 e 255.")
        if self.tamanho_max_logo[0] <= 0 or self.tamanho_max_logo[1] <= 0:
            raise ErroValidacaoDominio("Tamanho máximo da logo deve ser positivo.")


class CompositorCapa:
    """Aplica gradiente e sobreposição opcional de logotipo parametrizada por conta."""

    @staticmethod
    def criar_mascara_gradiente(
        largura: int,
        altura: int,
        config: ConfiguracaoCapa,
    ) -> Image.Image:
        """Gera camada RGBA com gradientes opcionais de topo e base em C via Pillow."""
        alfa = Image.new("L", (largura, altura), 0)
        grad_base = Image.linear_gradient("L")

        limite_topo = int(altura * config.altura_gradiente_topo)
        if limite_topo > 0 and config.opacidade_topo > 0:
            tabela_topo = [int(config.opacidade_topo * (1 - i / 255)) for i in range(256)]
            rampa_topo = grad_base.point(tabela_topo).resize(
                (largura, limite_topo),
                Image.Resampling.BILINEAR,
            )
            alfa.paste(rampa_topo, (0, 0))

        altura_base = int(altura * config.altura_gradiente_base)
        if altura_base > 0 and config.opacidade_base > 0:
            tabela_base = [int(config.opacidade_base * (i / 255)) for i in range(256)]
            rampa_base = grad_base.point(tabela_base).resize(
                (largura, altura_base),
                Image.Resampling.BILINEAR,
            )
            alfa.paste(rampa_base, (0, altura - altura_base))

        camada = Image.new("RGBA", (largura, altura), (*config.cor_gradiente, 255))
        camada.putalpha(alfa)
        return camada

    @staticmethod
    def sobrepor_logo(
        base: Image.Image,
        logo_bytes: bytes,
        tamanho_max: tuple[int, int],
        pos_y: int | None = None,
        deslocamento_y: int = 0,
    ) -> Image.Image:
        """Sobrepõe logotipo RGBA centralizado horizontalmente sobre imagem base RGBA."""
        logo = abrir_imagem_segura(logo_bytes).convert("RGBA")
        logo.thumbnail(tamanho_max, Image.Resampling.LANCZOS)
        pos_x = (base.width - logo.width) // 2
        destino_y = ((base.height - logo.height) // 2 + deslocamento_y) if pos_y is None else pos_y
        resultado = base.copy()
        resultado.paste(logo, (pos_x, destino_y), logo)
        return resultado

    @classmethod
    def compor(
        cls,
        dados_foto: bytes,
        logo_bytes: bytes | None = None,
        config: ConfiguracaoCapa | None = None,
        proporcao: str = "4:5",
    ) -> bytes:
        """Enquadra foto, aplica gradiente opcional e logo opcional, retornando JPEG RGB."""
        cfg = config or ConfiguracaoCapa()
        largura_alvo, altura_alvo = ProcessadorImagem.resolver_dimensoes(proporcao)
        foto_bruta = abrir_imagem_segura(dados_foto)
        foto_enquadrada = ProcessadorImagem.ajustar_proporcao(
            foto_bruta,
            largura_alvo,
            altura_alvo,
        ).convert("RGBA")

        composicao = foto_enquadrada
        if cfg.aplicar_gradiente:
            gradiente = cls.criar_mascara_gradiente(largura_alvo, altura_alvo, cfg)
            composicao = Image.alpha_composite(composicao, gradiente)

        if logo_bytes is not None:
            composicao = cls.sobrepor_logo(
                composicao,
                logo_bytes,
                cfg.tamanho_max_logo,
                pos_y=cfg.margem_topo_logo,
            )

        return serializar_jpeg(composicao, qualidade=cfg.qualidade_jpeg)
