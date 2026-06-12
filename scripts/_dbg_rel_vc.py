import requests
import json

s = requests.Session()
s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin', timeout=5)

r = s.get('http://localhost:3010/api/v2/meta/relationship/view-config/default', timeout=5)
print('vc:', r.status_code)
if r.status_code == 200:
    vc = r.json().get('data', r.json())
    print('form sections:')
    for sec in vc.get('form', {}).get('sections', []):
        print('  - section:', sec.get('title'))
        if sec.get('columns'):
            for c in sec['columns']:
                print('    col title:', c.get('title'), 'fields:', c.get('fields'))
        if sec.get('fields'):
            print('    fields:', sec['fields'])
    print('detail facets:')
    for f in vc.get('detail', {}).get('facets', []):
        print('  -', f.get('type'), 'title=', f.get('title'), 'fields=', f.get('fields'))
        for fg in f.get('fieldGroups', []) or []:
            print('    fg: title=', fg.get('title'), 'fields=', fg.get('fields'))
