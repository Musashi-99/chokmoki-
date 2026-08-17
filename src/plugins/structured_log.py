from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.plugins.logger import logger


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        s = str(value)
        return s if s else None
    except Exception:
        return None


@dataclass(frozen=True)
class SecurityLogEvent:
    timestamp: str
    request_id: Optional[str]
    trace_id: Optional[str]
    correlation_id: Optional[str]
    session_id: Optional[str]
    user_id: Optional[str]
    ip: Optional[str]
    endpoint: Optional[str]
    latency_ms: Optional[int]
    severity: str
    module: str
    event: str
    risk_score: Optional[int]
    fields: Dict[str, Any]

    def to_json(self) -> str:
        payload: Dict[str, Any] = {
            "timestamp": self.timestamp,
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "correlation_id": self.correlation_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "ip": self.ip,
            "endpoint": self.endpoint,
            "latency": self.latency_ms,
            "severity": self.severity,
            "module": self.module,
            "event": self.event,
            "risk_score": self.risk_score,
            **(self.fields or {}),
        }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=str)


def security_log(
    *,
    severity: str,
    module: str,
    event: str,
    request_id: Any = None,
    trace_id: Any = None,
    correlation_id: Any = None,
    session_id: Any = None,
    user_id: Any = None,
    ip: Any = None,
    endpoint: Any = None,
    latency_ms: Optional[int] = None,
    risk_score: Optional[int] = None,
    **fields: Any,
) -> None:
    entry = SecurityLogEvent(
        timestamp=_utc_now_iso(),
        request_id=_safe_str(request_id),
        trace_id=_safe_str(trace_id),
        correlation_id=_safe_str(correlation_id),
        session_id=_safe_str(session_id),
        user_id=_safe_str(user_id),
        ip=_safe_str(ip),
        endpoint=_safe_str(endpoint),
        latency_ms=latency_ms,
        severity=(severity or "INFO").upper(),
        module=module,
        event=event,
        risk_score=risk_score,
        fields=fields,
    )
    msg = entry.to_json()
    level = entry.severity
    if level in {"ERROR", "CRITICAL"}:
        logger.error(msg)
    elif level in {"WARN", "WARNING"}:
        logger.warning(msg)
    elif level in {"DEBUG"}:
        logger.debug(msg)
    else:
        logger.info(msg)


def app_log(
    *,
    severity: str,
    module: str,
    event: str,
    correlation_id: Any = None,
    **fields: Any,
) -> None:
    """Structured JSON log for business-logic events (orders, payments, inventory)."""
    security_log(
        severity=severity,
        module=module,
        event=event,
        correlation_id=correlation_id,
        **fields,
    )

