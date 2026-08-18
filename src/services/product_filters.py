from typing import List, Optional, Dict, Any
from bson import ObjectId

MAX_PRODUCT_IDS = 200


def parse_ids_query(ids: Optional[str]) -> Optional[List[str]]:
    if not ids:
        return None
    parsed = [part.strip() for part in ids.split(",") if part.strip()][:MAX_PRODUCT_IDS]
    return parsed or None


def ids_mongo_filter(ids: Optional[List[str]]) -> Optional[Dict[str, Any]]:
    if not ids:
        return None
    object_ids: List[ObjectId] = []
    tokens: List[str] = []
    for raw in ids:
        token = str(raw).strip()
        if not token:
            continue
        tokens.append(token)
        if ObjectId.is_valid(token):
            object_ids.append(ObjectId(token))
    if not tokens:
        return {"_id": {"$in": []}}
    clauses: List[Dict[str, Any]] = [{"slug": {"$in": tokens}}]
    if object_ids:
        clauses.insert(0, {"_id": {"$in": object_ids}})
    return clauses[0] if len(clauses) == 1 else {"$or": clauses}


def merge_mongo_filters(*parts: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    present = [part for part in parts if part]
    if not present:
        return {}
    if len(present) == 1:
        return present[0]
    return {"$and": present}
