#!/usr/bin/env python3
"""
simulate_phase05_v00721.py - 模拟 yonaa 当前状态 + V007.21 deploy.sh PHASE 0.5 逻辑

模拟 yonaa 状态:
  - meta/ 已部署 (V007.20 + 手工 patch)
  - sql_connection_pool.py 含 busy_timeout=30000
  - import_export_service.py 含 skip_audit=True (×9)
  - cache_manager.py 仍含 async with self._lock (V007.20 状态)
  - frontend_dist_files/ 已部署

期望: NEED_UNZIP=true (cache_manager V007.21 修复未部署)
"""
import os, re
from pathlib import Path

# 1. 创建 mock yonaa 状态
STAGING = Path(r'D:\filework\release-prep-worktree\deploy_bundle\.mock_yonaa')
if STAGING.exists():
    import shutil
    shutil.rmtree(STAGING)
STAGING.mkdir()
(STAGING / 'meta' / 'core').mkdir(parents=True)
(STAGING / 'meta' / 'core' / 'enums').mkdir(parents=True)
(STAGING / 'meta' / 'services').mkdir(parents=True)
(STAGING / 'frontend_dist_files').mkdir(parents=True)

# V007.20 状态: cache_manager 仍 async with
(STAGING / 'meta' / 'core' / 'enums' / 'cache_manager.py').write_text('''import threading
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

# V007.20 状态: sql_connection_pool 有 busy_timeout=30000
(STAGING / 'meta' / 'core' / 'sql_connection_pool.py').write_text('''# busy_timeout = 30000
def get():
    return 1
''')

# V007.20 状态: import_export_service 有 skip_audit=True
(STAGING / 'meta' / 'services' / 'import_export_service.py').write_text('''# skip_audit=True
def run():
    return 1
''')

print(f'[MOCK] yonaa 当前状态:')
print(f'  meta/ 存在 (V007.20 + 手工 patch)')
print(f'  frontend_dist_files/ 存在')
print(f'  cache_manager.py 含 async with self._lock (3处, V007.20 状态)')
print(f'  sql_connection_pool.py 含 busy_timeout=30000')
print(f'  import_export_service.py 含 skip_audit=True')
print()

# 2. 跑 PHASE 0.5 逻辑 (从 deploy.sh line 169-203 提取)
SERVER_DIR = STAGING / 'meta'
DEPLOYMENTS_DIR = STAGING

NEED_UNZIP = False

# 目录检查 (新逻辑: 独立 if, 不是 elif)
if not (SERVER_DIR).exists():
    NEED_UNZIP = True
    print('[触发] meta/ 不存在')
else:
    print('[跳过] meta/ 存在')
if not (DEPLOYMENTS_DIR / 'frontend_dist_files').exists():
    NEED_UNZIP = True
    print('[触发] frontend_dist_files/ 不存在')
else:
    print('[跳过] frontend_dist_files/ 存在')

# 内容检查 1: busy_timeout
sql_pool = SERVER_DIR / 'core' / 'sql_connection_pool.py'
if sql_pool.exists():
    c = sql_pool.read_text(encoding='utf-8')
    if not re.search(r'busy_timeout.*30000', c):
        NEED_UNZIP = True
        print('[触发] busy_timeout=30000 修复未部署')
    else:
        print('[PASS] busy_timeout=30000 已部署')

# 内容检查 2: skip_audit
imp_exp = SERVER_DIR / 'services' / 'import_export_service.py'
if imp_exp.exists():
    c = imp_exp.read_text(encoding='utf-8')
    if 'skip_audit=True' not in c:
        NEED_UNZIP = True
        print('[触发] skip_audit 修复未部署')
    else:
        print('[PASS] skip_audit=True 已部署')

# 内容检查 3: cache_manager (V007.21)
cache_mgr = SERVER_DIR / 'core' / 'enums' / 'cache_manager.py'
if cache_mgr.exists():
    c = cache_mgr.read_text(encoding='utf-8')
    # 排除注释行
    no_comments = '\n'.join(l for l in c.split('\n') if not l.lstrip().startswith('#'))
    if re.search(r'\basync\s+with\s+self\._lock', no_comments):
        NEED_UNZIP = True
        print('[触发] V007.21 cache_manager async with self._lock 未修复')
    else:
        print('[PASS] cache_manager V007.21 已修复')

print()
print('=' * 50)
if NEED_UNZIP:
    print(f'[RESULT] NEED_UNZIP=true → 触发解压 (期望: V007.21 部署)')
else:
    print(f'[RESULT] NEED_UNZIP=false → 跳过解压 (期望: 跳过, 但 V007.21 修复未部署!)')

# 清理
import shutil
shutil.rmtree(STAGING)
