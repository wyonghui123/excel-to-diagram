#!/usr/bin/env python3
import urllib.request, http.cookiejar, json
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')
r = opener.open('http://localhost:3010/api/v2/meta/product/ui-config')
data = json.loads(r.read().decode())
cs = data.get('data', {}).get('child_sections', [])
print('child_sections count:', len(cs))
for s in cs:
    print(' -', json.dumps(s, ensure_ascii=False))
