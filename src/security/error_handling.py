"""Generic client errors, correlation IDs, and secure server-side logging."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Mapping, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

CORRELATION_ID_HEADER = "X-Request-Id"
MAX_CLIENT_DETAIL_LENGTH = 200

INTERNAL_LEAK_PATTERN = re.compile(
    r"mongo|pymongo|bson|redis|traceback|sqlalchemy|integrityerror|"
    r"connectionrefused|connectionerror|operationalerror|server selection|"
    r"\bsecret\b|token_urlsafe|stack trace|file \"|line \d+|exception:|"
    r"E11000|duplicate key error",
    re.IGNORECASE,
)

GENERIC_BY_STATUS: dict[int, str] = {
    400: "The request could not be processed.",
    401: "Authentication required.",
    403: "Access denied.",
    404: "Resource not found.",
    409: "The request conflicts with current state.",
    422: "Validation failed.",
    429: "Too many requests.",
    500: "An internal error occurred.",
    503: "Service temporarily unavailable.",
}


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def resolve_correlation_id(request: Request) -> str:
    header_value = request.headers.get(CORRELATION_ID_HEADER)
    if header_value:
        candidate = header_value.strip()
        if candidate and len(candidate) <= 64 and re.fullmatch(r"[\w\-]+", candidate):
            return candidate

    state_id = getattr(request.state, "correlation_id", None)
    if isinstance(state_id, str) and state_id:
        return state_id
    return new_correlation_id()


def sanitize_client_detail(detail: Any, status_code: int) -> str:
    if status_code >= 500:
        return GENERIC_BY_STATUS.get(status_code, GENERIC_BY_STATUS[500])

    if isinstance(detail, list):
        return GENERIC_BY_STATUS.get(422, "Validation failed.")

    if not isinstance(detail, str):
        return GENERIC_BY_STATUS.get(status_code, GENERIC_BY_STATUS[400])

    text = detail.strip()
    if not text or len(text) > MAX_CLIENT_DETAIL_LENGTH:
        return GENERIC_BY_STATUS.get(status_code, GENERIC_BY_STATUS[400])
    if INTERNAL_LEAK_PATTERN.search(text):
        return GENERIC_BY_STATUS.get(status_code, GENERIC_BY_STATUS[400])
    return text


def error_response(
    status_code: int,
    correlation_id: str,
    detail: Any = None,
    headers: Optional[Mapping[str, str]] = None,
) -> JSONResponse:
    client_detail = sanitize_client_detail(detail, status_code)
    response_headers = {CORRELATION_ID_HEADER: correlation_id}
    if headers:
        response_headers.update(dict(headers))
    return JSONResponse(
        status_code=status_code,
        content={"detail": client_detail, "correlation_id": correlation_id},
        headers=response_headers,
    )


def log_server_exception(
    logger: logging.Logger,
    correlation_id: str,
    exc: BaseException,
    *,
    request: Optional[Request] = None,
    context: str = "",
) -> None:
    path = request.url.path if request else "unknown"
    suffix = f" [{context}]" if context else ""
    logger.exception(
        "Request failed%s path=%s correlation_id=%s",
        suffix,
        path,
        correlation_id,
        exc_info=exc,
    )


def register_exception_handlers(app, logger: Optional[logging.Logger]) -> None:
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException):
        correlation_id = resolve_correlation_id(request)
        return error_response(
            exc.status_code,
            correlation_id,
            exc.detail,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request, exc: RequestValidationError
    ):
        correlation_id = resolve_correlation_id(request)
        if logger:
            logger.warning(
                "Request validation failed path=%s correlation_id=%s errors=%s",
                request.url.path,
                correlation_id,
                exc.errors(),
            )
        return error_response(422, correlation_id)

    @app.exception_handler(Exception)
    async def handle_unhandled_exception(request: Request, exc: Exception):
        correlation_id = resolve_correlation_id(request)
        if logger:
            log_server_exception(logger, correlation_id, exc, request=request)
        return error_response(500, correlation_id)
