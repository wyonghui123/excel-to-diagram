# -*- coding: utf-8 -*-
"""W5 采购发票三单匹配服务测试夹具。

口径：
  · 使用真实 `SQLiteAdapter` + 临时文件（服务层依赖 table_exists /
    get_table_columns / DataSource.transaction），MemoryDataSource 不适用；
  · 发票头/行直接复用 v252 的生产 DDL，保证列集合与生产一致；
  · 单据流边表 / 消耗视图走 `ensure_doc_flow_edge_tables`（与生产同一机制）；
  · 规则写入走 `upsert_rules`（与 v254 迁移同源）。
"""

from __future__ import annotations

import uuid

from meta.core.sql_adapters import SQLiteAdapter
from meta.core.doc_flow_schema import ensure_doc_flow_edge_tables
from meta.core.doc_flow_rule_store import (
    ensure_doc_flow_rule_table,
    upsert_rules,
)
from meta.migrations.v252__vendor_invoice_object import HEADER_DDL, LINE_DDL
from meta.tests.shared.db_schema import create_audit_logs

# ---------------------------------------------------------------- 业务常量
SUPPLIER_ACCOUNT_ID = 8001
SUPPLIER_PARTY_ID = 9001
CURRENCY_ID = 1
ORG_ID = 10
PURCHASE_ORG_ID = 11
DOC_TYPE_ID = 9101
PO_ID = 7001
PO_LINE_ID = 7101
SCHEDULE_ID = 7201
RECEIPT_ID = 7301
RECEIPT_LINE_ID = 7401
ITEM_ID = 5001
UOM_ID = 1
LINE_TYPE_ID = 31

SUPPORT_DDL = (
    """
    CREATE TABLE IF NOT EXISTS purchase_orders (
        id INTEGER PRIMARY KEY,
        order_no VARCHAR(30),
        supplier_account_id INTEGER,
        supplier_party_id INTEGER,
        currency_id INTEGER,
        org_id INTEGER,
        purchase_org_id INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS purchase_order_lines (
        id INTEGER PRIMARY KEY,
        order_id INTEGER,
        line_no INTEGER,
        item_id INTEGER,
        item_group_id INTEGER,
        line_type_id INTEGER,
        uom_id INTEGER,
        unit_price NUMERIC(18,6)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS purchase_order_schedule (
        id INTEGER PRIMARY KEY,
        order_id INTEGER,
        line_id INTEGER,
        schedule_kind VARCHAR(20) DEFAULT 'delivery',
        promised_qty NUMERIC(18,4) DEFAULT 0,
        returned_qty NUMERIC(18,4) DEFAULT 0,
        status VARCHAR(20) DEFAULT 'planned'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS receipt_lines (
        id INTEGER PRIMARY KEY,
        receipt_id INTEGER,
        schedule_id INTEGER,
        order_line_id INTEGER,
        item_id INTEGER,
        uom_id INTEGER,
        qty_received NUMERIC(18,4) DEFAULT 0,
        qty_rejected NUMERIC(18,4) DEFAULT 0,
        rejection_disposition VARCHAR(30),
        status VARCHAR(20) DEFAULT 'posted'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS control_parameter_defs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code VARCHAR(80) UNIQUE,
        name VARCHAR(200),
        domain VARCHAR(30),
        value_type VARCHAR(20) DEFAULT 'decimal',
        target_bo VARCHAR(60),
        default_value VARCHAR(80),
        tolerance_direction VARCHAR(20) DEFAULT 'upper',
        tolerance_basis VARCHAR(20) DEFAULT 'absolute',
        status VARCHAR(20) DEFAULT 'active',
        description VARCHAR(500),
        created_at DATETIME
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS control_parameter_values (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        control_parameter_id INTEGER,
        org_id INTEGER,
        document_type_id INTEGER,
        line_type_id INTEGER,
        item_group_id INTEGER,
        specificity_rank INTEGER DEFAULT 0,
        value VARCHAR(80),
        status VARCHAR(20) DEFAULT 'active'
    )
    """,
)

