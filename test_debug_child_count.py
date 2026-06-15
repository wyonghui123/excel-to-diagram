import requests
s = requests.Session()
s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin')

for obj in ['domain', 'sub_domain', 'service_module']:
    print(f'=== {obj} ?ordering=child_count ===')
    for ordering in ['-child_count', 'child_count']:
        r = s.get(f'http://localhost:3010/api/v2/bo/{obj}',
                  params={'ordering': ordering, 'page': 1, 'page_size': 8})
        if r.status_code == 200:
            d = r.json().get('data', {})
            items = d.get('items', d) if isinstance(d, dict) else d
            vals = [it.get('child_count') for it in items]
            print(f'  {ordering}: {vals}')
        else:
            print(f'  {ordering}: HTTP {r.status_code}')

print('\n=== relation_count 无回归 ===')
for obj in ['domain', 'sub_domain', 'service_module']:
    for ordering in ['-relation_count']:
        r = s.get(f'http://localhost:3010/api/v2/bo/{obj}',
                  params={'ordering': ordering, 'page': 1, 'page_size': 5})
        if r.status_code == 200:
            d = r.json().get('data', {})
            items = d.get('items', d) if isinstance(d, dict) else d
            vals = [it.get('relation_count') for it in items]
            print(f'  {obj} {ordering}: {vals}')
