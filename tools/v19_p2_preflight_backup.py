"""[v19 P2 preflight] v088/v089 deploy 前的冷备份 (DB .backup + 单独存放)

策略 (与 deploy 自带 backup 区分, 这是 deploy 前的安全网):
  - 走 sqlite3 .backup API hot copy (无需停服)
  - 备份文件命名: preflight_v088_v089_<stamp>.db
  - 备份位置: 与 DB 同目录, 便于手动回滚
  - 收集 manifest: db_size / table_count / schema_migrations COUNT

Usage:
  python tools/v19_p2_preflight_backup.py staging
  python tools/v19_p2_preflight_backup.py prod
  python tools/v19_p2_preflight_backup.py --both
"""
import json
import sys
from datetime import datetime

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from tools.staging_round import (
    remote_exec, _build_remote_py_helper, use_prod_gateway,
)


STAGING_DB = '/opt/app/staging/meta/architecture.db'
PROD_DB = '/opt/app/deployments/meta/architecture.db'

INLINE = '''
import sqlite3, os, json
DB_PATH = "%(db_path)s"
STAMP = "%(stamp)s"
BACKUP_PATH = f"{DB_PATH}.preflight_v088_v089_{STAMP}"

conn = sqlite3.connect(DB_PATH, timeout=30)
size = os.path.getsize(DB_PATH)
tbl_count = conn.execute(
    "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
).fetchone()[0]
mig_count = conn.execute(
    "SELECT COUNT(*) FROM schema_migrations"
).fetchone()[0] if any(r[0] == 'schema_migrations' for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()) else 0

# 报告 legacy 表状态 (v089 目标)
LEGACY = ['user_groups', 'user_group_members', 'roles', 'role_permissions',
          'role_menu_permissions', 'role_data_permissions', 'user_roles',
          'group_roles', 'group_data_permissions']
legacy = {}
for t in LEGACY:
    n = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (t,),
    ).fetchone()[0]
    if n:
        legacy[t] = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]

# 报告 is_manager / manager_id 状态 (v088 目标)
v088_legacy = {}
if any(r[0] == 'orgs' for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()):
    v088_legacy['orgs.manager_id'] = conn.execute(
        "SELECT COUNT(*) FROM orgs WHERE manager_id IS NOT NULL"
    ).fetchone()[0]
    v088_legacy['org_members.is_manager=1'] = conn.execute(
        "SELECT COUNT(*) FROM org_members WHERE is_manager = 1"
    ).fetchone()[0]

# 备份
backup_size = -1
backup_ok = False
try:
    bck = sqlite3.connect(BACKUP_PATH, timeout=30)
    conn.backup(bck)
    backup_size = os.path.getsize(BACKUP_PATH)
    bck.close()
    backup_ok = True
except Exception as e:
    print(f"BACKUP_ERROR: {e}")
conn.close()

manifest = {
    'stamp': STAMP,
    'db_path': DB_PATH,
    'backup_path': BACKUP_PATH if backup_ok else None,
    'db_size_bytes': size,
    'backup_size_bytes': backup_size,
    'table_count': tbl_count,
    'schema_migrations': mig_count,
    'legacy_tables_pre_v089': legacy,
    'v088_legacy_data': v088_legacy,
    'backup_ok': backup_ok,
}
print("MANIFEST_BEGIN")
print(json.dumps(manifest, indent=2, ensure_ascii=False))
print("MANIFEST_END")
'''


def backup(env: str, db_path: str, stamp: str) -> None:
    print(f'\n=== [{env}] preflight v088/v089 cold backup ===')
    if env == 'prod':
        use_prod_gateway()
    script = INLINE % {'db_path': db_path, 'stamp': stamp}
    remote_path = _build_remote_py_helper('v19pfbk', script)
    r = remote_exec(
        f'python3 {remote_path} && rm -f {remote_path}',
        timeout=120,
    )
    out = r.get('stdout', '')
    if 'MANIFEST_BEGIN' in out:
        start = out.index('MANIFEST_BEGIN') + len('MANIFEST_BEGIN')
        end = out.index('MANIFEST_END')
        manifest = json.loads(out[start:end].strip())
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        if manifest['backup_ok']:
            print(f'\n  [OK] BACKUP OK: {manifest["backup_path"]}')
            print(f'     size: {manifest["db_size_bytes"]:,} → '
                  f'{manifest["backup_size_bytes"]:,} bytes')
        else:
            print(f'\n  [FAIL] BACKUP FAIL')
    else:
        print(f'OUT: {out}')
        if r.get('stderr'):
            print('STDERR:', r['stderr'])


if __name__ == '__main__':
    args = sys.argv[1:]
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if '--both' in args or not args:
        backup('staging', STAGING_DB, stamp)
        backup('prod', PROD_DB, stamp)
    elif 'staging' in args:
        backup('staging', STAGING_DB, stamp)
    elif 'prod' in args:
        backup('prod', PROD_DB, stamp)
    else:
        print(f'usage: {sys.argv[0]} [staging|prod|--both]')