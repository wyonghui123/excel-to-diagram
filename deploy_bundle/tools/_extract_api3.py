import zipfile, re
z = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
content = z.read('frontend_dist_files/assets/useVersionContext-BO-Qp8Kc.js').decode('utf-8', errors='ignore')

# 找 product 字符串
print('=== 含 product 字符串 ===')
idx = 0
while True:
    idx = content.lower().find('product', idx)
    if idx < 0: break
    print(f'  pos {idx}: ...{content[max(0,idx-30):idx+50]}...')
    idx += 1

# 找 /api/... 路径
print()
print('=== /api/ 路径 ===')
for m in re.finditer(r'/api/[\w/\-:.]+', content):
    print(f'  {m.group()}')

# 找 fetch / get / url / endpoint 等
print()
print('=== fetch/get/url 调用 ===')
for kw in ['fetch', 'axios', 'url:', 'url =', 'endpoint', '/v1/', '/v2/']:
    for m in re.finditer(re.escape(kw), content):
        pos = m.start()
        print(f'  "{kw}" at {pos}: ...{content[max(0,pos-20):pos+80]}...')

# 找 product_name
print()
print('=== 含 product_name ===')
for m in re.finditer(r'.{20}product_name.{40}', content):
    print(f'  {m.group()}')
