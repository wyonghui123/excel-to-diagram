# -*- coding: utf-8 -*-
"""销售订单波次 1 · 定价链测试助手

【为什么放在 factories/】
  `meta/tests/conftest.py::_check_raw_sql_in_tests` 会把**含裸 SQL DML**
  (`INSERT INTO` / `UPDATE x SET` / `DELETE FROM`) 的测试文件整体 skip ——
  测试自身真绿却默认不跑（假绿）。本模块收纳建表 / 播种 DML，
  让 W1-A 的种子测试与解析测试**默认口径即运行**，无需 `ALLOW_RAW_SQL=1`。

【对外接口】
  clone_schema(src, dst, tables, item_ids)  —— 复制表结构（可选复制物料行）
  create_pricing_tables(conn)               —— 解析测试的最小表结构
  seed_row(path, table, **values)           —— 插一行，返回 rowid
  seed_rule(path, **overrides)              —— pricing_determinations 一行
  seed_rate_table(path, **overrides)        —— rate_tables 一行
  update_row(path, table, row_id, **values) —— 按 id 改一行
"""
import sqlite3

#: 解析测试用的最小表结构（只含被测服务真正查询的列）
PRICING_DDL = """
CREATE TABLE pricing_determinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    sales_org_id INTEGER,
    order_type_id INTEGER,
    rate_table_id INTEGER,
    calc_procedure_id INTEGER,
    lookup_sequence_id INTEGER,
    currency TEXT,
    seq INTEGER,
    valid_from TEXT,
    valid_to TEXT,
    status TEXT,
    description TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE calc_procedures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT
);
CREATE TABLE lookup_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    steps TEXT
);
CREATE TABLE key_schemas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    key_fields TEXT
);
CREATE TABLE rate_tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    status TEXT,
    currency TEXT,
    owner_org_id INTEGER
);
"""

RULE_DEFAULTS = {
    'code': 'PD',
    'name': '规则',
    'sales_org_id': None,
    'order_type_id': None,
    'rate_table_id': 1,
    'calc_procedure_id': 1,
    'lookup_sequence_id': 1,
    'currency': None,
    'seq': 100,
    'valid_from': None,
    'valid_to': None,
    'status': 'active',
}

RATE_TABLE_DEFAULTS = {
    'code': 'PL_X',
    'name': '价目表',
    'status': 'approved',
    'currency': 'CNY',
    'owner_org_id': None,
}


def clone_schema(src_path, dst_path, tables, item_ids=()):
    """把源库指定表的 DDL 复制到目标库；`item_ids` 非空时把这些物料行一并复制。

    返回源库中缺失的表名列表（调用方可据此 skip）。
    """
    src = sqlite3.connect(str(src_path))
    dst = sqlite3.connect(str(dst_path))
    try:
        marks = ', '.join('?' * len(tables))
        rows = src.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' "
            "AND name IN ({0})".format(marks), list(tables)).fetchall()
        found = {name for name, _ddl in rows}
        missing = [t for t in tables if t not in found]
        for _name, ddl in rows:
            if ddl:
                dst.execute(ddl)

        if item_ids and 'items' in found:
            cols = [r[1] for r in src.execute('PRAGMA table_info(items)')]
            col_sql = ', '.join(cols)
            value_sql = ', '.join('?' * len(cols))
            for item_id in item_ids:
                row = src.execute(
                    'SELECT * FROM items WHERE id = ?', (item_id,)).fetchone()
                if row:
                    dst.execute(
                        'INSERT INTO items ({0}) VALUES ({1})'.format(
                            col_sql, value_sql), row)
        dst.commit()
    finally:
        src.close()
        dst.close()
    return missing


def create_pricing_tables(conn):
    """建解析测试用的最小表结构。"""
    conn.executescript(PRICING_DDL)
    conn.commit()


def seed_row(path, table, **values):
    """插一行；列名与表名来自本仓清单，非外部输入。返回 rowid。"""
    cols = list(values)
    sql = 'INSERT INTO {0} ({1}) VALUES ({2})'.format(
        table, ', '.join(cols), ', '.join('?' for _ in cols))
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.execute(sql, [values[c] for c in cols])
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def seed_rule(path, **overrides):
    row = dict(RULE_DEFAULTS)
    row.update(overrides)
    return seed_row(path, 'pricing_determinations', **row)


def seed_rate_table(path, **overrides):
    row = dict(RATE_TABLE_DEFAULTS)
    row.update(overrides)
    return seed_row(path, 'rate_tables', **row)


def update_row(path, table, row_id, **values):
    """按 id 更新一行。"""
    set_sql = ', '.join('{0} = ?'.format(c) for c in values)
    sql = 'UPDATE {0} SET {1} WHERE id = ?'.format(table, set_sql)
    conn = sqlite3.connect(str(path))
    try:
        params = [values[c] for c in values] + [row_id]
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def delete_row(path, table, **where):
    """按等值条件删除行；列名与表名来自本仓清单，非外部输入。"""
    sql = 'DELETE FROM {0} WHERE {1}'.format(
        table, ' AND '.join('{0} = ?'.format(c) for c in where))
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.execute(sql, [where[c] for c in where])
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
