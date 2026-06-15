#!/usr/bin/env python3
import urllib.request, http.cookiejar, json, time
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

ts = str(int(time.time()))
body = {
    'parent': {'id': f'CAT_MISS_{ts}', 'name': f'CAT MISS {ts}'},
    'children': {'version': [{'id': f'ver_{ts}', 'name': 'V1', 'is_current': 1}]}
}
req = urllib.request.Request('http://localhost:3010/api/v2/bo/product/deep', data=json.dumps(body).encode(), method='POST', headers={'Content-Type': 'application/json'})
try:
    r = opener.open(req, timeout=10)
    print('status:', r.status)
    print('body:', r.read().decode()[:500])
except urllib.error.HTTPError as e:
    print('err:', e.code)
    print('body:', e.read().decode()[:500])
