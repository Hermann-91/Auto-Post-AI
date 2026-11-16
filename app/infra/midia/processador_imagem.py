"""Processador determinístico de imagens em memória usando Pillow."""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError

from app.dominio.excecoes import ErroValidacaoDominio

DIMENSOES_PROPORCAO: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
}
MAX_PIXELS_IMAGEM = 40_000_000


def abrir_imagem_segura(dados: bytes) -> Image.Image:
    """Abre bytes de imagem validando integridade, limite de pixels e rotação EXIF."""
    if not dados:
        raise ErroValidacaoDominio("Arquivo de imagem vazio não pode ser processado.")
    try:
        with Image.open(BytesIO(dados)) as img_bruta:
            largura, altura = img_bruta.size
            if largura <= 0 or altura <= 0 or (largura * altura) > MAX_PIXELS_IMAGEM:
                raise ErroValidacaoDominio("Dimensões da imagem excedem o limite seguro.")
            transposta = ImageOps.exif_transpose(img_bruta)
            return transposta.copy()
    except ErroValidacaoDominio:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ErroValidacaoDominio("Imagem inválida ou corrompida.") from exc


def converter_para_rgb(
    img: Image.Image,
    cor_fundo: tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """Converte qualquer modo (incluindo RGBA/P com transparência) para RGB opaco."""
    if img.mode == "RGB":
        return img
    possui_alfa = img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    )
    if possui_alfa:
        rgba = img.convert("RGBA")
        fundo = Image.new("RGBA", rgba.size, (*cor_fundo, 255))
        composta = Image.alpha_composite(fundo, rgba)
        return composta.convert("RGB")
    return img.convert("RGB")


def serializar_jpeg(img: Image.Image, qualidade: int = 94) -> bytes:
    """Serializa imagem em JPEG RGB otimizado sem metadados EXIF."""
    if not 1 <= qualidade <= 100:
        raise ErroValidacaoDominio("Qualidade JPEG deve estar entre 1 e 100.")
    rgb = converter_para_rgb(img)
    saida = BytesIO()
    rgb.save(saida, format="JPEG", quality=qualidade, optimize=True, progressive=True)
    return saida.getvalue()


class ProcessadorImagem:
    """Compacta originais no upload e padroniza formatos para publicação na Meta."""

    @staticmethod
    def resolver_dimensoes(proporcao: str) -> tuple[int, int]:
        """Retorna largura e altura alvo para uma proporção suportada."""
        dimensoes = DIMENSOES_PROPORCAO.get(proporcao)
        if dimensoes is None:
            suportadas = ", ".join(sorted(DIMENSOES_PROPORCAO))
            raise ErroValidacaoDominio(
                f"Proporção '{proporcao}' não suportada. Use: {suportadas}."
            )
        return dimensoes

    @classmethod
    def ajustar_proporcao(
        cls,
        img: Image.Image,
        largura_alvo: int = 1080,
        altura_alvo: int = 1350,
    ) -> Image.Image:
        """Redimensiona mantendo aspecto (cover) e realiza corte centralizado exato."""
        if largura_alvo <= 0 or altura_alvo <= 0:
            raise ErroValidacaoDominio("Dimensões alvo devem ser maiores que zero.")
        proporcao_alvo = largura_alvo / altura_alvo
        proporcao_img = img.width / img.height

        if proporcao_img > proporcao_alvo:
            nova_altura = altura_alvo
            nova_largura = max(largura_alvo, round(altura_alvo * proporcao_img))
        else:
            nova_largura = largura_alvo
            nova_altura = max(altura_alvo, round(largura_alvo / proporcao_img))

        img_redim = img.resize((nova_largura, nova_altura), Image.Resampling.LANCZOS)
        esquerda = (nova_largura - largura_alvo) // 2
        topo = (nova_altura - altura_alvo) // 2
        return img_redim.crop((esquerda, topo, esquerda + largura_alvo, topo + altura_alvo))

    @classmethod
    def compactar_entrada(
        cls,
        dados: bytes,
        max_lado: int = 2048,
        qualidade: int = 85,
    ) -> bytes:
        """Normaliza foto original para economia de cota e custo multimodal."""
        if max_lado < 256:
            raise ErroValidacaoDominio("Lado máximo para compactação deve ser >= 256px.")
        img = abrir_imagem_segura(dados)
        if max(img.size) > max_lado:
            img.thumbnail((max_lado, max_lado), Image.Resampling.LANCZOS)
        return serializar_jpeg(img, qualidade=qualidade)

    @classmethod
    def aplicar_presets_melhoria(
        cls,
        img: Image.Image,
        presets: Sequence[str] | None = None,
    ) -> Image.Image:
        """Aplica presets combináveis (fullhd, iluminacao, foto_profissional) sobre a imagem."""
        if not presets:
            return img
        normalizados = {str(p).strip().lower() for p in presets if str(p).strip()}
        resultado = converter_para_rgb(img)

        if "iluminacao" in normalizados or "iluminacao_hdr" in normalizados:
            resultado = ImageOps.autocontrast(resultado, cutoff=1)
            resultado = ImageEnhance.Brightness(resultado).enhance(1.06)
            resultado = ImageEnhance.Contrast(resultado).enhance(1.08)

        if "foto_profissional" in normalizados or "profissional" in normalizados:
            resultado = ImageEnhance.Color(resultado).enhance(1.12)
            resultado = ImageEnhance.Contrast(resultado).enhance(1.07)
            resultado = ImageEnhance.Sharpness(resultado).enhance(1.18)

        if "fullhd" in normalizados or "resolucao_fullhd" in normalizados:
            resultado = resultado.filter(
                ImageFilter.UnsharpMask(radius=1.7, percent=140, threshold=3)
            )
            resultado = ImageEnhance.Sharpness(resultado).enhance(1.15)

        return resultado

    @classmethod
    def otimizar_para_formato(
        cls,
        dados: bytes,
        proporcao: str = "4:5",
        fator_contraste: float = 1.05,
        fator_cor: float = 1.05,
        qualidade: int = 94,
        presets: Sequence[str] | None = None,
    ) -> bytes:
        """Realça contraste/cor opcionais e enquadra na proporção alvo em JPEG RGB."""
        largura_alvo, altura_alvo = cls.resolver_dimensoes(proporcao)
        img = converter_para_rgb(abrir_imagem_segura(dados))
        if fator_contraste != 1.0:
            img = ImageEnhance.Contrast(img).enhance(fator_contraste)
        if fator_cor != 1.0:
            img = ImageEnhance.Color(img).enhance(fator_cor)
        enquadrada = cls.ajustar_proporcao(img, largura_alvo, altura_alvo)
        enquadrada = cls.aplicar_presets_melhoria(enquadrada, presets)
        return serializar_jpeg(enquadrada, qualidade=qualidade)
