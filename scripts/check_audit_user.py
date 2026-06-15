#!/usr/bin/env python3
import urllib.request, http.cookiejar, json

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

# 查 audit log 最近 20 条, 看 user_id
r = opener.open('http://localhost:3010/api/v1/audit/logs?page_size=10')
data = json.loads(r.read().decode())
print('type:', type(data['data']).__name__)
if isinstance(data['data'], list):
    for a in data['data'][:5]:
        print('user_id:', a.get('user_id'))
        print(' username:', a.get('username'))
        print(' user_name:', a.get('user_name'))
        print(' action:', a.get('action'))
        print(' business_key:', a.get('business_key'))
        print(' extra_data:', json.dumps(a.get('extra_data_parsed', {}), ensure_ascii=False)[:300])
        print('---')
