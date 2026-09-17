# -*- coding: utf-8 -*-
"""
[v085 2026-09-11] Spec 20 业务键锚点: 为维度表 code 列建单列索引

背景 (Spec 20 dimension scope business key):
  锚点子查询 WHERE code IN (...) 无法利用 (version_id, code) 联合唯一索引
  的最左前缀 (version_id 在最左, 纯 code 条件用不上).
  维度表 ≤ 数千行非当前瓶颈, 但索引廉价且随数据增长保平稳.

范围: RESOURCE_TABLE_MAP 中的四张维度表 (products / versions / domains /
sub_domains) 的 code 列. 其余维度表 (如 bo/service_module) 的 code 查询
由既有索引覆盖或数据量极小, 本迁移不动.

幂等: CREATE INDEX IF NOT EXISTS; 重复执行 no-op.
downgrade: DROP INDEX IF EXISTS.

说明: Spec 19 预留的 v085「manager_id 删列」顺延至 v087+ (本迁移先占 v085).
"""
import sqlite3
from pathlib import Path

INDEXES = [
    ('idx_products_bizkey_code', 'products', 'code'),
    ('idx_versions_bizkey_code', 'versions', 'code'),
    ('idx_domains_bizkey_code', 'domains', 'code'),
    ('idx_sub_domains_bizkey_code', 'sub_domains', 'code'),
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cur.fetchone() is not None


def _do_upgrade(conn: sqlite3.Connection) -> int:
    """建索引, 返回新建数量 (已存在的跳过)."""
    created = 0
    existing = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    for name, table, col in INDEXES:
        if not _table_exists(conn, table):
            print(f'  [v085] 表 {table} 不存在, 跳过索引 {name}')
            continue
        if name in existing:
            print(f'  [v085] 索引 {name} 已存在, 跳过')
            continue
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({col})")
        created += 1
        print(f'  [v085] created {name} ON {table}({col})')
    return created


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """[v085] 为维度表 code 列建单列索引 (锚点子查询加速)."""
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v085] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v085] 开始: 维度表 code 列单列索引')
        created = _do_upgrade(conn)
        conn.commit()
        print(f'  [v085] summary: created={created}/{len(INDEXES)}')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v085] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """验证: 四个索引全部存在 (对应表存在时)."""
    db_path = Path(db_path)
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        names = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        missing = [
            name for name, table, _ in INDEXES
            if _table_exists(conn, table) and name not in names
        ]
        if missing:
            print(f'  [v085 verify] FAIL: 缺少索引: {missing}')
            return False
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """回滚 v085: DROP 全部锚点 code 索引."""
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v085 downgrade] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for name, _, _ in INDEXES:
            conn.execute(f"DROP INDEX IF EXISTS {name}")
            print(f'  [v085 downgrade] dropped {name}')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v085 downgrade] 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('meta/architecture.db')
    print(f'[v085] running on {db}')
    success = migrate(db)
    print(f'[v085] success={success}, verify={verify(db)}')
