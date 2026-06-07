"""检查哪些页面有 value_help 过滤器"""
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

# 检查权限相关的页面
pages = ['permission', 'role_permission', 'user_group_member', 'menu_permission', 'role', 'user_group']

for page in pages:
    try:
        query_url = f'http://localhost:3010/api/v2/bo/{page}?page=1&page_size=1'
        with opener.open(query_url) as resp:
            data = json.loads(resp.read().decode())
            if data.get('success'):
                filters = data['data'].get('filters', [])
                if filters:
                    print(f"\n{page} filters:")
                    for f in filters:
                        print(f"  - {f.get('field')}: type={f.get('type')}, value_help={'有' if f.get('value_help') else '无'}")
                else:
                    print(f"{page}: 无 filters")
            else:
                print(f"{page}: {data.get('message')}")
    except Exception as e:
        print(f"{page}: {e}")
