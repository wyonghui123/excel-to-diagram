#!/usr/bin/env python3
"""
验证 AUDIT_WRITE_FAILED 是否真的修复
触发一次操作, 然后查 audit log API 看是否能查到
"""
import urllib.request
import urllib.parse
import json
import http.cookiejar

BASE = 'http://localhost:3010'


def get_session():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    return opener


def call(opener, method, path, data=None, raw=False):
    url = BASE + path
    if data is not None:
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
    print('1. login:', status)

    # 2. 触发 audit: 创建一个 enum_type (会触发 audit log)
    import time
    ts = str(int(time.time()))
    test_code = 'AUDIT_TEST_' + ts
    status, body = call(s, 'POST', '/api/v2/bo/enum_type', {
        'code': test_code,
        'name': 'AUDIT_TEST_' + ts,
        'category': 'business',
        'mutability': 'fullEditable'
    })
    print('2. create enum_type:', status, body[:200])

    # 3. 立即查 audit log
    audit_eps = [
        '/api/v2/audit-log?page_size=10',
        '/api/v2/audit-log?object_type=enum_type&object_code=' + test_code,
        '/api/v2/audit-log?action_type=CREATE&page_size=10',
        '/api/v2/audit_log?page_size=10',
        '/api/v2/audit_logs?page_size=10',
    ]
    print('3. audit queries:')
    for ep in audit_eps:
        status, body = call(s, 'GET', ep)
        result = 'OK' if status == 200 else f'FAIL({status})'
        print(f'   {ep} -> {result}: {body[:120]}')

    # 4. 查 410 响应 (v1 → v2 迁移路径)
    status, body = call(s, 'GET', '/api/v1/user-groups')
    print('4. v1 410 (user-groups):', status)
    if 'migrated_to' in body:
        import re
        m = re.search(r'migrated_to["\s:]+([/\w_-]+)', body)
        if m:
            print('   migrated_to:', m.group(1))
        else:
            print('   body:', body[:200])
    else:
        print('   body:', body[:200])

    # 5. 测后端日志中是否还有 AUDIT_WRITE_FAILED
    import os
    log_path = r'd:\filework\excel-to-diagram\meta\logs\app.jsonl'
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        audit_failed = [l for l in lines[-200:] if 'AUDIT_WRITE_FAILED' in l]
        print('5. AUDIT_WRITE_FAILED in last 200 log lines:', len(audit_failed))
        if audit_failed:
            print('   last:', audit_failed[-1][:200])
    else:
        print('5. no log file at', log_path)


if __name__ == '__main__':
    main()
