#!/usr/bin/env python3
"""
simulate_v46_deploy_pure.py - 纯 Python 模拟 V46 deploy.sh 跑 (无 subprocess bash)

[CHG 2026-07-06] Windows 无法 subprocess git-bash, 改用 Python 模拟 V46 deploy.sh 逻辑
"""
import os, shutil, subprocess, zipfile, re
from pathlib import Path

YONAA = Path(r'd:\filework\release-prep-worktree\deploy_bundle\.mock_yonaa_v46')
if YONAA.exists():
    shutil.rmtree(YONAA)
(YONAA / 'app' / 'deployments' / 'meta' / 'core' / 'enums').mkdir(parents=True)
(YONAA / 'app' / 'deployments' / 'meta' / 'services').mkdir(parents=True)
(YONAA / 'app' / 'deployments' / 'frontend_dist_files').mkdir(parents=True)
(YONAA / 'app' / 'deployments' / 'telemetry').mkdir()
(YONAA / 'app' / 'deployments' / 'mcp').mkdir()

ROOT = YONAA / 'app'
DEPLOYMENTS_DIR = ROOT / 'deployments'
SERVER_DIR = DEPLOYMENTS_DIR / 'meta'

# yonaa 修复后: meta/ 已有 V007.21 修复
(SERVER_DIR / 'core' / 'enums' / 'cache_manager.py').write_text('''import threading
class Cache:
    def __init__(self):
        self._lock = threading.Lock()
    def set(self):
        with self._lock:
            pass
    def invalidate(self):
        with self._lock:
            pass
    def invalidate_all(self):
        with self._lock:
            pass
''', encoding='utf-8')
(SERVER_DIR / 'core' / 'sql_connection_pool.py').write_text('def get():\n    conn.execute("PRAGMA busy_timeout = 30000")\n    return 1\n', encoding='utf-8')
(SERVER_DIR / 'services' / 'import_export_service.py').write_text('def run():\n    return skip_audit=True\n', encoding='utf-8')
# 模拟 yonaa 上现在状态: frontend_dist_files 是 V007.20 旧 dist (OLD_HASH)
(DEPLOYMENTS_DIR / 'frontend_dist_files' / 'index.html').write_text('<html><script src="index-OLD_HASH.js"></script></html>\n', encoding='utf-8')
(DEPLOYMENTS_DIR / 'MANIFEST').write_text('version: v20260704_007\n', encoding='utf-8')

