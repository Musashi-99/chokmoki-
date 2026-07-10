"""Admin orders backup: export/restore the orders + order_logs collections as a
standalone JSON file, separate from the site-content bundle (admin_import.py)
which deliberately excludes orders."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from api.bootstrap import (
    MAX_ORDERS_BACKUP_BYTES,
    OrdersBackupParseError,
    db,
    export_orders_backup,
    logger,
    parse_orders_backup,
    plan_orders_restore,
    require_admin,
    restore_orders_backup,
)

router = APIRouter()


@router.get("/api/admin/orders/export")
async def admin_export_orders(email: str = Depends(require_admin)):
    """Dump every order + order log as a downloadable JSON backup."""
    if db is None or export_orders_backup is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    database = await db.get_database()
    payload = await export_orders_backup(database)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        content=json.dumps(payload),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="chokmoki-orders-backup-{stamp}.json"'},
    )


@router.post("/api/admin/orders/import")
async def admin_import_orders(
    backup: UploadFile = File(...),
    dry_run: bool = False,
    email: str = Depends(require_admin),
):
    """Restore orders + order_logs from a previously exported backup JSON.
    Upserts by order_id (the unique business key), so it's safe to re-run and
    never depends on the target DB's Mongo _id state."""
    if db is None or parse_orders_backup is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    raw = await backup.read()
    if len(raw) > MAX_ORDERS_BACKUP_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Backup exceeds maximum size of {MAX_ORDERS_BACKUP_BYTES // (1024 * 1024)}MB",
        )

    try:
        parsed = parse_orders_backup(raw)
    except OrdersBackupParseError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    database = await db.get_database()

    if dry_run:
        plan = plan_orders_restore(parsed)
        return {
            "dry_run": True,
            "orders_to_restore": plan.orders_to_restore,
            "order_logs_to_restore": plan.order_logs_to_restore,
        }

    try:
        result = await restore_orders_backup(parsed, database)
    except Exception as e:
        if logger:
            logger.error(f"Admin orders import failed: {e}")
        raise HTTPException(status_code=500, detail="Restore failed") from e

    return {
        "orders_restored": result.orders_restored,
        "orders_skipped": result.orders_skipped,
        "order_logs_restored": result.order_logs_restored,
        "order_logs_skipped": result.order_logs_skipped,
    }
