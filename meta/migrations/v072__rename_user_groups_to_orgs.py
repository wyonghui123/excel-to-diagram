"""
[Phase 1 / Plan A Task 4] user_groups 系列 RENAME 为 orgs 系列 + 新增 org_type / org_scope 列

旧表 → 新表:
- user_groups → orgs
- user_group_members → org_members
- group_roles → org_permission_sets
- group_data_permissions → org_data_permissions

orgs 表新增列:
- org_type: TEXT DEFAULT 'department' (department/team/division/company/personal)
- org_scope: TEXT DEFAULT 'internal' (internal/external, 为二期预留)

规范遵循 (meta/migrations/README.md):
- 文件命名: v<NNN>__<desc>.py (v072)
- 入口签名: migrate(db_path, skip_backup=False) -> bool
- 幂等性: 每个 RENAME 前检查 new_name 是否已存在

修正说明 (2026-08-28, 当前 DB 状态):
- `group_data_permissions` 存在 (0 行), 直接 RENAME 即可
"""
import sqlite3
from pathlib import Path

RENAME_PAIRS = [
    ('user_groups', 'orgs'),
    ('user_group_members', 'org_members'),
    ('group_roles', 'org_permission_sets'),
    ('group_data_permissions', 'org_data_permissions'),
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cur.fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(r[1] == column for r in cur.fetchall())


def _classify_org_type(conn: sqlite3.Connection) -> None:
    """
    启发式归类:
    - personal_group_user_* → org_type='personal'
    - 含 部门/部/处/科 → org_type='department'
    - 含 公司/事业部/division → org_type='division'
    - 含 组/团队 → org_type='team'
    - 其它 → org_type='team' (默认)
    """
    cur = conn.execute("SELECT id, code, name FROM orgs")
    orgs = cur.fetchall()

    classified = {
        'department': 0, 'team': 0, 'division': 0,
        'company': 0, 'personal': 0, 'other': 0,
    }

    for org_id, code, name in orgs:
        org_type = _guess_org_type(code, name)
        conn.execute(
            "UPDATE orgs SET org_type = ? WHERE id = ?",
            (org_type, org_id),
        )
        classified[org_type] = classified.get(org_type, 0) + 1

    print(f'  org_type 分类完成: {classified}')


def _guess_org_type(code: str, name: str) -> str:
    text = f'{code or ""} {name or ""}'.lower()
    # personal 必须最先判断 (含"组"字的个人组)
    if code and code.startswith('personal_group_user_'):
        return 'personal'
    if any(kw in text for kw in ['部门', '部', '处', '科']):
        return 'department'
    if any(kw in text for kw in ['公司', '事业部', 'division']):
        return 'division'
    if any(kw in text for kw in ['组', '团队']):
        return 'team'
    return 'team'


def _do_upgrade(conn: sqlite3.Connection) -> None:
    """执行 rename + 新增列 + 数据回填 (幂等)"""
    # 1. RENAME (跳过不存在的, 或 new_name 已存在的)
    for old_name, new_name in RENAME_PAIRS:
        if not _table_exists(conn, old_name):
            print(f'  - {old_name} 不存在, 跳过 RENAME')
            continue
        if _table_exists(conn, new_name):
            print(f'  - {new_name} 已存在, 跳过 RENAME {old_name} → {new_name}')
            continue
        conn.execute(f'ALTER TABLE {old_name} RENAME TO {new_name}')
        print(f'  RENAME {old_name} → {new_name}')

    # 2. 新增 org_type / org_scope 列 (幂等: 已存在则跳过)
    if _table_exists(conn, 'orgs'):
        if not _column_exists(conn, 'orgs', 'org_type'):
            conn.execute(
                "ALTER TABLE orgs ADD COLUMN org_type TEXT DEFAULT 'department'"
            )
            print('  orgs 新增 org_type 列')
        if not _column_exists(conn, 'orgs', 'org_scope'):
            conn.execute(
                "ALTER TABLE orgs ADD COLUMN org_scope TEXT DEFAULT 'internal'"
            )
            print('  orgs 新增 org_scope 列')

        # 3. 数据回填 (启发式归类)
        _classify_org_type(conn)


def _do_downgrade(conn: sqlite3.Connection) -> None:
    """回滚 (逆序 RENAME; 不删除 org_type / org_scope 列, 因 SQLite 不支持 DROP COLUMN)"""
    for old_name, new_name in reversed(RENAME_PAIRS):
        if not _table_exists(conn, new_name):
            print(f'  - {new_name} 不存在, 跳过反向 RENAME')
            continue
        if _table_exists(conn, old_name):
            print(f'  - {old_name} 已存在, 跳过反向 RENAME {new_name} → {old_name}')
            continue
        conn.execute(f'ALTER TABLE {new_name} RENAME TO {old_name}')
        print(f'  RENAME {new_name} → {old_name}')
    print('  注: org_type / org_scope 列保留 (SQLite 不支持 DROP COLUMN, '
          '需要 SQLite >= 3.35 + 12-step 流程才能安全删除)')


# ─── 入口签名 (meta/migrations/README.md §2) ───

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """
    v072: rename user_groups → orgs + add org_type / org_scope

    Args:
        db_path: SQLite 数据库路径
        skip_backup: 是否跳过备份 (runner 已统一备份, 内部可跳过)

    Returns:
        True 如果成功执行或已执行 (幂等)
    """
    if not db_path.exists():
        print(f'[v072] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v072] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """验证 v072: orgs 系列表存在 + org_type/org_scope 列存在"""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        new_tables = [new for _, new in RENAME_PAIRS]
        for t in new_tables:
            if not _table_exists(conn, t):
                return False
        if not _column_exists(conn, 'orgs', 'org_type'):
            return False
        if not _column_exists(conn, 'orgs', 'org_scope'):
            return False
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """回滚 v072 (反向 RENAME, 保留新增列)"""
    if not db_path.exists():
        print(f'[v072] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v072] downgrade 失败: {e}')
        raise
    finally:
        conn.close()