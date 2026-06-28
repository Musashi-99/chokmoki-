#!/usr/bin/env python3
"""Full E2E QA for Chokmoki admin API — all phases."""
import io
import os
import sys
from datetime import datetime, timezone

import requests

BASE = os.environ.get("QA_BASE_URL", "http://localhost:8001")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@chokmoki.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

TOKEN = None
FAILURES = []
PASSED = []
CLEANUP = []


def log(msg):
    print(msg, flush=True)


def unwrap_list(resp_json):
    if isinstance(resp_json, list):
        return resp_json
    if isinstance(resp_json, dict) and "data" in resp_json:
        d = resp_json["data"]
        return d if isinstance(d, list) else [d]
    return resp_json if isinstance(resp_json, list) else []


def unwrap_settings(resp_json):
    if isinstance(resp_json, dict) and "data" in resp_json:
        return resp_json["data"] or {}
    return resp_json or {}


def req(method, path, *, auth=False, json_body=None, files=None, data=None, expect=None):
    url = f"{BASE}{path}"
    headers = {}
    if auth:
        headers["Authorization"] = f"Bearer {TOKEN}"
    try:
        r = requests.request(method, url, headers=headers, json=json_body, files=files, data=data, timeout=60)
    except Exception as e:
        FAILURES.append(f"{method} {path}: {e}")
        log(f"FAIL {method} {path} -> {e}")
        return None
    body = None
    try:
        body = r.json()
    except Exception:
        body = r.text[:800]
    log(f"{method} {path} -> {r.status_code}")
    if expect is not None:
        ok = expect if isinstance(expect, (list, tuple)) else [expect]
        if r.status_code not in ok:
            FAILURES.append(f"{method} {path} expected {expect}, got {r.status_code}: {body}")
    return r


def ok(r, status=None):
    if r is None:
        return False
    if status is None:
        return True
    codes = status if isinstance(status, (list, tuple)) else [status]
    return r.status_code in codes


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
        log(f"  PASS: {name}")
    else:
        FAILURES.append(f"{name}: {detail}")
        log(f"  FAIL: {name} — {detail}")


