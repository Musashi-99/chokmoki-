"""Legacy CQRS dispatch endpoint (POST /) used by src/cqrs + src/resources."""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
import json
from api.bootstrap import AuthorizationError, CQRSRouter, logger, settings
from api.json_utils import JSONEncoder
from src.security.idempotency import IdempotencyConflictError, IdempotencyService

router = APIRouter()


class APIRequest(BaseModel):
    type: str
    operation: str
    params: Dict[str, Any] = {}
    adminKey: Optional[str] = None
    idempotencyKey: Optional[str] = None


_IDEMPOTENT_CQRS_OPERATIONS = frozenset(
    {"order.create", "order.initiate", "order.verifyPayment"}
)


@router.post("/")
async def handle_request(request: APIRequest):
    if CQRSRouter is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    if request.type not in {"query", "mutation"}:
        raise HTTPException(status_code=400, detail="Invalid type")

    idem_service = IdempotencyService()
    idem_storage_key = None
    idem_fingerprint = None
    if request.type == "mutation" and request.operation in _IDEMPOTENT_CQRS_OPERATIONS:
        idem_key = request.idempotencyKey
        if (
            settings
            and settings.is_production
            and settings.idempotency_required_in_production
            and not idem_key
        ):
            raise HTTPException(status_code=400, detail="idempotencyKey is required")
        if idem_key:
            try:
                idem_storage_key = idem_service.normalize_key(idem_key)
                idem_fingerprint = idem_service.fingerprint(
                    scope=f"cqrs:{request.operation}",
                    payload=request.params,
                )
                cached = await idem_service.begin(idem_storage_key, idem_fingerprint)
                if cached:
                    return JSONResponse(status_code=cached.status_code, content=cached.body)
            except IdempotencyConflictError:
                raise HTTPException(
                    status_code=409, detail="Idempotency-Key reused with different payload"
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        if request.type == "query":
            result = await CQRSRouter.execute_query(
                request.operation, request.params, request.adminKey
            )
        else:
            result = await CQRSRouter.execute_mutation(
                request.operation, request.params, request.adminKey
            )

        response_body = json.loads(json.dumps(result, cls=JSONEncoder))
        if idem_storage_key and idem_fingerprint:
            await idem_service.store(
                idem_storage_key,
                idem_fingerprint,
                status_code=200,
                body=response_body,
            )
        return JSONResponse(content=response_body)

    except HTTPException:
        if idem_storage_key:
            await idem_service.release_lock(idem_storage_key)
        raise
    except ValidationError:
        if idem_storage_key:
            await idem_service.release_lock(idem_storage_key)
        raise HTTPException(status_code=400, detail="Invalid request parameters")
    except Exception as e:
        if idem_storage_key:
            await idem_service.release_lock(idem_storage_key)
        if AuthorizationError is not None and isinstance(e, AuthorizationError):
            raise HTTPException(status_code=403, detail=str(e))
        if isinstance(e, ValueError):
            message = str(e)
            if "authentication required" in message.lower():
                raise HTTPException(status_code=403, detail=message)
            raise HTTPException(status_code=400, detail=message)
        if logger:
            logger.error(str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
