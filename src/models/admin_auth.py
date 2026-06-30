from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AdminPrincipal:
    email: str
    role: str
    session_id: str
    jti: str

    def has_permission(self, permission: str) -> bool:
        from src.models.admin_rbac import role_has_permission

        return role_has_permission(self.role, permission)


@dataclass(frozen=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    csrf_token: str
    session_id: str
    expires_in: int
    token_type: str = "Bearer"


@dataclass(frozen=True)
class LoginResult:
    email: str
    role: str
    tokens: AuthTokens
    mfa_required: bool = False
