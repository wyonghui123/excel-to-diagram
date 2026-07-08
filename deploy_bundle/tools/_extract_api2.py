import zipfile, re
z = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
content = z.read('frontend_dist_files/assets/useVersionContext-BO-Qp8Kc.js').decode('utf-8', errors='ignore')

# 找 fetch / api / 字符串
# 看上下文
# 找 'api' 字符串
api_strs = re.findall(r"['\"]([^'\"]*api[^'\"]*?)['\"]", content, re.I)
for s in sorted(set(api_strs)):
    if '/api' in s.lower() or 'product' in s.lower() or 'version' in s.lower():
        print(f'  {s}')

# 找含 'fetch' 的关键调用
print('\n--- fetch 调用上下文 ---')
for m in re.finditer(r'fetch\(["\']([^"\']*)["\']', content):
    print(f'  fetch("{m.group(1)}")')

# 找 request
print('\n--- request 调用 ---')
for m in re.finditer(r'request\.(get|post|put|delete)\(["\']([^"\']*)["\']', content):
    print(f'  request.{m.group(1)}("{m.group(2)}")')

# 找 api.X
print('\n--- api.X 调用 ---')
for m in re.finditer(r'api\.(get|post|put|delete)\(["\']([^"\']*)["\']', content):
    print(f'  api.{m.group(1)}("{m.group(2)}")')
