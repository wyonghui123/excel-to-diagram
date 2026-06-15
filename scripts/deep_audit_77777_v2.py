#!/usr/bin/env python3
"""查 product:353 创建时的完整 extra_data, 确认是否带 V10"""
import urllib.request, http.cookiejar, json

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

# 查 audit log, 取 product:353 的所有 CREATE
r = op.open('http://localhost:3010/api/v1/audit/logs?object_type=product&action=create&page=1&page_size=100')
try:
    logs = json.loads(r.read().decode()).get('data', [])
    for log in logs:
        if log.get('object_id') == 353 or 'product:353' in str(log.get('business_key', '')):
            print(f'\n=== {log.get("created_at")} {log.get("action")} field={log.get("field_name")} ===')
            print(json.dumps(log.get('extra_data_parsed', {}), ensure_ascii=False, indent=2)[:1000])
except Exception as e:
    print(f'  失败: {e}')

# 查 15:00 - 15:06 之间所有 audit
print('\n\n=== 15:00 - 15:06 之间所有 audit (用户手动 + 脚本) ===')
r = op.open('http://localhost:3010/api/v1/audit/logs?page=1&page_size=200')
logs = json.loads(r.read().decode()).get('data', [])
import datetime
for log in logs:
    ts = log.get('created_at', '')
    if '15:00' in ts or '15:01' in ts or '15:02' in ts or '15:03' in ts or '15:04' in ts or '15:05' in ts or '15:06' in ts:
        obj_id = log.get('object_id')
        obj_type = log.get('object_type')
        bk = log.get('business_key', '')[:60]
        print(f'  {ts} {log.get("action")} {obj_type}:{obj_id} bk={bk} user={log.get("user_id")}')
