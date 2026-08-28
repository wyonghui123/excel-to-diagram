"""
[Phase 1 / Plan A Task 5] 新建 org_functions 表 (多职能视图, 对齐 spec 13 §5.1d)

Schema:
  org_functions(
    id INTEGER PK,
    org_id INTEGER FK orgs(id),
    function_type TEXT,
    is_primary BOOLEAN DEFAULT false,
    effective_from TIMESTAMP,
    effective_to TIMESTAMP,
    UNIQUE(org_id, function_type)
  )

设计要点:
- 一个 org 可同时是"行政组织"+"成本中心"+"利润中心" (多职能视图)
- is_primary=true 表示该职能是主职能 (一个 org 最多一个主职能)
- 默认每个 org 添加一条 administrative 主职能记录 (保证老数据默认正确)

规范遵循 (meta/migrations/README.md):
- 文件命名: v<NNN>__<desc>.py (v073)
- 入口签名: migrate(db_path, skip_backup=False) -> bool
- 幂等性: CREATE TABLE IF NOT EXISTS, INSERT OR IGNORE
- 依赖: v072 (orgs 表必须存在). 通过 FK 引用 + SELECT id FROM orgs
"""
import sqlite3
from pathlib import Path


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cur.fetchone() is not None


def prerequisites() -> list:
    """依赖: v072 必须先跑 (orgs 表必须存在)"""
    return ['v072__rename_user_groups_to_orgs']


def _do_upgrade(conn: sqlite3.Connection) -> None:
    """建表 + 默认数据 (幂等)"""
    # 1. 建表 (IF NOT EXISTS)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS org_functions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            function_type TEXT NOT NULL,
            is_primary BOOLEAN DEFAULT 0,
            effective_from TIMESTAMP,
            effective_to TIMESTAMP,
            FOREIGN KEY (org_id) REFERENCES orgs(id),
            UNIQUE(org_id, function_type)
        )
    ''')
    print('  创建 org_functions 表')

    # 2. 创建索引 (IF NOT EXISTS)
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_org_functions_org '
        'ON org_functions(org_id)'
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_org_functions_type '
        'ON org_functions(function_type)'
    )
    print('  创建 org_functions 索引')

    # 3. 数据回填: 给所有现有 org 添加一条 administrative 主职能记录
    #    依赖: orgs 表必须存在 (由 v072 创建)
    if not _table_exists(conn, 'orgs'):
        print('  ! orgs 表不存在, 跳过默认数据回填 (依赖 v072 先跑)')
        return

    cur = conn.execute("SELECT id FROM orgs")
    org_ids = [r[0] for r in cur.fetchall()]

    for org_id in org_ids:
        conn.execute('''
            INSERT OR IGNORE INTO org_functions
                (org_id, function_type, is_primary)
            VALUES (?, 'administrative', 1)
        ''', (org_id,))

    print(f'  默认给 {len(org_ids)} 个 org 添加 administrative 主职能记录')


def _do_downgrade(conn: sqlite3.Connection) -> None:
    """删表 (IF EXISTS)"""
    conn.execute('DROP TABLE IF EXISTS org_functions')
    print('  DROP org_functions')


# ─── 入口签名 (meta/migrations/README.md §2) ───

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """
    v073: create org_functions table

    Args:
        db_path: SQLite 数据库路径
        skip_backup: 是否跳过备份 (runner 已统一备份, 内部可跳过)

    Returns:
        True 如果成功执行或已执行 (幂等)
    """
    if not db_path.exists():
        print(f'[v073] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v073] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """验证 v073: org_functions 表存在"""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        return _table_exists(conn, 'org_functions')
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """回滚 v073 (DROP org_functions)"""
    if not db_path.exists():
        print(f'[v073] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v073] downgrade 失败: {e}')
        raise
    finally:
        conn.close()