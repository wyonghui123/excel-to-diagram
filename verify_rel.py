import requests, json
s = requests.Session()
s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin')
r = s.get('http://localhost:3010/api/v1/relationships?version_id=1&page_size=10000')
items = r.json()['data']
print('All relations:')
for i in items:
    sd = i.get('source_domain_id')
    td = i.get('target_domain_id')
    src = i.get('source_code')
    tgt = i.get('target_code')
    in_scope = i.get('is_in_scope')
    cat = i.get('category_type')
    rel_code = i.get('relation_code')
    rel_type = i.get('relation_type')
    rid = i.get('id')
    print(f'  id={rid}, src={src}(d={sd}), tgt={tgt}(d={td}), in_scope={in_scope}, cat={cat}, code={rel_code}, type={rel_type}')

# Test id__in filter
print('\n--- Testing id__in=29 (single id) ---')
r2 = s.get('http://localhost:3010/api/v1/relationships?version_id=1&id__in=29')
print('status:', r2.status_code)
data = r2.json()
if data.get('success'):
    print('total:', data.get('total'))
    print('items count:', len(data.get('data', [])))
else:
    print(data)

# Test multiple ids
print('\n--- Testing id__in=29,1,2 ---')
r3 = s.get('http://localhost:3010/api/v1/relationships?version_id=1&id__in=29,1,2')
print('status:', r3.status_code)
data = r3.json()
if data.get('success'):
    print('total:', data.get('total'))
    print('items count:', len(data.get('data', [])))
else:
    print(data)
