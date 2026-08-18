from bson import ObjectId
from src.services.product_filters import ids_mongo_filter, merge_mongo_filters, parse_ids_query


def test_ids_mongo_filter_matches_object_id_and_slug():
    oid = "507f1f77bcf86cd799439011"
    filt = ids_mongo_filter([oid, "wing-ring"])
    assert filt is not None
    assert "$or" in filt
    assert {"_id": {"$in": [ObjectId(oid)]}} in filt["$or"]
    assert {"slug": {"$in": [oid, "wing-ring"]}} in filt["$or"]


def test_ids_mongo_filter_empty():
    assert ids_mongo_filter(None) is None
    assert ids_mongo_filter([]) is None
    assert ids_mongo_filter(["  "]) == {"_id": {"$in": []}}


def test_merge_mongo_filters_ands_search_and_ids():
    merged = merge_mongo_filters(
        {"active": True},
        {"$or": [{"name": "x"}]},
        {"slug": {"$in": ["a"]}},
    )
    assert "$and" in merged
    assert {"active": True} in merged["$and"]


def test_parse_ids_query_keeps_large_wishlists():
    ids = [f"id{i}" for i in range(50)]
    parsed = parse_ids_query(",".join(ids))
    assert parsed == ids


def test_parse_ids_query_empty():
    assert parse_ids_query(None) is None
    assert parse_ids_query("") is None
    assert parse_ids_query("  ,  ") is None
