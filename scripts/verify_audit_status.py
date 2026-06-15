#!/usr/bin/env python3
"""
深度核查 AUDIT_WRITE_FAILED 状态
"""
import urllib.request
import http.cookiejar
import json
import time

BASE = 'http://localhost:3010'

s = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(s))

# login
opener.open(BASE + '/api/v1/auth/dev-login?username=admin')

# 1. 触发新 audit: 创建 + 删除
ts = str(int(time.time()))
test_code = 'AUDIT_HEALTH_' + ts

# create
req = urllib.request.Request(
    BASE + '/api/v2/bo/enum_type',
    data=json.dumps({
        'code': test_code, 'name': 'AUDIT_HEALTH_' + ts,
        'category': 'business', 'mutability': 'fullEditable'
    }).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST'
)
r = opener.open(req)
print('1. create:', r.status, r.read().decode()[:150])

time.sleep(0.5)

# 2. 查 overview
r = opener.open(BASE + '/api/v1/audit/overview')
j = json.loads(r.read().decode())
print()
print('=== AUDIT OVERVIEW ===')
data = j.get('data', {})
print('total:', data.get('total', 'N/A'))
print('by_action:')
for x in data.get('by_action', []):
    print(f'  {x["action"]}: {x["count"]}')
if 'by_level' in data:
    print('by_level:')
    for x in data['by_level'][:10]:
        print(f'  {x.get("level", "?")}: {x["count"]}')

# 3. 查最近 5 条
print()
print('=== RECENT 5 LOGS ===')
r = opener.open(BASE + '/api/v1/audit/logs?page_size=5')
j = json.loads(r.read().decode())
for item in j.get('data', [])[:5]:
    print('  id={} action={} level={} key={} created={}'.format(
        item.get('id'), item.get('action'), item.get('level', '-'),
        item.get('business_key', '-')[:40], item.get('created_at', '-')
    ))

# 4. 查刚创建 enum_type 的 audit
print()
print('=== SEARCH BY KEY (newly created) ===')
r = opener.open(BASE + '/api/v1/audit/logs?business_key=enum_type:' + test_code + '&page_size=5')
j = json.loads(r.read().decode())
items = j.get('data', [])
print('found items for new enum_type:', len(items))
for item in items:
    print('  ', item.get('action'), item.get('level', '-'), item.get('field_name', '-'))

# 5. AUDIT_WRITE_FAILED 计数 + last failed
print()
print('=== AUDIT_WRITE_FAILED STATUS ===')
r = opener.open(BASE + '/api/v1/audit/failed')
j = json.loads(r.read().decode())
items = j.get('data', {}).get('items', [])
print('failed items count:', len(items))
if items:
    for it in items[:3]:
        print('  failed id={} reason={}'.format(
            it.get('id'), it.get('error_message', it.get('reason', '-'))[:80]
        ))

# 6. retry status
print()
print('=== RETRY WORKER STATUS ===')
r = opener.open(BASE + '/api/v1/audit/retry/status')
print(r.read().decode()[:400])
