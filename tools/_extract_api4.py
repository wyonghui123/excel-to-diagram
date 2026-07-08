import zipfile, re
z = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
# 找 index-48IrQ6VL.js 中的 crud / query / api 定义
content = z.read('frontend_dist_files/assets/index-48IrQ6VL.js').decode('utf-8', errors='ignore')
print(f'index-48IrQ6VL.js 长度: {len(content)}')

# 找 query 函数
print()
print('=== query 函数定义 ===')
for m in re.finditer(r'.{50}\.query[\s=].{150}', content):
    s = m.group()
    if '/api' in s or 'method' in s.lower() or 'post' in s.lower() or 'get' in s.lower():
        print(f'  {s}')

# 找 baseURL
print()
print('=== baseURL ===')
for m in re.finditer(r'baseURL["\']?\s*[:=]\s*["\']([^"\']+)', content):
    print(f'  {m.group(1)}')

# 找 const [a-zA-Z]+ *=.*{.*query
print()
print('=== 含 query 字符串 ===')
for m in re.finditer(r'"/api/[^"]+"', content):
    print(f'  {m.group()}')

# 找 /api/v1/schema 或 /api/v1/entity
print()
print('=== /api/v1/ 路径 ===')
for m in re.finditer(r'/api/v1/[\w/_\-{}]+', content):
    s = m.group()
    if len(s) < 100:
        print(f'  {s}')
