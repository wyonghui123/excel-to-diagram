#!/usr/bin/env python3
"""
simulate_full_deploy.py - 完整模拟 yonaa 部署 V007.21

模拟 yonaa 状态:
  - /opt/app/deployments/ 根有 V007.21 刚解压的 meta/ frontend_dist_files/
  - v20260706_021/ 目录存在但空
  - current -> v20260706_021 软链接
  - 旧 v20260704_007/ 仍在 (但 cache_manager 仍是 async with)

模拟 deploy.sh 跑:
  1. PHASE 0.5 触发 (因为 cache_manager 含 async with self._lock)
  2. unzip deploy-v20260706_021.zip -d deployments/
  3. mkdir -p v20260706_021 + mv meta frontend_dist_files
  4. PHASE 7 切 current
  5. 验证 cache_manager async=0

[CHG 2026-07-06] V007.21 完整模拟
"""
import os, shutil, zipfile, re
from pathlib import Path

# 1. mock yonaa 状态
YONAA = Path(r'D:\filework\release-prep-worktree\deploy_bundle\.mock_yonaa_full')
if YONAA.exists():
    shutil.rmtree(YONAA)
YONAA.mkdir()

# deployments/ 根
DEPLOYMENTS = YONAA / 'deployments'
DEPLOYMENTS.mkdir()
(DEPLOYMENTS / 'v20260704_007' / 'meta' / 'core').mkdir(parents=True)
(DEPLOYMENTS / 'v20260704_007' / 'meta' / 'core' / 'enums').mkdir(parents=True)
(DEPLOYMENTS / 'v20260704_007' / 'frontend_dist_files').mkdir()
(DEPLOYMENTS / 'v20260704_007' / 'meta' / 'services').mkdir(parents=True)
(DEPLOYMENTS / 'v20260706_021').mkdir()  # 空目录!
# 模拟 V007.20 状态: cache_manager 仍 async with
(DEPLOYMENTS / 'v20260704_007' / 'meta' / 'core' / 'enums' / 'cache_manager.py').write_text('''import threading
class Cache:
    def __init__(self):
        self._lock = threading.Lock()
    async def set(self):
        async with self._lock:
            pass
    async def invalidate(self):
        async with self._lock:
            pass
    async def invalidate_all(self):
        async with self._lock:
            pass
''')
(DEPLOYMENTS / 'v20260704_007' / 'meta' / 'core' / 'sql_connection_pool.py').write_text('''# busy_timeout = 30000
def get(): return 1
''')
(DEPLOYMENTS / 'v20260704_007' / 'meta' / 'services' / 'import_export_service.py').write_text('''# skip_audit=True
def run(): return 1
''')

# current 软链接 - Windows 无权限, 用文件代替
current_link = YONAA / 'current'
if current_link.exists() or current_link.is_symlink():
    if current_link.is_symlink() or current_link.is_file():
        current_link.unlink()
    elif current_link.is_dir():
        shutil.rmtree(current_link)
current_link.mkdir()  # 作为目录占位 (模拟 current 指向 v20260706_021 空目录)
print(f'[MOCK] current/ (模拟空目录, 等同 v20260706_021/)')

# 模拟 yonaa 上有刚解压的 V007.21 内容 (上次失败的残留)
(DEPLOYMENTS / 'meta' / 'core' / 'enums').mkdir(parents=True, exist_ok=True)
(DEPLOYMENTS / 'meta' / 'services').mkdir(parents=True, exist_ok=True)
(DEPLOYMENTS / 'frontend_dist_files').mkdir(parents=True, exist_ok=True)

