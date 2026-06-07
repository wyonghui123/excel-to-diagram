"""深入检查 user view-config 的 tabs（找 association section）"""
import urllib.request, json, http.cookiejar

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open('http://localhost:3004/api/v1/auth/dev-login?username=admin')

d = json.loads(op.open('http://localhost:3004/api/v2/meta/user/view-config/default').read())
detail = d.get('data', {}).get('detail', {})
tabs = detail.get('tabs', [])
print(f'tabs count: {len(tabs)}')
for tab in tabs:
    print(f'\ntab: id={tab.get("id")} title={tab.get("title")} type={tab.get("type")}')
    if tab.get('type') == 'association':
        print(f'  columns: {tab.get("columns")}')
        print(f'  fields: {tab.get("fields")}')
        print(f'  association: {tab.get("association")}')
        print(f'  all keys: {list(tab.keys())}')