RULES = (
    {
        'rule_id': 'po_schedule_to_vendor_invoice_line',
        'source_bo': 'purchase_order_schedule',
        'target_bo': 'vendor_invoice_line',
        'source_qty_field': 'promised_qty',
        'pool': 'billing',
    },
    {
        'rule_id': 'receipt_line_to_vendor_invoice_line',
        'source_bo': 'receipt_line',
        'target_bo': 'vendor_invoice_line',
        'source_qty_field': 'qty_received',
        'pool': 'ap_match',
    },
    {
        'rule_id': 'vendor_invoice_line_to_credit_memo_line',
        'source_bo': 'vendor_invoice_line',
        'target_bo': 'vendor_invoice_line',
        'source_qty_field': 'qty',
        'pool': 'billing',
    },
)

#: 默认零容差，便于断言边界（金额容差 0.01 兜住四舍五入）
PARAMS = (
    ('vi_price_tolerance', '0', 'percent'),
    ('vi_qty_tolerance_receipt', '0', 'percent'),
    ('vi_qty_tolerance_order', '0', 'percent'),
    ('vi_amount_tolerance_abs', '0.01', 'absolute'),
    ('vi_rounding_tolerance_abs', '0.01', 'absolute'),
)


def make_env(tmp_path):
    """建一个带全部依赖表的临时库，返回已连接的 SQLiteAdapter。"""
    ds = SQLiteAdapter()
    ds.connect(path=str(tmp_path / 'vendor_invoice_match.db'))
    ds.execute(HEADER_DDL)
    ds.execute(LINE_DDL)
    for ddl in SUPPORT_DDL:
        ds.execute(ddl)
    create_audit_logs(ds)
    ensure_doc_flow_edge_tables(ds)
    ensure_doc_flow_rule_table(ds)
    upsert_rules(ds, list(RULES))
    seed_params(ds)
    ds.commit()
    return ds


def seed_params(ds):
    for code, value, basis in PARAMS:
        ds.execute(
            'INSERT INTO control_parameter_defs '
            '(code, name, domain, value_type, default_value, '
            ' tolerance_direction, tolerance_basis, status) '
            "VALUES (?, ?, 'procurement', 'decimal', ?, 'upper', ?, 'active')",
            [code, code, value, basis],
        )


def seed_purchase_order(ds, *, promised_qty=10.0, returned_qty=0.0,
                        unit_price=10.0, line_type_id=LINE_TYPE_ID):
    ds.execute(
        'INSERT OR REPLACE INTO purchase_orders '
        '(id, order_no, supplier_account_id, supplier_party_id, currency_id, '
        ' org_id, purchase_org_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
        [PO_ID, 'PO-0001', SUPPLIER_ACCOUNT_ID, SUPPLIER_PARTY_ID,
         CURRENCY_ID, ORG_ID, PURCHASE_ORG_ID],
    )
    ds.execute(
        'INSERT OR REPLACE INTO purchase_order_lines '
        '(id, order_id, line_no, item_id, item_group_id, line_type_id, uom_id, '
        ' unit_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        [PO_LINE_ID, PO_ID, 1, ITEM_ID, None, line_type_id, UOM_ID, unit_price],
    )
    ds.execute(
        'INSERT OR REPLACE INTO purchase_order_schedule '
        '(id, order_id, line_id, schedule_kind, promised_qty, returned_qty, '
        ' status) VALUES (?, ?, ?, ?, ?, ?, ?)',
        [SCHEDULE_ID, PO_ID, PO_LINE_ID, 'delivery', promised_qty,
         returned_qty, 'confirmed'],
    )
    ds.commit()


def seed_receipt_line(ds, *, qty_received=10.0, qty_rejected=0.0,
                      disposition=None):
    ds.execute(
        'INSERT OR REPLACE INTO receipt_lines '
        '(id, receipt_id, schedule_id, order_line_id, item_id, uom_id, '
        ' qty_received, qty_rejected, rejection_disposition, status) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [RECEIPT_LINE_ID, RECEIPT_ID, SCHEDULE_ID, PO_LINE_ID, ITEM_ID,
         UOM_ID, qty_received, qty_rejected, disposition, 'posted'],
    )
    ds.commit()


