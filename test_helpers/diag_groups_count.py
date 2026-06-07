"""验证 groups association counts 的值"""
import urllib.request, json, http.cookiejar

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open('http://localhost:3004/api/v1/auth/dev-login?username=admin')

d = json.loads(op.open('http://localhost:3004/api/v2/bo/user/1/associations/groups').read())
items = d.get('data', {}).get('items', [])
print(f'items: {len(items)}')
for item in items:
    print(f'  id={item.get("id")} name={item.get("name")}')
    print(f'    manager_id={item.get("manager_id")} manager_id_display={item.get("manager_id_display")}')
    print(f'    parent_id={item.get("parent_id")} parent_id_display={item.get("parent_id_display")}')
    print(f'    members_count={item.get("members_count")}')
    print(f'    roles_count={item.get("roles_count")}')

print()
# 对比 user_group list
d2 = json.loads(op.open('http://localhost:3004/api/v2/bo/user_group?page=1&page_size=20').read())
items2 = d2.get('data', {}).get('items', [])
print(f'user_group list (对比):')
for item in items2[:3]:
    print(f'  id={item.get("id")} name={item.get("name")} member_count={item.get("member_count")}')
