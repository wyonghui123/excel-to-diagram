"""最终验证：user/1/associations/groups 返回 member_count"""
import urllib.request, json, http.cookiejar

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open('http://localhost:3004/api/v1/auth/dev-login?username=admin')

d = json.loads(op.open('http://localhost:3004/api/v2/bo/user/1/associations/groups').read())
items = d.get('data', {}).get('items', [])
print(f'user/1 groups: {len(items)} items')
for item in items:
    print(f'  id={item.get("id")} name={item.get("name")}')
    print(f'    manager_id_display={item.get("manager_id_display")} parent_id_display={item.get("parent_id_display")}')
    print(f'    member_count={item.get("member_count")}  ← 前端渲染这个字段')
    print(f'    members_count={item.get("members_count")}  ← 旧字段(应为None)')

print()
# 对比 user_group list
d2 = json.loads(op.open('http://localhost:3004/api/v2/bo/user_group?page=1&page_size=20').read())
items2 = d2.get('data', {}).get('items', [])
print('user_group list:')
for item in items2[:3]:
    print(f'  id={item.get("id")} member_count={item.get("member_count")}')
