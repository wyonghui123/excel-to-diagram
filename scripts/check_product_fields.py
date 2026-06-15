#!/usr/bin/env python3
"""检查 product add 表单的字段"""
import urllib.request, http.cookiejar, json

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

# 查看 product meta 的 field policy
r = op.open('http://localhost:3010/api/v2/meta/product/field-policies?context=create')
data = json.loads(r.read().decode())
fields = data.get('data', {})
print('=== product create field policies ===')
for key, policy in sorted(fields.items()):
    req = policy.get('required', False)
    edit = policy.get('editable', '')
    ro = policy.get('readonly', False)
    vis = policy.get('visible', True)
    if vis and edit != 'hidden':
        print(f'  {key}: required={req}, editable={edit}, readonly={ro}, visible={vis}')

# 也查看 schema
r2 = op.open('http://localhost:3010/api/v2/meta/product/ui-config')
config = json.loads(r2.read().decode())
form_config = config.get('data', {}).get('form', {})
print('\n=== product form config ===')
sections = form_config.get('sections', [])
for sec in sections:
    print(f'  section: {sec.get("title", "untitled")}')
    for field in sec.get('fields', []):
        print(f'    {field.get("key")}: label={field.get("label")}, visible={field.get("visible", True)}')