# 把 V007.21 zip 里的 cache_manager 写到 deployments/meta (模拟上次解压)
zf = zipfile.ZipFile(r'D:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
zf.extract('meta/core/enums/cache_manager.py', str(DEPLOYMENTS))
zf.extract('meta/core/sql_connection_pool.py', str(DEPLOYMENTS))
zf.extract('meta/services/import_export_service.py', str(DEPLOYMENTS))

print('[MOCK] yonaa 状态:')
print(f'  deployments/ 根有 V007.21 残留: meta/ frontend_dist_files/')
print(f'  v20260706_021/ 存在但空')
print(f'  v20260704_007/ 仍有 V007.20 代码 (cache_manager async with)')
print(f'  current -> v20260706_021 (空)')
print()

# 2. 跑 PHASE 0.5 触发条件 + 新加的 mv 逻辑
print('=== PHASE 0.5 模拟 ===')
SERVER_DIR = DEPLOYMENTS / 'meta'  # 当前 current 指向 v20260706_021, 但 current 是空, server_dir 还是 deployments/meta
VERSION = 'v20260706_021'
VERSION_PATH = DEPLOYMENTS / VERSION
ZIP_PATH = Path(r'D:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')

NEED_UNZIP = False

# 目录检查
if not (DEPLOYMENTS / 'meta').exists():
    NEED_UNZIP = True
    print('[触发] meta/ 不存在')
else:
    print('[跳过] meta/ 存在 (deployments/meta)')
if not (DEPLOYMENTS / 'frontend_dist_files').exists():
    NEED_UNZIP = True
    print('[触发] frontend_dist_files/ 不存在')
else:
    print('[跳过] frontend_dist_files/ 存在 (deployments/frontend_dist_files)')

# 内容检查
sql_pool = DEPLOYMENTS / 'v20260704_007' / 'meta' / 'core' / 'sql_connection_pool.py'
cache_mgr = DEPLOYMENTS / 'v20260704_007' / 'meta' / 'core' / 'enums' / 'cache_manager.py'
imp_exp = DEPLOYMENTS / 'v20260704_007' / 'meta' / 'services' / 'import_export_service.py'

# 注意: 内容检查的是 current 的 cache_manager, 但 current 指向空目录, 所以这些检查会失败
# 这里假设 PHASE 0.5 检查的是 current 软链接的目标
if sql_pool.exists():
    c = sql_pool.read_text(encoding='utf-8')
    if not re.search(r'busy_timeout.*30000', c):
        NEED_UNZIP = True
        print('[触发] busy_timeout=30000 修复未部署')
    else:
        print('[PASS] busy_timeout=30000 已部署')

if imp_exp.exists():
    c = imp_exp.read_text(encoding='utf-8')
    if 'skip_audit=True' not in c:
        NEED_UNZIP = True
        print('[触发] skip_audit 修复未部署')
    else:
        print('[PASS] skip_audit=True 已部署')

if cache_mgr.exists():
    c = cache_mgr.read_text(encoding='utf-8')
    no_comments = '\n'.join(l for l in c.split('\n') if not l.lstrip().startswith('#'))
    if re.search(r'\basync\s+with\s+self\._lock', no_comments):
        NEED_UNZIP = True
        print('[触发] V007.21 cache_manager async with self._lock 未修复')
    else:
        print('[PASS] cache_manager V007.21 已修复')

print()
print(f'NEED_UNZIP = {NEED_UNZIP}')
print()

if NEED_UNZIP:
    print('=== PHASE 0.5 unzip + 新加的 mv 逻辑 ===')
    # unzip
    with zipfile.ZipFile(ZIP_PATH) as zf2:
        zf2.extractall(str(DEPLOYMENTS))
    print(f'[OK] unzip {ZIP_PATH.name} → {DEPLOYMENTS}')

    # 创建 VERSION_PATH
    if not VERSION_PATH.exists():
        VERSION_PATH.mkdir()
        print(f'[OK] mkdir -p {VERSION_PATH}')
    elif not list(VERSION_PATH.iterdir()):
        print(f'[INFO] {VERSION_PATH} 已存在但空')

    # mv 根目录内容到 VERSION_PATH
    for item in ['meta', 'frontend_dist_files', 'MANIFEST', 'telemetry', 'mcp']:
        src = DEPLOYMENTS / item
        dst = VERSION_PATH / item
        if src.exists() and not dst.exists():
            shutil.move(str(src), str(dst))
            print(f'[OK] mv {src.name} → {VERSION_PATH.name}/{dst.name}')
        elif src.exists() and dst.exists():
            print(f'[SKIP] {src.name} 已存在于 {VERSION_PATH.name}')

    # 验证
    if (VERSION_PATH / 'meta').exists():
        print(f'[OK] VERSION_PATH/meta 就绪')
    if (VERSION_PATH / 'frontend_dist_files').exists():
        print(f'[OK] VERSION_PATH/frontend_dist_files 就绪')

    # 切 current 软链接 (Windows 用目录代替)
    if current_link.is_dir():
        shutil.rmtree(current_link)
    current_link.mkdir()
    print(f'[OK] current/ 更新 (模拟 current -> {VERSION_PATH.name})')

    # 验证 cache_manager V007.21 fix
    new_cache = VERSION_PATH / 'meta' / 'core' / 'enums' / 'cache_manager.py'
    if new_cache.exists():
        c = new_cache.read_text(encoding='utf-8')
        no_comments = '\n'.join(l for l in c.split('\n') if not l.lstrip().startswith('#'))
        async_n = len(re.findall(r'\basync\s+with\s+self\._lock', no_comments))
        sync_n = len(re.findall(r'^\s+with\s+self\._lock\s*:', no_comments, re.MULTILINE))
        print()
        print(f'[VERIFY] V007.21 cache_manager in VERSION_PATH:')
        print(f'  async with self._lock: {async_n} (期望 0)')
        print(f'  with self._lock::     {sync_n} (期望 3)')

# 清理
shutil.rmtree(YONAA)
print()
print('[OK] 模拟完成')
