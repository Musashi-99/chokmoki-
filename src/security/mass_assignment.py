"""Admin update payload validation and protected-field stripping."""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Type

from pydantic import BaseModel, ConfigDict, ValidationError

PROTECTED_UPDATE_FIELDS: FrozenSet[str] = frozenset(
    {
        "_id",
        "id",
        "created_at",
        "updated_at",
        "settings_key",
        "meta_key",
    }
)


class StrictUpdateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def build_update_payload(
    model_cls: Type[BaseModel],
    payload: Dict[str, Any],
    *,
    exclude_unset: bool = True,
) -> Dict[str, Any]:
    """Validate and return only fields declared on the update model."""
    cleaned = {
        key: value
        for key, value in payload.items()
        if key not in PROTECTED_UPDATE_FIELDS
    }
    try:
        model = model_cls.model_validate(cleaned)
    except ValidationError as exc:
        raise ValueError("Invalid request parameters") from exc

    data = model.model_dump(exclude_unset=exclude_unset, exclude_none=True)
    for key in PROTECTED_UPDATE_FIELDS:
        data.pop(key, None)
    return data


def require_update_fields(data: Dict[str, Any]) -> None:
    if not data:
        raise ValueError("No valid fields to update")
