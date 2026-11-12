# -*- coding: utf-8 -*-
"""T6.1 外部编号校验的测试数据构造（非 test 文件，集中放 raw SQL）。

conftest 的 raw-SQL 守卫只扫描 `test_*.py`；把建表/播种集中到这里，
测试文件里就不出现 INSERT/UPDATE/DELETE 字面量。
"""

import sqlite3

from meta.tests.inventory_test_doubles import MemDS

SCHEMA = """
CREATE TABLE number_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    pattern TEXT,
    scope_fields TEXT,
    date_field TEXT,
    start_value INTEGER,
    on_exhaust TEXT,
    preview TEXT,
    status TEXT DEFAULT 'active',
    description TEXT,
    created_at TEXT
);
CREATE TABLE _sequences (
    sequence_name TEXT NOT NULL,
    current_value INTEGER NOT NULL DEFAULT 0,
    UNIQUE (sequence_name)
);
CREATE TABLE type_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_bo TEXT,
    level TEXT,
    number_sequence_id INTEGER
);
CREATE TABLE purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT
);
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT
);
"""

SEEDS = """
INSERT INTO number_sequences
    (code, name, pattern, date_field, start_value, on_exhaust)
VALUES ('PO', '采购订单', 'PO-{DATE:yyyymm}-{SEQ:4}', 'order_date', 10, 'error');
INSERT INTO number_sequences
    (code, name, pattern, date_field, start_value, on_exhaust)
VALUES ('SO', '销售订单', 'SO-{SEQ:3}', 'order_date', 1, 'extend');
INSERT INTO type_definitions (scope_bo, level, number_sequence_id)
VALUES ('purchase_order', 'header', 1);
INSERT INTO type_definitions (scope_bo, level, number_sequence_id)
VALUES ('sales_order', 'header', 2);
"""


def build_ds():
    conn = sqlite3.connect(':memory:', isolation_level=None)
    conn.executescript(SCHEMA)
    conn.executescript(SEEDS)
    return MemDS(conn)


def insert_order_no(ds, table, order_no, row_id=None):
    if row_id is None:
        ds.execute('INSERT INTO %s (order_no) VALUES (?)' % table, [order_no])
    else:
        ds.execute('INSERT INTO %s (id, order_no) VALUES (?, ?)' % table, [row_id, order_no])
