# -*- coding: utf-8 -*-
"""客户销售组织（W1-B）测试助手

【为什么放在 factories/】
  `meta/tests/conftest.py::_check_raw_sql_in_tests` 会把含裸 SQL DML 的测试文件
  整体 skip（假绿）。建表 / 播种 DML 收在本目录，测试文件只调用函数，
  默认口径即运行，无需 `ALLOW_RAW_SQL=1`。

【对外接口】
  SqliteDS(conn)                     —— 把 sqlite3 连接包成 data_source.query 口径
  create_tables(conn)                —— 最小表结构（只含被测代码真正查询的列）
  seed(conn, table, **values)        —— 插一行，返回 rowid
  seed_account(conn, **overrides)    —— 客户账户默认值
  seed_org_function(conn, org_id, function_type='sales')
  seed_override(conn, **overrides)   —— 客户销售组织差异行
  seed_order(conn, **overrides)      —— 销售订单抬头（重算用例的现值）
"""
import sqlite3

CSO_DDL = """
CREATE TABLE customer_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    default_payment_term_id INTEGER,
    default_incoterm_code TEXT,
    tax_classification_id INTEGER
);
CREATE TABLE customer_sales_orgs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_account_id INTEGER NOT NULL,
    sales_org_id INTEGER NOT NULL,
    tax_classification_id INTEGER,
    payment_term_id INTEGER,
    incoterm_code TEXT,
    currency_id INTEGER,
    status TEXT NOT NULL DEFAULT 'active',
    description TEXT
);
CREATE TABLE org_functions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER,
    function_type TEXT
);
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_account_id INTEGER,
    sales_org_id INTEGER,
    order_type_id INTEGER,
    payment_term_id INTEGER,
    incoterm_code TEXT
);
"""

ACCOUNT_DEFAULTS = {
    'default_payment_term_id': None,
    'default_incoterm_code': None,
    'tax_classification_id': None,
}

OVERRIDE_DEFAULTS = {
    'customer_account_id': 1,
    'sales_org_id': 318,
    'tax_classification_id': None,
    'payment_term_id': None,
    'incoterm_code': None,
    'currency_id': None,
    'status': 'active',
    'description': None,
}

ORDER_DEFAULTS = {
    'customer_account_id': 1,
    'sales_org_id': 318,
    'order_type_id': 1,
    'payment_term_id': None,
    'incoterm_code': None,
}


class SqliteDS:
    """`data_source.query(sql, params)` 的最小适配（返回 dict 行）。"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(CSO_DDL)
    conn.commit()


def seed(conn: sqlite3.Connection, table: str, **values):
    """插一行；表名/列名来自本仓清单，非外部输入。"""
    cols = list(values)
    sql = 'INSERT INTO {0} ({1}) VALUES ({2})'.format(
        table, ', '.join(cols), ', '.join('?' for _ in cols))
    cur = conn.execute(sql, [values[c] for c in cols])
    conn.commit()
    return cur.lastrowid


def seed_account(conn: sqlite3.Connection, **overrides):
    row = dict(ACCOUNT_DEFAULTS)
    row.update(overrides)
    return seed(conn, 'customer_accounts', **row)


def seed_org_function(conn: sqlite3.Connection, org_id, function_type='sales'):
    return seed(conn, 'org_functions', org_id=org_id,
                function_type=function_type)


def seed_override(conn: sqlite3.Connection, **overrides):
    row = dict(OVERRIDE_DEFAULTS)
    row.update(overrides)
    return seed(conn, 'customer_sales_orgs', **row)


def seed_order(conn: sqlite3.Connection, **overrides):
    row = dict(ORDER_DEFAULTS)
    row.update(overrides)
    return seed(conn, 'sales_orders', **row)
