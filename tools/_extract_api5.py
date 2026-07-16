import zipfile, re
z = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
# 看 vendor-vue-ep-IZw8u4FP.js (ep 可能是 element-plus)
# 看 index-48IrQ6VL.js 含 'query' 上下文
content = z.read('frontend_dist_files/assets/index-48IrQ6VL.js').decode('utf-8', errors='ignore')

# 找 query 函数上下文 (带 entity 形参)
print('=== query(entity 形参) ===')
for m in re.finditer(r'query\s*\(\s*[a-zA-Z_$][\w$]*\s*[,)]', content):
    pos = m.start()
    print(f'  pos {pos}: ...{content[max(0,pos-100):pos+200]}...')
    print()

# 找 post 字符串
print('=== post 调用 ===')
for m in re.finditer(r'post\(["\']([^"\']+)', content):
    print(f'  post("{m.group(1)}")')

# 找 ${entity} 字符串
print()
print('=== ${entity} 模板字符串 ===')
for m in re.finditer(r'["\`][^"\`]*\$\{[^}]+\}[^"\`]*["\`]', content):
    s = m.group()
    if 'api' in s.lower() or 'query' in s.lower():
        print(f'  {s}')
