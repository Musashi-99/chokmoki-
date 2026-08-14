from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from api.bootstrap import PincodeService

router = APIRouter()


@router.get("/api/pincode/{pincode}")
async def api_lookup_pincode(pincode: str):
    if PincodeService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    if not pincode.isdigit() or len(pincode) != 6:
        raise HTTPException(status_code=400, detail="Invalid pincode")

    place = await PincodeService().lookup(pincode)
    if not place:
        raise HTTPException(status_code=404, detail="Pincode not found")
    return JSONResponse(content=place)
