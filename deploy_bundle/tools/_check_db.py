import zipfile
z = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
# 找 .db 文件
for name in z.namelist():
    if name.endswith('.db') or '.db.' in name or 'architecture' in name.lower():
        print(name, z.getinfo(name).file_size)
