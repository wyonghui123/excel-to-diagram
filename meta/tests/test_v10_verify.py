import requests
import json
import sys

s = requests.Session()
login = s.get('http://localhost:3010/api/v1/auth/dev-login?username=TEST333', allow_redirects=True)
print('login status:', login.status_code, 'cookie auth_token:', 'auth_token' in s.cookies)

list_resp = s.get('http://localhost:3010/api/v1/versions?page_size=50')
print('list status:', list_resp.status_code)
list_data = list_resp.json()
print()
print('version list total:', list_data.get('data', {}).get('total', '?'))
items = list_data.get('data', {}).get('items', [])
print('  returned', len(items), 'items')

v10 = [v for v in items if v.get('name') == 'V10']
print()
if v10:
    v = v10[0]
    print('  [FIX VERIFIED] V10 IS visible!')
    print('  id={id} name={name!r} product_id={pid} product_name={pname!r} visibility={vis}'.format(
        id=v.get('id'), name=v.get('name'),
        pid=v.get('product_id'), pname=v.get('product_name'),
        vis=v.get('visibility'),
    ))
else:
    print('  [BUG NOT FIXED] V10 still NOT visible')
    p476 = [v for v in items if v.get('product_id') == 476]
    print('  product 476 versions:', len(p476))
    for v in p476[:5]:
        print('    id={id} name={name!r} product_id={pid}'.format(
            id=v.get('id'), name=v.get('name'), pid=v.get('product_id')
        ))

