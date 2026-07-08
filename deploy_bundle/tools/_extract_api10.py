import zipfile, re
z = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
content = z.read('frontend_dist_files/assets/vendor-vue-ep-IZw8u4FP.js').decode('utf-8', errors='ignore')

# 找 export g (g as ...) 或 function g
print(f'vendor-vue-ep 大小: {len(content)}')

# 找 export {...g...}
print('=== export g ===')
for m in re.finditer(r'export\s*\{[^}]*\bg\b[^}]*\}', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-30):pos+300]}')
    print()

# 找 g: function
print()
print('=== g: function ===')
for m in re.finditer(r'\bg\s*:\s*function', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-30):pos+200]}')
    print()

# 找 function g(
print()
print('=== function g( ===')
for m in re.finditer(r'function\s+g\s*\(', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-30):pos+300]}')
    print()

# 找 query(entity) 调用
print()
print('=== query(entity 形参) 调用 ===')
for m in re.finditer(r'query\s*\(\s*[a-zA-Z_$]', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-30):pos+200]}')
    print()
