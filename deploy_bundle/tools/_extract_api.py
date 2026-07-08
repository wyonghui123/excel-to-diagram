import zipfile, re
z = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
content = z.read('frontend_dist_files/assets/useVersionContext-BO-Qp8Kc.js').decode('utf-8', errors='ignore')
# 找 fetch / axios / API path
# 通常是 /api/v1/products, /api/v2/products
matches = re.findall(r"['\"](/api/[^'\"?]+)['\"]", content)
print('useVersionContext-BO-Qp8Kc.js API URLs:')
for u in sorted(set(matches)):
    print(f'  {u}')

# 也看含 product 的字符串
print()
print('product-related strings:')
for m in re.finditer(r'[A-Za-z0-9_]*[Pp]roduct[A-Za-z0-9_]*', content):
    s = m.group()
    if len(s) > 3 and s not in ('Product', 'product', 'products', 'Products'):
        print(f'  {s}')
