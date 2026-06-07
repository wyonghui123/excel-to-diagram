# -*- coding: utf-8 -*-
"""直接查询后端 API：验证 relation_code__in=APPROVES,CREATES 返回几条"""
import urllib.request, json

# 先登录获取 cookie
login_req = urllib.request.Request("http://localhost:3010/api/v1/auth/dev-login?username=admin")
login_resp = urllib.request.urlopen(login_req)
cookies = login_resp.headers.get('Set-Cookie', '')
print(f"Login cookies: {cookies[:100]}")

# 查询
url = "http://localhost:3010/api/v2/bo/relationship?page=1&page_size=20&version_id=1&relation_code__in=APPROVES,CREATES&ordering=-updated_at"
req = urllib.request.Request(url)
req.add_header('Cookie', cookies.split(';')[0] if cookies else '')
resp = urllib.request.urlopen(req)
data = json.loads(resp.read().decode())

results = data.get('results', data.get('data', []))
count = data.get('count', len(results))
print(f"\nTotal count: {count}")
for r in results[:10]:
    src = r.get('source_code', r.get('source_bo_code', '?'))
    tgt = r.get('target_code', r.get('target_bo_code', '?'))
    code = r.get('relation_code', '?')
    src_name = r.get('source_name', r.get('source_bo_name', ''))
    tgt_name = r.get('target_name', r.get('target_bo_name', ''))
    print(f"  {src}({src_name}) -> {tgt}({tgt_name}) code={code}")
