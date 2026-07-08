import zipfile, re
z = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
content = z.read('frontend_dist_files/assets/index-48IrQ6VL.js').decode('utf-8', errors='ignore')

# 找 import {g as ...} from ...
print('=== import g ===')
for m in re.finditer(r'import\s*\{[^}]*\bg\b[^}]*\}\s*from', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-30):pos+400]}')
    print()

# 找 const gt = ... 或 let gt = ...
print()
print('=== gt = g ===')
for m in re.finditer(r'\bgt\s*=\s*g\b', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-30):pos+200]}')
    print()

# 找 /api/v1/entity/${e} 或 /api/v1/schema/${e} 模板
print()
print('=== /api/v1/${e} 模板 ===')
for m in re.finditer(r'/api/v\d+/[^"\'`]*?\$\{[^}]+\}', content):
    print(f'  {m.group()}')

# 找 request.post(/api/v1/${e}/query
print()
print('=== /query 路径 ===')
for m in re.finditer(r'/query["\']', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-100):pos+100]}')
    print()
