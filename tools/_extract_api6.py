import zipfile, re
z = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
content = z.read('frontend_dist_files/assets/index-48IrQ6VL.js').decode('utf-8', errors='ignore')

# 找 'query' 字符串
print('=== 字符串 query ===')
for m in re.finditer(r'["\'`]query["\'`]', content):
    pos = m.start()
    ctx_start = max(0, pos - 80)
    ctx_end = pos + 150
    print(f'pos {pos}: {content[ctx_start:ctx_end]}')
    print()

# 找 "L.query" 上下文
print('=== L.query 调用 ===')
for m in re.finditer(r'L\.query|L\[\s*[\'"]query[\'"]\s*\]', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-100):pos+200]}')
    print()

# 找 import { query } from
print('=== import query ===')
for m in re.finditer(r'import\s*\{[^}]*query[^}]*\}', content):
    print(f'  {m.group()}')
