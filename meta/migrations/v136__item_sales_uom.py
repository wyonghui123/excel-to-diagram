# -*- coding: utf-8 -*-
"""[v136] 物料默认销售单位：索引 + 存量可换算性核查

依据:
  docs/superpowers/specs/2026-10-26-sales-order-master-data-gap-spec.md
    §2.3 字段契约 / §2.7 迁移与回滚

背景:
  订单行单位必填但原先没有默认来源。新增 `items.sales_uom`（可空，FK uom），
  订单行创建时按 `sales_uom → base_uom` 带出默认单位。

本迁移只做 YAML 管不到的事（列由 sync_schema 按 YAML 生成，不重复建表/建列）:
  1. 断言 items.sales_uom 已存在且可空（NOT NULL = 0）
  2. 建非唯一索引 idx_item_sales_uom（IF NOT EXISTS）
  3. 输出存量订单行的不可换算清单：
     sales_order_lines JOIN items，取 uom_id 非空、i.base_uom 非空且两者不同的行，
     逐行用 UomQuantityService.is_compatible 判定，只打印 False 的行；
     None（数据不足）跳过、不阻断。

幂等:
  索引 CREATE INDEX IF NOT EXISTS；已存在只输出 [SKIP]。重复执行只输出 [SKIP]。

回滚:
  只删索引；列与数据保留（列由 YAML 声明，删列会造成数据不可解释）。
"""
import sqlite3
from pathlib import Path

TABLE = 'items'
COLUMN = 'sales_uom'
INDEX = 'idx_item_sales_uom'

#: 存量核查 SQL（§2.7 上线前存量核查）
_CANDIDATE_SQL = (
    'SELECT l.id AS line_id, l.item_id, l.uom_id, i.base_uom '
    'FROM sales_order_lines l '
    'JOIN items i ON i.id = l.item_id '
    'WHERE l.uom_id IS NOT NULL '
    '  AND i.base_uom IS NOT NULL '
    '  AND l.uom_id <> i.base_uom'
)


class _ConnDataSource:
    """最小数据源适配：把 sqlite3 查询结果转成 dict 列表。"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def query(self, sql, params):
        cur = self.conn.execute(sql, params)
        columns = [c[0] for c in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _column_info(conn: sqlite3.Connection, table: str) -> dict:
    if not _table_exists(conn, table):
        return {}
    return {row[1]: row for row in conn.execute(f'PRAGMA table_info({table})')}


def _index_sql(conn: sqlite3.Connection, name: str):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone()
    return row[0] if row else None


def _incompatible_lines(conn: sqlite3.Connection):
    """返回 [(line_id, item_id, uom_id, base_uom)]，仅 False 的行。"""
    from meta.services.uom_quantity_service import UomQuantityService

    try:
        rows = conn.execute(_CANDIDATE_SQL).fetchall()
    except sqlite3.Error as e:
        print(f'  - [WARN] 存量核查跳过（查询失败: {e}）')
        return []

    service = UomQuantityService(_ConnDataSource(conn))
    bad = []
    for row in rows:
        line_id, item_id, uom_id, base_uom = row
        compatible = service.is_compatible(item_id, uom_id, base_uom)
        if compatible is False:
            bad.append((line_id, item_id, uom_id, base_uom))
        # None = 数据不足，跳过不阻断
    return bad


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v136] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v136] 开始: 物料销售单位索引 + 存量可换算性核查')
        info = _column_info(conn, TABLE)
        if not info:
            print(f'[v136] 表 {TABLE} 不存在：请先执行 '
                  f'`python -m meta.tools.sync_schema --source sqlite '
                  f'--local {db_path} --execute` 建列')
            return False
        if COLUMN not in info:
            print(f'[v136] 列 {TABLE}.{COLUMN} 不存在：请先执行 sync_schema 建列')
            return False
        if info[COLUMN][3] != 0:
            print(f'[v136] 列 {TABLE}.{COLUMN} 应为可空（NOT NULL=0），'
                  f'实际 NOT NULL={info[COLUMN][3]}')
            return False

        if _index_sql(conn, INDEX):
            print(f'  - [SKIP] 索引 {INDEX} 已存在')
        else:
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS {INDEX} ON {TABLE}({COLUMN})')
            print(f'  - [NEW] 索引 {INDEX} ({COLUMN}) 非唯一')

        bad = _incompatible_lines(conn)
        if bad:
            print(f'  - [CHECK] 存量订单行 {len(bad)} 条单位不可换算（需人工修正）：')
            for line_id, item_id, uom_id, base_uom in bad:
                print(f'      line_id={line_id} item_id={item_id} '
                      f'uom_id={uom_id} base_uom={base_uom}')
        else:
            print('  - [CHECK] 存量订单行无「可判定为不可换算」的单位')

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v136] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言 items.sales_uom 存在且可空、索引存在。"""
    if not db_path.exists():
        print('[v136 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        info = _column_info(conn, TABLE)
        if COLUMN not in info:
            print(f'[v136 verify] FAIL: 缺列 {TABLE}.{COLUMN}')
            return False
        if info[COLUMN][3] != 0:
            print(f'[v136 verify] FAIL: {TABLE}.{COLUMN} 应可空'
                  f'（空 = 使用基本单位）')
            return False

        sql = _index_sql(conn, INDEX)
        if not sql:
            print(f'[v136 verify] FAIL: 缺索引 {INDEX}')
            return False
        if 'SALES_UOM' not in sql.upper():
            print(f'[v136 verify] FAIL: {INDEX} 口径不是 ({COLUMN})')
            return False

        print(f'[v136 verify] OK: {TABLE}.{COLUMN} 可空，{INDEX} 就位')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """只删索引；列与数据由 YAML 管理、保留。"""
    if not db_path.exists():
        print(f'[v136] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if _index_sql(conn, INDEX):
            conn.execute(f'DROP INDEX {INDEX}')
            print(f'  - [DROP] 索引 {INDEX}')
        else:
            print(f'  - [SKIP] 索引 {INDEX} 不存在')
        print(f'  - [KEEP] 列 {TABLE}.{COLUMN} 与数据保留 (由 YAML 声明)')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v136] rollback 失败: {e}')
        raise
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
        print(f'[v136] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v136] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v136] verify: {"PASS" if _v else "FAIL"}')
