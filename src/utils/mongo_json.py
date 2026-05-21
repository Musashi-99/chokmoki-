"""JSON helpers for MongoDB documents (ObjectId, datetime)."""
import json
from datetime import datetime
from typing import Any

from bson import ObjectId


class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def mongo_json_dumps(obj: Any) -> str:
    return json.dumps(obj, cls=MongoJSONEncoder)
