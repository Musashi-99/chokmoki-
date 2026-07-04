from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.alerts.events import EVENT_ADMIN_MUTATION, publish_alert
from src.plugins.audit import log_admin_audit
from src.plugins.logger import logger
from src.security.client_ip import get_client_ip


class AdminAuditMiddleware(BaseHTTPMiddleware):
    SKIP_PATHS = {
        "/api/admin/login",
        "/api/admin/refresh",
        "/api/admin/logout",
        "/api/admin/me",
    }

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if not path.startswith("/api/admin/"):
            return response
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return response
        if path in self.SKIP_PATHS:
            return response

        principal = getattr(request.state, "admin_principal", None)
        email = getattr(request.state, "admin_email", None)
        if not email and principal:
            email = principal.email
        if not email:
            return response

        resource = path.removeprefix("/api/admin/").split("/")[0] or "admin"
        action = f"{request.method.lower()}_{resource}"
        await log_admin_audit(
            actor_email=email,
            action=action,
            resource=resource,
            method=request.method,
            path=path,
            status_code=response.status_code,
            ip=get_client_ip(request),
            session_id=getattr(principal, "session_id", None),
        )

        if response.status_code < 400:
            try:
                await publish_alert(
                    EVENT_ADMIN_MUTATION,
                    {
                        "actor_email": email,
                        "resource": resource,
                        "action": action,
                        "method": request.method,
                        "path": path,
                        "status_code": response.status_code,
                    },
                )
            except Exception as e:
                if logger:
                    logger.warning(f"Failed to publish admin mutation alert: {e}")

        return response
