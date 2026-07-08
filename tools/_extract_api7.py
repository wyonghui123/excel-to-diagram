import zipfile, re
z = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
content = z.read('frontend_dist_files/assets/useVersionContext-BO-Qp8Kc.js').decode('utf-8', errors='ignore')

# 找 L.query 用法
print('=== L.query 用法 ===')
for m in re.finditer(r'L\.query\([^)]*\)', content):
    print(f'  {m.group()}')

# 找 L 变量定义
print()
print('=== L 变量定义 ===')
for m in re.finditer(r'\bL\s*=', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-20):pos+200]}')
    print()

# 找 L.query 调用上下文
print()
print('=== L.query 上下文 ===')
for m in re.finditer(r'L\.query\("product"', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-300):pos+50]}')
    print()

# 找 .query
print()
print('=== .query 调用 ===')
for m in re.finditer(r'\.query\s*\(', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-30):pos+200]}')
    print()
