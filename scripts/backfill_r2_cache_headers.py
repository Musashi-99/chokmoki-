#!/usr/bin/env python3
"""Backfill immutable Cache-Control headers onto existing R2 objects.

Existing assets were uploaded before the immutable cache header was added to the
upload pipeline, so they are served with no Cache-Control and miss the Cloudflare
edge cache (cf-cache-status: DYNAMIC). This rewrites their metadata in place.

The operation is metadata-only: object bytes and keys never change, so every
existing URL keeps working and the site looks identical. UUID filenames make the
immutable directive safe (a key's content never changes).

Usage (run from the chokmoki-serverless project root, with R2_* env vars set):

    python -m scripts.backfill_r2_cache_headers            # dry run (default)
    python -m scripts.backfill_r2_cache_headers --apply    # actually rewrite

Verify a single object afterwards:

    curl -I https://cdn.amplifycheckout.com/<key>
    # expect: Cache-Control: public, max-age=31536000, immutable
"""
import argparse
import sys

from src.services.r2_service import R2Service, IMMUTABLE_CACHE_CONTROL


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually rewrite metadata. Without this flag the script only reports.",
    )
    args = parser.parse_args()

    service = R2Service()
    print(f"Target Cache-Control: {IMMUTABLE_CACHE_CONTROL}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}\n")

    summary = service.backfill_cache_headers(dry_run=not args.apply)

    print("\n--- Summary ---")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    if not args.apply and summary["updated"]:
        print("\nDry run complete. Re-run with --apply to rewrite the objects above.")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
