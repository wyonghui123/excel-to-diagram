# -*- coding: utf-8 -*-
"""[v125] 销售订单波次 1 W1-B：客户销售组织差异表

依据:
  docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md
    §4.2 对象字段 / §4.6 迁移与验收

背景:
  `customer_sales_org` 是「客户档案默认值」之上的组织级差异层：同一客户在不同
  销售组织下可各自约定付款条件 / 贸易条款 / 税分类 / 币种，未填的字段继续沿用
  账户级默认值（逐字段回退，见 meta/services/customer_sales_org_service.py）。

本迁移只做两件 YAML 管不到的事:
  1. 确认表已由 sync_schema 建好（本迁移不重复建表，避免与 YAML 双源）
  2. 补唯一索引 uidx_customer_sales_org_account_org
     —— 同一客户在同一销售组织下只允许一条差异行（W1-R12）

幂等:
  索引 CREATE UNIQUE INDEX IF NOT EXISTS；已存在只输出 [SKIP]。
  重复执行只输出 [SKIP]。

回滚:
  只删唯一索引；表与数据保留（对象由 YAML 声明，删表会造成数据不可解释）。
"""
import sqlite3
from pathlib import Path

TABLE = 'customer_sales_orgs'
UNIQUE_INDEX = 'uidx_customer_sales_org_account_org'
UNIQUE_COLUMNS = '(customer_account_id, sales_org_id)'

#: 必填列（NOT NULL）
REQUIRED_COLUMNS = ('customer_account_id', 'sales_org_id')
#: 差异字段（可空 = 沿用账户级；逐字段回退的载体）
OVERRIDE_COLUMNS = ('tax_classification_id', 'payment_term_id',
                    'incoterm_code', 'currency_id')


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _index_sql(conn: sqlite3.Connection, name: str):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone()
    return row[0] if row else None


def _duplicate_pairs(conn: sqlite3.Connection):
    return conn.execute(
        f'SELECT customer_account_id, sales_org_id, COUNT(*) AS n '
        f'FROM {TABLE} GROUP BY customer_account_id, sales_org_id '
        f'HAVING n > 1').fetchall()


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v125] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v125] 开始: 客户销售组织差异表唯一索引')
        if not _table_exists(conn, TABLE):
            print(f'[v125] 表 {TABLE} 不存在：请先执行 '
                  f'`python -m meta.tools.sync_schema --source sqlite '
                  f'--local {db_path} --execute` 建表')
            return False

        duplicates = _duplicate_pairs(conn)
        if duplicates:
            print(f'[v125] 发现重复 (客户, 销售组织) 组合，无法建唯一索引: {duplicates}')
            return False

        if _index_sql(conn, UNIQUE_INDEX):
            print(f'  - [SKIP] 唯一索引 {UNIQUE_INDEX} 已存在')
        else:
            conn.execute(
                f'CREATE UNIQUE INDEX IF NOT EXISTS {UNIQUE_INDEX} '
                f'ON {TABLE}{UNIQUE_COLUMNS}')
            print(f'  - [NEW] 唯一索引 {UNIQUE_INDEX} {UNIQUE_COLUMNS}')

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v125] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言表/必填列/差异列/唯一索引/无重复组合齐备。"""
    if not db_path.exists():
        print('[v125 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, TABLE):
            print(f'[v125 verify] FAIL: 表 {TABLE} 不存在')
            return False

        info = {row[1]: row for row in conn.execute(f'PRAGMA table_info({TABLE})')}
        for column in REQUIRED_COLUMNS:
            if column not in info:
                print(f'[v125 verify] FAIL: 缺列 {TABLE}.{column}')
                return False
            if info[column][3] != 1:
                print(f'[v125 verify] FAIL: {TABLE}.{column} 应为 NOT NULL')
                return False
        for column in OVERRIDE_COLUMNS:
            if column not in info:
                print(f'[v125 verify] FAIL: 缺列 {TABLE}.{column}')
                return False
            if info[column][3] != 0:
                print(f'[v125 verify] FAIL: {TABLE}.{column} 应可空（空 = 沿用账户级）')
                return False

        if 'status' not in info:
            print(f'[v125 verify] FAIL: 缺列 {TABLE}.status')
            return False
        if str(info['status'][4]).strip("'\"") != 'active':
            print(f'[v125 verify] FAIL: status 默认值异常 {info["status"][4]!r}')
            return False

        sql = _index_sql(conn, UNIQUE_INDEX)
        if not sql or 'UNIQUE' not in sql.upper():
            print(f'[v125 verify] FAIL: 缺唯一索引 {UNIQUE_INDEX}')
            return False
        if 'CUSTOMER_ACCOUNT_ID' not in sql.upper() \
                or 'SALES_ORG_ID' not in sql.upper():
            print(f'[v125 verify] FAIL: {UNIQUE_INDEX} 口径不是 (客户, 销售组织)')
            return False

        duplicates = _duplicate_pairs(conn)
        if duplicates:
            print(f'[v125 verify] FAIL: 存在重复组合 {duplicates}')
            return False

        print(f'[v125 verify] OK: {TABLE} 结构就位，{UNIQUE_INDEX} 唯一且无重复组合')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """只删唯一索引；表与数据由 YAML 管理、保留。"""
    if not db_path.exists():
        print(f'[v125] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if _index_sql(conn, UNIQUE_INDEX):
            conn.execute(f'DROP INDEX {UNIQUE_INDEX}')
            print(f'  - [DROP] 索引 {UNIQUE_INDEX}')
        else:
            print(f'  - [SKIP] 索引 {UNIQUE_INDEX} 不存在')
        print(f'  - [KEEP] 表 {TABLE} 与数据保留 (由 YAML 声明)')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v125] rollback 失败: {e}')
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
        print(f'[v125] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v125] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v125] verify: {"PASS" if _v else "FAIL"}')
