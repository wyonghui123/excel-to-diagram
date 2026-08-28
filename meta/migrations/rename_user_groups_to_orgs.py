"""
[Phase 1] user_groups 系列 RENAME 为 orgs 系列 + 新增 org_type / org_scope 列

旧表 → 新表:
- user_groups → orgs
- user_group_members → org_members
- group_roles → org_permission_sets
- group_data_permissions → org_data_permissions

orgs 表新增列:
- org_type: TEXT DEFAULT 'department' (department/team/division/company/personal)
- org_scope: TEXT DEFAULT 'internal' (internal/external, 为二期预留)

修正说明 (2026-08-28, 当前 DB 状态):
- `group_data_permissions` 存在 (0 行), 直接 RENAME 即可
"""
import sqlite3

RENAME_PAIRS = [
    ('user_groups', 'orgs'),
    ('user_group_members', 'org_members'),
    ('group_roles', 'org_permission_sets'),
    ('group_data_permissions', 'org_data_permissions'),
]


def upgrade(conn: sqlite3.Connection) -> None:
    """执行 rename + 新增列 + 数据回填"""
    # 1. RENAME (跳过不存在的)
    for old_name, new_name in RENAME_PAIRS:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (old_name,)
        )
        if cur.fetchone() is None:
            print(f'  - {old_name} 不存在, 跳过 RENAME')
            continue
        conn.execute(f'ALTER TABLE {old_name} RENAME TO {new_name}')
        print(f'  ✓ RENAME {old_name} → {new_name}')

    # 2. 新增 org_type / org_scope 列
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='orgs'"
    )
    if cur.fetchone() is not None:
        conn.execute(
            "ALTER TABLE orgs ADD COLUMN org_type TEXT DEFAULT 'department'"
        )
        conn.execute(
            "ALTER TABLE orgs ADD COLUMN org_scope TEXT DEFAULT 'internal'"
        )
        print('  ✓ orgs 新增 org_type / org_scope 列')

        # 3. 数据回填 (启发式归类)
        _classify_org_type(conn)

    conn.commit()


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
        'company': 0, 'personal': 0, 'other': 0
    }

    for org_id, code, name in orgs:
        org_type = _guess_org_type(code, name)
        conn.execute(
            "UPDATE orgs SET org_type = ? WHERE id = ?",
            (org_type, org_id)
        )
        classified[org_type] = classified.get(org_type, 0) + 1

    print(f'  ✓ org_type 分类完成: {classified}')


def _guess_org_type(code: str, name: str) -> str:
    text = f'{code or ""} {name or ""}'.lower()
    if code and code.startswith('personal_group_user_'):
        return 'personal'
    if any(kw in text for kw in ['部门', '部', '处', '科']):
        return 'department'
    if any(kw in text for kw in ['公司', '事业部', 'division']):
        return 'division'
    if any(kw in text for kw in ['组', '团队']):
        return 'team'
    return 'team'


def downgrade(conn: sqlite3.Connection) -> None:
    """回滚 (逆序)"""
    for old_name, new_name in reversed(RENAME_PAIRS):
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (new_name,)
        )
        if cur.fetchone() is None:
            print(f'  - {new_name} 不存在, 跳过反向 RENAME')
            continue
        conn.execute(f'ALTER TABLE {new_name} RENAME TO {old_name}')
        print(f'  ✓ RENAME {new_name} → {old_name}')
    conn.commit()
