"""验证 user_group/1/members association 是否有 member_count 和 _display"""
import urllib.request, json, http.cookiejar

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open('http://localhost:3004/api/v1/auth/dev-login?username=admin')

# user_group/1 的 members 关联（many-to-many through user_group_members）
endpoints = [
    'http://localhost:3004/api/v2/bo/user_group/1/$associations/members',
    'http://localhost:3004/api/v2/bo/user_group/1/associations/members',
]
for ep in endpoints:
    try:
        d = json.loads(op.open(ep).read())
        items = d.get('data', {}).get('items', []) if isinstance(d.get('data'), dict) else d.get('data', [])
        print(f'URL: {ep.replace("http://localhost:3004","")}')
        print(f'  items: {len(items)}')
        for item in items[:5]:
            print(f'    keys: {list(item.keys())}')
            # 检查 _display 和 _count
            display_keys = [k for k in item if k.endswith('_display')]
            count_keys = [k for k in item if k.endswith('_count')]
            print(f'    _display: {display_keys}')
            print(f'    _count: {count_keys}')
            print(f'    sample: {str({k: item[k] for k in ["id","name","code"] + display_keys + count_keys})[:300]}')
        print()
    except Exception as e:
        print(f'URL: {ep.replace("http://localhost:3004","")}')
        print(f'  ERROR: {e}')
        print()
