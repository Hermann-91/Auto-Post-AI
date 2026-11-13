"""Entidades de tenant raiz, usuários, sessões e contas do Instagram."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.dominio.excecoes import ErroValidacaoDominio
from app.dominio.objetos_valor.enums_tenant import PapelUsuario, PlanoEmpresa, ProvedorMeta


@dataclass(slots=True)
class Empresa:
    """Tenant raiz que isola usuários, contas Instagram e orçamento de IA."""

    nome: str
    plano: PlanoEmpresa = PlanoEmpresa.TRIAL
    limite_mensal_usd: Decimal = Decimal("10.00")
    bloqueio_orcamento: bool = True
    id: UUID = field(default_factory=uuid4)
    criado_em: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        self.nome = self.nome.strip()
        if len(self.nome) < 2:
            raise ErroValidacaoDominio("Nome da empresa deve ter ao menos 2 caracteres.")
        if self.limite_mensal_usd < Decimal("0"):
            raise ErroValidacaoDominio("Limite mensal em USD não pode ser negativo.")


@dataclass(slots=True)
class Usuario:
    """Usuário autenticado pertencente obrigatoriamente a uma Empresa."""

    empresa_id: UUID
    email: str
    senha_hash: str
    papel: PapelUsuario = PapelUsuario.ADMIN
    ativo: bool = True
    id: UUID = field(default_factory=uuid4)
    criado_em: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        self.email = self.email.strip().lower()
        if "@" not in self.email or len(self.email) < 5:
            raise ErroValidacaoDominio("E-mail do usuário inválido.")
        if not self.senha_hash:
            raise ErroValidacaoDominio("Hash de senha não pode ser vazio.")


@dataclass(slots=True)
class RefreshTokenRegistro:
    """Estado de sessão para rotação segura e revogação por família de tokens."""

    usuario_id: UUID
    empresa_id: UUID
    familia_id: UUID
    token_hash: str
    expira_em: datetime
    revogado: bool = False
    substituido_por: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    criado_em: datetime = field(default_factory=lambda: datetime.now(UTC))

    def esta_valido(self, agora: datetime | None = None) -> bool:
        """Retorna True se o token não foi revogado, substituído ou expirado."""
        referencia = agora or datetime.now(UTC)
        return not self.revogado and self.substituido_por is None and self.expira_em > referencia


@dataclass(slots=True)
class ContaInstagram:
    """Conta Instagram gerenciada por uma Empresa com token criptografado."""

    empresa_id: UUID
    ig_user_id: str
    username: str
    access_token_enc: str
    token_expira_em: datetime
    provedor: ProvedorMeta = ProvedorMeta.INSTAGRAM_LOGIN
    ativa: bool = True
    id: UUID = field(default_factory=uuid4)
    criado_em: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        self.username = self.username.strip().lstrip("@")
        if not self.ig_user_id.strip() or not self.username:
            raise ErroValidacaoDominio("Conta Instagram exige ig_user_id e username.")

    def token_expirado(self, agora: datetime | None = None) -> bool:
        """Indica se o Long-Lived Token já expirou."""
        referencia = agora or datetime.now(UTC)
        return self.token_expira_em <= referencia

    def atualizar_token(self, novo_token_enc: str, nova_expiracao: datetime) -> None:
        """Atualiza o token criptografado e sua validade."""
        if not novo_token_enc:
            raise ErroValidacaoDominio("Token criptografado não pode ser vazio.")
        self.access_token_enc = novo_token_enc
        self.token_expira_em = nova_expiracao
