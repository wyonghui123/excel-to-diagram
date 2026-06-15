# -*-usr/bin/env python
# -*- coding: utf-8 -*-
"""Check ui-config API response for version/product/role"""
import json
import os
import sys
import urllib.request
import urllib.parse
from http.cookiejar import CookieJar

BASE = "http://127.0.0.1:3010"


def login():
    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    req = urllib.request.Request(f"{BASE}/api/v1/auth/dev-login?username=admin", method="GET")
    with opener.open(req, timeout=10) as resp:
        r = json.loads(resp.read().decode())
    return opener


def call(opener, path):
    req = urllib.request.Request(f"{BASE}{path}", method="GET")
    with opener.open(req, timeout=15) as resp:
        return resp.status, json.loads(resp.read().decode())


def main():
    opener = login()
    for ot in ['version', 'product', 'role']:
        status, body = call(opener, f"/api/v2/meta/{ot}/ui-config")
        if not body.get('success'):
            print(f"=== {ot} === FAILED: {body}")
            continue
        data = body.get('data', {})
        # 找 audit_aspect
        aspects = data.get('aspects', [])
        has_audit = 'audit_aspect' in aspects
        # 找 history tab/facet
        tabs = data.get('tabs', [])
        history_tab = [t for t in tabs if t.get('type') == 'history']
        facets = data.get('facets', [])
        history_facet = [f for f in facets if f.get('type') == 'history']
        print(f"=== {ot} ===")
        print(f"  has audit_aspect: {has_audit}")
        print(f"  history tabs: {len(history_tab)}")
        for t in history_tab:
            print(f"    {t}")
        print(f"  history facets: {len(history_facet)}")
        for f in history_facet:
            print(f"    {f}")
        # 找 aspects
        print(f"  aspects: {aspects[:5]}{'...' if len(aspects) > 5 else ''}")
        print()


if __name__ == "__main__":
    main()
