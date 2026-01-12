from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional
from bson import ObjectId
from datetime import datetime
import json
import sys

try:
    from src.database.connection import db
    from src.cqrs.router import CQRSRouter
    from src.plugins.logger import logger
except Exception as e:
    # Log import errors but don't crash
    print(f"Import error: {e}", file=sys.stderr)
    db = None
    CQRSRouter = None
    logger = None


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class APIRequest(BaseModel):
    type: str
    operation: str
    params: Dict[str, Any] = {}
    adminKey: Optional[str] = None


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    if db is not None:
        try:
            await db.connect()
            if logger:
                logger.info("Database connected")
        except Exception as e:
            if logger:
                logger.error(f"Database connection error: {str(e)}")
            # Don't crash the app if DB connection fails - will connect lazily on first use


@app.on_event("shutdown")
async def shutdown_event():
    if db is not None:
        try:
            await db.close()
            if logger:
                logger.info("Database disconnected")
        except Exception as e:
            if logger:
                logger.error(f"Database disconnection error: {str(e)}")


@app.post("/")
async def handle_request(request: APIRequest):
    if CQRSRouter is None:
        raise HTTPException(status_code=500, detail="Server not properly initialized")
    
    try:
        if not request.operation:
            raise HTTPException(status_code=400, detail="Operation is required")
        
        if request.type not in ["query", "mutation"]:
            raise HTTPException(status_code=400, detail="Type must be 'query' or 'mutation'")
        
        if request.type == "query":
            result = await CQRSRouter.execute_query(request.operation, request.params, request.adminKey)
        else:
            result = await CQRSRouter.execute_mutation(request.operation, request.params, request.adminKey)
        
        return JSONResponse(
            content=json.loads(json.dumps(result, cls=JSONEncoder)),
            status_code=200
        )
    
    except ValueError as e:
        if logger:
            logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        if logger:
            logger.error(f"Server error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/health")
async def health_check():
    return {"status": "ok"}


from mangum import Mangum

handler = Mangum(app)
