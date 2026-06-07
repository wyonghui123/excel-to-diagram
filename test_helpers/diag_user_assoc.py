"""抓用户详情页 association section 的 API 请求"""
import urllib.request, json, http.cookiejar

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open('http://localhost:3004/api/v1/auth/dev-login?username=admin')

# 看 association section 走的 API
# 常见路径：
# 1. /api/v2/bo/user/<id>/associations/user_group
# 2. /api/v2/bo/user_group?user_id=<id> (用 FK 过滤)
# 3. /api/v1/bo/user/<id>/associations/user_group

endpoints = [
    'http://localhost:3004/api/v2/bo/user/1/associations/user_group',
    'http://localhost:3004/api/v1/bo/user/1/associations/user_group',
    'http://localhost:3004/api/v2/bo/user_group?user_id=1',
    'http://localhost:3004/api/v2/bo/user_group?members__user_id=1',
]
for ep in endpoints:
    try:
        d = json.loads(op.open(ep).read())
        print(f'URL: {ep.replace("http://localhost:3004","")}')
        print(f'  keys: {list(d.keys())}')
        if 'data' in d and isinstance(d['data'], dict):
            print(f'  data keys: {list(d["data"].keys())}')
            for k, v in d['data'].items():
                if isinstance(v, list):
                    print(f'    {k}: list[{len(v)}]')
                    if v:
                        print(f'      first item keys: {list(v[0].keys()) if isinstance(v[0], dict) else v[0]}')
                        if isinstance(v[0], dict):
                            print(f'      first item: {json.dumps(v[0], ensure_ascii=False)[:300]}')
                else:
                    print(f'    {k}: {str(v)[:100]}')
        elif 'data' in d and isinstance(d['data'], list):
            print(f'  data: list[{len(d["data"])}]')
            if d['data']:
                print(f'    first: {json.dumps(d["data"][0], ensure_ascii=False)[:300]}')
        print()
    except Exception as e:
        print(f'URL: {ep.replace("http://localhost:3004","")}')
        print(f'  ERROR: {e}')
        print()
