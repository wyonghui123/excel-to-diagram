# -*- coding: utf-8 -*-
"""
[MODULE] 诊断失败 action 的具体错误
"""
import http.client
import json
import os
import sys
import time
import sqlite3
import traceback
import urllib.parse

PROJECT_ROOT = r'd:/filework/excel-to-diagram'
HOST = 'localhost'
PORT = 3010


def _req(method, path, body=None, cookie=None):
    conn = http.client.HTTPConnection(HOST, PORT, timeout=20)
    body_bytes = json.dumps(body or {}, ensure_ascii=False).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Content-Length': str(len(body_bytes)),
    }
    if cookie:
        headers['Cookie'] = cookie
    conn.request(method, path, body=body_bytes, headers=headers)
    r = conn.getresponse()
    raw = r.read().decode('utf-8', errors='replace')
    try:
        data = json.loads(raw)
    except Exception:
        data = {'_raw': raw[:300]}
    conn.close()
    return r.status, data


def login():
    s, d = _req('POST', '/api/v2/action/user.authenticate', {
        'username': 'admin', 'password': 'admin123'
    })
    if s == 200 and d.get('success'):
        return True
    return False


def get_cookie():
    conn = http.client.HTTPConnection(HOST, PORT, timeout=10)
    body = json.dumps({'username': 'admin', 'password': 'admin123'}).encode('utf-8')
    conn.request('POST', '/api/v2/action/user.authenticate', body, headers={
        'Content-Type': 'application/json', 'Content-Length': str(len(body))
    })
    r = conn.getresponse()
    cookie = r.getheader('Set-Cookie').split(';')[0]
    r.read()
    conn.close()
    return cookie


def diag(label, status, data):
    print(f"[{status}] {label}")
    print(f"   body: {json.dumps(data, ensure_ascii=False)[:400]}")


