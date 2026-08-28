"""
[Phase 1] 新建 org_functions 表 (多职能视图, 对齐 spec 13 §5.1d)

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
"""
import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    """建表 + 默认数据"""
    # 1. 建表
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
    print('  ✓ 创建 org_functions 表')

    # 2. 创建索引
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_org_functions_org '
        'ON org_functions(org_id)'
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_org_functions_type '
        'ON org_functions(function_type)'
    )
    print('  ✓ 创建 org_functions 索引')

    # 3. 数据回填: 给所有现有 org 添加一条 administrative 主职能记录
    cur = conn.execute("SELECT id FROM orgs")
    org_ids = [r[0] for r in cur.fetchall()]

    for org_id in org_ids:
        conn.execute('''
            INSERT OR IGNORE INTO org_functions
                (org_id, function_type, is_primary)
            VALUES (?, 'administrative', 1)
        ''', (org_id,))

    print(f'  ✓ 默认给 {len(org_ids)} 个 org 添加 administrative 主职能记录')

    conn.commit()


def downgrade(conn: sqlite3.Connection) -> None:
    """删表"""
    conn.execute('DROP TABLE IF EXISTS org_functions')
    conn.commit()
