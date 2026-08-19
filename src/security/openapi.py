"""OpenAPI / docs exposure policy."""

from __future__ import annotations

from typing import Any, Dict


def fastapi_docs_kwargs(is_production: bool) -> Dict[str, Any]:
    if is_production:
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {}
