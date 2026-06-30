# F-13 — Webhook-Secret / Lost-Webhook Order Reconciliation

## Vulnerability
Paid Razorpay orders are held in Redis as `pending_order:<order_id>` (with the
inventory reservation) until the `payment.captured` **webhook** moves them to
MongoDB via `OrderService.complete_pending_order`.

If `RAZORPAY_WEBHOOK_SECRET` is unset or misconfigured,
`RazorpayService.verify_webhook_signature` returns `False` and the webhook
endpoint rejects the call (500/400). The same loss happens if Razorpay's webhook
is simply dropped (transient outage, deploy window, network). In every case the
captured payment is **never persisted** and the pending record is deleted when
its Redis TTL (`inventory_reservation_ttl_seconds`, default 3600s) expires.

**Impact:** the customer is charged but the order is lost — no fulfillment, no
record, no inventory commit. Availability/financial-integrity issue.

## Root cause
The only path from "payment captured" to "order persisted" was the inbound
webhook. There was no server-initiated fallback that reconciles against
Razorpay's authoritative payment state.

## Fix
A pull-based reconciliation job that does not trust any client input — it asks
Razorpay directly.

### 1. `RazorpayService.fetch_captured_payment(razorpay_order_id)`
Calls `client.order.payments(...)` and returns the first `captured`/`authorized`
payment (`id`, `status`, `amount_inr`) or `None`. Errors are logged and return
`None` (safe — the order just stays pending for the next run).

### 2. Persist the Razorpay order id into the pending record
`OrderService.initiate_order` now writes `razorpay_order_id` back into the
`pending_order:<id>` Redis record (via `redis.set(..., keepttl=True)`, preserving
the reservation TTL) right after the Razorpay order is created. This is the
mapping the reconciler needs to query Razorpay.

### 3. `OrderService.reconcile_pending_payments(limit=200)`
Scans `pending_order:*`, and for each **razorpay** order that carries a
`razorpay_order_id`, queries Razorpay; if a payment was captured/authorized it
calls `complete_pending_order(order_id, razorpay_order_id, payment_id)`. Returns
`{checked, recovered, still_pending, errors}`.

**Idempotency / safety:** `complete_pending_order` upserts on the unique
`order_id` index with `$setOnInsert`, and re-verifies the captured amount against
the order total before persisting. So the reconciler:
- cannot create duplicates (a concurrent webhook completing the same order just
  yields `status == "existing"`),
- cannot be tricked into persisting an under/over-paid order (amount re-checked),
- can be run repeatedly and safely.

### 4. Authenticated cron route `POST /cron/orders/reconcile`
Mirrors the existing `/cron/inventory/reconcile` auth: requires `X-Cron-Secret`
matching `CRON_SECRET` (constant-time compare). In production the secret is
mandatory; in development it is enforced only if configured. Schedule it (e.g.
every few minutes) with an external scheduler / Vercel cron, same as the
inventory reconcile job.

## Modified / added files
- `src/services/razorpay_service.py` — `fetch_captured_payment`.
- `src/services/order_service.py` — store `razorpay_order_id` in the pending
  record; add `reconcile_pending_payments`.
- `api/index.py` — `POST /cron/orders/reconcile` route.
- `__tests__/test_security_f13.py` — unit, integration, regression, and
  route-auth tests.

## Tests
`__tests__/test_security_f13.py` (10 tests): `fetch_captured_payment`
captured/none/error; reconcile recovers a captured order, skips uncaptured,
skips COD and pre-F-13 records without a `razorpay_order_id`, and counts errors
without aborting the batch; the cron route is registered, runs in dev without a
secret, and returns 401 when a secret is configured but the header is missing.

## Operational note
This is defense in depth. The **primary** fix remains setting
`RAZORPAY_WEBHOOK_SECRET` correctly in the platform secret store so webhooks
verify in real time; the reconciler is the safety net for the gap window and for
dropped webhooks.

## Migration & rollback
- **Migration:** none for existing data. New pending orders automatically carry
  `razorpay_order_id`. Pending orders created **before** this change lack that
  field and are reported as `still_pending` by the reconciler (they are still
  recoverable by the webhook, and any new order is fully covered). Add the cron
  schedule for `/cron/orders/reconcile` and ensure `CRON_SECRET` is set.
- **Rollback:** remove the cron route and `reconcile_pending_payments`; the extra
  `razorpay_order_id` field in the Redis record is harmless and self-expires with
  the record's TTL. No persistent state to revert.
