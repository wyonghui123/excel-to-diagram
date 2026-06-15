import requests
s = requests.Session()
r = s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin', timeout=5)
print('login:', r.status_code)

# 正确 URL: /api/v2/meta/<object_type>/ui-config
r = s.get('http://localhost:3010/api/v2/meta/business_object/ui-config', timeout=10)
print('ui-config status:', r.status_code)
if r.status_code == 200:
    j = r.json()
    cfg = j.get('data', {})
    print('top keys:', list(cfg.keys()))
    print('ui_view_config keys:', list(cfg.get('ui_view_config', {}).keys()))
    detail = cfg.get('ui_view_config', {}).get('detail', {})
    print('detail keys:', list(detail.keys()))
    facets = detail.get('facets', [])
    print('facets count:', len(facets))
    for f in facets:
        print(f'  - {f.get("title")} type={f.get("type")} fields={f.get("fields", [])}')

    print()
    fields = cfg.get('fields', [])
    print('fields count:', len(fields))
    for f in fields:
        if f.get('id', '').endswith('_id'):
            ui = f.get('ui', {})
            print(f'  {f.get("id")}: ui={ui}, value_help={bool(f.get("value_help"))}')
else:
    print('Error:', r.text[:500])
