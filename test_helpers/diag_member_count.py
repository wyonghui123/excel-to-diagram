"""最小排查脚本"""
import urllib.request, json, http.cookiejar

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open('http://localhost:3004/api/v1/auth/dev-login?username=admin')

# 验证后端是否处理 member_count__gte/__lte
for url in [
    'http://localhost:3004/api/v2/bo/user_group?page=1&page_size=20',
    'http://localhost:3004/api/v2/bo/user_group?page=1&page_size=20&member_count__gte=1&member_count__lte=10',
    'http://localhost:3004/api/v2/bo/user_group?page=1&page_size=20&member_count_min=1&member_count_max=10',
]:
    d = json.loads(op.open(url).read())
    rows = d.get('data', {}).get('data', [])
    print(f'URL: {url.split("?")[1]}')
    print(f'  total={d.get("data",{}).get("total","?")}, returned={len(rows)}')
    for r in rows:
        print(f'    - {r.get("code")} member_count={r.get("member_count")}')
    print()
