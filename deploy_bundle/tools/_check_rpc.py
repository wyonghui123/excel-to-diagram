import zipfile, re
z = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
# 找 frontend_dist_files/assets/RolePermissionCenter-*.js (含 product page list?)
for name in z.namelist():
    if 'RolePermissionCenter' in name and name.endswith('.js') and '.map' not in name:
        content = z.read(name).decode('utf-8', errors='ignore')
        # 找 L.query
        for m in re.finditer(r'L\.query\([^)]+\)', content):
            print(f'{name}: {m.group()}')
