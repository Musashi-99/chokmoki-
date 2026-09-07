"""One-time backfill of the new `stock` (multi-region) field on every
product that doesn't have one yet — same shape/spirit as
migrate_market_prices.py.

Stock is tracked per-region (src/models/product.py: MarketStock), not a
single global number, so checkout can verify against the *specific* country
an order is actually for — a product can be sold out in India while still
available in Australia. `InventoryService.tracks_inventory()` treats a
region with qty=None as "doesn't track inventory there at all" — no
reservation, no decrement, never "out of stock" for that region.

Every product gets an "IN" entry and a "default" entry (the fallback
bucket for every country outside the configured markets), both seeded with
the same conservative starting quantity. AU/NZ entries are NOT backfilled
here — an admin prices/stocks each product for those markets deliberately
via the admin panel's region stock editor; leaving them unset means those
regions fall back to the "default" bucket's quantity until set.

This also removes the old flat `stock_status`/`stock_qty` fields once a
product is migrated, so there's exactly one source of truth going forward.

Usage (inside the backend container):
    python scripts/migrate_stock_quantities.py                    # dry run
    python scripts/migrate_stock_quantities.py --default-qty 25   # dry run, custom starting quantity
    python scripts/migrate_stock_quantities.py --apply            # write
"""
import argparse
import asyncio
import sys

sys.path.insert(0, "/app")

from src.database.connection import db  # noqa: E402

DEFAULT_STARTING_QTY = 50


async def run(default_qty: int, apply: bool) -> None:
    database = await db.get_database()
    collection = database["products"]

    cursor = collection.find({"stock": {"$in": [None, []]}})
    total = 0
    samples = []

    async for doc in cursor:
        total += 1
        # Respect an existing manual out_of_stock mark from the old flat
        # field rather than silently reviving it as in-stock.
        legacy_status = doc.get("stock_status") or "in_stock"
        stock = [
            {"country": "IN", "qty": default_qty, "status": legacy_status},
            {"country": "default", "qty": default_qty, "status": legacy_status},
        ]

        if len(samples) < 5:
            samples.append((str(doc.get("_id")), doc.get("slug"), stock))

        if apply:
            await collection.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {"stock": stock},
                    "$unset": {"stock_status": "", "stock_qty": ""},
                },
            )

    print(f"Scanned {total} products with no `stock` array.")
    print(f"{'Updated' if apply else 'Would update'} {total} products with stock_qty={default_qty}.")
    for pid, slug, stock in samples:
        print(f"  - {slug} ({pid}): {stock}")
    if not apply:
        print("\nDry run only — re-run with --apply to write changes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--default-qty", type=int, default=DEFAULT_STARTING_QTY,
        help=f"Starting stock quantity for IN and default buckets (default: {DEFAULT_STARTING_QTY})",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = parser.parse_args()
    asyncio.run(run(default_qty=args.default_qty, apply=args.apply))
