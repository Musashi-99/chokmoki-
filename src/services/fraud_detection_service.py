from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException

from src.config import settings
from src.database.connection import db
from src.fraud.enrichment import FraudEnrichmentService
from src.fraud.engine import FraudEngine
from src.fraud.models import FraudAction, FraudContext, FraudDecision
from src.fraud.rules import LoadedRuleSet, try_reload_rules
from src.services.fraud_review_service import FraudReviewService
from src.plugins.metrics import FRAUD_EVAL_LATENCY_MS, FRAUD_EVAL_TOTAL
from src.plugins.structured_log import security_log


@dataclass(frozen=True)
class FraudEvaluateInput:
    context: FraudContext
    payload: Dict[str, Any]


class FraudDetectionService:
    DECISIONS_COLLECTION = "fraud_decisions"

    def __init__(self) -> None:
        self._loaded: Optional[LoadedRuleSet] = None

    async def evaluate_or_raise(
        self,
        *,
        ctx: FraudContext,
        payload: Dict[str, Any],
    ) -> FraudDecision:
        decision = await self.evaluate(ctx=ctx, payload=payload)
        if decision.action == FraudAction.REJECT:
            raise HTTPException(status_code=403, detail="Order rejected")
        return decision

    async def evaluate(
        self,
        *,
        ctx: FraudContext,
        payload: Dict[str, Any],
    ) -> FraudDecision:
        if not settings.fraud_enabled:
            return FraudDecision(
                action=FraudAction.ALLOW,
                risk_score=0,
                confidence=0,
                matched=[],
                rule_set_id="disabled",
                rule_set_version="0",
            )

        start = time.perf_counter()
        reloaded = False

        try:
            self._loaded, reloaded = try_reload_rules(
                current=self._loaded, path=settings.fraud_rules_file
            )
            engine = FraudEngine(self._loaded.rule_set)
            enrichment = await FraudEnrichmentService().enrich(ctx=ctx, payload=payload)
            ctx_dict = self._build_ctx_dict(ctx=ctx, payload=payload, enrichment=enrichment)
            with FRAUD_EVAL_LATENCY_MS.time():
                result = engine.evaluate(ctx=ctx_dict)
            decision = result.decision
        except Exception as e:
            if settings.fraud_fail_closed:
                security_log(
                    severity="ERROR",
                    module="fraud",
                    event="fraud_engine_error_fail_closed",
                    request_id=ctx.request_id,
                    trace_id=ctx.trace_id,
                    correlation_id=ctx.correlation_id,
                    session_id=ctx.session_id,
                    user_id=ctx.user_id,
                    ip=ctx.ip,
                    endpoint=ctx.endpoint,
                    risk_score=100,
                    error=str(e),
                )
                return FraudDecision(
                    action=FraudAction.REJECT,
                    risk_score=100,
                    confidence=0,
                    matched=[],
                    rule_set_id="error",
                    rule_set_version="0",
                )

            security_log(
                severity="ERROR",
                module="fraud",
                event="fraud_engine_error_fail_open",
                request_id=ctx.request_id,
                trace_id=ctx.trace_id,
                correlation_id=ctx.correlation_id,
                session_id=ctx.session_id,
                user_id=ctx.user_id,
                ip=ctx.ip,
                endpoint=ctx.endpoint,
                error=str(e),
                risk_score=0,
            )
            return FraudDecision(
                action=FraudAction.ALLOW,
                risk_score=0,
                confidence=0,
                matched=[],
                rule_set_id="error",
                rule_set_version="0",
            )
        finally:
            latency_ms = int((time.perf_counter() - start) * 1000)
            security_log(
                severity="INFO",
                module="fraud",
                event="fraud_decision",
                request_id=ctx.request_id,
                trace_id=ctx.trace_id,
                correlation_id=ctx.correlation_id,
                session_id=ctx.session_id,
                user_id=ctx.user_id,
                ip=ctx.ip,
                endpoint=ctx.endpoint,
                latency_ms=latency_ms,
                risk_score=None,
                reloaded_rules=reloaded,
            )

        FRAUD_EVAL_TOTAL.labels(
            action=decision.action,
            rule_set_id=decision.rule_set_id,
            rule_set_version=decision.rule_set_version,
        ).inc()

        if settings.fraud_audit_enabled:
            try:
                await self._audit_decision(ctx=ctx, decision=decision)
            except Exception:
                # Audit must never block the request path.
                pass

        if decision.action == FraudAction.MANUAL_REVIEW:
            try:
                await FraudReviewService().enqueue(ctx=ctx, decision=decision, payload=payload)
            except Exception:
                pass

        security_log(
            severity="INFO",
            module="fraud",
            event="fraud_decision_final",
            request_id=ctx.request_id,
            trace_id=ctx.trace_id,
            correlation_id=ctx.correlation_id,
            session_id=ctx.session_id,
            user_id=ctx.user_id,
            ip=ctx.ip,
            endpoint=ctx.endpoint,
            risk_score=decision.risk_score,
            action=decision.action,
            confidence=decision.confidence,
            matched_rules=[m.rule_id for m in decision.matched[:10]],
            rule_set_id=decision.rule_set_id,
            rule_set_version=decision.rule_set_version,
        )

        return decision

    def _build_ctx_dict(
        self,
        *,
        ctx: FraudContext,
        payload: Dict[str, Any],
        enrichment: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        shipping = payload.get("shippingAddress") or payload.get("shipping_address") or {}
        enrichment = enrichment or {}
        return {
            "request": {
                "ip": ctx.ip,
                "user_agent": ctx.user_agent,
                "endpoint": ctx.endpoint,
            },
            "event": {
                "type": ctx.event_type,
                "amount": ctx.amount,
                "currency": ctx.currency,
            },
            "user": {
                "email": ctx.email or payload.get("userEmail") or payload.get("user_email"),
                "phone": ctx.phone or shipping.get("phone"),
            },
            "shipping": {
                "country": shipping.get("country"),
                "postal_code": shipping.get("postal_code") or shipping.get("postalCode"),
                "city": shipping.get("city"),
                "state": shipping.get("state"),
            },
            "velocity": enrichment.get("velocity", {}),
            "attributes": {
                **(ctx.attributes or {}),
                **(enrichment.get("attributes") or {}),
            },
        }

    async def _audit_decision(self, *, ctx: FraudContext, decision: FraudDecision) -> None:
        database = await db.get_database()
        coll = database[self.DECISIONS_COLLECTION]
        doc = {
            "rule_set_id": decision.rule_set_id,
            "rule_set_version": decision.rule_set_version,
            "engine_version": decision.engine_version,
            "action": decision.action,
            "risk_score": decision.risk_score,
            "confidence": decision.confidence,
            "matched": [m.model_dump() for m in decision.matched[:50]],
            "request": {
                "request_id": ctx.request_id,
                "trace_id": ctx.trace_id,
                "correlation_id": ctx.correlation_id,
                "session_id": ctx.session_id,
                "user_id": ctx.user_id,
                "ip": ctx.ip,
                "endpoint": ctx.endpoint,
                "user_agent": ctx.user_agent,
            },
            "event": {
                "type": ctx.event_type,
                "amount": ctx.amount,
                "currency": ctx.currency,
                "email": ctx.email,
                "phone": ctx.phone,
            },
            "created_at": time.time(),
        }
        await coll.insert_one(doc)

