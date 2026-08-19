"""Public contact form + newsletter signup."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from typing import Any, Dict
from pydantic import ValidationError
from api.bootstrap import ContactSubmissionCreate, InboxService, NewsletterSubscribeCreate
from api.json_utils import _json_response_content

router = APIRouter()


@router.post("/api/contact")
async def api_submit_contact(payload: Dict[str, Any]):
    if InboxService is None or ContactSubmissionCreate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        data = ContactSubmissionCreate(**payload)
        created = await InboxService().create_contact(data)
    except ValidationError:
        raise HTTPException(status_code=400, detail="Invalid contact form")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not submit the form")
    return JSONResponse(content=_json_response_content({
        "success": True,
        "id": str(created.id),
    }))


@router.post("/api/newsletter")
async def api_subscribe_newsletter(payload: Dict[str, Any]):
    if InboxService is None or NewsletterSubscribeCreate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        data = NewsletterSubscribeCreate(**payload)
        created = await InboxService().subscribe_newsletter(data)
    except ValidationError:
        raise HTTPException(status_code=400, detail="Invalid newsletter signup")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not subscribe")
    return JSONResponse(content=_json_response_content({
        "success": True,
        "id": str(created.id),
    }))
