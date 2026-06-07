"""检查 user_group meta_object.associations"""
import urllib.request, json, http.cookiejar

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open('http://localhost:3004/api/v1/auth/dev-login?username=admin')

# 直接在 backend 中检查
d = json.loads(op.open('http://localhost:3004/api/v2/bo/user_group/1/associations/groups').read())
items = d.get('data', {}).get('items', [])
print(f'items returned: {len(items)}')
if items:
    print(f'item[0] keys: {list(items[0].keys())}')
    # 检查是否有 members_count
    for k in items[0]:
        if '_count' in k:
            print(f'  FOUND _count: {k}={items[0][k]}')
    print(f'item[0] sample: {str({k: items[0][k] for k in ["id","name","code","manager_id","manager_id_display","members_count"] if k in items[0]})}')
