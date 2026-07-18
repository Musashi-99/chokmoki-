"""One-time (and invertible) rewrite of stored media URL bases.

Why: image URLs are stored ABSOLUTE in Mongo (product thumbnails/galleries,
hero images, site assets, ...). When the public media base changes — e.g.
cdn.amplifycheckout.com died and images moved behind our own
api.chokmoki.com/media proxy — every stored URL must be rewritten once.

Usage (inside the backend container):
    python scripts/migrate_media_urls.py --old https://cdn.amplifycheckout.com --new https://api.chokmoki.com/media            # dry run
    python scripts/migrate_media_urls.py --old ... --new ... --apply                                                          # write

Invertible by swapping --old/--new. Dry run is the default and prints a
per-collection count of documents that would change, plus a few sample
before/after values, without writing anything.
"""
import argparse
import asyncio
import sys
from typing import Any, List, Tuple

sys.path.insert(0, "/app")

from src.database.connection import db  # noqa: E402

# Collections that never store media URLs and/or must never be bulk-rewritten.
SKIP_COLLECTIONS = {
    "order_events",
    "order_logs",
    "system_logs",
    "payment_reconcile_log",
    "counters",
    "inventory_reservations",
    "admin_audit_logs",
    "admin_users",
}


def rewrite(value: Any, old: str, new: str, samples: List[Tuple[str, str]]) -> Tuple[Any, bool]:
    """Deep-rewrite `old` -> `new` inside any nested str/dict/list value.
    Returns (new_value, changed).
    """
    if isinstance(value, str):
        if old in value:
            replaced = value.replace(old, new)
            if len(samples) < 5:
                samples.append((value, replaced))
            return replaced, True
        return value, False
    if isinstance(value, dict):
        changed = False
        out = {}
        for k, v in value.items():
            out[k], c = rewrite(v, old, new, samples)
            changed = changed or c
        return out, changed
    if isinstance(value, list):
        changed = False
        out_list = []
        for v in value:
            nv, c = rewrite(v, old, new, samples)
            out_list.append(nv)
            changed = changed or c
        return out_list, changed
    return value, False


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", required=True, help="Old URL base, e.g. https://cdn.amplifycheckout.com")
    parser.add_argument("--new", required=True, help="New URL base, e.g. https://api.chokmoki.com/media")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = parser.parse_args()
    old = args.old.rstrip("/")
    new = args.new.rstrip("/")

    await db.connect()
    database = await db.get_database()

    total_changed = 0
    for name in sorted(await database.list_collection_names()):
        if name in SKIP_COLLECTIONS or name.startswith("system."):
            continue
        collection = database[name]
        # Cheap pre-filter: only walk documents that contain the old base
        # somewhere. $where is unavailable/slow, so scan candidates via a
        # regex over the whole doc is impossible server-side — instead scan
        # every doc client-side but only in collections, which are all small
        # (content/config collections; the big ones are in SKIP).
        changed_in_collection = 0
        samples: List[Tuple[str, str]] = []
        async for doc in collection.find({}):
            doc_id = doc.pop("_id")
            new_doc, changed = rewrite(doc, old, new, samples)
            if not changed:
                continue
            changed_in_collection += 1
            if args.apply:
                await collection.replace_one({"_id": doc_id}, new_doc)
        if changed_in_collection:
            total_changed += changed_in_collection
            mode = "UPDATED" if args.apply else "would update"
            print(f"{name}: {mode} {changed_in_collection} document(s)")
            for before, after in samples[:2]:
                print(f"    - {before[:90]}")
                print(f"    + {after[:90]}")

    print(f"\n{'APPLIED' if args.apply else 'DRY RUN'}: {total_changed} document(s) total")


if __name__ == "__main__":
    asyncio.run(main())
