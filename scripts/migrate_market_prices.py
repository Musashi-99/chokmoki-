"""One-time backfill of the new `prices` (multi-region) field on every
product from its existing `price_inr`/`selling_price` — see
docs/multi-region-scope-of-work.md.

Every product gets an "IN" entry (mirroring its current India price) and a
"default" entry (the fallback bucket for every country outside the
configured markets, currency USD). AU/NZ entries are NOT backfilled here —
an admin must price each product for those markets deliberately via the
new "Market Pricing" editor in the admin panel; leaving them unset means
those products fall back to the "default" bucket for AU/NZ customers until
priced.

Usage (inside the backend container):
    python scripts/migrate_market_prices.py                      # dry run
    python scripts/migrate_market_prices.py --usd-rate 0.012     # dry run, custom INR->USD rate for the default bucket
    python scripts/migrate_market_prices.py --apply              # write
"""
import argparse
import asyncio
import sys

sys.path.insert(0, "/app")

from src.database.connection import db  # noqa: E402


async def run(usd_rate: float, apply: bool) -> None:
    database = await db.get_database()
    collection = database["products"]

    cursor = collection.find({"prices": {"$in": [None, []]}})
    total = 0
    changed = 0
    samples = []

    async for doc in cursor:
        total += 1
        price_inr = float(doc.get("price_inr") or doc.get("selling_price") or 0)
        mrp_inr = float(doc.get("price_inr") or price_inr)
        if price_inr <= 0:
            continue

        prices = [
            {
                "country": "IN",
                "sym": "₹",
                "currency": "INR",
                "mrp": round(mrp_inr, 2),
                "sellingPrice": round(price_inr, 2),
            },
            {
                "country": "default",
                "sym": "$",
                "currency": "USD",
                "mrp": round(mrp_inr * usd_rate, 2),
                "sellingPrice": round(price_inr * usd_rate, 2),
            },
        ]

        if len(samples) < 5:
            samples.append((str(doc.get("_id")), doc.get("slug"), prices))

        changed += 1
        if apply:
            await collection.update_one({"_id": doc["_id"]}, {"$set": {"prices": prices}})

    print(f"Scanned {total} products without a `prices` array.")
    print(f"{'Updated' if apply else 'Would update'} {changed} products.")
    for pid, slug, prices in samples:
        print(f"  - {slug} ({pid}): {prices}")
    if not apply:
        print("\nDry run only — re-run with --apply to write changes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--usd-rate", type=float, default=0.012,
        help="INR->USD conversion rate used only to seed the 'default' bucket (admin can edit afterwards)",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = parser.parse_args()
    asyncio.run(run(usd_rate=args.usd_rate, apply=args.apply))
