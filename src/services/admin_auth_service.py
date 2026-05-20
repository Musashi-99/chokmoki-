import secrets
from typing import Optional
from datetime import datetime, timedelta
from jose import jwt, JWTError
from src.config import settings
from src.plugins.logger import logger


class AdminAuthService:
    """
    Super-admin authentication backed entirely by environment variables
    (ADMIN_EMAIL / ADMIN_PASSWORD). A successful login mints a short-lived
    JWT that is then used to authorize admin actions (product create, etc.).
    """

    def _create_token(self, email: str) -> str:
        expire = datetime.utcnow() + timedelta(hours=settings.jwt_expiration_hours)
        payload = {"sub": email, "exp": expire, "type": "admin"}
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    def verify_token(self, token: str) -> Optional[str]:
        """Return the admin email if the token is a valid, unexpired admin JWT."""
        try:
            payload = jwt.decode(
                token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
            )
            if payload.get("type") != "admin":
                return None
            return payload.get("sub")
        except JWTError:
            return None

    async def authenticate(self, email: str, password: str) -> Optional[str]:
        """Validate credentials against the env-configured super admin."""
        expected_email = (settings.admin_email or "").strip()
        expected_password = settings.admin_password or ""

        if not expected_email or not expected_password:
            logger.error("ADMIN_EMAIL / ADMIN_PASSWORD are not configured")
            return None

        # Constant-time comparison to avoid leaking timing information.
        email_ok = secrets.compare_digest(
            email.strip().lower(), expected_email.lower()
        )
        password_ok = secrets.compare_digest(password, expected_password)

        if email_ok and password_ok:
            logger.info(f"Admin authenticated: {expected_email}")
            return self._create_token(expected_email)

        return None
