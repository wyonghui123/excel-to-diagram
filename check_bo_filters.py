"""检查 /api/v2/bo/user_group API 返回的 filters"""
import urllib.request
import json
import http.cookiejar

# 先登录
login_url = 'http://localhost:3010/api/v1/auth/dev-login?username=admin'
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

with opener.open(login_url) as resp:
    login_data = json.loads(resp.read().decode())
    print('Login:', login_data.get('success'))

# 获取 bo API
query_url = 'http://localhost:3010/api/v2/bo/user_group?page=1&page_size=1'
with opener.open(query_url) as resp:
    data = json.loads(resp.read().decode())

    if data.get('success'):
        filters = data['data'].get('filters', [])
        print(f'\nfilters: {len(filters)} 个')

        # 找到 parent_id 和 manager_id filter
        for f in filters:
            field = f.get('field', '')
            if 'parent' in field.lower() or 'manager' in field.lower():
                print(f"\n=== {field} filter ===")
                print(f"type: {repr(f.get('type'))}")
                print(f"filter_type: {repr(f.get('filter_type'))}")
                print(f"value_help: {'有' if f.get('value_help') else '无'}")
                if f.get('value_help'):
                    print(f"value_help.behavior.multiple: {f['value_help'].get('behavior', {}).get('multiple')}")
    else:
        print('Error:', data.get('message'))
