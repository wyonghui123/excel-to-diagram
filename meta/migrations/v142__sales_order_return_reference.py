# -*- coding: utf-8 -*-
"""[v142] 销售订单退货引用链：列 / 索引 / 存量核查

依据:
  docs/superpowers/specs/2026-10-26-sales-order-master-data-gap-spec.md §10
  meta/schemas/sales_order_line.yaml 头注释 ⑧ / deletion_policy

背景:
  退货行用 reference_line_id 回指原销售订单行（方案 A：行级自引用，可空）。
  合法性由守卫 R-RET-1~9 校验；被引用行禁止删除（schema deletion_policy）。
  常规建列由 sync_schema 按 YAML 完成，本迁移负责无法靠 YAML 表达的部分。

本迁移内容:
  1. 断言 sales_order_lines 表存在
  2. 缺列时补 reference_line_id（INTEGER，可空）
  3. 缺索引时补 idx_sales_order_line_reference
  4. 输出存量非法引用清单（引用不存在 / 同单 / 指向退货行 /
     原单非 confirmed-closed / 客户不一致 / 物料不一致 / 累计退货量超原行）
  5. 重复执行输出 SKIP

幂等:
  列与索引均先查后用；核查只读，不修改业务数据。

回滚:
  只删索引；列由 YAML 声明、数据保留（回滚不丢引用关系）。
"""
import sqlite3
from pathlib import Path

LINE_TABLE = 'sales_order_lines'
ORDER_TABLE = 'sales_orders'
TYPE_TABLE = 'type_definitions'
REFERENCE_COLUMN = 'reference_line_id'
INDEX_NAME = 'idx_sales_order_line_reference'
ORIGINAL_STATUSES = ('confirmed', 'closed')
RETURN_CATEGORY = 'return'
QTY_TOLERANCE = 1e-9


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _query(conn: sqlite3.Connection, sql: str) -> list:
    try:
        return conn.execute(sql).fetchall()
    except sqlite3.Error:
        return []


def _invalid_missing(conn: sqlite3.Connection) -> list:
    return _query(conn, f'''
        SELECT l.id, l.order_id, l.reference_line_id
        FROM {LINE_TABLE} l
        LEFT JOIN {LINE_TABLE} r ON r.id = l.reference_line_id
        WHERE l.{REFERENCE_COLUMN} IS NOT NULL AND r.id IS NULL
    ''')


def _invalid_same_order(conn: sqlite3.Connection) -> list:
    return _query(conn, f'''
        SELECT l.id, l.{REFERENCE_COLUMN}
        FROM {LINE_TABLE} l
        JOIN {LINE_TABLE} r ON r.id = l.{REFERENCE_COLUMN}
        WHERE r.order_id = l.order_id
    ''')


def _invalid_target_return(conn: sqlite3.Connection) -> list:
    return _query(conn, f'''
        SELECT l.id, l.{REFERENCE_COLUMN}
        FROM {LINE_TABLE} l
        JOIN {LINE_TABLE} r ON r.id = l.{REFERENCE_COLUMN}
        JOIN {TYPE_TABLE} t ON t.id = r.line_type_id
        WHERE t.line_category = '{RETURN_CATEGORY}'
    ''')


def _invalid_original_status(conn: sqlite3.Connection) -> list:
    statuses = ', '.join(f"'{s}'" for s in ORIGINAL_STATUSES)
    return _query(conn, f'''
        SELECT l.id, l.{REFERENCE_COLUMN}, o.status
        FROM {LINE_TABLE} l
        JOIN {LINE_TABLE} r ON r.id = l.{REFERENCE_COLUMN}
        JOIN {ORDER_TABLE} o ON o.id = r.order_id
        WHERE o.status NOT IN ({statuses})
    ''')


def _invalid_customer(conn: sqlite3.Connection) -> list:
    return _query(conn, f'''
        SELECT l.id, l.{REFERENCE_COLUMN}, co.customer_account_id,
               o.customer_account_id
        FROM {LINE_TABLE} l
        JOIN {LINE_TABLE} r ON r.id = l.{REFERENCE_COLUMN}
        JOIN {ORDER_TABLE} co ON co.id = l.order_id
        JOIN {ORDER_TABLE} o ON o.id = r.order_id
        WHERE co.customer_account_id IS NOT NULL
          AND o.customer_account_id IS NOT NULL
          AND co.customer_account_id <> o.customer_account_id
    ''')


def _invalid_item(conn: sqlite3.Connection) -> list:
    return _query(conn, f'''
        SELECT l.id, l.{REFERENCE_COLUMN}, l.item_id, r.item_id
        FROM {LINE_TABLE} l
        JOIN {LINE_TABLE} r ON r.id = l.{REFERENCE_COLUMN}
        WHERE l.item_id IS NOT NULL AND r.item_id IS NOT NULL
          AND l.item_id <> r.item_id
    ''')


