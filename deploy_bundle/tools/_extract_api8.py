import zipfile, re
z = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
content = z.read('frontend_dist_files/assets/index-48IrQ6VL.js').decode('utf-8', errors='ignore')

# 找 export {g as ...
print('=== export g as ===')
for m in re.finditer(r'\bg\s+as\s+\w+|export\s*\{[^}]*\bg\b[^}]*\}', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-30):pos+150]}')
    print()

# 找 const g = function
print('=== const g = ... ===')
for m in re.finditer(r'\bg\s*=\s*(?:function|\(|\{)', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-30):pos+200]}')
    print()

# 找 query: function
print('=== query: function ===')
for m in re.finditer(r'query\s*:\s*function', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-30):pos+400]}')
    print()

# 找 schemaApi / entityApi / crudApi
print('=== schemaApi / crudApi ===')
for kw in ['schemaApi', 'crudApi', 'entityApi', 'queryApi', 'api.entity']:
    for m in re.finditer(re.escape(kw), content):
        pos = m.start()
        print(f'  "{kw}" pos {pos}: {content[max(0,pos-30):pos+150]}')
