import requests
import sys

sys.path.insert(0, r'd:\filework\excel-to-diagram')
from meta.services.token_service import TokenService
from meta.services.auth_provider import UserInfo

user = UserInfo(user_id='1', username='test_user', display_name='Test User', email='test@test.com', roles=['admin'], permissions=['*'])
token, _ = TokenService.create_token(user)
headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}

BASE = 'http://localhost:3010/api/v2'

# 取 ui-config
r = requests.get(BASE + '/meta/business_object/ui-config', headers=headers, timeout=10)
print('status:', r.status_code)
cfg = r.json().get('data') or r.json()
fields = cfg.get('fields', [])
print('total fields:', len(fields))
# 找 *_name 字段
for f in fields:
    fid = f.get('id', '')
    if fid in ['sub_domain_name', 'domain_name', 'service_module_name', 'version_name']:
        print('--- {} ---'.format(fid))
        for k, v in f.items():
            print('  {}: {!r}'.format(k, v))
