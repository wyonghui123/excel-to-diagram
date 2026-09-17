# -*- coding: utf-8 -*-
"""
[v089 2026-09-15] Spec 19 TBD-4 双表收敛：DROP legacy user_groups / user_group_members / roles

背景 (Spec 19 TBD-4, [19_org_admin_delegation.md §10 TBD-4](19_org_admin_delegation.md)):
  v072 已 RENAME roles → permission_sets, user_groups → orgs, user_group_members → org_members
  ([v072__rename_user_groups_to_orgs.py](v072__rename_user_groups_to_orgs.py))。
  v080 backup + v081 drop 应清理 legacy 表 ([v080__backup_spec16_legacy_tables.py](v080__backup_spec16_legacy_tables.py),
  [v081__drop_spec16_legacy_tables.py](v081__drop_spec16_legacy_tables.py))。
  但 2026-09-15 数据摸底 ([tools/v19_p2_audit_remote.py](tools/v19_p2_audit_remote.py)) 发现:
    - user_groups / user_group_members / roles 三张 legacy 表 **仍在 sqlite_master 中**
    - staging + prod 同状态 (rows=0 但表存在)
  根因推测: v081 DROP 走了 "DROP IF EXISTS _pre_v080_backup" 路径, 但 v080 backup 没真正 rename
  (legacy 表名还在), 导致 v081 跳过 DROP; 或 v081 在 prod 没跑过。

策略 (DROP-only, 幂等):
  1. DROP TABLE IF EXISTS user_groups;
  2. DROP TABLE IF EXISTS user_group_members;
  3. DROP TABLE IF EXISTS roles;
  (4. DROP TABLE IF EXISTS role_permissions; 等 8 张 spec16 衍生 legacy 表 — 若存在则一并清)

不动:
  - permission_sets / orgs / org_members (现行 schema)
  - v08x 衍生 backup 表 (*_pre_v080_backup, *_pre_v071_backup, *_pre_v083_backup, *_pre_v087_backup)
    — 这些是其他迁移的 audit 备份, 不能动

幂等性:
  - DROP TABLE IF EXISTS 在 SQLite 中天然幂等 (3.8+)
  - verify: 三张表不再出现在 sqlite_master

downgrade:
  不支持 (DROP 是不可逆; 恢复需要 DB .backup 还原)
"""
import sqlite3
import sys
from pathlib import Path

# Spec16 改名后已不使用的 legacy 表 (从 generated_schema.sql §初始化段 + init_auth_tables.py 枚举)
LEGACY_TABLES = [
    'user_groups',            # → orgs (v072)
    'user_group_members',     # → org_members (v072)
    'roles',                  # → permission_sets (v072)
    'role_permissions',       # → permission_set_permissions (v072)
    'role_menu_permissions',  # → permission_set_menu_permissions (v072)
    'role_data_permissions',  # → permission_set_data_permissions (v072)
    'role_dimension_scopes',  # → permission_set_dimension_scopes (v072)
    'role_effective_intents', # → permission_set_effective_intents (v072)
    'user_roles',             # → user_permission_sets (v072)
    'group_roles',            # → org_permission_sets (v072)
    'group_data_permissions', # → org_data_permissions (v072)
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """[v089 DROP] 幂等 DROP 11 张 legacy 表 + 报告."""
    if not db_path.exists():
        print(f'[v089] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v089] legacy 表 DROP 报告:')
        dropped = []
        for tbl in LEGACY_TABLES:
            if _table_exists(conn, tbl):
                cnt = conn.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
                conn.execute(f'DROP TABLE {tbl}')
                dropped.append(f'{tbl} (rows={cnt})')
                print(f'  - DROP {tbl} (rows={cnt} 丢弃; 期望为 0)')
            else:
                print(f'  - SKIP {tbl} (不存在)')
        conn.commit()
        print(f'[v089] 已 DROP {len(dropped)} 张表: {dropped}')
        return True
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """[v089 verify] 11 张 legacy 表均不存在."""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        for tbl in LEGACY_TABLES:
            n = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
                (tbl,),
            ).fetchone()[0]
            if n:
                print(f'[v089 verify] FAIL: {tbl} 仍存在')
                ok = False
            else:
                print(f'[v089 verify] OK: {tbl} 不存在')
        # 额外 verify: 现行表仍完好
        for tbl in ['orgs', 'org_members', 'permission_sets', 'permission_set_permissions']:
            n = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
                (tbl,),
            ).fetchone()[0]
            if not n:
                print(f'[v089 verify] FAIL: 现行表 {tbl} 不存在!')
                ok = False
        return ok
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """v089 无 downgrade (DROP 不可逆)."""
    print('[v089] downgrade not supported (DROP 不可逆; 从 DB .backup 恢复)')
    return False


if __name__ == '__main__':
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'architecture.db'
    print(f'[v089] migrating {db}')
    ok = migrate(db)
    print(f'[v089] migrate: {"OK" if ok else "FAIL"}')
    v = verify(db)
    print(f'[v089] verify: {"PASS" if v else "FAIL"}')
    sys.exit(0 if (ok and v) else 1)