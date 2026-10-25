# -*- coding: utf-8 -*-
"""往来单位地址（W1-C）测试助手

【为什么放在 factories/】
  `meta/tests/conftest.py::_check_raw_sql_in_tests` 会把含裸 SQL DML 的测试文件
  整体 skip（假绿）。建表 / 播种 DML 收在本目录，测试文件只调用函数。

【对外接口】
  SqliteDS(conn)      —— 把 sqlite3 连接包成 data_source.query 口径
  create_tables(conn) —— 最小表结构（只含被测代码真正查询的列）
  seed(conn, table, **values)
  seed_address(conn, **overrides)
  seed_party_address(conn, **overrides)
  seed_relation(conn, **overrides)
  seed_account(conn, **overrides)
  seed_order(conn, **overrides)
"""
import sqlite3

PA_DDL = """
CREATE TABLE addresses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    formatted_address TEXT,
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE party_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    party2_id INTEGER
);
CREATE TABLE customer_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relation_id INTEGER
);
CREATE TABLE party_addresses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    party_id INTEGER NOT NULL,
    address_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    description TEXT
);
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_account_id INTEGER,
    ship_to_party_id INTEGER,
    bill_to_account_id INTEGER,
    ship_to_address_id INTEGER,
    bill_to_address_id INTEGER
);
"""

ADDRESS_DEFAULTS = {'code': 'ADDR-1', 'formatted_address': '某地某街 1 号',
                    'status': 'active'}

PARTY_ADDRESS_DEFAULTS = {
    'party_id': 1,
    'address_id': 1,
    'role': 'ship_to',
    'is_default': 1,
    'status': 'active',
    'description': None,
}

RELATION_DEFAULTS = {'party2_id': 1}

ACCOUNT_DEFAULTS = {'relation_id': 1}

ORDER_DEFAULTS = {
    'customer_account_id': 1,
    'ship_to_party_id': None,
    'bill_to_account_id': None,
    'ship_to_address_id': None,
    'bill_to_address_id': None,
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
    conn.executescript(PA_DDL)
    conn.commit()


def seed(conn: sqlite3.Connection, table: str, **values):
    """插一行；表名/列名来自本仓清单，非外部输入。"""
    cols = list(values)
    sql = 'INSERT INTO {0} ({1}) VALUES ({2})'.format(
        table, ', '.join(cols), ', '.join('?' for _ in cols))
    cur = conn.execute(sql, [values[c] for c in cols])
    conn.commit()
    return cur.lastrowid


def seed_address(conn: sqlite3.Connection, **overrides):
    row = dict(ADDRESS_DEFAULTS)
    row.update(overrides)
    return seed(conn, 'addresses', **row)


def seed_party_address(conn: sqlite3.Connection, **overrides):
    row = dict(PARTY_ADDRESS_DEFAULTS)
    row.update(overrides)
    return seed(conn, 'party_addresses', **row)


def seed_relation(conn: sqlite3.Connection, **overrides):
    row = dict(RELATION_DEFAULTS)
    row.update(overrides)
    return seed(conn, 'party_relations', **row)


def seed_account(conn: sqlite3.Connection, **overrides):
    row = dict(ACCOUNT_DEFAULTS)
    row.update(overrides)
    return seed(conn, 'customer_accounts', **row)


def seed_order(conn: sqlite3.Connection, **overrides):
    row = dict(ORDER_DEFAULTS)
    row.update(overrides)
    return seed(conn, 'sales_orders', **row)
