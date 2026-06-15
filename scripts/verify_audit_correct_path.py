#!/usr/bin/env python3
"""
用正确路径验证 audit log
"""
import urllib.request
import http.cookiejar

BASE = 'http://localhost:3010'


def get_session():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    return opener


def call(opener, method, path, data=None):
    url = BASE + path
    if data is not None:
        import json
        body = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=body, method=method,
                                      headers={'Content-Type': 'application/json'})
    else:
        req = urllib.request.Request(url, method=method)
    try:
        r = opener.open(req, timeout=10)
        return r.status, r.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='replace')


def main():
    s = get_session()
    # 1. login
    status, body = call(s, 'GET', '/api/v1/auth/dev-login?username=admin')
    print('login:', status)

    # 2. 触发 audit: 创建一个 enum_type
    import time
    ts = str(int(time.time()))
    test_code = 'AUDIT_TEST_' + ts
    status, body = call(s, 'POST', '/api/v2/bo/enum_type', {
        'code': test_code,
        'name': 'AUDIT_TEST_' + ts,
        'category': 'business',
        'mutability': 'fullEditable'
    })
    print('create enum_type:', status)

    # 3. 测多种 audit API 路径
    print('\n=== audit API paths ===')
    paths = [
        '/api/v2/audit/logs?page_size=10',
        '/api/v2/audit/logs?level=ERROR&page_size=10',
        '/api/v2/audit/logs?object_type=enum_type&page_size=10',
        '/api/v2/audit/logs?action_type=CREATE&page_size=10',
        '/api/v2/audit/overview',
        '/api/v2/audit/failed',
        '/api/v2/audit/retry/status',
    ]
    for p in paths:
        status, body = call(s, 'GET', p)
        if status == 200:
            import json
            try:
                j = json.loads(body)
                if 'items' in j:
                    print(f'  {p} -> 200, items: {len(j["items"])}')
                elif 'data' in j:
                    d = j['data']
                    if isinstance(d, dict) and 'items' in d:
                        print(f'  {p} -> 200, data.items: {len(d["items"])}')
                    else:
                        print(f'  {p} -> 200, data keys: {list(d.keys())[:5] if isinstance(d, dict) else type(d).__name__}')
                else:
                    print(f'  {p} -> 200, keys: {list(j.keys())[:5]}')
            except:
                print(f'  {p} -> 200, body: {body[:80]}')
        else:
            print(f'  {p} -> {status}, body: {body[:80]}')


if __name__ == '__main__':
    main()