def insert_invoice(ds, *, invoice_no='VI-0001', category='invoice',
                   direction=1, status='draft', supplier_invoice_no=None,
                   match_mode='gr_based', pricing_mode='po_price',
                   net_amount=100.0, tax_amount=13.0, gross_amount=113.0,
                   invoice_date='2026-11-01', document_type_id=DOC_TYPE_ID):
    ds.execute(
        'INSERT INTO vendor_invoices '
        '(invoice_no, document_type_id, document_category, direction, '
        ' invoice_date, status, match_mode, supplier_account_id, '
        ' supplier_party_id, currency_id, org_id, supplier_invoice_no, '
        ' net_amount, tax_amount, gross_amount, match_pricing_mode) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [invoice_no, document_type_id, category, direction, invoice_date,
         status, match_mode, SUPPLIER_ACCOUNT_ID, SUPPLIER_PARTY_ID,
         CURRENCY_ID, ORG_ID, supplier_invoice_no or invoice_no,
         net_amount, tax_amount, gross_amount, pricing_mode],
    )
    rows = ds.query('SELECT id FROM vendor_invoices WHERE invoice_no = ?',
                    [invoice_no])
    return rows[0]['id']


def insert_line(ds, invoice_id, *, line_no=1, qty=10.0, unit_price=10.0,
                net_amount=100.0, tax_amount=13.0, gross_amount=113.0,
                schedule_id=None, receipt_line_id=None, invoice_line_id=None,
                return_line_id=None, po_unit_price=None,
                item_id=ITEM_ID, uom_id=UOM_ID, line_type_id=LINE_TYPE_ID,
                match_status='unmatched', override_reason=None):
    ds.execute(
        'INSERT INTO vendor_invoice_lines '
        '(invoice_id, line_no, schedule_id, receipt_line_id, invoice_line_id, '
        ' return_line_id, item_id, line_type_id, qty, uom_id, unit_price, '
        ' po_unit_price, net_amount, tax_amount, gross_amount, match_status, '
        ' override_reason) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [invoice_id, line_no, schedule_id, receipt_line_id, invoice_line_id,
         return_line_id, item_id, line_type_id, qty, uom_id, unit_price,
         po_unit_price, net_amount, tax_amount, gross_amount, match_status,
         override_reason],
    )
    ds.commit()
    rows = ds.query(
        'SELECT id FROM vendor_invoice_lines WHERE invoice_id = ? AND line_no = ?',
        [invoice_id, line_no])
    return rows[0]['id']


def insert_edge(ds, *, rule_id='receipt_line_to_vendor_invoice_line',
                source_bo='receipt_line', source_id=RECEIPT_LINE_ID,
                target_line_id, quantity=10.0, pool='ap_match',
                status='active', quantity_sign='normal',
                edge_kind='normal', amount=100.0):
    """直接落一条正常边（绕开 derive 引擎，用于红冲场景）。"""
    edge_id = uuid.uuid4().hex
    ds.execute(
        'INSERT INTO doc_flow_edges '
        '(id, rule_id, source_bo, source_id, source_item, target_bo, target_id, '
        ' target_item, quantity, amount, currency, unit, quantity_sign, '
        ' edge_kind, pool, status, source_instance_id, target_instance_id, '
        ' derive_key, derived_by, derived_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [edge_id, rule_id, source_bo, str(source_id), '', 'vendor_invoice_line',
         str(target_line_id), str(target_line_id), quantity, amount, '',
         str(UOM_ID), quantity_sign, edge_kind, pool, status, '', '', '', 'test',
         '2026-11-01 00:00:00'],
    )
    ds.commit()
    return edge_id


def consumed_qty(ds, source_bo, source_id, pool):
    rows = ds.query(
        'SELECT COALESCE(SUM(consumed_qty), 0) AS q '
        'FROM v_doc_flow_consumed_qty '
        'WHERE source_bo = ? AND source_id = ? AND pool = ?',
        [source_bo, str(source_id), pool])
    return float(rows[0]['q'] or 0) if rows else 0.0


def count_edges(ds, **where):
    clause = ' AND '.join('{0} = ?'.format(key) for key in where)
    params = list(where.values())
    sql = 'SELECT COUNT(*) AS n FROM doc_flow_edges'
    if clause:
        sql += ' WHERE ' + clause
    return ds.query(sql, params)[0]['n']