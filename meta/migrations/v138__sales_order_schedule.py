# -*- coding: utf-8 -*-
"""[v138] 销售订单计划行 sales_order_schedule：索引补齐与结构断言

依据:
  docs/superpowers/specs/2026-10-26-sales-order-schedule-line-spec.md v1.1
    §2.1 表结构 / §2.2 索引 / §6 P0 验收

背景:
  计划行表 `sales_order_schedules` 由 YAML（meta/schemas/sales_order_schedule.yaml）
  + `python -m meta.tools.sync_schema --source sqlite --local <db> --execute` 建。
  本迁移**不建表**，只做 YAML 管不到或需防御性补齐的事:
    1. 断言表存在，缺失时提示先跑 sync_schema 并返回 False
    2. 补齐 4 个索引（sync_schema 已建则 [SKIP]）
       - uq_schedule_line_kind_no         唯一 (line_id, schedule_kind, schedule_no)
       - uq_schedule_service_visit        部分唯一 (line_id, service_visit_no)
                                          WHERE schedule_kind = 'service'
                                            AND service_visit_no IS NOT NULL
       - idx_schedule_order               (order_id)
       - idx_schedule_line                (line_id)
    3. 建索引前检查重复数据，冲突则明确 FAIL 而不是抛数据库异常

本波口径:
  **不建任何 DOC_FLOW 规则**（交货单 BO 尚不存在，Spec §0 C6 / §4.1）
  **不建菜单、不建权限**（入口折叠在订单内，权限随 sales_order，Spec §5）

幂等:
  所有索引均先查 sqlite_master 再 CREATE ... IF NOT EXISTS；重复执行只输出 [SKIP]。

回滚:
  只删本迁移补建的 4 个索引；**保留**表与数据（由 YAML 声明）。
"""
import sqlite3
from pathlib import Path

TABLE = 'sales_order_schedules'

#: (索引名, 是否唯一, 字段列表, WHERE 条件或 None)
INDEXES = (
    ('uq_schedule_line_kind_no', True,
     ('line_id', 'schedule_kind', 'schedule_no'), None),
    ('uq_schedule_service_visit', True,
     ('line_id', 'service_visit_no'),
     "schedule_kind = 'service' AND service_visit_no IS NOT NULL"),
    ('idx_schedule_order', False, ('order_id',), None),
    ('idx_schedule_line', False, ('line_id',), None),
)

#: verify 断言的必填列
REQUIRED_COLUMNS = (
    'order_id', 'line_id', 'schedule_no', 'schedule_kind',
    'promised_date', 'status',
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


def _duplicates(conn: sqlite3.Connection, columns, where: str = None):
    """返回违反唯一约束的键值清单（供 FAIL 输出）。"""
    cols = ', '.join(columns)
    sql = f'SELECT {cols}, COUNT(*) AS n FROM {TABLE}'
    if where:
        sql += f' WHERE {where}'
    sql += f' GROUP BY {cols} HAVING n > 1'
    return conn.execute(sql).fetchall()


def _do_indexes(conn: sqlite3.Connection) -> bool:
    for name, unique, columns, condition in INDEXES:
        existing = _index_sql(conn, name)
        if existing:
            if unique and 'UNIQUE' not in existing.upper():
                print(f'  - [FAIL] 索引 {name} 已存在但不是 UNIQUE: {existing}')
                return False
            if condition and condition.upper() not in existing.upper():
                print(f'  - [CHECK] 索引 {name} 已存在但 WHERE 条件与声明不一致，'
                      f'保留现状（如需重建请先 DROP）')
            else:
                print(f'  - [SKIP] 索引 {name} 已存在')
            continue

        if unique:
            dupes = _duplicates(conn, columns, condition)
            if dupes:
                print(f'  - [FAIL] 发现重复键，无法建唯一索引 {name}: {dupes}')
                return False

        cols = ', '.join(columns)
        unique_kw = 'UNIQUE ' if unique else ''
        sql = f'CREATE {unique_kw}INDEX IF NOT EXISTS {name} ON {TABLE}({cols})'
        if condition:
            sql += f' WHERE {condition}'
        conn.execute(sql)
        print(f'  - [NEW] 索引 {name} ({cols})'
              f'{" WHERE " + condition if condition else ""}')
    return True


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v138] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v138] 开始: 订单计划行索引补齐')
        if not _table_exists(conn, TABLE):
            print(f'[v138] 表 {TABLE} 不存在：请先执行 '
                  f'`python -m meta.tools.sync_schema --source sqlite '
                  f'--local {db_path} --execute` 建表')
            return False

        if not _do_indexes(conn):
            conn.rollback()
            return False

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v138] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言表 / 必填列 / 4 个索引（唯一性与 WHERE 条件）齐备。"""
    if not db_path.exists():
        print('[v138 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        info = _column_info(conn, TABLE)
        if not info:
            print(f'[v138 verify] FAIL: 表 {TABLE} 不存在')
            return False

        for column in REQUIRED_COLUMNS:
            if column not in info:
                print(f'[v138 verify] FAIL: 缺列 {TABLE}.{column}')
                return False
            if info[column][3] != 1:
                print(f'[v138 verify] FAIL: {TABLE}.{column} 应为 NOT NULL')
                return False

        for name, unique, columns, condition in INDEXES:
            sql = _index_sql(conn, name)
            if not sql:
                print(f'[v138 verify] FAIL: 缺索引 {name}')
                return False
            upper = sql.upper()
            if unique and 'UNIQUE' not in upper:
                print(f'[v138 verify] FAIL: 索引 {name} 不是 UNIQUE')
                return False
            for col in columns:
                if col.upper() not in upper:
                    print(f'[v138 verify] FAIL: 索引 {name} 缺列 {col}')
                    return False
            if condition and condition.upper() not in upper:
                print(f'[v138 verify] FAIL: 索引 {name} 缺 WHERE 条件')
                return False

        print(f'[v138 verify] OK: {TABLE} 就位，4 个索引齐备')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """删除本迁移补建的索引；表与数据保留（由 YAML 声明）。"""
    if not db_path.exists():
        print(f'[v138] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for name, _unique, _columns, _condition in INDEXES:
            if _index_sql(conn, name):
                conn.execute(f'DROP INDEX {name}')
                print(f'  - [DROP] 索引 {name}')
            else:
                print(f'  - [SKIP] 索引 {name} 不存在')
        print(f'  - [KEEP] 表 {TABLE} 与数据保留 (由 YAML 声明)')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v138] rollback 失败: {e}')
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
        print(f'[v138] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v138] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v138] verify: {"PASS" if _v else "FAIL"}')