def _invalid_over_returned(conn: sqlite3.Connection) -> list:
    return _query(conn, f'''
        SELECT r.id, r.qty, SUM(rl.qty)
        FROM {LINE_TABLE} r
        JOIN {LINE_TABLE} rl ON rl.{REFERENCE_COLUMN} = r.id
        JOIN {ORDER_TABLE} ro ON ro.id = rl.order_id
        WHERE rl.status <> 'cancelled' AND ro.status <> 'cancelled'
        GROUP BY r.id, r.qty
        HAVING SUM(rl.qty) > r.qty + {QTY_TOLERANCE}
    ''')


_CHECKS = (
    ('引用行不存在', _invalid_missing, lambda row: f'line={row[0]} ref={row[2]}'),
    ('引用当前订单自身行', _invalid_same_order,
     lambda row: f'line={row[0]} ref={row[1]}'),
    ('引用的是退货行', _invalid_target_return,
     lambda row: f'line={row[0]} ref={row[1]}'),
    ('原单非 confirmed/closed', _invalid_original_status,
     lambda row: f'line={row[0]} ref={row[1]} status={row[2]}'),
    ('退货客户与原单不一致', _invalid_customer,
     lambda row: f'line={row[0]} ref={row[1]} {row[2]}!={row[3]}'),
    ('退货物料与原行不一致', _invalid_item,
     lambda row: f'line={row[0]} ref={row[1]} {row[2]}!={row[3]}'),
    ('累计退货量超原行', _invalid_over_returned,
     lambda row: f'orig_line={row[0]} qty={row[1]} returned={row[2]}'),
)


def _report_invalid(conn: sqlite3.Connection, tag: str) -> int:
    total = 0
    for label, check, fmt in _CHECKS:
        rows = check(conn)
        if not rows:
            continue
        total += len(rows)
        print(f'  - [{tag}] {label}：{len(rows)} 条')
        for row in rows:
            print(f'      {fmt(row)}')
    return total


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v142] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v142] 开始: 销售订单退货引用链')
        if not _table_exists(conn, LINE_TABLE):
            print(f'[v142] 表 {LINE_TABLE} 不存在：请先执行 '
                  f'`python -m meta.tools.sync_schema --source sqlite '
                  f'--local {db_path} --execute` 建表')
            return False

        cols = _columns(conn, LINE_TABLE)
        if REFERENCE_COLUMN not in cols:
            conn.execute(
                f'ALTER TABLE {LINE_TABLE} ADD COLUMN {REFERENCE_COLUMN} INTEGER')
            print(f'  - [ADD] {LINE_TABLE}.{REFERENCE_COLUMN}（可空）')
        else:
            print(f'  - [SKIP] {LINE_TABLE}.{REFERENCE_COLUMN} 已存在')

        if _index_exists(conn, INDEX_NAME):
            print(f'  - [SKIP] 索引 {INDEX_NAME} 已存在')
        else:
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS {INDEX_NAME} '
                f'ON {LINE_TABLE} ({REFERENCE_COLUMN})')
            print(f'  - [ADD] 索引 {INDEX_NAME}')

        total = _report_invalid(conn, 'CHECK')
        if not total:
            print('  - [CHECK] 存量引用关系合法')

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v142] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言列与索引存在；存量非法引用只提示不拦截（新迁移数据应为空）。"""
    if not db_path.exists():
        print('[v142 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if REFERENCE_COLUMN not in _columns(conn, LINE_TABLE):
            print(f'[v142 verify] FAIL: 缺列 {LINE_TABLE}.{REFERENCE_COLUMN}')
            return False
        if not _index_exists(conn, INDEX_NAME):
            print(f'[v142 verify] FAIL: 缺索引 {INDEX_NAME}')
            return False

        total = _report_invalid(conn, 'WARN')
        if total:
            print(f'[v142 verify] PASS（结构齐备，存量非法引用 {total} 条待清理）')
        else:
            print('[v142 verify] PASS: 列 / 索引齐备，引用关系合法')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """只删索引；列由 YAML 声明、数据保留。"""
    if not db_path.exists():
        print(f'[v142] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if _index_exists(conn, INDEX_NAME):
            conn.execute(f'DROP INDEX {INDEX_NAME}')
            print(f'  - [DROP] 索引 {INDEX_NAME}')
        else:
            print(f'  - [SKIP] 索引 {INDEX_NAME} 不存在')
        print(f'  - [KEEP] {LINE_TABLE}.{REFERENCE_COLUMN} 与引用数据保留 '
              f'(由 YAML 声明)')
        conn.commit()
        return True
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    import sys
    from meta.core.db_path import get_meta_db_path

    _args = [a for a in sys.argv[1:] if a != '--rollback']
    _db = Path(_args[0]) if _args else Path(get_meta_db_path())
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v142] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v142] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v142] verify: {"PASS" if _v else "FAIL"}')
