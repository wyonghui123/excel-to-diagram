"""检查前端 association section 的配置：期望的字段名"""
import urllib.request, json, http.cookiejar

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open('http://localhost:3004/api/v1/auth/dev-login?username=admin')

# 1. 看 user 的 view-config，association section 配置
d = json.loads(op.open('http://localhost:3004/api/v2/meta/user/view-config/default').read())
print('=== user view-config ===')
detail = d.get('data', {}).get('detail', {})
print(f'detail keys: {list(detail.keys())}')

# 找 association sections
sections = detail.get('sections', [])
for s in sections:
    print(f'\nsection: {s.get("id")} / {s.get("title")} / {s.get("type")}')
    if s.get('type') == 'association':
        print(f'  columns: {s.get("columns")}')
        print(f'  fields: {s.get("fields")}')

# 2. user_group 的 view-config
d2 = json.loads(op.open('http://localhost:3004/api/v2/meta/user_group/view-config/default').read())
print('\n=== user_group view-config ===')
detail2 = d2.get('data', {}).get('detail', {})
sections2 = detail2.get('sections', [])
for s in sections2:
    print(f'\nsection: {s.get("id")} / {s.get("title")} / {s.get("type")}')
    if s.get('type') == 'association':
        print(f'  columns: {s.get("columns")}')
        print(f'  fields: {s.get("fields")}')
