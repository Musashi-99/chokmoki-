from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime
from typing import Optional

from src.config import settings
from src.database.redis_connection import redis_client
from src.models.user import CustomerAuthTokens


class CustomerSessionService:
    """Refresh-token/session storage for customer logins — same
    opaque-token-in-Redis mechanism as AdminSessionService, under its own
    key prefix so admin and customer sessions never collide.
    """

    SESSION_PREFIX = "customer:session:"
    REFRESH_PREFIX = "customer:refresh:"
    REVOKED_PREFIX = "customer:revoked:"
    USER_SESSIONS_PREFIX = "customer:user_sessions:"

    def _refresh_ttl_seconds(self) -> int:
        return settings.customer_jwt_refresh_ttl_days * 24 * 60 * 60

    def _access_ttl_seconds(self) -> int:
        return settings.customer_jwt_access_ttl_minutes * 60

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def create_session(self, user_id: str, phone: str) -> tuple[str, str]:
        """Returns (session_id, refresh_token_plain)."""
        session_id = str(uuid.uuid4())
        refresh_token = secrets.token_urlsafe(48)
        refresh_hash = self._hash_token(refresh_token)

        session_doc = {
            "user_id": user_id,
            "phone": phone,
            "refresh_token_hash": refresh_hash,
            "created_at": datetime.utcnow().isoformat(),
            "last_rotated_at": datetime.utcnow().isoformat(),
        }

        redis = await redis_client.get_client()
        pipe = redis.pipeline()
        pipe.setex(
            f"{self.SESSION_PREFIX}{session_id}",
            self._refresh_ttl_seconds(),
            json.dumps(session_doc),
        )
        pipe.setex(
            f"{self.REFRESH_PREFIX}{refresh_hash}",
            self._refresh_ttl_seconds(),
            session_id,
        )
        pipe.sadd(f"{self.USER_SESSIONS_PREFIX}{user_id}", session_id)
        pipe.expire(f"{self.USER_SESSIONS_PREFIX}{user_id}", self._refresh_ttl_seconds())
        await pipe.execute()

        return session_id, refresh_token

    async def get_session(self, session_id: str) -> Optional[dict]:
        redis = await redis_client.get_client()
        raw = await redis.get(f"{self.SESSION_PREFIX}{session_id}")
        return json.loads(raw) if raw else None

    async def is_jti_revoked(self, jti: str) -> bool:
        redis = await redis_client.get_client()
        return bool(await redis.exists(f"{self.REVOKED_PREFIX}{jti}"))

    async def revoke_jti(self, jti: str, ttl_seconds: int) -> None:
        redis = await redis_client.get_client()
        await redis.setex(f"{self.REVOKED_PREFIX}{jti}", max(ttl_seconds, 1), "1")

    async def revoke_session(self, session_id: str) -> None:
        redis = await redis_client.get_client()
        raw = await redis.get(f"{self.SESSION_PREFIX}{session_id}")
        if not raw:
            return
        session = json.loads(raw)
        user_id = session.get("user_id")
        refresh_hash = session.get("refresh_token_hash")

        pipe = redis.pipeline()
        pipe.delete(f"{self.SESSION_PREFIX}{session_id}")
        if refresh_hash:
            pipe.delete(f"{self.REFRESH_PREFIX}{refresh_hash}")
        if user_id:
            pipe.srem(f"{self.USER_SESSIONS_PREFIX}{user_id}", session_id)
        await pipe.execute()

    async def rotate_refresh_token(self, refresh_token: str) -> Optional[tuple[str, str, str, str]]:
        """Returns (session_id, user_id, phone, new_refresh_token) or None."""
        refresh_hash = self._hash_token(refresh_token)
        redis = await redis_client.get_client()
        session_id = await redis.get(f"{self.REFRESH_PREFIX}{refresh_hash}")
        if not session_id:
            return None

        session = await self.get_session(session_id)
        if not session:
            await redis.delete(f"{self.REFRESH_PREFIX}{refresh_hash}")
            return None

        if not secrets.compare_digest(session.get("refresh_token_hash") or "", refresh_hash):
            await self.revoke_session(session_id)
            return None

        new_refresh = secrets.token_urlsafe(48)
        new_hash = self._hash_token(new_refresh)
        session["refresh_token_hash"] = new_hash
        session["last_rotated_at"] = datetime.utcnow().isoformat()

        pipe = redis.pipeline()
        pipe.setex(f"{self.SESSION_PREFIX}{session_id}", self._refresh_ttl_seconds(), json.dumps(session))
        pipe.delete(f"{self.REFRESH_PREFIX}{refresh_hash}")
        pipe.setex(f"{self.REFRESH_PREFIX}{new_hash}", self._refresh_ttl_seconds(), session_id)
        await pipe.execute()

        return session_id, session["user_id"], session["phone"], new_refresh

    async def get_session_id_for_refresh(self, refresh_token: str) -> Optional[str]:
        refresh_hash = self._hash_token(refresh_token)
        redis = await redis_client.get_client()
        return await redis.get(f"{self.REFRESH_PREFIX}{refresh_hash}")

    def build_auth_tokens(self, *, access_token: str, refresh_token: str, session_id: str) -> CustomerAuthTokens:
        return CustomerAuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            session_id=session_id,
            expires_in=self._access_ttl_seconds(),
        )
