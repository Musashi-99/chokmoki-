from __future__ import annotations

import json
import os
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Dict, List, Optional, Tuple

import yaml
from pydantic import BaseModel, Field, ValidationError

from src.fraud.models import FraudAction, RuleSeverity


class Condition(BaseModel):
    field: str
    op: str
    value: Any = None


class Rule(BaseModel):
    id: str
    name: str
    enabled: bool = True
    group: Optional[str] = None
    priority: int = 0
    severity: RuleSeverity = RuleSeverity.LOW
    confidence: int = Field(ge=0, le=100, default=50)
    risk: int = Field(ge=0, le=100, default=0)
    action: FraudAction = FraudAction.ALLOW
    when: List[Condition] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class RuleGroup(BaseModel):
    id: str
    enabled: bool = True
    defaults: Dict[str, Any] = Field(default_factory=dict)


class RuleSet(BaseModel):
    id: str = "default"
    version: str = "1"
    groups: List[RuleGroup] = Field(default_factory=list)
    rules: List[Rule] = Field(default_factory=list)


@dataclass(frozen=True)
class LoadedRuleSet:
    rule_set: RuleSet
    etag: str
    mtime_ns: int
    source_path: str


def _compute_etag(content: bytes) -> str:
    return sha256(content).hexdigest()


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def load_rules(path: str) -> LoadedRuleSet:
    raw_path = (path or "").strip()
    if not raw_path:
        raise ValueError("fraud rules path is empty")

    abs_path = raw_path
    if not os.path.isabs(abs_path):
        abs_path = os.path.abspath(abs_path)

    content = _read_bytes(abs_path)
    etag = _compute_etag(content)
    st = os.stat(abs_path)

    text = content.decode("utf-8")
    data: Dict[str, Any]
    if abs_path.lower().endswith((".yml", ".yaml")):
        data = yaml.safe_load(text) or {}
    elif abs_path.lower().endswith(".json"):
        data = json.loads(text)
    else:
        raise ValueError("Unsupported fraud rules file type (expected .yaml/.yml/.json)")

    try:
        parsed = RuleSet(**data)
    except ValidationError as e:
        raise ValueError(f"Invalid fraud rules schema: {e}") from e

    return LoadedRuleSet(
        rule_set=parsed,
        etag=etag,
        mtime_ns=getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)),
        source_path=abs_path,
    )


def try_reload_rules(
    *,
    current: Optional[LoadedRuleSet],
    path: str,
) -> Tuple[LoadedRuleSet, bool]:
    loaded = load_rules(path) if current is None else current
    try:
        st = os.stat(loaded.source_path)
        mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
        if mtime_ns == loaded.mtime_ns:
            return loaded, False
    except Exception:
        # If we can't stat, keep last good config.
        return loaded, False

    # File changed; reload from the configured path (may differ).
    reloaded = load_rules(path)
    return reloaded, True


def apply_group_defaults(rule_set: RuleSet) -> RuleSet:
    group_defaults: Dict[str, Dict[str, Any]] = {
        g.id: (g.defaults or {}) for g in rule_set.groups if g.enabled
    }
    enabled_groups = {g.id for g in rule_set.groups if g.enabled}

    merged_rules: List[Rule] = []
    for r in rule_set.rules:
        if not r.enabled:
            continue
        if r.group and r.group in enabled_groups:
            defaults = group_defaults.get(r.group, {})
            # Only let explicitly configured rule fields override group defaults.
            payload = {**defaults, **r.model_dump(exclude_unset=True)}
            merged_rules.append(Rule(**payload))
        else:
            merged_rules.append(r)

    return RuleSet(
        id=rule_set.id,
        version=rule_set.version,
        groups=[g for g in rule_set.groups if g.enabled],
        rules=merged_rules,
    )

