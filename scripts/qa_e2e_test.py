#!/usr/bin/env python3
"""Comprehensive E2E QA test for Chokmoki admin API."""
import json
import sys
import io
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = os.environ.get("QA_BASE_URL", "http://localhost:8001")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@chokmoki.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

TOKEN = None
FAILURES = []
PASSED = []
LOG = []


def log(msg):
    print(msg)
    LOG.append(msg)


def req(method, path, *, auth=False, json_body=None, files=None, data=None, expect=None):
    url = f"{BASE}{path}"
    headers = {}
    if auth and TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    try:
        r = requests.request(method, url, headers=headers, json=json_body, files=files, data=data, timeout=30)
    except Exception as e:
        FAILURES.append(f"{method} {path} -> connection error: {e}")
        log(f"FAIL {method} {path} -> {e}")
        return None
    body = None
    try:
        body = r.json()
    except Exception:
        body = r.text[:500]
    log(f"{method} {path} -> {r.status_code}")
    if expect is not None and r.status_code not in (expect if isinstance(expect, (list, tuple)) else [expect]):
        FAILURES.append(f"{method} {path} expected {expect}, got {r.status_code}: {body}")
        log(f"  FAIL expected {expect}, body={body}")
    return r


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
        log(f"  PASS: {name}")
    else:
        FAILURES.append(f"{name}: {detail}")
        log(f"  FAIL: {name} — {detail}")


def phase1():
    log("\n=== PHASE 1: AUTH ===")
    r = req("POST", "/api/admin/login", json_body={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    check("login 200", r and r.status_code == 200, r.text if r else "no response")
    global TOKEN
    if r and r.status_code == 200:
        TOKEN = r.json().get("token") or r.json().get("access_token")
        check("token received", bool(TOKEN), str(r.json()))
    r = req("GET", "/api/admin/me", auth=True)
    check("me 200", r and r.status_code == 200, r.text if r else "")


def phase2():
    log("\n=== PHASE 2: PUBLIC API ===")
    r = req("GET", "/api/categories")
    check("categories 200", r and r.status_code == 200)
    cats = r.json() if r and r.status_code == 200 else []
    first_cat = cats[0]["slug"] if cats else None

    r = req("GET", "/api/products")
    check("products 200", r and r.status_code == 200)
    prods = r.json() if r and r.status_code == 200 else []
    first_prod = prods[0]["slug"] if prods else None

    if first_cat:
        req("GET", f"/api/products?category={first_cat}")
    req("GET", "/api/products?is_best_seller=true")
    req("GET", "/api/products?is_curated=true")
    if first_prod:
        r = req("GET", f"/api/products/{first_prod}")
        check(f"product/{first_prod} 200", r and r.status_code == 200)
    if first_cat:
        r = req("GET", f"/api/categories/{first_cat}")
        check(f"categories/{first_cat} 200", r and r.status_code == 200)

    for ep in [
        "/api/testimonials", "/api/hero", "/api/site-assets", "/api/faq",
        "/api/collection-slides", "/api/studio-settings", "/api/shop-page",
        "/api/policies", "/api/home-page", "/api/story-page", "/api/navigation",
        "/api/contact-page", "/api/history-page", "/api/product-page", "/api/journal",
        "/health",
    ]:
        r = req("GET", ep)
        check(f"{ep} 200", r and r.status_code == 200, r.text[:200] if r else "")

    return first_cat, first_prod, cats, prods


def main():
    log(f"QA E2E against {BASE}")
    phase1()
    if not TOKEN:
        log("ABORT: no token")
        print_summary()
        sys.exit(1)
    first_cat, first_prod, cats, prods = phase2()
    if not cats:
        log("WARNING: no categories — may need seed")
    if not prods:
        log("WARNING: no products — may need seed")
    print_summary()


def print_summary():
    log(f"\n=== SUMMARY: {len(PASSED)} passed, {len(FAILURES)} failed ===")
    for f in FAILURES:
        log(f"  FAIL: {f}")


if __name__ == "__main__":
    main()
