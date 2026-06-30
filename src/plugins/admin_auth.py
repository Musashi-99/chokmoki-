from src.services.admin_auth_service import AdminAuthService


async def validate_admin_key(admin_key: str) -> bool:
    """
    Validate an admin credential for CQRS operations.

    The CQRS `adminKey` field must carry a session-backed `admin_access` JWT
    from /api/admin/login with a valid Redis session and non-revoked jti.
    """
    if not admin_key:
        return False
    principal = await AdminAuthService().verify_admin_key(admin_key)
    return principal is not None
