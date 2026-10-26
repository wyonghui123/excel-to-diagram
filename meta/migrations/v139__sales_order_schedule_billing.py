# -*- coding: utf-8 -*-
"""[v139] 销售订单计划行 billing_percent：结构断言与数据体检

依据:
  docs/superpowers/specs/2026-10-26-sales-order-billing-and-header-discount-spec.md
    §3.1 Schema 变更 / §3.4 迁移 / §6 验收 V-A1 ~ V-A4

背景:
  `billing_percent` 列由 YAML（meta/schemas/sales_order_schedule.yaml）
  + `python -m meta.tools.sync_schema --source sqlite --local <db> --execute` 建。
  本迁移**不建表、不加列**，只做:
    1. 断言表存在，缺失时提示先跑 sync_schema 并返回 False
    2. 断言 `billing_percent` 列存在，缺失时同样提示先跑 sync_schema
    3. 数据体检（**只报告，不修改**）:
       - billing 且 billing_percent IS NULL
       - billing 且 promised_qty IS NOT NULL
       - billing 且 plant_location_id IS NOT NULL
    4. verify: 列存在且可空 + 复用 v138 的 4 个索引检查

幂等:
  本迁移不写库；重复执行结果一致，第二次仅输出 [SKIP] / [CHECK]。

回滚:
  列与索引均由 YAML / v138 声明，本迁移不改变结构，rollback 只打印 [KEEP]。
"""
import sqlite3
from pathlib import Path

TABLE = 'sales_order_schedules'
COLUMN = 'billing_percent'

#: 与 v138 保持一致的 4 个索引（本迁移不创建，只断言）
INDEXES = (
    ('uq_schedule_line_kind_no', True,
     ('line_id', 'schedule_kind', 'schedule_no'), None),
    ('uq_schedule_service_visit', True,
     ('line_id', 'service_visit_no'),
     "schedule_kind = 'service' AND service_visit_no IS NOT NULL"),
    ('idx_schedule_order', False, ('order_id',), None),
    ('idx_schedule_line', False, ('line_id',), None),
)

#: billing 行的数据体检项（只报告，不修改）
BILLING_CHECKS = (
    ('billing 缺收款比例', 'billing_percent IS NULL'),
    ('billing 仍带承诺数量', 'promised_qty IS NOT NULL'),
    ('billing 仍带发货点', 'plant_location_id IS NOT NULL'),
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _index_sql(conn: sqlite3.Connection, name: str):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone()
    return row[0] if row else None


def _column_info(conn: sqlite3.Connection, table: str) -> dict:
    if not _table_exists(conn, table):
        return {}
    return {row[1]: row for row in conn.execute(f'PRAGMA table_info({table})')}


def _report_billing_data(conn: sqlite3.Connection) -> None:
    for label, condition in BILLING_CHECKS:
        n = conn.execute(
            f'SELECT COUNT(*) FROM {TABLE} '
            f"WHERE schedule_kind = 'billing' AND {condition}"
        ).fetchone()[0]
        print(f'  - [CHECK] {label}: {n} 行')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v139] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v139] 开始: 订单计划行 billing_percent 结构断言')
        if not _table_exists(conn, TABLE):
            print(f'[v139] 表 {TABLE} 不存在：请先执行 '
                  f'`python -m meta.tools.sync_schema --source sqlite '
                  f'--local {db_path} --execute` 建表')
            return False

        info = _column_info(conn, TABLE)
        if COLUMN not in info:
            print(f'[v139] 列 {TABLE}.{COLUMN} 不存在：请先执行 '
                  f'`python -m meta.tools.sync_schema --source sqlite '
                  f'--local {db_path} --execute` 同步 YAML 结构')
            return False
        print(f'  - [SKIP] 列 {TABLE}.{COLUMN} 已存在')

        _report_billing_data(conn)
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v139] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言 billing_percent 列可空 + 复用 v138 的 4 个索引检查。"""
    if not db_path.exists():
        print('[v139 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        info = _column_info(conn, TABLE)
        if not info:
            print(f'[v139 verify] FAIL: 表 {TABLE} 不存在')
            return False
        if COLUMN not in info:
            print(f'[v139 verify] FAIL: 缺列 {TABLE}.{COLUMN}')
            return False
        if info[COLUMN][3] != 0:
            print(f'[v139 verify] FAIL: {TABLE}.{COLUMN} 应为可空')
            return False

        for name, unique, columns, condition in INDEXES:
            sql = _index_sql(conn, name)
            if not sql:
                print(f'[v139 verify] FAIL: 缺索引 {name}')
                return False
            upper = sql.upper()
            if unique and 'UNIQUE' not in upper:
                print(f'[v139 verify] FAIL: 索引 {name} 不是 UNIQUE')
                return False
            for col in columns:
                if col.upper() not in upper:
                    print(f'[v139 verify] FAIL: 索引 {name} 缺列 {col}')
                    return False
            if condition and condition.upper() not in upper:
                print(f'[v139 verify] FAIL: 索引 {name} 缺 WHERE 条件')
                return False

        print(f'[v139 verify] OK: {TABLE}.{COLUMN} 可空，4 个索引齐备')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """列与索引均由 YAML / v138 声明，本迁移不改结构。"""
    print(f'  - [KEEP] 表 {TABLE} / 列 {COLUMN} / 4 个索引保留 (由 YAML 声明)')
    return True


downgrade = rollback


if __name__ == '__main__':
    import sys
    from meta.core.db_path import get_meta_db_path

    _args = [a for a in sys.argv[1:] if a != '--rollback']
    _db = Path(_args[0]) if _args else Path(get_meta_db_path())
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v139] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v139] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v139] verify: {"PASS" if _v else "FAIL"}')
