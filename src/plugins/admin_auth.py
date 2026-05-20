from src.services.admin_auth_service import AdminAuthService


def validate_admin_key(admin_key: str) -> bool:
    """
    Validate an admin credential for CQRS operations.

    The static API key has been removed — the only accepted credential is a
    JWT minted by /api/admin/login (from ADMIN_EMAIL / ADMIN_PASSWORD). The
    CQRS `adminKey` field should carry that token.
    """
    if not admin_key:
        return False
    return AdminAuthService().verify_token(admin_key) is not None
