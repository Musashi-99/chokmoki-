from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.fraud.models import FraudAction, FraudDecision, FraudMatch, FraudSignal, RuleSeverity
from src.fraud.rules import Condition, Rule, RuleSet, apply_group_defaults


def _get_field(ctx: Dict[str, Any], path: str) -> Any:
    cur: Any = ctx
    for part in (path or "").split("."):
        if part == "":
            return None
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _as_str(v: Any) -> str:
    return "" if v is None else str(v)


def _match_condition(value: Any, cond: Condition) -> Tuple[bool, Dict[str, Any]]:
    op = (cond.op or "").strip().lower()
    expected = cond.value

    if op == "exists":
        return (value is not None), {"op": op}
    if op == "equals":
        return (value == expected), {"op": op, "expected": expected}
    if op == "in":
        try:
            return (value in expected), {"op": op, "expected": expected}
        except Exception:
            return False, {"op": op, "expected": expected, "error": "invalid_in"}
    if op == "contains":
        return (_as_str(expected) in _as_str(value)), {"op": op, "expected": expected}
    if op == "regex":
        try:
            pat = re.compile(str(expected), re.IGNORECASE)
            return (pat.search(_as_str(value)) is not None), {"op": op, "expected": expected}
        except Exception:
            return False, {"op": op, "expected": expected, "error": "invalid_regex"}
    if op == "cidr":
        try:
            if value is None:
                return False, {"op": op, "expected": expected}
            ip = ipaddress.ip_address(_as_str(value))
            net = ipaddress.ip_network(str(expected), strict=False)
            return (ip in net), {"op": op, "expected": expected}
        except Exception:
            return False, {"op": op, "expected": expected, "error": "invalid_cidr"}
    if op == "gt":
        try:
            return (float(value) > float(expected)), {"op": op, "expected": expected}
        except Exception:
            return False, {"op": op, "expected": expected, "error": "invalid_number"}
    if op == "gte":
        try:
            return (float(value) >= float(expected)), {"op": op, "expected": expected}
        except Exception:
            return False, {"op": op, "expected": expected, "error": "invalid_number"}
    if op == "lt":
        try:
            return (float(value) < float(expected)), {"op": op, "expected": expected}
        except Exception:
            return False, {"op": op, "expected": expected, "error": "invalid_number"}
    if op == "lte":
        try:
            return (float(value) <= float(expected)), {"op": op, "expected": expected}
        except Exception:
            return False, {"op": op, "expected": expected, "error": "invalid_number"}

    return False, {"op": op, "expected": expected, "error": "unknown_op"}


def _severity_weight(sev: RuleSeverity) -> int:
    return {
        RuleSeverity.LOW: 15,
        RuleSeverity.MEDIUM: 35,
        RuleSeverity.HIGH: 60,
        RuleSeverity.CRITICAL: 85,
    }.get(sev, 15)


def _action_rank(action: FraudAction) -> int:
    return {
        FraudAction.ALLOW: 0,
        FraudAction.CHALLENGE: 1,
        FraudAction.MANUAL_REVIEW: 2,
        FraudAction.REJECT: 3,
    }.get(action, 0)


@dataclass(frozen=True)
class EngineResult:
    decision: FraudDecision
    evaluated_rules: int


class FraudEngine:
    def __init__(self, rule_set: RuleSet):
        self._rule_set = apply_group_defaults(rule_set)

    def evaluate(self, *, ctx: Dict[str, Any]) -> EngineResult:
        matches: List[FraudMatch] = []
        evaluated = 0

        for rule in sorted(self._rule_set.rules, key=lambda r: (-r.priority, r.id)):
            evaluated += 1
            ok, explanation, signals = self._rule_matches(rule, ctx)
            if not ok:
                continue

            risk = int(max(0, min(100, rule.risk)))
            conf = int(max(0, min(100, rule.confidence)))
            rec = rule.action
            matches.append(
                FraudMatch(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    rule_version=self._rule_set.version,
                    group=rule.group,
                    priority=rule.priority,
                    severity=rule.severity,
                    confidence=conf,
                    risk_score=risk,
                    recommendation=rec,
                    signals=signals,
                    explanation=explanation,
                )
            )

        if not matches:
            decision = FraudDecision(
                action=FraudAction.ALLOW,
                risk_score=0,
                confidence=0,
                matched=[],
                rule_set_id=self._rule_set.id,
                rule_set_version=self._rule_set.version,
            )
            return EngineResult(decision=decision, evaluated_rules=evaluated)

        matches_sorted = sorted(
            matches,
            key=lambda m: (
                -m.priority,
                -_action_rank(m.recommendation),
                -m.risk_score,
                -m.confidence,
                m.rule_id,
            ),
        )

        total_risk = 0
        total_weight = 0
        total_conf = 0
        conf_weight = 0

        for m in matches_sorted[:10]:
            w = _severity_weight(m.severity)
            total_risk += m.risk_score * w
            total_weight += w
            total_conf += m.confidence * w
            conf_weight += w

        risk_score = int(round(total_risk / max(1, total_weight)))
        confidence = int(round(total_conf / max(1, conf_weight)))
        action = matches_sorted[0].recommendation

        decision = FraudDecision(
            action=action,
            risk_score=max(0, min(100, risk_score)),
            confidence=max(0, min(100, confidence)),
            matched=matches_sorted,
            rule_set_id=self._rule_set.id,
            rule_set_version=self._rule_set.version,
        )
        return EngineResult(decision=decision, evaluated_rules=evaluated)

    def _rule_matches(
        self, rule: Rule, ctx: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any], List[FraudSignal]]:
        if not rule.when:
            return False, {"error": "empty_when"}, []

        explanation: Dict[str, Any] = {"when": []}
        signals: List[FraudSignal] = []

        for cond in rule.when:
            value = _get_field(ctx, cond.field)
            ok, meta = _match_condition(value, cond)
            explanation["when"].append(
                {
                    "field": cond.field,
                    "value": value,
                    "result": ok,
                    **meta,
                }
            )
            if not ok:
                return False, explanation, []

        # Default signals: surface core inputs that triggered evaluation.
        if rule.group:
            signals.append(FraudSignal(key="group", value=rule.group, weight=0))
        signals.append(FraudSignal(key="rule_id", value=rule.id, weight=0))
        return True, explanation, signals

