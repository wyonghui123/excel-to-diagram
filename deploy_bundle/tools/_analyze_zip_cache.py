import zipfile, re
z = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
c = z.read('meta/core/enums/cache_manager.py').decode()
# 全文
print('=== ZIP 内 cache_manager.py 全文 ===')
print(c)
print()
print('=== 分析 ===')
# 区分注释 vs 代码
lines = c.split('\n')
print(f'总行数: {len(lines)}')
# 找 async with self._lock
for i, line in enumerate(lines, 1):
    if 'async with self._lock' in line:
        is_comment = line.lstrip().startswith('#')
        is_docstring = '"""' in line or "'''" in line
        print(f'  line {i}: {"[COMMENT]" if is_comment else "[CODE]"} {"[DOCSTRING]" if is_docstring else ""}')
        print(f'    {line.rstrip()}')
# 找 with self._lock:
print()
print('with self._lock 行:')
for i, line in enumerate(lines, 1):
    if 'with self._lock:' in line and not 'async' in line:
        is_comment = line.lstrip().startswith('#')
        print(f'  line {i}: {"[COMMENT]" if is_comment else "[CODE]"}')
        print(f'    {line.rstrip()}')
