# -*- coding: utf-8 -*-
"""[v134] 销售区域 M3：销售订单抬头 `territory_id` 快照列与索引

依据:
  docs/superpowers/specs/2026-10-26-sales-territory-design.md
    §4.5 sales_order.territory_id（新增，抬头快照）
    §5 R-TER-8（确认后冻结）
    §9 M3（订单 territory_id、带出与确认冻结）

背景:
  `sales_orders.territory_id` 由 `sales_order.yaml` 声明；正常路径由
  `python -m meta.tools.sync_schema --execute` 补列。本迁移在未跑 sync 的库上
  兜底补列，并确保 `idx_sales_order_territory` 存在（列表按区域过滤与数据范围
  过滤都走这列，不给客户分配表加回查）。

不做的:
  · 不回填历史订单：存量订单当时无区域归属，按「未分配」呈现（§6.2 fail-open）
  · 不建行级快照（§4.5 / D-TER-4）

幂等:
  列已存在 / 索引已存在只输出 [SKIP]；sales_orders 表不存在时终止并返回 False。

回滚:
  删除本次补建的索引。**保留**列 —— SQLite 删列有版本门槛，且该列可空、
  保留无业务风险（回滚只回到「无区域索引」的状态）。
"""
import sqlite3
from pathlib import Path

ORDER_TABLE = 'sales_orders'
COLUMN = 'territory_id'
IDX_ORDER_TERRITORY = 'idx_sales_order_territory'

_COLUMN_DDL = f'ALTER TABLE {ORDER_TABLE} ADD COLUMN {COLUMN} INTEGER'
_INDEX_DDL = (f'CREATE INDEX IF NOT EXISTS {IDX_ORDER_TERRITORY} '
              f'ON {ORDER_TABLE} ({COLUMN})')


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(
        'PRAGMA table_info({0})'.format(table)))


def _do_column(conn: sqlite3.Connection) -> None:
    if _has_column(conn, ORDER_TABLE, COLUMN):
        print(f'  - [SKIP] 列 {ORDER_TABLE}.{COLUMN} 已存在')
        return
    conn.execute(_COLUMN_DDL)
    print(f'  - [ALTER] {ORDER_TABLE}: ADD COLUMN {COLUMN}')


def _do_index(conn: sqlite3.Connection) -> None:
    if _index_exists(conn, IDX_ORDER_TERRITORY):
        print(f'  - [SKIP] 索引 {IDX_ORDER_TERRITORY} 已存在')
        return
    conn.execute(_INDEX_DDL)
    print(f'  - [NEW] 索引 {IDX_ORDER_TERRITORY}')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v134] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v134] 开始: 销售订单抬头 territory_id 快照列 / 索引')
        if not _table_exists(conn, ORDER_TABLE):
            print(f'[v134] 缺少表 {ORDER_TABLE}, 终止')
            return False
        _do_column(conn)
        _do_index(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v134] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言 sales_orders 表 / territory_id 列 / 区域索引三件齐备。"""
    if not db_path.exists():
        print('[v134 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, ORDER_TABLE):
            print(f'[v134 verify] FAIL: {ORDER_TABLE} 表不存在')
            return False
        if not _has_column(conn, ORDER_TABLE, COLUMN):
            print(f'[v134 verify] FAIL: 缺列 {ORDER_TABLE}.{COLUMN}')
            return False
        if not _index_exists(conn, IDX_ORDER_TERRITORY):
            print(f'[v134 verify] FAIL: 缺索引 {IDX_ORDER_TERRITORY}')
            return False
        print(f'[v134 verify] OK: {ORDER_TABLE}.{COLUMN} + {IDX_ORDER_TERRITORY}')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """删除区域索引；列保留（见模块说明）。"""
    if not db_path.exists():
        print(f'[v134] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if _index_exists(conn, IDX_ORDER_TERRITORY):
            conn.execute(f'DROP INDEX {IDX_ORDER_TERRITORY}')
            print(f'  - [DROP] 索引 {IDX_ORDER_TERRITORY}')
        else:
            print(f'  - [SKIP] 索引 {IDX_ORDER_TERRITORY} 不存在')
        print(f'  - [KEEP] 列 {ORDER_TABLE}.{COLUMN} 保留（可空，无业务风险）')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v134] rollback 失败: {e}')
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
        print(f'[v134] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v134] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v134] verify: {"PASS" if _v else "FAIL"}')