def phase1():
    global TOKEN
    log("\n=== PHASE 1: AUTH ===")
    r = req("POST", "/api/admin/login", json_body={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    check("login", r and r.status_code == 200)
    TOKEN = r.json().get("token") if r else None
    check("token", bool(TOKEN))
    r = req("GET", "/api/admin/me", auth=True)
    check("me", r and r.status_code == 200)


def phase2():
    log("\n=== PHASE 2: PUBLIC API ===")
    r = req("GET", "/api/categories")
    cats = unwrap_list(r.json()) if r else []
    first_cat = cats[0]["slug"] if cats else "rings"
    r = req("GET", "/api/products")
    prods = unwrap_list(r.json()) if r else []
    first_prod = prods[0]["slug"] if prods else None
    first_prod_id = prods[0]["_id"] if prods else None
    check("categories", r and len(cats) > 0)
    check("products", len(prods) > 0)
    if first_cat:
        req("GET", f"/api/products?category={first_cat}")
    req("GET", "/api/products?is_best_seller=true")
    req("GET", "/api/products?is_curated=true")
    if first_prod:
        check("product slug", req("GET", f"/api/products/{first_prod}").status_code == 200)
    if first_cat:
        check("category slug", req("GET", f"/api/categories/{first_cat}").status_code == 200)
    for ep in ["/api/testimonials", "/api/hero", "/api/site-assets", "/api/faq",
               "/api/collection-slides", "/api/studio-settings", "/api/shop-page",
               "/api/policies", "/api/home-page", "/api/story-page", "/api/navigation",
               "/api/contact-page", "/api/history-page", "/api/product-page", "/api/journal", "/health"]:
        r = req("GET", ep)
        check(ep, r and r.status_code == 200)
    return first_cat, first_prod_id


def phase3(first_cat):
    log("\n=== PHASE 3: PRODUCTS CRUD ===")
    req("GET", "/api/admin/products", auth=True)
    payload = {
        "name": "QA Test Ring", "slug": "qa-test-ring", "price_inr": 4999,
        "category": first_cat, "collection": "QA Collection",
        "thumbnail": "https://cdn.amplifycheckout.com/chokmoki/products/test.jpg",
        "gallery": [], "material": "Sterling Silver", "craftsmanship": "Handcrafted",
        "shipping_details": "Ships in 5-7 days", "care_guide": "Wipe with soft cloth",
        "returns_policy": "7 day returns", "authenticity_details": "92.5 hallmarked",
        "description": "QA test product", "sizes": ["6", "7", "8"],
        "is_best_seller": False, "is_curated": False,
        "best_seller_order": 99, "curated_order": 99,
        "purity": "92.5% Sterling Silver", "stock_status": "in_stock", "active": True,
    }
    r = req("POST", "/api/admin/products", auth=True, json_body=payload)
    check("create", r and r.status_code in (200, 201))
    pid = r.json().get("_id") if r else None
    check("in admin list", "qa-test-ring" in [p["slug"] for p in unwrap_list(req("GET", "/api/admin/products", auth=True).json())])
    check("public read", req("GET", "/api/products/qa-test-ring").status_code == 200)
    req("PUT", f"/api/admin/products/{pid}", auth=True, json_body={"price_inr": 5999, "is_best_seller": True})
    check("price", req("GET", "/api/products/qa-test-ring").json().get("price_inr") == 5999)
    req("PUT", f"/api/admin/products/{pid}", auth=True, json_body={"is_curated": True, "curated_order": 1})
    curated = [p["slug"] for p in unwrap_list(req("GET", "/api/products?is_curated=true").json())]
    check("curated", "qa-test-ring" in curated)
    req("DELETE", f"/api/admin/products/{pid}", auth=True)
    r404 = req("GET", "/api/products/qa-test-ring")
    check("404 after delete", ok(r404, 404))


def phase4():
    log("\n=== PHASE 4: CATEGORIES ===")
    r = req("POST", "/api/admin/categories", auth=True, json_body={
        "name": "QA Category", "slug": "qa-category", "tagline": "Test",
        "description": "QA", "sort_order": 99, "active": True,
    })
    cid = r.json().get("_id") if r else None
    req("PUT", f"/api/admin/categories/{cid}", auth=True, json_body={"tagline": "Updated tagline"})
    check("public cat", req("GET", "/api/categories/qa-category").json().get("tagline") == "Updated tagline")
    req("DELETE", f"/api/admin/categories/{cid}", auth=True)
    check("cat 404", req("GET", "/api/categories/qa-category").status_code == 404)


def phase5():
    log("\n=== PHASE 5: TESTIMONIALS ===")
    r = req("POST", "/api/admin/testimonials", auth=True, json_body={
        "name": "QA User", "text": "Great product", "rating": 5, "active": True,
    })
    tid = r.json().get("_id") if r else None
    check("create testimonial", r and r.status_code in (200, 201))
    req("PUT", f"/api/admin/testimonials/{tid}", auth=True, json_body={"text": "Updated"})
    req("DELETE", f"/api/admin/testimonials/{tid}", auth=True)


def phase6():
    log("\n=== PHASE 6: HERO ===")
    payload = {
        "media_type": "image", "media_url": "https://cdn.amplifycheckout.com/chokmoki/hero/test.jpg",
        "media_type_desktop": "image", "media_url_desktop": "https://cdn.amplifycheckout.com/chokmoki/hero/test.jpg",
        "media_type_mobile": "image", "media_url_mobile": "https://cdn.amplifycheckout.com/chokmoki/hero/test.jpg",
        "media_urls_desktop": [], "media_urls_mobile": [], "slide_interval_seconds": 5,
        "alt_text": "QA Hero", "active": False,
    }
    r = req("POST", "/api/admin/hero", auth=True, json_body=payload)
    hid = r.json().get("_id") if r else None
    check("create hero", r and r.status_code in (200, 201))
    r2 = req("PUT", f"/api/admin/hero/{hid}", auth=True, json_body={"alt_text": "Updated Hero"})
    check("update hero", r2 and r2.status_code == 200)
    req("DELETE", f"/api/admin/hero/{hid}", auth=True)


def phase7():
    log("\n=== PHASE 7: COLLECTION SLIDES ===")
    r = req("POST", "/api/admin/collection-slides", auth=True, json_body={
        "heading": "QA Slide", "description": "Test",
        "image_url": "https://cdn.amplifycheckout.com/chokmoki/slides/test.jpg",
        "cta_label": "Shop", "cta_to": "/products", "active": True, "sort_order": 99,
    })
    sid = r.json().get("_id") if r else None
    check("create slide", r and r.status_code in (200, 201))
    req("PUT", f"/api/admin/collection-slides/{sid}", auth=True, json_body={"heading": "Updated"})
    req("DELETE", f"/api/admin/collection-slides/{sid}", auth=True)


def phase8():
    log("\n=== PHASE 8: FAQ ===")
    r = req("POST", "/api/admin/faq", auth=True, json_body={
        "question": "QA Question?", "answer": "QA Answer.", "scope": "homepage", "sort_order": 99, "active": True,
    })
    fid = r.json().get("_id") if r else None
    req("PUT", f"/api/admin/faq/{fid}", auth=True, json_body={"answer": "Updated."})
    qs = [i.get("question") for i in unwrap_list(req("GET", "/api/faq?scope=homepage").json())]
    check("faq public", "QA Question?" in qs)
    req("DELETE", f"/api/admin/faq/{fid}", auth=True)


def phase9():
    log("\n=== PHASE 9: SITE ASSETS ===")
    r = req("POST", "/api/admin/site-assets", auth=True, json_body={
        "key": "qa-test-asset", "asset_type": "image",
        "url": "https://cdn.amplifycheckout.com/chokmoki/assets/test.jpg",
        "alt_text": "QA Asset", "active": True,
    })
    aid = r.json().get("_id") if r else None
    req("PUT", f"/api/admin/site-assets/{aid}", auth=True, json_body={"alt_text": "Updated"})
    check("public asset", req("GET", "/api/site-assets/qa-test-asset").status_code == 200)
    req("DELETE", f"/api/admin/site-assets/{aid}", auth=True)


def settings_rt(path, field):
    r = req("GET", path, auth=True)
    orig = unwrap_settings(r.json() if r else {})
    val = orig.get(field) or ""
    new = val + " [QA]"
    req("PUT", path, auth=True, json_body={field: new})
    got = unwrap_settings(req("GET", path, auth=True).json()).get(field)
    check(f"{path} {field}", got == new, f"got {got!r}")
    req("PUT", path, auth=True, json_body={field: val})


def phase10():
    log("\n=== PHASE 10: SETTINGS ===")
    for f in ["heritage_eyebrow", "trust_eyebrow", "postcard_title", "newsletter_heading", "footer_tagline"]:
        settings_rt("/api/admin/home-page", f)
    for ep in ["/api/admin/shop-page", "/api/admin/studio-settings", "/api/admin/story-page",
               "/api/admin/navigation", "/api/admin/contact-page", "/api/admin/history-page", "/api/admin/product-page"]:
        r = req("GET", ep, auth=True)
        check(f"{ep} GET", r and r.status_code == 200)
    check("journal/meta GET", req("GET", "/api/admin/journal/meta", auth=True).status_code == 200)
    check("policies/meta GET", req("GET", "/api/admin/policies/meta", auth=True).status_code == 200)
    r = req("GET", "/api/admin/policies", auth=True)
    sections = r.json().get("sections", []) if r else []
    if sections:
        slug, content = sections[0].get("slug"), sections[0].get("body", "")
        req("PUT", f"/api/admin/policies/sections/{slug}", auth=True, json_body={"body": content + " [QA]"})
        req("PUT", f"/api/admin/policies/sections/{slug}", auth=True, json_body={"body": content})


def phase11():
    log("\n=== PHASE 11: BLOG ===")
    r = req("POST", "/api/admin/blog-posts", auth=True, json_body={
        "title": "QA Post", "slug": "qa-post", "content": "QA content",
        "excerpt": "QA", "published": False, "tags": ["qa"],
    })
    pid = r.json().get("_id") if r else None
    check("create post", r and r.status_code in (200, 201))
    slugs = [p.get("slug") for p in unwrap_list(req("GET", "/api/admin/journal", auth=True).json())]
    check("in admin journal", "qa-post" in slugs)
    req("PUT", f"/api/admin/blog-posts/{pid}", auth=True, json_body={"title": "Updated"})
    pub = [p.get("slug") for p in unwrap_list(req("GET", "/api/journal").json())]
    check("unpublished hidden", "qa-post" not in pub)
    req("DELETE", f"/api/admin/blog-posts/{pid}", auth=True)


def order_payload(pid):
    return {
        "shippingAddress": {
            "email": "qa@chokmoki.com", "full_name": "QA Tester", "phone": "9999999999",
            "address_line1": "123 QA Street", "address_line2": "",
            "city": "Kolkata", "state": "West Bengal", "postal_code": "700001", "country": "India",
        },
        "items": [{"productId": pid, "productName": "QA Product", "variant": {},
                   "quantity": 1, "price": 4999, "total": 4999, "size": "7"}],
        "pricing": {"subtotal": 4999, "discount": 0, "shipping": 0, "total": 4999},
        "userEmail": "qa@chokmoki.com",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "specialMessage": "QA test order", "paymentMethod": "cod",
    }


def phase12(pid):
    log("\n=== PHASE 12: ORDERS ===")
    r = req("POST", "/api/orders", json_body=order_payload(pid))
    check("create order", r and r.status_code in (200, 201), r.text if r else "")
    oid = r.json().get("order_id") if r else None
    CLEANUP.append(("order", oid))
    check("admin list", req("GET", "/api/admin/orders", auth=True).status_code == 200)
    orders = unwrap_list(req("GET", "/api/admin/orders?search=qa@chokmoki.com", auth=True).json())
    check("search", len(orders) > 0)
    check("detail", req("GET", f"/api/admin/orders/{oid}", auth=True).status_code == 200)
    for st in ["out_for_delivery", "accepted", "rejected", "delivered", "in_hub", "agent"]:
        req("PUT", f"/api/admin/orders/{oid}/status", auth=True, json_body={"status": {"type": st}})
    r = req("PUT", f"/api/admin/orders/{oid}/status", auth=True,
            json_body={"status": {"type": "invalid_status_xyz"}}, expect=[400, 422])
    check("invalid status", ok(r, [400, 422]))
    return oid


def phase13():
    log("\n=== PHASE 13: STATS ===")
    r = req("GET", "/api/admin/stats", auth=True)
    d = r.json() if r else {}
    check("totalOrders", isinstance(d.get("totalOrders"), (int, float)))
    check("totalRevenue", isinstance(d.get("totalRevenue"), (int, float)))


def phase14(pid):
    log("\n=== PHASE 14: MANUAL ORDER ===")
    p = order_payload(pid)
    p["userEmail"] = "qa-manual@chokmoki.com"
    p["shippingAddress"]["email"] = "qa-manual@chokmoki.com"
    r = req("POST", "/api/admin/orders", auth=True, json_body=p)
    check("admin order", r and r.status_code in (200, 201), r.text if r else "")
    if r and r.status_code in (200, 201):
        CLEANUP.append(("order", r.json().get("order_id")))


def phase15():
    log("\n=== PHASE 15: INBOX ===")
    req("POST", "/api/contact", json_body={"name": "QA", "email": "qa@chokmoki.com", "message": "Test"})
    req("POST", "/api/newsletter", json_body={"email": "qa-news@chokmoki.com"})
    inbox = req("GET", "/api/admin/inbox", auth=True).json()
    cid = next((c["_id"] for c in inbox.get("contacts", []) if c.get("email") == "qa@chokmoki.com"), None)
    nid = next((n["_id"] for n in inbox.get("newsletter", []) if n.get("email") == "qa-news@chokmoki.com"), None)
    if cid:
        req("PATCH", f"/api/admin/inbox/contacts/{cid}", auth=True, json_body={"read": True})
        req("DELETE", f"/api/admin/inbox/contacts/{cid}", auth=True)
    if nid:
        req("PATCH", f"/api/admin/inbox/newsletter/{nid}", auth=True, json_body={"read": True})
        req("DELETE", f"/api/admin/inbox/newsletter/{nid}", auth=True)


def phase16():
    log("\n=== PHASE 16: UPLOAD ===")
    jpeg = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x7F, 0xFF, 0xD9,
    ])
    r = req("POST", "/api/admin/upload", auth=True,
            files=[("files", ("t.jpg", io.BytesIO(jpeg), "image/jpeg"))], data={"folder": "products"})
    check("upload", ok(r, 200) and bool(r.json().get("urls")))
    r = req("POST", "/api/admin/upload", auth=True,
            files=[("files", ("t.exe", io.BytesIO(b"MZ\x00"), "application/octet-stream"))],
            data={"folder": "products"}, expect=400)
    check("reject exe", ok(r, 400))
    r = req("POST", "/api/admin/upload", auth=True, data={"folder": "products"}, expect=422)
    check("no file", ok(r, 422))


