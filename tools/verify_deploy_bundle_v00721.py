#!/usr/bin/env python3
"""
verify_deploy_bundle_v00721.py - 验证 deploy_bundle/ 完整性
"""
import zipfile, re
from pathlib import Path

ROOT = Path('d:/filework/worktrees/release-prep')
BUNDLE = ROOT / 'deploy_bundle'
ZIP = BUNDLE / 'deploy-v20260706_021.zip'
DEPLOY_SH = BUNDLE / 'deploy.sh'

print('========== deploy_bundle/ 完整性验证 ==========\n')

# 1. 文件清单
print('[1] deploy_bundle/ 文件清单:')
items = sorted(BUNDLE.iterdir(), key=lambda x: (x.is_file(), x.name))
for f in items:
    if f.is_file():
        print(f'   {f.name:40s} {f.stat().st_size:>10} bytes')
    else:
        n = sum(1 for _ in f.rglob('*'))
        print(f'   {f.name:40s} <dir, {n} entries>')
print(f'   TOTAL: {len(list(BUNDLE.iterdir()))} items\n')

# 2. zip 业务内容
print('[2] zip 业务内容 (deploy-v20260706_021.zip):')
with zipfile.ZipFile(ZIP) as z:
    names = z.namelist()
    tel = [n for n in names if n.startswith('telemetry/')]
    mcp = [n for n in names if n.startswith('mcp/')]
    meta = [n for n in names if n.startswith('meta/')]
    fdist = [n for n in names if n.startswith('frontend_dist_files/')]

    print(f'   total files:          {len(names)}')
    print(f'   meta/:                {len(meta)}')
    print(f'   frontend_dist_files/: {len(fdist)}')
    print(f'   telemetry/:           {len(tel)}')
    print(f'   mcp/:                 {len(mcp)}')

    # V007.21 cache_manager fix
    c = z.read('meta/core/enums/cache_manager.py').decode()
    nc = '\n'.join(l for l in c.split('\n') if not l.lstrip().startswith('#'))
    async_n = len(re.findall(r'\basync\s+with\s+self\._lock', nc))
    sync_n = len(re.findall(r'^\s+with\s+self\._lock\s*:', nc, re.MULTILINE))
    print(f'   cache_manager V007.21:  async={async_n} (期望 0)  sync={sync_n} (期望 3)')

    # V007.20 保留
    c2 = z.read('meta/core/sql_connection_pool.py').decode()
    print(f'   busy_timeout=30000:     {"busy_timeout = 30000" in c2}')

    c3 = z.read('meta/services/import_export_service.py').decode()
    print(f'   skip_audit=True:        x{c3.count("skip_audit=True")} (期望 >= 9)')

    # 0 垃圾
    GARBAGE = ['.db', '.bak', '.backup', '.pyc', '__pycache__', 'logs/', 'screenshots/', '.db-wal', '.db-shm']
    garbage = [n for n in names for g in GARBAGE if g in n.lower()]
    print(f'   garbage files:          {len(garbage)} (期望 0)')

print()

# 3. deploy.sh 修复
print('[3] deploy.sh 修复:')
content = DEPLOY_SH.read_text(encoding='utf-8', errors='replace')
print(f'   size: {len(content)} bytes')

DQ = '"'
checks = [
    ('has VERSION_PATH 修复', f'VERSION_PATH={DQ}$DEPLOYMENTS_DIR/$VERSION{DQ}' in content),
    ('has mv meta/frontend_dist_files/MANIFEST/telemetry/mcp', 'for item in meta frontend_dist_files MANIFEST telemetry mcp' in content),
    ('has V007.21 内容检查', 'async with self._lock 未修复' in content),
    ('has busy_timeout 检查', 'busy_timeout.*30000' in content),
    ('has skip_audit 检查', 'skip_audit=True' in content),
    ('has MANIFEST mv 逻辑', 'mv "$DEPLOYMENTS_DIR/$item" "$VERSION_PATH/$item"' in content),
]
for name, ok in checks:
    print(f'   {name}: {ok}')

# 4. lib/ 完整性
print()
print('[4] lib/:')
lib_files = sorted((BUNDLE / 'lib').iterdir())
for f in lib_files:
    print(f'   {f.name:30s} {f.stat().st_size:>10} bytes')

# 5. CRLF 检查 (Windows PS 打包会带 CRLF, yonaa Linux bash 解析失败)
print()
print('[5] CRLF 检查 (Windows PS 打包会带 ^M, yonaa Linux bash 解析失败):')
sh_files = list(BUNDLE.rglob('*.sh'))
crlf_files = []
for f in sh_files:
    if b'\r\n' in f.read_bytes():
        crlf_files.append(f)
        rel = f.relative_to(BUNDLE)
        print(f'   [FAIL] CRLF: {rel}')
if not crlf_files:
    print(f'   [OK] {len(sh_files)} 个 .sh 全是 LF, yonaa bash 可直接解析')
else:
    print(f'   [FIX] 运行: python tools/fix_crlf_in_bundle.py')

# 6. 模拟 PHASE 0.5 行为
print()
print('[6] PHASE 0.5 模拟 (yonaa 状态):')
print('   yonaa 上: cache_manager 仍含 async with self._lock (旧版)')
print('   deploy.sh PHASE 0.5 触发条件:')
print('     - meta/ 存在 (deployments/meta 残留) → 跳过')
print('     - frontend_dist_files/ 存在 (deployments/frontend_dist_files 残留) → 跳过')
print('     - V007.21 cache_manager 检查 → [触发] NEED_UNZIP=true')
print('   PHASE 0.5 新加的 mv 逻辑:')
print('     - mkdir -p v20260706_021/')
print('     - mv 5 项 (meta/frontend_dist_files/MANIFEST/telemetry/mcp) 到 v20260706_021/')
print('     - 验证 VERSION_PATH/meta + VERSION_PATH/frontend_dist_files')
print('   预期结果: cache_manager 验证 0/3 ✓')

print()
print('========== 验证完成 ==========')
