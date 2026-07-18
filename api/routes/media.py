"""Public media proxy — serves R2 objects through our own domain.

Exists because the original public base (cdn.amplifycheckout.com, a
Cloudflare-proxied hostname from another project) died with a 524 while the
R2 bucket + S3 credentials remained fully functional. Rather than depending
on that external domain again, images are streamed through the backend:
GET /media/<key> -> R2 get_object -> response. Objects are content-addressed
(UUID keys, uploaded with immutable cache-control), so browsers cache them
for a year after first load and repeat traffic through this route is small.
"""
import asyncio

from botocore.client import Config as BotoConfig
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.bootstrap import logger, settings

router = APIRouter()

_client = None


def _get_client():
    """Separate boto3 client from R2Service's — this one carries tight
    connect/read timeouts, because it sits on a public, unauthenticated
    request path where a hung upstream must fail fast, not hold the
    connection open the way an admin upload is allowed to.
    """
    global _client
    if _client is None:
        import boto3

        endpoint = settings.r2_endpoint_url or f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
        config_kwargs = {
            "signature_version": "s3v4",
            "connect_timeout": 5,
            "read_timeout": 20,
            "retries": {"max_attempts": 2},
        }
        if settings.r2_endpoint_url:
            config_kwargs["s3"] = {"addressing_style": "path"}
        _client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            config=BotoConfig(**config_kwargs),
            region_name="auto",
        )
    return _client


@router.get("/media/{key:path}")
async def serve_media(key: str):
    if settings is None or not settings.r2_account_id:
        raise HTTPException(status_code=404, detail="Not found")

    key = key.strip("/")
    # The bucket is shared with another project's files — only serve keys
    # under our own configured prefix (e.g. "chokmoki/..."), and never
    # anything path-traversal-shaped.
    allowed_prefix = (settings.r2_key_prefix or "").strip("/")
    if not key or ".." in key:
        raise HTTPException(status_code=404, detail="Not found")
    if allowed_prefix and not key.startswith(f"{allowed_prefix}/"):
        raise HTTPException(status_code=404, detail="Not found")

    def fetch():
        client = _get_client()
        obj = client.get_object(Bucket=settings.r2_bucket, Key=key)
        return (
            obj["Body"].read(),
            obj.get("ContentType") or "application/octet-stream",
            obj.get("CacheControl") or "public, max-age=31536000, immutable",
            obj.get("ETag"),
        )

    try:
        body, content_type, cache_control, etag = await asyncio.to_thread(fetch)
    except Exception as e:
        code = getattr(e, "response", {}).get("Error", {}).get("Code", "") if hasattr(e, "response") else ""
        if code in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail="Not found")
        if logger:
            logger.error(f"Media proxy failed for key '{key}': {e}")
        raise HTTPException(status_code=502, detail="Media temporarily unavailable")

    headers = {"Cache-Control": cache_control}
    if etag:
        headers["ETag"] = etag
    return Response(content=body, media_type=content_type, headers=headers)
