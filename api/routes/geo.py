"""First-visit GeoIP bootstrap for the storefront's country/market detection."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from api.bootstrap import GeoIPDiscoveryAdapter, get_client_ip

router = APIRouter()


@router.get("/api/geo/detect")
async def api_detect_country(request: Request):
    if GeoIPDiscoveryAdapter is None or get_client_ip is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    ip = get_client_ip(request)
    result = await GeoIPDiscoveryAdapter().lookup(ip)
    return JSONResponse(content={"ip": result.ip, "country": result.country})
