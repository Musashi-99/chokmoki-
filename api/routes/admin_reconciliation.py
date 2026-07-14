"""Admin visibility into the payment reconciliation worker — recent runs
(payment_reconcile_log) and unresolved/abandoned payment attempts
(payment_attempts). Read-only: this is an audit view, the actual recovery
work happens in src/worker.py's background loop.
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import Optional
from api.bootstrap import PaymentReconciliationService, SystemLogService, require_admin
from api.json_utils import _json_response_content

router = APIRouter()


@router.get("/api/admin/payment-reconciliation/runs")
async def admin_list_reconciliation_runs(
    limit: int = 50,
    email: str = Depends(require_admin),
):
    if PaymentReconciliationService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    runs = await PaymentReconciliationService().list_runs(limit=limit)
    return JSONResponse(content=_json_response_content({"data": runs}))


@router.get("/api/admin/payment-reconciliation/attempts")
async def admin_list_payment_attempts(
    status: Optional[str] = None,
    limit: int = 100,
    email: str = Depends(require_admin),
):
    if PaymentReconciliationService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    attempts = await PaymentReconciliationService().list_attempts(status=status, limit=limit)
    return JSONResponse(content=_json_response_content({"data": attempts}))


@router.get("/api/admin/system-logs")
async def admin_list_system_logs(
    component: Optional[str] = None,
    level: Optional[str] = None,
    limit: int = 100,
    email: str = Depends(require_admin),
):
    """Durable operational log — fallback triggers, detected inconsistencies,
    degraded-mode operation. See src/services/system_log_service.py.
    """
    if SystemLogService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    logs = await SystemLogService().list_logs(component=component, level=level, limit=limit)
    return JSONResponse(content=_json_response_content({"data": logs}))
