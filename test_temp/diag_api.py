#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断 product/version API 响应格式"""
import urllib.request
import urllib.error
import json
import http.cookiejar

BASE = "http://localhost:3010"
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

# 1. dev-login
resp = opener.open(f"{BASE}/api/v1/auth/dev-login?username=admin")
print(f"[1] dev-login status: {resp.status}")

# 2. product list
resp = opener.open(f"{BASE}/api/v2/bo/product?page_size=3")
body = resp.read().decode("utf-8-sig")  # 兼容 BOM
data = json.loads(body)
print(f"\n[2] product list response keys: {list(data.keys()) if isinstance(data, dict) else 'NOT DICT'}")
if isinstance(data, dict):
    for k, v in data.items():
        if isinstance(v, list):
            print(f"    {k}: list of {len(v)} items, first: {json.dumps(v[0], ensure_ascii=False)[:200]}")
        elif isinstance(v, dict):
            print(f"    {k}: dict with keys {list(v.keys())[:10]}")
        else:
            print(f"    {k}: {v}")

# 3. version list
resp = opener.open(f"{BASE}/api/v2/bo/version?page_size=3")
body = resp.read().decode("utf-8-sig")
data = json.loads(body)
print(f"\n[3] version list response keys: {list(data.keys()) if isinstance(data, dict) else 'NOT DICT'}")
if isinstance(data, dict):
    for k, v in data.items():
        if isinstance(v, list):
            print(f"    {k}: list of {len(v)} items, first: {json.dumps(v[0], ensure_ascii=False)[:200]}")
        elif isinstance(v, dict):
            print(f"    {k}: dict with keys {list(v.keys())[:10]}")
        else:
            print(f"    {k}: {v}")
