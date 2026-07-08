import zipfile, re
z = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
# 找 GlobalToolbar 实际 fetch 调什么
# 先找含 fetchProducts 的文件
for name in z.namelist():
    if not name.startswith('frontend_dist_files/assets/') or not name.endswith('.js') or '.map' in name:
        continue
    try:
        content = z.read(name).decode('utf-8', errors='ignore')
    except:
        continue
    if 'fetchProducts' in content:
        # 找 fetchProducts 调用
        for m in re.finditer(r'.{50}fetchProducts.{150}', content):
            print(f'### {name} ###')
            print(m.group())
            print()
