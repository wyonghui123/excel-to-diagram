# -*- coding: utf-8 -*-
"""[v139] 销售订单汇率快照：类型 / 日期存量回填

依据:
  docs/superpowers/specs/2026-10-26-sales-order-master-data-gap-spec.md §E5
  meta/schemas/sales_order.yaml 头注释 W0-R9 / W0-R13

背景:
  订单新增汇率快照两列 `exchange_rate_type` / `exchange_rate_date`。
  W0-R13 要求「存在折算（exchange_rate != 1）时汇率日期必填」，否则存量库里
  有折算但缺日期的订单，任何后续更新都会被守卫拦下（R13 校验读旧行）。

本迁移只做 YAML 管不到的事（列由 sync_schema 按 YAML 生成，不重复建列）:
  1. 断言 sales_orders 两列已存在
  2. 回填 exchange_rate_type = 'spot'（空值行）
  3. 回填 exchange_rate_date = order_date（rate != 1 且日期为空）
     order_date 缺失时退到 created_at 的日期部分
  4. 输出仍无法回填的折算订单（无 order_date / created_at）

幂等:
  两条 UPDATE 都带空值条件，重复执行只输出 0 行。

回滚:
  数据回填无下界（回填值即正确快照），rollback 只输出说明并返回 True；
  列由 YAML 声明，保留。
"""
import sqlite3
from pathlib import Path

TABLE = 'sales_orders'
TYPE_COLUMN = 'exchange_rate_type'
DATE_COLUMN = 'exchange_rate_date'
RATE_TYPE_DEFAULT = 'spot'

#: 折算判定：本币 rate = 1 允许汇率日期留空
_CONVERTED = f'({TABLE}.exchange_rate IS NOT NULL AND {TABLE}.exchange_rate <> 1)'


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _column_info(conn: sqlite3.Connection, table: str) -> dict:
    if not _table_exists(conn, table):
        return {}
    return {row[1]: row for row in conn.execute(f'PRAGMA table_info({table})')}


def _count(conn: sqlite3.Connection, where: str) -> int:
    row = conn.execute(f'SELECT COUNT(*) FROM {TABLE} WHERE {where}').fetchone()
    return row[0] if row else 0


def _blank(col: str) -> str:
    return f'({col} IS NULL OR TRIM({col}) = \'\')'


def _unresolved_dates(conn: sqlite3.Connection):
    return conn.execute(
        f'SELECT id, order_no, order_date, created_at FROM {TABLE} '
        f'WHERE {_CONVERTED} AND {_blank(DATE_COLUMN)}'
    ).fetchall()


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v139] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v139] 开始: 销售订单汇率类型 / 日期回填')
        info = _column_info(conn, TABLE)
        if not info:
            print(f'[v139] 表 {TABLE} 不存在：请先执行 '
                  f'`python -m meta.tools.sync_schema --source sqlite '
                  f'--local {db_path} --execute` 建列')
            return False
        for col in (TYPE_COLUMN, DATE_COLUMN):
            if col not in info:
                print(f'[v139] 列 {TABLE}.{col} 不存在：请先执行 sync_schema 建列')
                return False

        blank_type = _count(conn, _blank(TYPE_COLUMN))
        if blank_type:
            conn.execute(
                f'UPDATE {TABLE} SET {TYPE_COLUMN} = ? WHERE {_blank(TYPE_COLUMN)}',
                (RATE_TYPE_DEFAULT,))
            print(f'  - [FILL] {TYPE_COLUMN} = {RATE_TYPE_DEFAULT}：{blank_type} 行')
        else:
            print(f'  - [SKIP] {TYPE_COLUMN} 无空值')

        blank_date = _count(conn, f'{_CONVERTED} AND {_blank(DATE_COLUMN)}')
        if blank_date:
            conn.execute(
                f'UPDATE {TABLE} SET {DATE_COLUMN} = '
                f'COALESCE(NULLIF(TRIM(order_date), \'\'), '
                f'substr(created_at, 1, 10)) '
                f'WHERE {_CONVERTED} AND {_blank(DATE_COLUMN)}')
            print(f'  - [FILL] {DATE_COLUMN} = order_date：{blank_date} 行（折算订单）')
        else:
            print(f'  - [SKIP] 折算订单无缺失 {DATE_COLUMN}')

        unresolved = _unresolved_dates(conn)
        if unresolved:
            print(f'  - [CHECK] 仍有 {len(unresolved)} 条折算订单缺汇率日期'
                  f'（无 order_date / created_at，需人工补录）：')
            for order_id, order_no, order_date, created_at in unresolved:
                print(f'      id={order_id} order_no={order_no} '
                      f'order_date={order_date} created_at={created_at}')
        else:
            print('  - [CHECK] 折算订单汇率日期齐备')

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v139] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言两列存在、汇率类型无空值、折算订单汇率日期无空值。"""
    if not db_path.exists():
        print('[v139 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        info = _column_info(conn, TABLE)
        for col in (TYPE_COLUMN, DATE_COLUMN):
            if col not in info:
                print(f'[v139 verify] FAIL: 缺列 {TABLE}.{col}')
                return False

        blank_type = _count(conn, _blank(TYPE_COLUMN))
        if blank_type:
            print(f'[v139 verify] FAIL: {TABLE}.{TYPE_COLUMN} 仍有 {blank_type} 行空值')
            return False

        unresolved = _unresolved_dates(conn)
        if unresolved:
            print(f'[v139 verify] FAIL: {len(unresolved)} 条折算订单缺 '
                  f'{DATE_COLUMN}（W0-R13 会拦截其更新）')
            return False

        print(f'[v139 verify] OK: {DATE_COLUMN} / {TYPE_COLUMN} 快照齐备')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """回填值即正确快照，无下界可回；列由 YAML 管理、保留。"""
    if not db_path.exists():
        print(f'[v139] DB 不存在: {db_path}')
        return False
    print(f'  - [KEEP] {TABLE}.{TYPE_COLUMN} / {DATE_COLUMN} 与回填数据保留 '
          f'(由 YAML 声明，回填值即正确快照)')
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
