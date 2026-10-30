# -*- coding: utf-8 -*-
"""[v160 2026-10-31] 变式物料 provenance + 唯一索引 + 物化权限

背景:
  二次对标头部产品后收紧 auto 物化的并发与溯源（spec
  2026-10-30-variant-item-materialization §12）:
  1. items 增两列，物理承载幂等键 (model_item_id, config_hash):
       variant_of_item_id  INTEGER REFERENCES items(id)
       variant_config_hash TEXT
  2. 建部分唯一索引 ux_items_variant_identity 兜底并发重复物化；
     普通物料两列为 NULL，不受约束影响。
  3. configuration:configuration_materialize 权限码落库；端点
     POST /api/v1/config/materialize 已挂 require_permission。

回填:
  从 configurations(variant_item_id → model_item_id / config_hash) 回填存量。
  若发现同一 (model, hash) 指向多个物料，先 raise 不建索引，需人工合并。

幂等:
  - 列已存在则跳过（PRAGMA table_info 探测）。
  - CREATE UNIQUE INDEX IF NOT EXISTS；权限 INSERT OR IGNORE。

回滚:
  列、索引与 permissions 行均保留（删列需重建表；权限可能已被角色授予）。
"""
import sqlite3
from pathlib import Path

COLUMNS = (
    ('items', 'variant_of_item_id', 'INTEGER REFERENCES items(id)'),
    ('items', 'variant_config_hash', 'TEXT'),
)

INDEX_NAME = 'ux_items_variant_identity'
INDEX_SQL = (
    f'CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME} '
    'ON items(variant_of_item_id, variant_config_hash) '
    'WHERE variant_of_item_id IS NOT NULL'
)

BACKFILL_SQL = (
    'UPDATE items SET '
    '  variant_of_item_id = ('
    '    SELECT c.model_item_id FROM configurations c'
    '    WHERE c.variant_item_id = items.id ORDER BY c.id LIMIT 1), '
    '  variant_config_hash = ('
    '    SELECT c.config_hash FROM configurations c'
    '    WHERE c.variant_item_id = items.id ORDER BY c.id LIMIT 1) '
    'WHERE id IN ('
    '  SELECT DISTINCT variant_item_id FROM configurations'
    '  WHERE variant_item_id IS NOT NULL)'
)

DUPLICATES_SQL = (
    'SELECT variant_of_item_id, variant_config_hash, COUNT(*) AS n '
    'FROM items WHERE variant_of_item_id IS NOT NULL '
    'GROUP BY variant_of_item_id, variant_config_hash HAVING COUNT(*) > 1'
)

PERMISSION = (
    'configuration:configuration_materialize',
    '物化配置实例',
    'configuration',
    'materialize',
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> dict:
    return {row[1]: row for row in conn.execute(f'PRAGMA table_info({table})')}


def _do_columns(conn: sqlite3.Connection) -> None:
    added = 0
    for table, column, definition in COLUMNS:
        if not _table_exists(conn, table):
            print(f'  - [SKIP] 表 {table} 不存在, 跳过 {column}')
            continue
        if column in _columns(conn, table):
            print(f'  - [SKIP] {table}.{column} 已存在')
            continue
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
        added += 1
        print(f'  - [NEW] {table}.{column}')
    print(f'  - [SUMMARY] columns: +{added} 新增')


def _do_backfill(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'configurations'):
        print('  - [SKIP] configurations 表不存在, 跳过回填')
        return
    conn.execute(BACKFILL_SQL)
    done = conn.execute(
        'SELECT COUNT(*) FROM items WHERE variant_of_item_id IS NOT NULL'
    ).fetchone()[0]
    print(f'  - [BACKFILL] 变式物料 provenance 回填 {done} 行')


def _check_duplicates(conn: sqlite3.Connection) -> None:
    rows = conn.execute(DUPLICATES_SQL).fetchall()
    if rows:
        detail = ', '.join(
            f'(model={r[0]}, hash={r[1]})×{r[2]}' for r in rows[:5])
        raise RuntimeError(
            f'存在同 (model, hash) 指向多个物料的存量行，需人工合并后再建唯一索引: {detail}')


def _do_index(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'items'):
        print('  - [SKIP] items 表不存在, 跳过唯一索引')
        return
    _check_duplicates(conn)
    if _index_exists(conn, INDEX_NAME):
        print(f'  - [SKIP] 索引 {INDEX_NAME} 已存在')
        return
    conn.execute(INDEX_SQL)
    print(f'  - [NEW] 唯一索引 {INDEX_NAME}')


def _do_permissions(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'permissions'):
        print('  - permissions 表不存在, 跳过权限写入')
        return
    cur = conn.execute(
        "INSERT OR IGNORE INTO permissions (code, name, resource_type, action) "
        "VALUES (?, ?, ?, ?)", PERMISSION)
    if cur.rowcount:
        print(f'  - [NEW] 权限 {PERMISSION[0]} ({PERMISSION[1]})')
    else:
        print(f'  - [SKIP] 权限 {PERMISSION[0]} 已存在')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v160] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v160] 开始: 变式物料 provenance + 唯一索引 + 权限')
        conn.execute('BEGIN')
        _do_columns(conn)
        _do_backfill(conn)
        _do_index(conn)
        _do_permissions(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v160] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言两列、唯一索引、权限码与「无重复身份」四项。"""
    if not db_path.exists():
        print('[v160 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'items'):
            print('[v160 verify] FAIL: items 表不存在')
            return False
        info = _columns(conn, 'items')
        for _table, column, _definition in COLUMNS:
            if column not in info:
                print(f'[v160 verify] FAIL: 缺列 items.{column}')
                return False

        if not _index_exists(conn, INDEX_NAME):
            print(f'[v160 verify] FAIL: 缺唯一索引 {INDEX_NAME}')
            return False

        duplicates = conn.execute(DUPLICATES_SQL).fetchall()
        if duplicates:
            print(f'[v160 verify] FAIL: 重复变式身份 {duplicates[:5]}')
            return False

        if _table_exists(conn, 'permissions') and not conn.execute(
                'SELECT 1 FROM permissions WHERE code = ?',
                (PERMISSION[0],)).fetchone():
            print(f'[v160 verify] FAIL: 缺权限码 {PERMISSION[0]}')
            return False

        print(f'[v160 verify] OK: provenance 2 列 + {INDEX_NAME} + 权限码齐备')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """列、索引、permissions 行保留（删列需重建表；权限可能已授予角色）。"""
    print('[v160] downgrade: 列 / 索引 / permissions 行保留，无删除动作')
    return True


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v160] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v160] verify: {"PASS" if _v else "FAIL"}')
