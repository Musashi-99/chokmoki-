from __future__ import annotations

from enum import StrEnum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class FraudAction(StrEnum):
    ALLOW = "allow"
    CHALLENGE = "challenge"
    MANUAL_REVIEW = "manual_review"
    REJECT = "reject"


class RuleSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FraudSignal(BaseModel):
    key: str
    value: Any
    weight: int = Field(ge=0, le=100, default=0)


class FraudMatch(BaseModel):
    rule_id: str
    rule_name: str
    rule_version: str
    group: Optional[str] = None
    priority: int = 0
    severity: RuleSeverity = RuleSeverity.LOW
    confidence: int = Field(ge=0, le=100, default=50)
    risk_score: int = Field(ge=0, le=100, default=0)
    recommendation: FraudAction = FraudAction.ALLOW
    signals: List[FraudSignal] = Field(default_factory=list)
    explanation: Dict[str, Any] = Field(default_factory=dict)


class FraudDecision(BaseModel):
    action: FraudAction
    risk_score: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    matched: List[FraudMatch] = Field(default_factory=list)
    rule_set_id: str
    rule_set_version: str
    engine_version: str = "1.0.0"

    model_config = {"extra": "forbid"}


class FraudContext(BaseModel):
    # Request context
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    endpoint: Optional[str] = None
    request_id: Optional[str] = None
    trace_id: Optional[str] = None
    correlation_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None

    # Business context
    event_type: Literal["order_create", "order_initiate", "admin_order_create"]
    currency: str = "INR"
    amount: float = 0.0
    email: Optional[str] = None
    phone: Optional[str] = None
    device_id: Optional[str] = None

    # Arbitrary enrichment
    attributes: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "ignore"}

