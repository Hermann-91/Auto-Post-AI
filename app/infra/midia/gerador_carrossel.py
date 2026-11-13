"""Gerador determinístico de slides para carrosséis no Instagram (2 a 10 itens)."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from app.dominio.excecoes import ErroValidacaoDominio
from app.infra.midia.compositor_capa import CompositorCapa, ConfiguracaoCapa
from app.infra.midia.processador_imagem import ProcessadorImagem, serializar_jpeg

MIN_SLIDES_CARROSSEL = 2
MAX_SLIDES_CARROSSEL = 10


@dataclass(frozen=True, slots=True)
class ConfiguracaoCarrossel:
    """Parâmetros visuais parametrizados por conta para montagem de carrosséis."""

    proporcao: str = "4:5"
    aplicar_gradiente: bool = True
    opacidade_topo: int = 180
    opacidade_base: int = 220
    cor_gradiente: tuple[int, int, int] = (15, 10, 5)
    cor_fundo_encerramento: tuple[int, int, int] = (18, 14, 10)
    incluir_slide_encerramento: bool = False
    tamanho_logo_slide: tuple[int, int] = (320, 160)
    tamanho_logo_encerramento: tuple[int, int] = (650, 450)
    margem_topo_logo: int = 50
    deslocamento_y_encerramento: int = -50
    qualidade_jpeg: int = 95

    def __post_init__(self) -> None:
        ProcessadorImagem.resolver_dimensoes(self.proporcao)
        if not 0 <= self.opacidade_topo <= 255 or not 0 <= self.opacidade_base <= 255:
            raise ErroValidacaoDominio("Opacidade do carrossel deve estar entre 0 e 255.")


class GeradorCarrossel:
    """Gera sequência de slides JPEG RGB em memória sem strings ou logos fixas."""

    def __init__(self, compositor: CompositorCapa | None = None) -> None:
        self._compositor = compositor or CompositorCapa()

    def gerar_slides(
        self,
        imagens_bytes: list[bytes],
        logo_bytes: bytes | None = None,
        config: ConfiguracaoCarrossel | None = None,
    ) -> list[bytes]:
        """Processa os slides fotográficos e opcionalmente anexa slide de encerramento."""
        cfg = config or ConfiguracaoCarrossel()
        total_final = len(imagens_bytes) + (1 if cfg.incluir_slide_encerramento else 0)
        if not imagens_bytes:
            raise ErroValidacaoDominio("Carrossel exige pelo menos uma imagem de entrada.")
        if not MIN_SLIDES_CARROSSEL <= total_final <= MAX_SLIDES_CARROSSEL:
            raise ErroValidacaoDominio(
                f"Carrossel deve resultar entre {MIN_SLIDES_CARROSSEL} e "
                f"{MAX_SLIDES_CARROSSEL} slides."
            )
        if cfg.incluir_slide_encerramento and logo_bytes is None:
            raise ErroValidacaoDominio(
                "Slide de encerramento institucional requer logotipo da conta."
            )

        capa_cfg = ConfiguracaoCapa(
            aplicar_gradiente=cfg.aplicar_gradiente,
            altura_gradiente_topo=0.25,
            opacidade_topo=cfg.opacidade_topo,
            altura_gradiente_base=0.30,
            opacidade_base=cfg.opacidade_base,
            cor_gradiente=cfg.cor_gradiente,
            tamanho_max_logo=cfg.tamanho_logo_slide,
            margem_topo_logo=cfg.margem_topo_logo,
            qualidade_jpeg=cfg.qualidade_jpeg,
        )
        slides = [
            self._compositor.compor(
                foto,
                logo_bytes=logo_bytes,
                config=capa_cfg,
                proporcao=cfg.proporcao,
            )
            for foto in imagens_bytes
        ]
        if cfg.incluir_slide_encerramento and logo_bytes is not None:
            slides.append(self.gerar_slide_encerramento(logo_bytes, cfg))
        return slides

    def gerar_slide_encerramento(
        self,
        logo_bytes: bytes,
        config: ConfiguracaoCarrossel | None = None,
    ) -> bytes:
        """Gera slide final institucional com fundo parametrizado e logo centralizada."""
        cfg = config or ConfiguracaoCarrossel()
        largura, altura = ProcessadorImagem.resolver_dimensoes(cfg.proporcao)
        base = Image.new("RGBA", (largura, altura), (*cfg.cor_fundo_encerramento, 255))

        if cfg.aplicar_gradiente:
            grad_cfg = ConfiguracaoCapa(
                aplicar_gradiente=True,
                altura_gradiente_topo=0.25,
                opacidade_topo=min(cfg.opacidade_topo, 60),
                altura_gradiente_base=0.30,
                opacidade_base=min(cfg.opacidade_base, 110),
                cor_gradiente=cfg.cor_gradiente,
            )
            gradiente = self._compositor.criar_mascara_gradiente(largura, altura, grad_cfg)
            base = Image.alpha_composite(base, gradiente)

        com_logo = self._compositor.sobrepor_logo(
            base,
            logo_bytes,
            cfg.tamanho_logo_encerramento,
            pos_y=None,
            deslocamento_y=cfg.deslocamento_y_encerramento,
        )
        return serializar_jpeg(com_logo, qualidade=cfg.qualidade_jpeg)
