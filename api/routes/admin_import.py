"""Admin restore-from-backup: accepts a content bundle ZIP and repopulates MongoDB + R2."""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from api.bootstrap import (
    db, R2Service, require_admin, logger, BundleParseError,
    parse_bundle_zip, restore_bundle, plan_restore, MAX_BUNDLE_BYTES,
)

router = APIRouter()


@router.post("/api/admin/import")
async def admin_import_bundle(
    bundle: UploadFile = File(...),
    dry_run: bool = False,
    email: str = Depends(require_admin),
):
    """Restore all site content + images from a previously exported backup ZIP."""
    if db is None or R2Service is None or parse_bundle_zip is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    raw = await bundle.read()
    if len(raw) > MAX_BUNDLE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Bundle exceeds maximum size of {MAX_BUNDLE_BYTES // (1024 * 1024)}MB",
        )

    try:
        parsed = parse_bundle_zip(raw)
    except BundleParseError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    database = await db.get_database()

    if dry_run:
        plan = await plan_restore(parsed, database)
        return {
            "dry_run": True,
            "sections_to_restore": plan.sections_to_restore,
            "sections_skipped": plan.sections_skipped,
            "sections_skip_reasons": plan.sections_skip_reasons,
            "assets_to_upload": plan.assets_to_upload,
            "id_diff": plan.id_diff,
        }

    r2 = R2Service()
    try:
        result = await restore_bundle(parsed, database, r2)
    except Exception as e:
        if logger:
            logger.error(f"Admin import failed: {e}")
        raise HTTPException(status_code=500, detail="Restore failed") from e

    return {
        "sections_restored": result.sections_restored,
        "sections_skipped": result.sections_skipped,
        "sections_skip_reasons": result.sections_skip_reasons,
        "assets_restored": result.assets_restored,
        "assets_failed": result.assets_failed,
        "assets_deduplicated": result.assets_deduplicated,
    }
