#!/usr/bin/env python3
import urllib.request, http.cookiejar, json
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

# 看不同的端点
for path in [
    '/api/v2/meta/product/ui-config',
    '/api/v1/meta/product/ui-config',
    '/api/v2/meta/product/view-config/default',
    '/api/v1/meta/product/view-config/default',
]:
    try:
        r = opener.open(f'http://localhost:3010{path}', timeout=5)
        data = json.loads(r.read().decode())
        if data.get('data'):
            cs = data['data'].get('child_sections') or data['data'].get('ui_view_config', {}).get('child_sections') or []
            print(f'{path}: status={r.status} child_sections={len(cs)}')
            for s in cs:
                print(f'  - {s.get("child_object")} display={s.get("display", "expandable")}')
        else:
            print(f'{path}: status={r.status} no data: {data.get("message")}')
    except Exception as e:
        print(f'{path}: err: {e}')