def main():
    print("=" * 80)
    print("  诊断: 失败 action 的具体错误")
    print("=" * 80)

    cookie = get_cookie()
    print(f"  [OK] 登录, cookie={cookie[:30]}...")

    ts = int(time.time())

    # 1. role: update/delete
    print("\n=== role update/delete ===")
    s, d = _req('POST', '/api/v2/bo/role', {
        'code': f'DIAG_ROLE_{ts}', 'name': f'Diag Role {ts}',
        'description': 'diag', 'status': 'active',
    }, cookie)
    diag("create role", s, d)
    rid = (d.get('data') or {}).get('id') if s in (200, 201) else None

    if rid:
        s, d = _req('PUT', f'/api/v2/bo/role/{rid}', {'description': 'updated'}, cookie)
        diag(f"update role/{rid}", s, d)
        s, d = _req('DELETE', f'/api/v2/bo/role/{rid}', None, cookie)
        diag(f"delete role/{rid}", s, d)

    # 2. user_group update/delete
    print("\n=== user_group update/delete ===")
    s, d = _req('POST', '/api/v2/bo/user_group', {
        'code': f'DIAG_UG_{ts}', 'name': f'Diag UG {ts}', 'description': 'd',
    }, cookie)
    diag("create user_group", s, d)
    gid = (d.get('data') or {}).get('id') if s in (200, 201) else None

    if gid:
        s, d = _req('PUT', f'/api/v2/bo/user_group/{gid}', {'description': 'u'}, cookie)
        diag(f"update user_group/{gid}", s, d)
        s, d = _req('DELETE', f'/api/v2/bo/user_group/{gid}', None, cookie)
        diag(f"delete user_group/{gid}", s, d)

    # 3. product update/delete
    print("\n=== product update/delete ===")
    s, d = _req('POST', '/api/v2/bo/product', {
        'code': f'DIAG_PROD_{ts}', 'name': f'Diag Prod {ts}',
        'description': 'd', 'is_active': 1,
    }, cookie)
    diag("create product", s, d)
    pid = (d.get('data') or {}).get('id') if s in (200, 201) else None

    if pid:
        s, d = _req('PUT', f'/api/v2/bo/product/{pid}', {'description': 'u'}, cookie)
        diag(f"update product/{pid}", s, d)
        s, d = _req('DELETE', f'/api/v2/bo/product/{pid}', None, cookie)
        diag(f"delete product/{pid}", s, d)

    # 4. version create
    print("\n=== version create ===")
    if pid:
        s, d = _req('POST', '/api/v2/bo/version', {
            'code': f'DIAG_VER_{ts}', 'name': f'Diag Ver {ts}',
            'product_id': pid, 'is_current': 0,
        }, cookie)
        diag(f"create version (product_id={pid})", s, d)
    else:
        print("   [skip] no parent product")
        s, d = _req('POST', '/api/v2/bo/product', {
            'code': f'DIAG_VP_{ts}', 'name': f'Version Parent {ts}', 'is_active': 1,
        }, cookie)
        diag("create product for version", s, d)
        pid2 = (d.get('data') or {}).get('id') if s in (200, 201) else None
        if pid2:
            s, d = _req('POST', '/api/v2/bo/version', {
                'code': f'DIAG_VER2_{ts}', 'name': f'Diag Ver2 {ts}',
                'product_id': pid2, 'is_current': 0,
            }, cookie)
            diag(f"create version (product_id={pid2})", s, d)

    # 5. assign/unassign
    print("\n=== assign/unassign user<->user_group ===")
    s, d = _req('POST', '/api/v2/bo/user', {
        'username': f'diag_u_{ts}', 'display_name': 'd',
        'email': f'du_{ts}@x.com', 'password_hash': 'p',
    }, cookie)
    diag("create user", s, d)
    uid = (d.get('data') or {}).get('id') if s in (200, 201) else None
    s, d = _req('POST', '/api/v2/bo/user_group', {
        'code': f'diag_ug2_{ts}', 'name': f'Diag UG2 {ts}',
    }, cookie)
    diag("create user_group", s, d)
    gid2 = (d.get('data') or {}).get('id') if s in (200, 201) else None

    if uid and gid2:
        # Try both endpoints
        s, d = _req('POST', f'/api/v2/bo/user/{uid}/$associations/groups/assign', {
            'target_type': 'user_group', 'target_id': gid2,
        }, cookie)
        diag(f"assign v2 user/{uid} -> group/{gid2}", s, d)

        s, d = _req('POST', f'/api/v2/bo/user/{uid}/associations/groups', {
            'target_type': 'user_group', 'target_id': gid2,
        }, cookie)
        diag(f"associate v1 user/{uid} -> group/{gid2}", s, d)

        # list associations to see what works
        s, d = _req('GET', f'/api/v2/bo/user/{uid}', None, cookie)
        diag(f"read user/{uid} (look for groups field)", s, d)
        data_obj = (d.get('data') or {})
        if 'groups' in data_obj or 'user_group' in data_obj:
            print(f"   association key: {[k for k in data_obj.keys() if 'group' in k.lower()]}")

    # 6. export
    print("\n=== export ===")
    for endpoint, payload in [
        ('/api/v1/export', {
            'object_type': 'product', 'scope': 'single',
            'options': {'include_metadata_sheet': True},
        }),
        ('/api/v1/export', {
            'object_type': 'product', 'scope': 'list',
            'options': {'include_metadata_sheet': True},
        }),
        ('/api/v1/export', {
            'scope': 'template', 'selected_types': ['product'],
            'options': {'include_metadata_sheet': True},
        }),
        ('/api/v2/export', {
            'object_type': 'product', 'scope': 'single',
        }),
    ]:
        s, d = _req('POST', endpoint, payload, cookie)
        diag(f"POST {endpoint} payload={json.dumps(payload)[:80]}", s, d)

    return 0


if __name__ == '__main__':
    sys.exit(main())
