import urllib.request, json

# 登录
req1 = urllib.request.Request(
    'http://localhost:3010/api/v1/auth/login',
    data=json.dumps({'username': 'admin', 'password': 'admin123'}).encode(),
    headers={'Content-Type': 'application/json'}
)
token = json.loads(urllib.request.urlopen(req1).read().decode())['data']['token']

# 无过滤
req2 = urllib.request.Request(
    'http://localhost:3010/api/v1/user-groups?page=1&page_size=5',
    headers={'Authorization': f'Bearer {token}'}
)
resp2 = json.loads(urllib.request.urlopen(req2).read().decode())
print(f"无过滤 resp keys: {list(resp2.keys())}")
if 'data' in resp2:
    d = resp2['data']
    if isinstance(d, dict):
        print(f"无过滤: total={d.get('total')}, items={len(d.get('items', []))}")
    elif isinstance(d, list):
        print(f"无过滤: items={len(d)}")
        if d:
            print(f"  第一条: {json.dumps(d[0], ensure_ascii=False)[:200]}")

# parent_id=1 过滤
req3 = urllib.request.Request(
    'http://localhost:3010/api/v1/user-groups?page=1&page_size=5&parent_id=1',
    headers={'Authorization': f'Bearer {token}'}
)
resp3 = json.loads(urllib.request.urlopen(req3).read().decode())
d3 = resp3.get('data', {})
if isinstance(d3, dict):
    print(f"parent_id=1: total={d3.get('total')}, items={len(d3.get('items', []))}")
elif isinstance(d3, list):
    print(f"parent_id=1: items={len(d3)}")

# parent_id__in=1 过滤
req4 = urllib.request.Request(
    'http://localhost:3010/api/v1/user-groups?page=1&page_size=5&parent_id__in=1',
    headers={'Authorization': f'Bearer {token}'}
)
resp4 = json.loads(urllib.request.urlopen(req4).read().decode())
d4 = resp4.get('data', {})
if isinstance(d4, dict):
    print(f"parent_id__in=1: total={d4.get('total')}, items={len(d4.get('items', []))}")
elif isinstance(d4, list):
    print(f"parent_id__in=1: items={len(d4)}")
