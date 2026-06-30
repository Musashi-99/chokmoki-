"""Defense-in-depth validation for values used in MongoDB filters."""

from __future__ import annotations

from typing import Any, Optional


def reject_mongo_operator_value(value: Any, field_name: str) -> None:
    if isinstance(value, (dict, list)):
        raise ValueError(
            f"{field_name} must be a scalar value, not {type(value).__name__}"
        )
    if isinstance(value, str) and value.startswith("$"):
        raise ValueError(f"{field_name} contains invalid characters")


def coerce_safe_string(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    reject_mongo_operator_value(value, field_name)
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value.strip()


def coerce_safe_int(
    value: Any,
    field_name: str,
    *,
    default: int,
) -> int:
    if value is None:
        return default
    reject_mongo_operator_value(value, field_name)
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    raise ValueError(f"{field_name} must be an integer")