def phase17(pid):
    log("\n=== PHASE 17: CACHE ===")
    prods = unwrap_list(req("GET", "/api/products").json())
    t = next((p for p in prods if p["_id"] == pid), prods[0] if prods else None)
    if not t:
        return
    orig, new = t["name"], t["name"] + " CACHE_QA"
    req("PUT", f"/api/admin/products/{t['_id']}", auth=True, json_body={"name": new})
    found = next((p for p in unwrap_list(req("GET", "/api/products").json()) if p["_id"] == t["_id"]), None)
    check("cache bust", found and found["name"] == new)
    req("PUT", f"/api/admin/products/{t['_id']}", auth=True, json_body={"name": orig})


def phase18():
    global TOKEN
    log("\n=== PHASE 18: AUTH ===")
    saved = TOKEN
    TOKEN = None
    r = req("GET", "/api/admin/products", expect=401)
    check("no token", ok(r, 401) and "detail" in r.json())
    TOKEN = "garbage"
    r = req("GET", "/api/admin/products", auth=True, expect=[401, 403])
    check("bad token", ok(r, [401, 403]))
    TOKEN = saved


def phase19():
    log("\n=== PHASE 19: ERRORS ===")
    r = req("GET", "/api/products/nonexistent-slug-xyz", expect=404)
    check("404 json", ok(r, 404) and "detail" in r.json())
    r = req("GET", "/api/admin/products/000000000000000000000000", auth=True, expect=404)
    check("admin product 404", ok(r, 404))
    r = req("POST", "/api/admin/products", auth=True, json_body={"name": "X"}, expect=[400, 422])
    r = req("POST", "/api/admin/products", auth=True, json_body={
        "name": "Dup", "slug": "endless-love-ring", "price_inr": 100, "category": "rings",
        "collection": "x", "thumbnail": "https://x.com/a.jpg", "material": "x",
        "craftsmanship": "x", "description": "x", "active": True,
    }, expect=[400, 409])
    check("dup slug", ok(r, [400, 409]))
    r = req("DELETE", "/api/admin/products/000000000000000000000000", auth=True, expect=404)
    r = req("POST", "/api/orders", json_body={"items": []}, expect=[400, 422])


def main():
    log(f"QA against {BASE}")
    phase1()
    if not TOKEN:
        sys.exit(1)
    first_cat, pid = phase2()
    phase3(first_cat)
    phase4()
    phase5()
    phase6()
    phase7()
    phase8()
    phase9()
    phase10()
    phase11()
    phase12(pid)
    phase13()
    phase14(pid)
    phase15()
    phase16()
    phase17(pid)
    phase18()
    phase19()
    log(f"\n{'='*60}\nPASSED: {len(PASSED)}  FAILED: {len(FAILURES)}")
    for f in FAILURES:
        log(f"  FAIL: {f}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
