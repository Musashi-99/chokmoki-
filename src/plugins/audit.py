from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from src.plugins.logger import logger


async def log_admin_audit(
    *,
    actor_email: str,
    action: str,
    resource: str,
    method: str,
    path: str,
    status_code: int,
    ip: Optional[str] = None,
    session_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "admin_audit",
        "severity": "info",
        "actor_email": actor_email,
        "action": action,
        "resource": resource,
        "resource_id": resource_id,
        "method": method,
        "path": path,
        "status_code": status_code,
        "ip": ip,
        "session_id": session_id,
        "metadata": metadata or {},
    }
    logger.info(json.dumps(entry, default=str))
