# -*- coding: utf-8 -*-
"""开票计划生成测试夹具（内存 SQLite，建表 / 播种集中在此）。

conftest 的 raw-SQL 扫描只放行 factories 目录，故 DDL 与 INSERT 全部收口于本文件；
测试文件只调用 `build_conn` / `add_line` / `add_schedule` / `list_schedules`。
"""
import sqlite3

from meta.tests.factories._customer_invoice_helpers import MemoryDataSource

ORDER_ID = 1
LINE_TM = 31
LINE_FIXED = 32
LINE_MILESTONE = 33
LINE_DELIVERY = 34

DDL = """
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY,
    order_no TEXT,
    document_type_id INTEGER,
    order_date TEXT,
    status TEXT,
    sales_org_id INTEGER,
    org_id INTEGER,
    currency_id INTEGER,
    exchange_rate REAL,
    customer_account_id INTEGER,
    project_id INTEGER,
    confirmed_date TEXT
);
CREATE TABLE sales_order_lines (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    line_no INTEGER,
    qty REAL,
    uom_id INTEGER,
    net_amount REAL,
    billed_amount REAL DEFAULT 0,
    project_id INTEGER,
    plant_location_id INTEGER,
    line_type_id INTEGER,
    billing_relevance TEXT,
    billing_method TEXT,
    service_start_date TEXT,
    service_end_date TEXT,
    billing_period_count INTEGER,
    billing_interval_months INTEGER DEFAULT 1,
    billing_anchor_date TEXT,
    billing_lead_days INTEGER DEFAULT 0,
    billing_proration TEXT DEFAULT 'none'
);
CREATE TABLE sales_order_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    line_id INTEGER,
    project_id INTEGER,
    plant_location_id INTEGER,
    schedule_no INTEGER,
    schedule_kind TEXT,
    promised_date TEXT,
    promised_qty REAL,
    billing_percent REAL,
    billed_amount REAL DEFAULT 0,
    billing_status TEXT,
    milestone_code TEXT,
    service_visit_no INTEGER,
    status TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE type_definitions (
    id INTEGER PRIMARY KEY,
    delivery_relevant INTEGER DEFAULT 1
);
"""


def build_conn(*, order_status: str = 'confirmed',
               confirmed_date: str = '2026-01-10',
               project_id: int = 7) -> sqlite3.Connection:
    conn = sqlite3.connect(':memory:')
    conn.executescript(DDL)
    conn.execute(
        'INSERT INTO sales_orders (id, order_no, document_type_id, order_date, '
        'status, sales_org_id, org_id, currency_id, exchange_rate, '
        'customer_account_id, project_id, confirmed_date) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [ORDER_ID, 'SO-0001', 1, '2026-01-01', order_status, 1, 1, 1, 1.0,
         100, project_id, confirmed_date])
    conn.commit()
    return conn


def make_ds(conn: sqlite3.Connection) -> MemoryDataSource:
    return MemoryDataSource(conn)


def add_line(conn: sqlite3.Connection, line_id: int, *,
             order_id: int = ORDER_ID, line_no: int = None,
             relevance: str = 'plan', method: str = 'time_and_material',
             qty: float = 100.0, net_amount: float = 1000.0,
             billed_amount: float = 0.0, project_id: int = None,
             plant_location_id: int = None, line_type_id: int = None,
             service_start: str = None, service_end: str = None,
             period_count: int = None, interval: int = None,
             anchor: str = None, lead_days: int = None,
             proration: str = None) -> None:
    conn.execute(
        'INSERT INTO sales_order_lines (id, order_id, line_no, qty, uom_id, '
        'net_amount, billed_amount, project_id, plant_location_id, '
        'line_type_id, billing_relevance, billing_method, service_start_date, '
        'service_end_date, billing_period_count, billing_interval_months, '
        'billing_anchor_date, billing_lead_days, billing_proration) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [line_id, order_id, line_no if line_no is not None else line_id,
         qty, 1, net_amount, billed_amount, project_id, plant_location_id,
         line_type_id, relevance, method, service_start, service_end,
         period_count, interval, anchor, lead_days, proration])
    conn.commit()


def add_schedule(conn: sqlite3.Connection, line_id: int, *,
                 schedule_no: int = 1, status: str = 'planned',
                 billing_percent: float = 100.0,
                 billed_amount: float = 0.0,
                 promised_date: str = '2026-01-10',
                 order_id: int = ORDER_ID) -> None:
    conn.execute(
        'INSERT INTO sales_order_schedules (order_id, line_id, project_id, '
        'plant_location_id, schedule_no, schedule_kind, promised_date, '
        'promised_qty, billing_percent, billed_amount, billing_status, '
        'milestone_code, service_visit_no, status, created_at, updated_at) '
        "VALUES (?, ?, ?, ?, ?, 'billing', ?, NULL, ?, ?, 'none', NULL, NULL, "
        "?, '2026-01-01 00:00:00', '2026-01-01 00:00:00')",
        [order_id, line_id, None, None, schedule_no, promised_date,
         billing_percent, billed_amount, status])
    conn.commit()


def list_schedules(conn: sqlite3.Connection,
                   line_id: int = None) -> list:
    sql = ('SELECT id, line_id, schedule_no, schedule_kind, promised_date, '
           'promised_qty, billing_percent, billed_amount, billing_status, '
           'status, plant_location_id, milestone_code '
           'FROM sales_order_schedules')
    params = []
    if line_id is not None:
        sql += ' WHERE line_id = ?'
        params.append(line_id)
    sql += ' ORDER BY line_id, schedule_no, id'
    cur = conn.execute(sql, params)
    columns = [item[0] for item in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]