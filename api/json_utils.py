"""Shared JSON serialization helpers used across api/routes/*.

Mongo documents contain ObjectId/datetime values the stdlib json module
can't serialize directly — every route handler routes its response through
one of these instead of calling json.dumps directly.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from bson import ObjectId


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            # Mongo stores naive UTC; suffix Z so clients bucket IST correctly.
            s = obj.isoformat()
            return s if obj.tzinfo is not None else f"{s}Z"
        return super().default(obj)


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, cls=JSONEncoder)


def _json_response_content(obj: Any) -> Any:
    return json.loads(_json_dumps(obj))
