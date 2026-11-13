"""Rotas HTTP de autenticação, registro multi-tenant e gestão de cookies."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.dependencias.container_auth import (
    ContainerAuth,
    obter_autenticar_uc,
    obter_config_app,
    obter_container_auth,
    obter_encerrar_uc,
    obter_registrar_uc,
    obter_renovar_uc,
)
from app.api.dependencias.usuario_atual import obter_usuario_atual
from app.api.rotas.cookies import (
    checar_csrf_cookie,
    extrair_ip_cliente,
    gravar_cookies_sessao,
    limpar_cookies_sessao,
)
from app.api.schemas.auth import (
    ConfigPublicaAuthResponse,
    LoginRequest,
    MensagemResponse,
    RegistroRequest,
    SessaoResponse,
    UsuarioResponse,
)
from app.aplicacao.auth import (
    AutenticarUsuarioUseCase,
    EncerrarSessaoUseCase,
    LoginCmd,
    RegistrarUsuarioUseCase,
    RegistroUsuarioCmd,
    RenovarSessaoUseCase,
    UsuarioAutenticadoDTO,
)
from app.core.config import Configuracoes
from app.dominio.excecoes import ErroCredenciaisInvalidas
from app.dominio.portas.seguranca import PayloadAccessToken

router = APIRouter(prefix="/auth", tags=["autenticacao"])


def _to_usuario_response(dto: UsuarioAutenticadoDTO) -> UsuarioResponse:
    return UsuarioResponse(
        id=dto.id,
        empresa_id=dto.empresa_id,
        email=dto.email,
        papel=dto.papel,
        ativo=dto.ativo,
    )


@router.get("/config", response_model=ConfigPublicaAuthResponse)
async def obter_config_publica_auth(
    cfg: Annotated[Configuracoes, Depends(obter_config_app)],
) -> ConfigPublicaAuthResponse:
    """Expõe parâmetros públicos do Turnstile para o painel web."""
    return ConfigPublicaAuthResponse(
        captcha_enabled=cfg.captcha_enabled,
        turnstile_site_key=cfg.turnstile_site_key,
    )


@router.post("/register", response_model=SessaoResponse, status_code=status.HTTP_201_CREATED)
async def registrar(
    payload: RegistroRequest,
    request: Request,
    response: Response,
    caso_uso: Annotated[RegistrarUsuarioUseCase, Depends(obter_registrar_uc)],
    cfg: Annotated[Configuracoes, Depends(obter_config_app)],
) -> SessaoResponse:
    """Cria nova empresa + usuário ADMIN e emite cookies HttpOnly iniciais."""
    tokens = await caso_uso.executar(
        RegistroUsuarioCmd(
            nome_empresa=payload.nome_empresa,
            email=str(payload.email),
            senha=payload.senha,
            token_captcha=payload.turnstile_token,
            ip_remoto=extrair_ip_cliente(request),
        )
    )
    gravar_cookies_sessao(response, tokens, cfg)
    return SessaoResponse(
        mensagem="Cadastro realizado com sucesso.",
        usuario=_to_usuario_response(tokens.usuario),
    )


@router.post("/login", response_model=SessaoResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    caso_uso: Annotated[AutenticarUsuarioUseCase, Depends(obter_autenticar_uc)],
    cfg: Annotated[Configuracoes, Depends(obter_config_app)],
) -> SessaoResponse:
    """Autentica usuário seguindo Rate Limit -> Turnstile -> Argon2id -> JWT."""
    tokens = await caso_uso.executar(
        LoginCmd(
            email=str(payload.email),
            senha=payload.senha,
            token_captcha=payload.turnstile_token,
            ip_remoto=extrair_ip_cliente(request),
        )
    )
    gravar_cookies_sessao(response, tokens, cfg)
    return SessaoResponse(
        mensagem="Login realizado com sucesso.",
        usuario=_to_usuario_response(tokens.usuario),
    )


@router.post("/refresh", response_model=SessaoResponse, dependencies=[Depends(checar_csrf_cookie)])
async def refresh(
    request: Request,
    response: Response,
    caso_uso: Annotated[RenovarSessaoUseCase, Depends(obter_renovar_uc)],
    cfg: Annotated[Configuracoes, Depends(obter_config_app)],
) -> SessaoResponse:
    """Rotaciona o Refresh Token do cookie HttpOnly e renova a sessão."""
    token_bruto = request.cookies.get(cfg.cookie_refresh_nome)
    tokens = await caso_uso.executar(token_bruto)
    gravar_cookies_sessao(response, tokens, cfg)
    return SessaoResponse(
        mensagem="Sessão renovada com sucesso.",
        usuario=_to_usuario_response(tokens.usuario),
    )


@router.post(
    "/logout",
    response_model=MensagemResponse,
    dependencies=[Depends(checar_csrf_cookie)],
)
async def logout(
    request: Request,
    response: Response,
    caso_uso: Annotated[EncerrarSessaoUseCase, Depends(obter_encerrar_uc)],
    cfg: Annotated[Configuracoes, Depends(obter_config_app)],
) -> MensagemResponse:
    """Revoga família do refresh token e limpa os cookies do navegador."""
    token_bruto = request.cookies.get(cfg.cookie_refresh_nome)
    await caso_uso.executar(token_bruto)
    limpar_cookies_sessao(response, cfg)
    return MensagemResponse(mensagem="Sessão encerrada com sucesso.")


@router.get("/me", response_model=UsuarioResponse)
async def perfil_atual(
    ctx: Annotated[PayloadAccessToken, Depends(obter_usuario_atual)],
    container: Annotated[ContainerAuth, Depends(obter_container_auth)],
) -> UsuarioResponse:
    """Retorna os dados do usuário autenticado isolado pelo seu empresa_id."""
    usuario = await container.usuario_repo.buscar_por_id(
        empresa_id=ctx.empresa_id,
        usuario_id=ctx.usuario_id,
    )
    if usuario is None or not usuario.ativo:
        raise ErroCredenciaisInvalidas("Sessão inválida ou usuário inativo.")
    return UsuarioResponse(
        id=usuario.id,
        empresa_id=usuario.empresa_id,
        email=usuario.email,
        papel=usuario.papel,
        ativo=usuario.ativo,
    )
