import zipfile, re
z = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
content = z.read('frontend_dist_files/assets/index-48IrQ6VL.js').decode('utf-8', errors='ignore')

# 找 index 内的 import g from ...
print('=== index 内的 import g ===')
for m in re.finditer(r'import\s*\{[^}]*\bg\b[^}]*\}\s*from', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-30):pos+300]}')
    print()

# 找 const g = X 形如 const g = 某个函数
print('=== const g = ===')
for m in re.finditer(r'\bconst\s+g\s*=', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-30):pos+300]}')
    print()

# 找 g 的 export (在 index 内)
print()
print('=== index 内的 export g ===')
for m in re.finditer(r'\bg\s+as\s+\w+', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-30):pos+150]}')
    print()

# 找 index 整个 export
print()
print('=== index 末尾 export ===')
# export 找 pos > 100000
for m in re.finditer(r'export\s*\{[^}]+\}', content):
    pos = m.start()
    if pos > 150000:
        print(f'pos {pos}: {content[max(0,pos-30):pos+200]}')
        print()
