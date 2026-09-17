#!/usr/bin/env python3
"""
simulate_v46_deploy.py - 完整模拟 V46 deploy.sh 跑
"""
import os, shutil, subprocess
from pathlib import Path

YONAA = Path(r'd:\filework\worktrees/release-prep\deploy_bundle\.mock_yonaa_v46')
if YONAA.exists():
    shutil.rmtree(YONAA)
(YONAA / 'app' / 'deployments' / 'meta' / 'core' / 'enums').mkdir(parents=True)
(YONAA / 'app' / 'deployments' / 'meta' / 'services').mkdir(parents=True)
(YONAA / 'app' / 'deployments' / 'frontend_dist_files').mkdir(parents=True)
(YONAA / 'app' / 'deployments' / 'telemetry').mkdir()
(YONAA / 'app' / 'deployments' / 'mcp').mkdir()

ROOT = YONAA / 'app'
DEPLOYMENTS_DIR = ROOT / 'deployments'

# yonaa 修复后: meta/ 已有 V007.21 修复
(DEPLOYMENTS_DIR / 'meta' / 'core' / 'enums' / 'cache_manager.py').write_text('''import threading
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
(DEPLOYMENTS_DIR / 'meta' / 'core' / 'sql_connection_pool.py').write_text('def get():\n    conn.execute("PRAGMA busy_timeout = 30000")\n    return 1\n', encoding='utf-8')
(DEPLOYMENTS_DIR / 'meta' / 'services' / 'import_export_service.py').write_text('def run():\n    return skip_audit=True\n', encoding='utf-8')
(DEPLOYMENTS_DIR / 'frontend_dist_files' / 'index.html').write_text('<html><script src="index-48IrQ6VL.js"></script></html>\n', encoding='utf-8')
(DEPLOYMENTS_DIR / 'MANIFEST').write_text('version: v20260706_021\n', encoding='utf-8')

# zip
ZIP = DEPLOYMENTS_DIR / 'deploy-v20260706_021.zip'
shutil.copy(r'd:\filework\worktrees/release-prep\deploy_bundle\deploy-v20260706_021.zip', ZIP)

# current 软链接 (用目录代替, Windows 无 symlink 权限)
current_link = ROOT / 'current'
current_link.mkdir()

print('[MOCK] yonaa 修复后状态:')
print(f'  DEPLOYMENTS_DIR/meta/  (V007.21 修复)')
print(f'  DEPLOYMENTS_DIR/frontend_dist_files/')
print(f'  DEPLOYMENTS_DIR/MANIFEST')
print(f'  DEPLOYMENTS_DIR/telemetry/')
print(f'  DEPLOYMENTS_DIR/mcp/')
print(f'  DEPLOYMENTS_DIR/v20260706_021.zip  (待部署)')
print(f'  /opt/app/current -> v20260706_021  (断链, V46 不在乎)')
print()

deploy_sh = Path(r'd:\filework\worktrees/release-prep\deploy_bundle\deploy.sh')
env = {
    **os.environ,
    'DEPLOY_ROOT': str(ROOT),
    'DEPLOYMENTS_DIR': str(DEPLOYMENTS_DIR),
    'DEPLOY_ZIP': str(ZIP),
}
print(f'env: DEPLOY_ROOT={env["DEPLOY_ROOT"]}')
print(f'env: DEPLOYMENTS_DIR={env["DEPLOYMENTS_DIR"]}')
print(f'env: DEPLOY_ZIP={env["DEPLOY_ZIP"]}')
print()

def to_bash_path(p: Path) -> str:
    """Convert Windows path to Git bash /c/... style"""
    s = str(p).replace('\\', '/')
    if ':' in s:
        drive = s[0].lower()
        s = '/' + drive + s[2:]
    return s

bash_cmd = f'"{to_bash_path(deploy_sh)}" --version v20260706_021 --port 3011 --skip-precheck'
bash = subprocess.run(
    [r'C:\Program Files\Git\bin\bash.exe', '-c', bash_cmd],
    env={k: to_bash_path(Path(v)) if isinstance(v, str) and (v.startswith('D:\\') or v.startswith('C:\\')) else v for k, v in env.items()},
    capture_output=True, text=True, timeout=60, shell=False
)

print('========== deploy.sh 输出 ==========')
print('--- STDOUT (前 5000 字符) ---')
print(bash.stdout[:5000])
if bash.stderr:
    print('--- STDERR (前 2000 字符) ---')
    print(bash.stderr[:2000])
print(f'Exit code: {bash.returncode}')

shutil.rmtree(YONAA)
