"""通过一个 admin 账号查 product, 看是否 5 条都在"""
import requests
import json

BASE = 'http://localhost:3010'

# 用 admin 登录
sess = requests.Session()
r = sess.get(f'{BASE}/api/v1/auth/dev-login?username=admin', allow_redirects=False)
print(f'admin login: {r.status_code}')
if r.status_code != 200:
    print(f'  {r.text[:200]}')
    exit(1)

# 查 product
r = sess.get(f'{BASE}/api/v2/bo/product?page=1&page_size=20')
print(f'admin /api/v2/bo/product: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    items = data.get('data', {}).get('items', [])
    print(f'  total={data.get("data", {}).get("total", "?")}, count={len(items)}')
    for it in items[:10]:
        print(f'    {it.get("id")} | {it.get("code")} | {it.get("name")}')

# 用 admin 查 version
r = sess.get(f'{BASE}/api/v2/bo/version?page=1&page_size=20')
print(f'admin /api/v2/bo/version: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    items = data.get('data', {}).get('items', [])
    print(f'  total={data.get("data", {}).get("total", "?")}, count={len(items)}')
    for it in items[:10]:
        print(f'    {it.get("id")} | product_id={it.get("product_id")} | {it.get("code")}')
