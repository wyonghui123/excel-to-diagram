import zipfile
v = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
sh_files = [n for n in v.namelist() if n.endswith('.sh')]
print(f'.sh files in zip: {len(sh_files)}')
crlf_count = 0
for n in sh_files:
    data = v.read(n)
    has_crlf = b'\r\n' in data
    if has_crlf:
        crlf_count += 1
        print(f'  CRLF: {n}')
    else:
        print(f'  LF:   {n}')
print(f'\nTotal CRLF: {crlf_count}/{len(sh_files)}')
