# -*- coding: utf-8 -*-
"""真实服务器验证：导出关系（version_id 为数组）"""
import urllib.request
import json

# 1. 登录拿 token
login = json.dumps({'username': 'admin', 'password': 'admin123'}).encode()
req = urllib.request.Request(
    'http://localhost:3010/api/v1/auth/login',
    data=login,
    headers={'Content-Type': 'application/json'}
)
token = json.loads(urllib.request.urlopen(req).read())['data']['token']
print(f"[LOGIN OK] token={token[:20]}...")

# 2. 导出关系（version_id 为数组，触发 fix）
body = json.dumps({
    'object_type': 'relationship',
    'scope': 'single',
    'filters': {'version_id': [1]},
    'options': {
        'include_hierarchy_path': False,
        'include_hierarchy_ids': False
    }
}).encode()
req2 = urllib.request.Request(
    'http://localhost:3010/api/v1/export',
    data=body,
    headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }
)
try:
    resp = json.loads(urllib.request.urlopen(req2).read())
    if resp.get('success'):
        print(f"[SUCCESS] download_url={resp.get('data', {}).get('download_url', 'N/A')}")
    else:
        print(f"[FAIL] {resp.get('message', resp)}")
except urllib.error.HTTPError as e:
    body_err = e.read()
    try:
        err_data = json.loads(body_err)
        print(f"[HTTP {e.code}] {err_data}")
    except Exception:
        print(f"[HTTP {e.code}] {body_err}")
