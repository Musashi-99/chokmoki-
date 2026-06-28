import boto3
from botocore.client import Config
from typing import Optional
from src.config import settings
from src.plugins.logger import logger
import uuid

# Immutable, long-lived caching for content-addressed assets.
# Safe because every object key is a fresh UUID — a given key's bytes never change,
# so the browser/edge can cache it for a year and never revalidate.
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"


class R2Service:
    def __init__(self):
        self._client = None
        self._bucket = settings.r2_bucket
        # Optional key prefix so all objects live under a sub-"folder",
        # e.g. R2_KEY_PREFIX=chokmoki -> chokmoki/products/<uuid>.jpg
        self._key_prefix = (settings.r2_key_prefix or "").strip("/")
        self._public_url = settings.r2_public_base_url.rstrip("/") if settings.r2_public_base_url else ""

    def _get_client(self):
        if self._client is None:
            endpoint = f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
            self._client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=settings.r2_access_key_id,
                aws_secret_access_key=settings.r2_secret_access_key,
                config=Config(signature_version="s3v4"),
                region_name="auto",
            )
        return self._client

    def ensure_bucket(self) -> None:
        """Create the configured R2 bucket if it does not already exist."""
        if not settings.r2_account_id or not settings.r2_access_key_id:
            logger.warning("R2 credentials not configured; skipping bucket check")
            return

        client = self._get_client()
        try:
            client.head_bucket(Bucket=self._bucket)
            logger.info(f"R2 bucket '{self._bucket}' is ready")
        except Exception:
            try:
                client.create_bucket(Bucket=self._bucket)
                logger.info(f"R2 bucket '{self._bucket}' created")
            except Exception as e:
                # Bucket may already exist or be owned by this account
                logger.warning(f"R2 bucket '{self._bucket}' create skipped: {e}")

    async def upload_file(
        self,
        file_bytes: bytes,
        extension: str,
        content_type: str,
        folder: str = "products",
    ) -> Optional[str]:
        """Upload validated file bytes to R2 and return public URL."""
        try:
            client = self._get_client()
            ext = extension.lower().lstrip(".")
            folder = (folder or "").strip("/")
            parts = [p for p in (self._key_prefix, folder, f"{uuid.uuid4().hex}.{ext}") if p]
            key = "/".join(parts)

            client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=file_bytes,
                ContentType=content_type,
                CacheControl=IMMUTABLE_CACHE_CONTROL,
            )

            if self._public_url:
                return f"{self._public_url}/{key}"
            # Fallback: construct Cloudflare R2 public URL
            return f"https://{settings.r2_account_id}.r2.cloudflarestorage.com/{self._bucket}/{key}"
        except Exception as e:
            logger.error(f"R2 upload failed: {e}")
            raise

    def backfill_cache_headers(self, dry_run: bool = True) -> dict:
        """Backfill `Cache-Control: immutable` onto existing objects.

        Walks every object under the configured key prefix and, for any object
        whose CacheControl differs from IMMUTABLE_CACHE_CONTROL, rewrites it in
        place via copy_object(MetadataDirective="REPLACE"). The bytes and key are
        untouched — only response metadata changes — so URLs and visuals are
        identical. ContentType is preserved from the existing object.

        Set dry_run=False to actually apply. Returns a summary dict.
        """
        client = self._get_client()
        prefix = f"{self._key_prefix}/" if self._key_prefix else ""
        paginator = client.get_paginator("list_objects_v2")

        scanned = 0
        updated = 0
        skipped = 0
        errors = 0

        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                scanned += 1
                try:
                    head = client.head_object(Bucket=self._bucket, Key=key)
                    if head.get("CacheControl") == IMMUTABLE_CACHE_CONTROL:
                        skipped += 1
                        continue
                    if dry_run:
                        updated += 1
                        logger.info(f"[dry-run] would set immutable cache on {key}")
                        continue
                    client.copy_object(
                        Bucket=self._bucket,
                        Key=key,
                        CopySource={"Bucket": self._bucket, "Key": key},
                        MetadataDirective="REPLACE",
                        ContentType=head.get("ContentType", "application/octet-stream"),
                        CacheControl=IMMUTABLE_CACHE_CONTROL,
                    )
                    updated += 1
                    logger.info(f"set immutable cache on {key}")
                except Exception as e:
                    errors += 1
                    logger.error(f"backfill failed for {key}: {e}")

        summary = {
            "dry_run": dry_run,
            "scanned": scanned,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
        }
        logger.info(f"R2 cache backfill summary: {summary}")
        return summary

    async def delete_file(self, url: str) -> bool:
        """Delete file from R2 by URL"""
        try:
            client = self._get_client()
            # Extract key from URL
            if self._public_url and url.startswith(self._public_url):
                key = url.replace(f"{self._public_url}/", "")
            else:
                # Try to extract key from full URL
                parts = url.split(f"/{self._bucket}/")
                key = parts[-1] if len(parts) > 1 else url.split("/")[-1]

            client.delete_object(Bucket=self._bucket, Key=key)
            return True
        except Exception as e:
            logger.error(f"R2 delete failed: {e}")
            return False
