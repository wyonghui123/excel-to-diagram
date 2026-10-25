# -*- coding: utf-8 -*-
"""销售员与客户销售员分配（W1-D）测试助手

【为什么放在 factories/】
  `meta/tests/conftest.py::_check_raw_sql_in_tests` 会把含裸 SQL DML 的测试文件
  整体 skip（假绿）。建表 / 播种 DML 收在本目录，测试文件只调用函数，
  默认口径即运行，无需 `ALLOW_RAW_SQL=1`。

【对外接口】
  SqliteDS(conn)                        —— 把 sqlite3 连接包成 data_source.query 口径
  create_tables(conn)                   —— 最小表结构（只含被测代码真正查询的列）
  seed(conn, table, **values)           —— 插一行，返回 rowid
  seed_salesperson(conn, **overrides)   —— 销售员默认值
  seed_assignment(conn, **overrides)    —— 客户销售员分配默认值
  seed_order(conn, **overrides)         —— 销售订单抬头（重算用例的现值）
"""
import sqlite3

SP_DDL = """
CREATE TABLE salespersons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    party_id INTEGER,
    user_id INTEGER,
    status TEXT NOT NULL DEFAULT 'active',
    description TEXT
);
CREATE TABLE customer_salesperson_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_account_id INTEGER NOT NULL,
    sales_org_id INTEGER,
    salesperson_id INTEGER NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    valid_from TEXT,
    valid_to TEXT,
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_account_id INTEGER,
    sales_org_id INTEGER,
    price_date TEXT,
    salesperson_id INTEGER
);
"""

SALESPERSON_DEFAULTS = {
    'code': 'SP001',
    'name': '张三',
    'party_id': None,
    'user_id': None,
    'status': 'active',
    'description': None,
}

ASSIGNMENT_DEFAULTS = {
    'customer_account_id': 1,
    'sales_org_id': 318,
    'salesperson_id': 1,
    'is_primary': 1,
    'valid_from': None,
    'valid_to': None,
    'status': 'active',
}

ORDER_DEFAULTS = {
    'customer_account_id': 1,
    'sales_org_id': 318,
    'price_date': None,
    'salesperson_id': None,
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
    conn.executescript(SP_DDL)
    conn.commit()


def seed(conn: sqlite3.Connection, table: str, **values):
    """插一行；表名/列名来自本仓清单，非外部输入。"""
    cols = list(values)
    sql = 'INSERT INTO {0} ({1}) VALUES ({2})'.format(
        table, ', '.join(cols), ', '.join('?' for _ in cols))
    cur = conn.execute(sql, [values[c] for c in cols])
    conn.commit()
    return cur.lastrowid


def seed_salesperson(conn: sqlite3.Connection, **overrides):
    row = dict(SALESPERSON_DEFAULTS)
    row.update(overrides)
    return seed(conn, 'salespersons', **row)


def seed_assignment(conn: sqlite3.Connection, **overrides):
    row = dict(ASSIGNMENT_DEFAULTS)
    row.update(overrides)
    return seed(conn, 'customer_salesperson_assignments', **row)


def seed_order(conn: sqlite3.Connection, **overrides):
    row = dict(ORDER_DEFAULTS)
    row.update(overrides)
    return seed(conn, 'sales_orders', **row)
