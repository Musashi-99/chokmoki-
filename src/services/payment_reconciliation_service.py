"""Webhook-independent payment reconciliation — the correctness path behind
the webhook's fast path.

Never trust only webhooks: networks fail, our server can be down at the
exact moment Razorpay delivers, webhook signature verification can fail,
Redis can be down, a deploy can restart mid-delivery. This service is the
source-of-truth repair mechanism — on a schedule (src/worker.py), it asks
Razorpay directly for the true state of anything we're still unsure about,
independent of whether any webhook ever arrived.

Deliberately a separate, durable record from the Redis pending_order key:
that key's TTL (src/config.py: inventory_reservation_ttl_seconds, 1h by
default) exists to release reserved stock, not to bound how long we can
recover a missed payment. A payment_attempts row here outlives that TTL, so
reconciliation can still find and recover a payment even after Redis has
already forgotten it — this is exactly the gap in the earlier, simpler
Redis-scanning approach (OrderService.reconcile_pending_payments()).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List

import razorpay.errors

from src.config import settings
from src.database.connection import db
from src.plugins.logger import logger
from src.resilience.circuit_breaker import CircuitBreaker
from src.resilience.guarded import call_guarded
from src.services.razorpay_service import RazorpayService
from src.services.system_log_service import SystemLogService

PAYMENT_ATTEMPTS_COLLECTION = "payment_attempts"
# Same name as order_service.py's RAZORPAY_BREAKER — CircuitBreaker's state
# lives in Redis keyed by name, so this is the same shared breaker, not a
# separate one; defined again here (rather than imported) to avoid a
# module-level import cycle with order_service.py (which imports this
# module's PaymentReconciliationService at module level, and this module
# already lazily imports OrderService inside run() for the same reason).
RAZORPAY_BREAKER = CircuitBreaker(
    "razorpay", failure_threshold=5, failure_window_seconds=60, cooldown_seconds=30
)
RECONCILE_LOG_COLLECTION = "payment_reconcile_log"
ORDERS_COLLECTION = "orders"
SYSTEM_LOG_COMPONENT = "payment_reconciliation"


class PaymentReconciliationService:
    async def _db(self):
        return await db.get_database()

    async def ensure_indexes(self) -> None:
        database = await self._db()
        attempts = database[PAYMENT_ATTEMPTS_COLLECTION]
        await attempts.create_index("order_id", unique=True)
        await attempts.create_index([("status", 1), ("created_at", 1)])
        await attempts.create_index("razorpay_order_id")
        logs = database[RECONCILE_LOG_COLLECTION]
        await logs.create_index([("started_at", -1)])
        await SystemLogService().ensure_indexes()

    async def record_attempt(
        self,
        *,
        order_id: str,
        razorpay_order_id: str,
        user_email: str,
        total_amount: float,
        order_snapshot: Dict[str, Any],
    ) -> None:
        """Called from OrderService.initiate_order() right after creating the
        Razorpay order — a durable, time-queryable "we started this payment"
        record, independent of the Redis pending_order key.

        order_snapshot is the full order_dict that was also written to Redis.
        Redis's pending_order key is only kept for inventory_reservation_ttl_seconds
        (1h by default) — shorter than this service's own reconcile window (2h by
        default). Without a durable copy of the order payload itself, recovering a
        payment whose webhook arrived late (or never) would still fail with
        "not_found" once Redis has already expired the key. Storing it here is
        what actually closes that gap.
        """
        database = await self._db()
        await database[PAYMENT_ATTEMPTS_COLLECTION].update_one(
            {"order_id": order_id},
            {
                "$setOnInsert": {
                    "order_id": order_id,
                    "razorpay_order_id": razorpay_order_id,
                    "user_email": user_email,
                    "total_amount": total_amount,
                    "order_snapshot": order_snapshot,
                    "status": "pending",
                    "created_at": datetime.utcnow(),
                    "resolved_at": None,
                    "resolution_source": None,
                }
            },
            upsert=True,
        )

    async def get_attempt(self, order_id: str) -> Dict[str, Any] | None:
        database = await self._db()
        return await database[PAYMENT_ATTEMPTS_COLLECTION].find_one({"order_id": order_id})

    async def list_runs(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        """Most recent reconciliation runs, newest first — the admin-panel
        audit view of every scheduled/manual pass, whether or not it found
        anything to recover.
        """
        database = await self._db()
        cursor = database[RECONCILE_LOG_COLLECTION].find({}).sort("started_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def list_attempts(
        self, *, status: str | None = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Recent payment_attempts rows, optionally filtered by status
        (pending/resolved/abandoned) — lets an admin see exactly which
        orders are still unresolved, without the full order_snapshot payload.
        """
        database = await self._db()
        query: Dict[str, Any] = {"status": status} if status else {}
        cursor = database[PAYMENT_ATTEMPTS_COLLECTION].find(
            query, {"order_snapshot": 0}
        ).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def mark_resolved(self, *, order_id: str, source: str) -> None:
        """Called from OrderService.complete_pending_order() the moment an
        order actually completes — regardless of whether the webhook, the
        client-side verify() fast path, or this reconciliation service
        itself is what got there first. Filter on status="pending" so a
        racing second caller (e.g. reconcile checking the instant the
        webhook also lands) can't clobber the accurate first resolution
        source — whichever path actually resolved it first wins.
        """
        database = await self._db()
        await database[PAYMENT_ATTEMPTS_COLLECTION].update_one(
            {"order_id": order_id, "status": "pending"},
            {"$set": {"status": "resolved", "resolved_at": datetime.utcnow(), "resolution_source": source}},
        )

    async def _log_and_save(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        """Every run — success, no-op, or partial failure — lands in
        payment_reconcile_log. This must never itself raise into the caller;
        a logging failure is bad, but must never look like a crashed worker.
        """
        database = await self._db()
        try:
            await database[RECONCILE_LOG_COLLECTION].insert_one(dict(summary))
        except Exception as e:
            if logger:
                logger.error(f"Payment reconcile: failed to persist run summary: {e}")
        return summary

    async def _check_consistency(
        self, *, payments_in_window: Dict[str, Any], by_razorpay_order_id: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Reverse check: for every captured/authorized payment Razorpay
        reports in this window that ISN'T one of our currently-pending
        attempts, is there at least a resolved payment_attempts row or a real
        order for it? If neither exists, Razorpay took money for an order_id
        our system has zero record of — a genuine data inconsistency (e.g. a
        crash between creating the Razorpay order and writing payment_attempts),
        not just "already handled elsewhere." Never raises — a failed
        consistency check must not fail the reconciliation run itself.
        """
        result = {"payments_seen": len(payments_in_window), "unmatched": 0, "orphaned": []}
        try:
            unmatched_ids = [
                rzp_id for rzp_id in payments_in_window if rzp_id not in by_razorpay_order_id
            ]
            result["unmatched"] = len(unmatched_ids)
            if not unmatched_ids:
                return result

            database = await self._db()
            known_orders = await database[ORDERS_COLLECTION].distinct(
                "razorpay_order_id", {"razorpay_order_id": {"$in": unmatched_ids}}
            )
            known_attempts = await database[PAYMENT_ATTEMPTS_COLLECTION].distinct(
                "razorpay_order_id", {"razorpay_order_id": {"$in": unmatched_ids}}
            )
            known = set(known_orders) | set(known_attempts)
            orphaned_ids = [rzp_id for rzp_id in unmatched_ids if rzp_id not in known]
            if orphaned_ids:
                result["orphaned"] = [
                    {"razorpay_order_id": rzp_id, **payments_in_window[rzp_id]}
                    for rzp_id in orphaned_ids[:20]  # cap what we store/log, not what we detect
                ]
        except Exception as e:
            if logger:
                logger.error(f"Payment reconcile: consistency check failed: {e}")
        return result

    async def _fallback_check(
        self,
        *,
        run_id: str,
        still_pending_attempts: List[Dict[str, Any]],
        cutoff: datetime,
        started_at: datetime,
    ) -> Dict[str, Any]:
        """Throttled per-order fallback for whatever the bulk fetch didn't
        resolve — the bulk GET /v1/payments pass can miss something at its
        page cap, or a payment can settle right at the window's edge between
        when the window was computed and when Razorpay processed it. Rather
        than one-call-per-order all at once (the exact pattern we removed
        from the old design), this throttles: N calls, then sleep, repeat —
        configurable so it can be tuned to Razorpay's actual rate limit
        without a code change.
        """
        batch_size = max(1, settings.payment_reconcile_fallback_batch_size)
        interval = max(0, settings.payment_reconcile_fallback_interval_seconds)
        razorpay_service = RazorpayService()

        from src.services.order_service import OrderService  # avoid import cycle

        order_service = OrderService()
        database = await self._db()
        attempts_collection = database[PAYMENT_ATTEMPTS_COLLECTION]

        recovered: List[Dict[str, Any]] = []
        still_pending = 0
        abandoned = 0
        errors: List[Dict[str, Any]] = []
        api_calls = 0

        for i in range(0, len(still_pending_attempts), batch_size):
            batch = still_pending_attempts[i : i + batch_size]
            for attempt in batch:
                order_id = attempt["order_id"]
                razorpay_order_id = attempt["razorpay_order_id"]
                api_calls += 1
                try:
                    payment = await asyncio.to_thread(
                        razorpay_service.fetch_captured_payment, razorpay_order_id
                    )
                except Exception as e:
                    errors.append({"order_id": order_id, "error": str(e)})
                    if logger:
                        logger.error(f"Payment reconcile fallback: check failed for {order_id}: {e}")
                    continue

                if payment:
                    try:
                        _order, completion_status = await order_service.complete_pending_order(
                            order_id, razorpay_order_id, payment["id"], resolution_source="reconcile_fallback"
                        )
                        if completion_status == "created":
                            recovered.append({"order_id": order_id, "payment_id": payment["id"]})
                            if logger:
                                logger.info(
                                    f"Payment reconcile fallback RECOVERED (bulk pass missed it): "
                                    f"order_id={order_id} payment_id={payment['id']}"
                                )
                        else:
                            await self.mark_resolved(order_id=order_id, source="already_processed")
                    except Exception as e:
                        errors.append({"order_id": order_id, "error": str(e)})
                        if logger:
                            logger.error(f"Payment reconcile fallback: recovery failed for {order_id}: {e}")
                else:
                    if attempt["created_at"] <= cutoff:
                        try:
                            await attempts_collection.update_one(
                                {"order_id": order_id},
                                {"$set": {"status": "abandoned", "resolved_at": started_at}},
                            )
                            abandoned += 1
                        except Exception as e:
                            errors.append({"order_id": order_id, "error": str(e)})
                    else:
                        still_pending += 1

            is_last_batch = i + batch_size >= len(still_pending_attempts)
            if not is_last_batch and interval:
                await asyncio.sleep(interval)

        try:
            await SystemLogService().log(
                component=SYSTEM_LOG_COMPONENT,
                level="warning",
                message=(
                    f"Bulk fetch left {len(still_pending_attempts)} payment attempt(s) "
                    f"unresolved — ran throttled per-order fallback."
                ),
                context={
                    "run_id": run_id,
                    "attempted": len(still_pending_attempts),
                    "recovered": len(recovered),
                    "api_calls": api_calls,
                    "batch_size": batch_size,
                    "interval_seconds": interval,
                },
            )
        except Exception:
            pass

        return {
            "recovered": recovered,
            "still_pending": still_pending,
            "abandoned": abandoned,
            "errors": errors,
            "api_calls": api_calls,
        }

    async def run(self) -> Dict[str, Any]:
        """One reconciliation pass.

        Bulk-fetch-then-cross-reference, not one-Razorpay-call-per-pending-order:
        at any real volume, pending (not-yet-webhooked) orders are a tiny
        fraction of total payment volume, so the old approach of asking
        Razorpay "was THIS order paid?" once per pending attempt wasted API
        calls (and ate into Razorpay's own rate limit) in proportion to how
        many webhooks we'd missed, not how many payments actually happened.

        Instead: ask Razorpay once for "every captured/authorized payment in
        this window" (paginated GET /v1/payments, RazorpayService.fetch_payments_window),
        load our own still-pending attempts into an in-memory hashmap keyed by
        razorpay_order_id, and cross-reference locally — O(1) per attempt,
        zero additional API calls. Total Razorpay calls per run scale with
        payment volume / 100 (pagination page size), completely decoupled
        from how many orders are stuck pending. If there's nothing pending,
        Razorpay isn't called at all.

        Anything the bulk pass leaves unresolved gets a throttled per-order
        fallback (_fallback_check), and every run also runs a reverse
        consistency check (_check_consistency) — does Razorpay know about a
        captured payment our system has literally no record of at all?

        This method must never raise — every stage is wrapped so a single
        failure degrades gracefully (partial results, logged) rather than
        crashing the worker's reconcile loop.
        """
        run_id = str(uuid.uuid4())
        started_at = datetime.utcnow()
        window_hours = settings.payment_reconcile_window_hours
        cutoff = started_at - timedelta(hours=window_hours)

        database = await self._db()
        attempts_collection = database[PAYMENT_ATTEMPTS_COLLECTION]

        try:
            pending_attempts = await attempts_collection.find(
                {"status": "pending", "created_at": {"$gte": cutoff}}
            ).to_list(length=500)
        except Exception as e:
            if logger:
                logger.error(f"Payment reconcile: failed to load pending attempts: {e}")
            return await self._log_and_save({
                "run_id": run_id, "started_at": started_at, "finished_at": datetime.utcnow(),
                "duration_ms": 0, "window_hours": window_hours, "checked": 0,
                "recovered": [], "recovered_count": 0, "still_pending": 0, "abandoned": 0,
                "errors": [{"order_id": None, "error": f"failed to load pending attempts: {e}"}],
                "bulk_fetch": {}, "fallback": {}, "consistency": {},
            })

        checked = len(pending_attempts)

        if not pending_attempts:
            finished_at = datetime.utcnow()
            return await self._log_and_save({
                "run_id": run_id, "started_at": started_at, "finished_at": finished_at,
                "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
                "window_hours": window_hours, "checked": 0, "recovered": [], "recovered_count": 0,
                "still_pending": 0, "abandoned": 0, "errors": [],
                "bulk_fetch": {"api_calls": 0, "payments_seen": 0},
                "fallback": {}, "consistency": {},
            })

        # In-memory hashmap: razorpay_order_id -> attempt. Pending-attempt
        # volume is bounded (capped at 500/run) and already loaded above, so a
        # plain dict is the "or similar" to a Redis hashmap here — no need for
        # a second, duplicated piece of state for something this small and
        # already cheap to query from Mongo each run.
        by_razorpay_order_id = {
            a["razorpay_order_id"]: a for a in pending_attempts if a.get("razorpay_order_id")
        }

        razorpay_service = RazorpayService()
        from src.services.order_service import OrderService  # avoid import cycle

        order_service = OrderService()

        try:
            bulk_result = await call_guarded(
                dependency="razorpay",
                fn=lambda: asyncio.to_thread(
                    razorpay_service.fetch_payments_window,
                    int(cutoff.timestamp()),
                    int(started_at.timestamp()),
                ),
                breaker=RAZORPAY_BREAKER,
                timeout_seconds=30.0,  # bulk pagination can take longer than a single call
                bulkhead_limit=10,
                retries=2,
                retryable_exceptions=(razorpay.errors.ServerError, razorpay.errors.GatewayError),
            )
            payments_in_window = bulk_result["payments"]
            if bulk_result.get("hit_page_cap"):
                try:
                    await SystemLogService().log(
                        component=SYSTEM_LOG_COMPONENT,
                        level="warning",
                        message=(
                            "Bulk GET /v1/payments hit its max_pages cap — the window may "
                            "have more payments than were fetched this run."
                        ),
                        context={
                            "run_id": run_id,
                            "pages_fetched": bulk_result.get("pages_fetched"),
                            "raw_payments_seen": bulk_result.get("raw_payments_seen"),
                        },
                    )
                except Exception:
                    pass
        except Exception as e:
            if logger:
                logger.error(f"Payment reconcile: bulk payments fetch failed: {e}")
            try:
                await SystemLogService().log(
                    component=SYSTEM_LOG_COMPONENT, level="error",
                    message=f"Bulk GET /v1/payments fetch failed: {e}",
                    context={"run_id": run_id},
                )
            except Exception:
                pass
            finished_at = datetime.utcnow()
            return await self._log_and_save({
                "run_id": run_id, "started_at": started_at, "finished_at": finished_at,
                "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
                "window_hours": window_hours, "checked": checked, "recovered": [], "recovered_count": 0,
                "still_pending": checked, "abandoned": 0,
                "errors": [{"order_id": None, "error": f"bulk fetch failed: {e}"}],
                "bulk_fetch": {"pages_fetched": 0, "payments_seen": 0, "failed": True},
                "fallback": {}, "consistency": {},
            })

        recovered: List[Dict[str, Any]] = []
        still_pending_attempts: List[Dict[str, Any]] = []
        abandoned = 0
        errors: List[Dict[str, Any]] = []

        for razorpay_order_id, attempt in by_razorpay_order_id.items():
            order_id = attempt["order_id"]
            payment = payments_in_window.get(razorpay_order_id)

            if payment:
                try:
                    _order, completion_status = await order_service.complete_pending_order(
                        order_id, razorpay_order_id, payment["id"], resolution_source="reconcile"
                    )
                    if completion_status == "created":
                        recovered.append({"order_id": order_id, "payment_id": payment["id"]})
                        if logger:
                            logger.info(
                                f"Payment reconcile RECOVERED missed webhook: "
                                f"order_id={order_id} payment_id={payment['id']}"
                            )
                    else:
                        # Already completed via another path in the meantime.
                        await self.mark_resolved(order_id=order_id, source="already_processed")
                except Exception as e:
                    errors.append({"order_id": order_id, "error": str(e)})
                    if logger:
                        logger.error(f"Payment reconcile: recovery failed for {order_id}: {e}")
            else:
                # Not captured (yet). Age attempts out once past the window
                # so we stop re-checking them forever and the collection
                # doesn't accumulate permanently-unresolved noise.
                if attempt["created_at"] <= cutoff:
                    try:
                        await attempts_collection.update_one(
                            {"order_id": order_id},
                            {"$set": {"status": "abandoned", "resolved_at": started_at}},
                        )
                        abandoned += 1
                    except Exception as e:
                        errors.append({"order_id": order_id, "error": str(e)})
                else:
                    still_pending_attempts.append(attempt)

        # Throttled fallback for whatever the bulk pass couldn't resolve.
        fallback_summary: Dict[str, Any] = {}
        if still_pending_attempts:
            try:
                fallback_summary = await self._fallback_check(
                    run_id=run_id,
                    still_pending_attempts=still_pending_attempts,
                    cutoff=cutoff,
                    started_at=started_at,
                )
                recovered.extend(fallback_summary.get("recovered", []))
                errors.extend(fallback_summary.get("errors", []))
                abandoned += fallback_summary.get("abandoned", 0)
                still_pending = fallback_summary.get("still_pending", 0)
            except Exception as e:
                if logger:
                    logger.error(f"Payment reconcile: fallback stage crashed: {e}")
                errors.append({"order_id": None, "error": f"fallback stage failed: {e}"})
                still_pending = len(still_pending_attempts)
        else:
            still_pending = 0

        consistency = await self._check_consistency(
            payments_in_window=payments_in_window, by_razorpay_order_id=by_razorpay_order_id
        )
        if consistency.get("orphaned"):
            try:
                await SystemLogService().log(
                    component=SYSTEM_LOG_COMPONENT,
                    level="error",
                    message=(
                        f"Found {len(consistency['orphaned'])} captured Razorpay payment(s) "
                        f"with no matching order or payment_attempts record — possible gap "
                        f"between creating the Razorpay order and recording the attempt."
                    ),
                    context={"run_id": run_id, "orphaned": consistency["orphaned"]},
                )
            except Exception:
                pass

        finished_at = datetime.utcnow()
        summary = {
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
            "window_hours": window_hours,
            "checked": checked,
            "recovered": recovered,
            "recovered_count": len(recovered),
            "still_pending": still_pending,
            "abandoned": abandoned,
            "errors": errors,
            "bulk_fetch": {
                "pages_fetched": bulk_result.get("pages_fetched"),
                "raw_payments_seen": bulk_result.get("raw_payments_seen"),
                "payments_seen": len(payments_in_window),
                "hit_page_cap": bulk_result.get("hit_page_cap", False),
            },
            "fallback": fallback_summary,
            "consistency": consistency,
        }
        await self._log_and_save(summary)

        if logger and (recovered or errors or consistency.get("orphaned")):
            logger.info(
                f"Payment reconcile run {run_id}: checked={checked} "
                f"recovered={len(recovered)} still_pending={still_pending} "
                f"abandoned={abandoned} errors={len(errors)} "
                f"orphaned={len(consistency.get('orphaned') or [])}"
            )
        return summary
