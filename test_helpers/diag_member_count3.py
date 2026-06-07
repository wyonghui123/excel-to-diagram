"""验证后端 filter"""
import urllib.request, json, http.cookiejar

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open('http://localhost:3004/api/v1/auth/dev-login?username=admin')

cases = [
    ('base',         'http://localhost:3004/api/v2/bo/user_group?page=1&page_size=20'),
    ('__gte/__lte',  'http://localhost:3004/api/v2/bo/user_group?page=1&page_size=20&member_count__gte=1&member_count__lte=10'),
    ('_min/_max',    'http://localhost:3004/api/v2/bo/user_group?page=1&page_size=20&member_count_min=1&member_count_max=10'),
    ('__gte only',   'http://localhost:3004/api/v2/bo/user_group?page=1&page_size=20&member_count__gte=1'),
    ('__lte only',   'http://localhost:3004/api/v2/bo/user_group?page=1&page_size=20&member_count__lte=0'),
]
for label, url in cases:
    d = json.loads(op.open(url).read())
    items = d.get('data', {}).get('items', [])
    total = d.get('data', {}).get('total', '?')
    print(f'[{label}] total={total}, returned={len(items)}')
    for r in items:
        print(f'    - {r.get("code")} member_count={r.get("member_count")}')
    print()