# zip (V007.21)
ZIP = DEPLOYMENTS_DIR / 'deploy-v20260706_021.zip'
shutil.copy(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip', ZIP)

# current 软链接 (用目录代替)
current_link = ROOT / 'current'
current_link.mkdir()

print('[MOCK] yonaa 修复后状态:')
print(f'  DEPLOYMENTS_DIR/meta/  (V007.21 修复)')
print(f'  DEPLOYMENTS_DIR/frontend_dist_files/  (含 OLD_HASH)')
print(f'  DEPLOYMENTS_DIR/MANIFEST')
print(f'  DEPLOYMENTS_DIR/telemetry/')
print(f'  DEPLOYMENTS_DIR/mcp/')
print(f'  DEPLOYMENTS_DIR/v20260706_021.zip  (V007.21 zip 含 NEW_HASH index-48IrQ6VL.js)')
print(f'  /opt/app/current -> v20260706_021  (断链)')
print()

# ====== PHASE 0.5 模拟 ======
print('========== PHASE 0.5 ==========')
NEED_UNZIP = False

# meta/ 存在
if (DEPLOYMENTS_DIR / 'meta').exists():
    print('[OK] meta/ 已存在')
else:
    NEED_UNZIP = True
    print('[触发] meta/ 不存在')

# frontend_dist_files/ 存在
if (DEPLOYMENTS_DIR / 'frontend_dist_files').exists():
    print('[OK] frontend_dist_files/ 已存在')
else:
    NEED_UNZIP = True
    print('[触发] frontend_dist_files/ 不存在')

# busy_timeout 验证
sql_pool = SERVER_DIR / 'core' / 'sql_connection_pool.py'
if sql_pool.exists():
    c = sql_pool.read_text(encoding='utf-8')
    if re.search(r'busy_timeout.*30000', c):
        print('[OK] busy_timeout=30000 已部署')
    else:
        NEED_UNZIP = True
        print('[触发] busy_timeout=30000 未部署')

# skip_audit 验证
imp_exp = SERVER_DIR / 'services' / 'import_export_service.py'
if imp_exp.exists():
    c = imp_exp.read_text(encoding='utf-8')
    if 'skip_audit=True' in c:
        print('[OK] skip_audit=True 已部署')
    else:
        NEED_UNZIP = True
        print('[触发] skip_audit=True 未部署')

# V007.21 cache_manager 验证
cache_mgr = SERVER_DIR / 'core' / 'enums' / 'cache_manager.py'
if cache_mgr.exists():
    c = cache_mgr.read_text(encoding='utf-8')
    nc = '\n'.join(l for l in c.split('\n') if not l.lstrip().startswith('#'))
    if re.search(r'\basync\s+with\s+self\._lock', nc):
        NEED_UNZIP = True
        print('[触发] V007.21 cache_manager async with 未修复')
    else:
        print('[OK] V007.21 cache_manager 已修复')

print()
print(f'NEED_UNZIP = {NEED_UNZIP}')
print()

# ====== unzip 或 skip ======
if NEED_UNZIP:
    print('========== unzip ==========')
    with zipfile.ZipFile(ZIP) as zf:
        zf.extractall(DEPLOYMENTS_DIR)
    print(f'[OK] unzip {ZIP.name} → {DEPLOYMENTS_DIR}')

    # 验证 SERVER_DIR
    if (SERVER_DIR).exists():
        print(f'[OK] {SERVER_DIR} 已就绪')
    if (DEPLOYMENTS_DIR / 'frontend_dist_files').exists():
        print(f'[OK] frontend_dist_files/ 已就绪')

    # dist hash 验证
    ZIP_INDEX_HASH = None
    with zipfile.ZipFile(ZIP) as zf:
        try:
            idx = zf.read('frontend_dist_files/index.html').decode()
            m = re.search(r'index-([A-Za-z0-9_-]+)\.js', idx)
            if m:
                ZIP_INDEX_HASH = m.group(0)
        except KeyError:
            pass
    if ZIP_INDEX_HASH:
        print(f'[INFO] zip 内 index.html 引用: {ZIP_INDEX_HASH}')
        idx = (DEPLOYMENTS_DIR / 'frontend_dist_files' / 'index.html').read_text(encoding='utf-8')
        m = re.search(r'index-([A-Za-z0-9_-]+)\.js', idx)
        if m:
            ACTUAL = m.group(0)
            print(f'[INFO] root index.html 引用: {ACTUAL}')
            if ZIP_INDEX_HASH == ACTUAL:
                print('[OK] dist hash 一致')
            else:
                print('[FAIL] dist hash 不一致 - V46 deploy.sh 会 die')
else:
    print('========== skip unzip ==========')
    # dist hash 验证 (V46 即使 --skip-unzip 也验证)
    with zipfile.ZipFile(ZIP) as zf:
        try:
            idx = zf.read('frontend_dist_files/index.html').decode()
            m = re.search(r'index-([A-Za-z0-9_-]+)\.js', idx)
            if m:
                ZIP_INDEX_HASH = m.group(0)
        except KeyError:
            pass
    if ZIP_INDEX_HASH:
        print(f'[INFO] zip 内 index.html 引用: {ZIP_INDEX_HASH}')
        idx = (DEPLOYMENTS_DIR / 'frontend_dist_files' / 'index.html').read_text(encoding='utf-8')
        m = re.search(r'index-([A-Za-z0-9_-]+)\.js', idx)
        if m:
            ACTUAL = m.group(0)
            print(f'[INFO] root index.html 引用: {ACTUAL}')
            if ZIP_INDEX_HASH == ACTUAL:
                print('[OK] dist hash 一致')
            else:
                print('[FAIL] dist hash 不一致 - V46 deploy.sh 会 die')

print()
print('========== 模拟完成 ==========')

# 清理
shutil.rmtree(YONAA)
