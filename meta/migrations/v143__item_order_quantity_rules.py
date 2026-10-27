# -*- coding: utf-8 -*-
"""[v143] 物料最小订单量 / 订单倍数：补列 + 存量核查

依据:
  E9 最小订单量 / 订单倍数（物料主数据订单约束）

背景:
  物料表 items 需要承载下单约束：min_order_qty（最小订单量）、
  order_multiple（订单倍数）。两者都是 REAL 可空列：
  空 = 不约束；有值 = 下单量必须满足。
  本迁移只负责补列与存量报告，不做校验/舍入逻辑（校验由业务层完成）。

本迁移内容:
  1. 断言 items 表存在（不存在提示先跑 sync_schema）
  2. 缺列时补 min_order_qty / order_multiple（REAL，可空），输出 [ADD]
  3. 存量核查：统计 min_order_qty <= 0、order_multiple <= 0 的行数并输出清单
     （只报告，不阻断、不改数据，也不做任何舍入）
  4. 重复执行输出 SKIP

幂等:
  列先查后用；核查只读，不修改业务数据。

回滚:
  只报告「保留列」，不删列、不改数据（列由 YAML 声明，删列会导致数据丢失）。
"""
import sqlite3
from pathlib import Path

TABLE = 'items'
COLUMNS = {
    'min_order_qty': 'REAL',
    'order_multiple': 'REAL',
}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> dict:
    if not _table_exists(conn, table):
        return {}
    return {row[1]: row for row in conn.execute(f'PRAGMA table_info({table})')}


def _query(conn: sqlite3.Connection, sql: str) -> list:
    try:
        return conn.execute(sql).fetchall()
    except sqlite3.Error:
        return []


def _report_non_positive(conn: sqlite3.Connection, column: str) -> int:
    rows = _query(
        conn,
        f'SELECT id, {column} FROM {TABLE} '
        f'WHERE {column} <= 0 ORDER BY id')
    if not rows:
        print(f'  - [CHECK] {column} <= 0：0 条')
        return 0
    print(f'  - [CHECK] {column} <= 0：{len(rows)} 条（只报告，不阻断）')
    for row_id, value in rows:
        print(f'      id={row_id} {column}={value}')
    return len(rows)


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v143] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v143] 开始: 物料最小订单量 / 订单倍数')
        if not _table_exists(conn, TABLE):
            print(f'[v143] 表 {TABLE} 不存在：请先执行 '
                  f'`python -m meta.tools.sync_schema --source sqlite '
                  f'--local {db_path} --execute` 建表')
            return False

        cols = _columns(conn, TABLE)
        for name, col_type in COLUMNS.items():
            if name not in cols:
                conn.execute(
                    f'ALTER TABLE {TABLE} ADD COLUMN {name} {col_type}')
                print(f'  - [ADD] {TABLE}.{name}（{col_type} 可空）')
            else:
                print(f'  - [SKIP] {TABLE}.{name} 已存在')

        for name in COLUMNS:
            _report_non_positive(conn, name)

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v143] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言两列存在且可空（PRAGMA table_info 的 notnull == 0）。"""
    if not db_path.exists():
        print('[v143 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, TABLE):
            print(f'[v143 verify] FAIL: 表 {TABLE} 不存在')
            return False
        cols = _columns(conn, TABLE)
        for name in COLUMNS:
            if name not in cols:
                print(f'[v143 verify] FAIL: 缺列 {TABLE}.{name}')
                return False
            if cols[name][3] != 0:
                print(f'[v143 verify] FAIL: {TABLE}.{name} 应可空（notnull=0），'
                      f'实际 notnull={cols[name][3]}')
                return False

        print(f'[v143 verify] PASS: {TABLE}.min_order_qty / '
              f'{TABLE}.order_multiple 存在且可空')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """只报告「保留列」，不删列、不改数据。"""
    if not db_path.exists():
        print(f'[v143] DB 不存在: {db_path}')
        return False
    for name in COLUMNS:
        print(f'  - [KEEP] {TABLE}.{name} 与数据保留 (由 YAML 声明)')
    return True


downgrade = rollback


if __name__ == '__main__':
    import sys
    from meta.core.db_path import get_meta_db_path

    _argv = sys.argv[1:]
    _args = [a for a in _argv if not a.startswith('--')]
    _db = Path(_args[0]) if _args else Path(get_meta_db_path())
    if '--rollback' in _argv:
        _ok = rollback(_db)
        print(f'[v143] rollback: {"OK" if _ok else "FAIL"}')
    elif '--verify' in _argv:
        _v = verify(_db)
        print(f'[v143] verify: {"PASS" if _v else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v143] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v143] verify: {"PASS" if _v else "FAIL"}')
