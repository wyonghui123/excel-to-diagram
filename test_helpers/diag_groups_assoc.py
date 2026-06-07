"""验证 user/1/associations/groups 是否有 member_count 和 _display"""
import urllib.request, json, http.cookiejar

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open('http://localhost:3004/api/v1/auth/dev-login?username=admin')

endpoints = [
    ('groups正确名', 'http://localhost:3004/api/v2/bo/user/1/associations/groups'),
    ('groups用$', 'http://localhost:3004/api/v2/bo/user/1/$associations/groups'),
]
for label, ep in endpoints:
    try:
        d = json.loads(op.open(ep).read())
        items = d.get('data', {}).get('items', []) if isinstance(d.get('data'), dict) else d.get('data', [])
        print(f'[{label}] {ep.replace("http://localhost:3004","")}')
        print(f'  items: {len(items)}, total: {d.get("data",{}).get("total","?") if isinstance(d.get("data"),dict) else "?"}')
        for item in items[:5]:
            display_keys = [k for k in item if k.endswith('_display')]
            count_keys = [k for k in item if k.endswith('_count')]
            print(f'    _display: {display_keys}')
            print(f'    _count: {count_keys}')
            print(f'    {str({k: item[k] for k in ["id","name","code","member_count","manager_id","manager_id_display","parent_id","parent_id_display"]})[:250]}')
        print()
    except Exception as e:
        print(f'[{label}] ERROR: {e}')
        print()
