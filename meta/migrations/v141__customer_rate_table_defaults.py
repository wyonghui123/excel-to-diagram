# -*- coding: utf-8 -*-
"""[v141] 客户价目表默认值：列断言 + 存量覆盖率核查

依据:
  docs/superpowers/specs/2026-10-26-sales-order-master-data-gap-spec.md
    §5 E1 客户价目表

背景:
  客户档案新增账户级默认价目表 `customer_accounts.default_rate_table_id`，
  销售组织差异新增组织级覆盖 `customer_sales_orgs.rate_table_id`；订单取价时
  由 CustomerSalesOrgService 逐字段回退解析，并作为「优选价目表」传给定价确定
  服务（approved / 币种相符 / 组织作用域内才采用，否则静默回退既有规则）。

本迁移只做 YAML 管不到的事（列由 sync_schema 按 YAML 生成，不重复建列）:
  1. 断言两列已存在且可空（NOT NULL = 0）
  2. 输出存量覆盖率（账户级 / 组织级各配置了多少条）
  3. 输出非法引用清单（指向不存在或非 approved 价目表），供人工修正

幂等:
  只读断言与统计，无写入；重复执行输出一致。

回滚:
  无结构变更，不删列（列由 YAML 声明）；rollback 仅打印说明。
"""
import sqlite3
from pathlib import Path

ACCOUNT_TABLE = 'customer_accounts'
ACCOUNT_COLUMN = 'default_rate_table_id'
SALES_ORG_TABLE = 'customer_sales_orgs'
SALES_ORG_COLUMN = 'rate_table_id'

#: 非法引用（指向不存在或非 approved 的价目表）
_INVALID_ACCOUNT_SQL = (
    'SELECT a.id, a.default_rate_table_id '
    'FROM customer_accounts a '
    'LEFT JOIN rate_tables r ON r.id = a.default_rate_table_id '
    'WHERE a.default_rate_table_id IS NOT NULL '
    '  AND (r.id IS NULL OR r.status <> \'approved\')'
)
_INVALID_SALES_ORG_SQL = (
    'SELECT s.id, s.rate_table_id '
    'FROM customer_sales_orgs s '
    'LEFT JOIN rate_tables r ON r.id = s.rate_table_id '
    'WHERE s.rate_table_id IS NOT NULL '
    '  AND (r.id IS NULL OR r.status <> \'approved\')'
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _column_info(conn: sqlite3.Connection, table: str) -> dict:
    if not _table_exists(conn, table):
        return {}
    return {row[1]: row for row in conn.execute(f'PRAGMA table_info({table})')}


def _assert_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    info = _column_info(conn, table)
    if not info:
        print(f'[v141] 表 {table} 不存在：请先执行 '
              f'`python -m meta.tools.sync_schema --source sqlite '
              f'--local <db> --execute` 建列')
        return False
    if column not in info:
        print(f'[v141] 列 {table}.{column} 不存在：请先执行 sync_schema 建列')
        return False
    if info[column][3] != 0:
        print(f'[v141] 列 {table}.{column} 应为可空（NOT NULL=0），'
              f'实际 NOT NULL={info[column][3]}')
        return False
    return True


def _count(conn: sqlite3.Connection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v141] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v141] 开始: 客户价目表默认值列断言 + 存量核查')
        if not _assert_column(conn, ACCOUNT_TABLE, ACCOUNT_COLUMN):
            return False
        if not _assert_column(conn, SALES_ORG_TABLE, SALES_ORG_COLUMN):
            return False

        account_total = _count(conn, f'SELECT COUNT(*) FROM {ACCOUNT_TABLE}')
        account_set = _count(
            conn,
            f'SELECT COUNT(*) FROM {ACCOUNT_TABLE} '
            f'WHERE {ACCOUNT_COLUMN} IS NOT NULL')
        org_total = _count(conn, f'SELECT COUNT(*) FROM {SALES_ORG_TABLE}')
        org_set = _count(
            conn,
            f'SELECT COUNT(*) FROM {SALES_ORG_TABLE} '
            f'WHERE {SALES_ORG_COLUMN} IS NOT NULL')
        print(f'  - [CHECK] 账户级默认价目表: {account_set}/{account_total} 条已配置')
        print(f'  - [CHECK] 组织级价目表差异: {org_set}/{org_total} 条已配置')

        for label, sql in (
            ('客户档案', _INVALID_ACCOUNT_SQL),
            ('销售组织差异', _INVALID_SALES_ORG_SQL),
        ):
            try:
                rows = conn.execute(sql).fetchall()
            except sqlite3.Error as e:
                print(f'  - [WARN] {label}非法引用核查跳过（查询失败: {e}）')
                continue
            if rows:
                print(f'  - [CHECK] {label}存在 {len(rows)} 条非法价目表引用'
                      f'（不存在或未审核，需人工修正）：')
                for row_id, table_id in rows:
                    print(f'      {label} id={row_id} rate_table_id={table_id}')
            else:
                print(f'  - [CHECK] {label}无非法价目表引用')
        return True
    except Exception as e:
        print(f'[v141] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言两列存在且可空。"""
    if not db_path.exists():
        print('[v141 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for table, column in (
            (ACCOUNT_TABLE, ACCOUNT_COLUMN),
            (SALES_ORG_TABLE, SALES_ORG_COLUMN),
        ):
            info = _column_info(conn, table)
            if column not in info:
                print(f'[v141 verify] FAIL: 缺列 {table}.{column}')
                return False
            if info[column][3] != 0:
                print(f'[v141 verify] FAIL: {table}.{column} 应可空'
                      f'（空 = 未配置，回退既有规则）')
                return False
        print(f'[v141 verify] OK: {ACCOUNT_TABLE}.{ACCOUNT_COLUMN} / '
              f'{SALES_ORG_TABLE}.{SALES_ORG_COLUMN} 可空')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """无结构变更，列与数据由 YAML 管理、保留。"""
    if not db_path.exists():
        print(f'[v141] DB 不存在: {db_path}')
        return False
    print(f'  - [KEEP] 列 {ACCOUNT_TABLE}.{ACCOUNT_COLUMN} / '
          f'{SALES_ORG_TABLE}.{SALES_ORG_COLUMN} 与数据保留 (由 YAML 声明)')
    return True


downgrade = rollback


if __name__ == '__main__':
    import sys
    from meta.core.db_path import get_meta_db_path

    _args = [a for a in sys.argv[1:] if a != '--rollback']
    _db = Path(_args[0]) if _args else Path(get_meta_db_path())
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v141] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v141] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v141] verify: {"PASS" if _v else "FAIL"}')
