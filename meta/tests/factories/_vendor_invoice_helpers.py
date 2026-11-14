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
from meta.migrations.v252__vendor_invoice_object import (
    HEADER_DDL,
    HEADER_TABLE,
    LINE_DDL,
)
from meta.migrations.v271__vendor_invoice_schedule import (
    INDEXES as SCHEDULE_INDEXES,
    SCHEDULE_DDL,
)
from meta.migrations.v273__vendor_return_open_amount import RETURN_OPEN_DDL
from meta.tests.shared.db_schema import create_audit_logs

# ---------------------------------------------------------------- 业务常量
SUPPLIER_ACCOUNT_ID = 8001
SUPPLIER_PARTY_ID = 9001
CURRENCY_ID = 1
ORG_ID = 10
PURCHASE_ORG_ID = 11
DOC_TYPE_ID = 9101
RED_TYPE_ID = 9102
#: R-VI-52：贷项的红字类型（借项单，direction +1）
DEBIT_TYPE_ID = 9103
ADJUSTMENT_TYPE_ID = 9105
#: 退货收货单类型（scope_bo='receipt'，document_category='return'）
RECEIPT_RETURN_TYPE_ID = 9301
VI_SEQUENCE_ID = 9201
VCM_SEQUENCE_ID = 9202
VIA_SEQUENCE_ID = 9203
VDM_SEQUENCE_ID = 9204
VRT_SEQUENCE_ID = 9205
PO_ID = 7001
PO_LINE_ID = 7101
SCHEDULE_ID = 7201
RECEIPT_ID = 7301
RECEIPT_LINE_ID = 7401
ITEM_ID = 5001
UOM_ID = 1
LINE_TYPE_ID = 31
# W6 行类型种子（Spec §22.10）
LINE_TYPE_SERVICE_ID = 32
LINE_TYPE_FREIGHT_ID = 33
LINE_TYPE_SURCHARGE_ID = 34
LINE_TYPE_DISCOUNT_ID = 35

SUPPORT_DDL = (
    """
    CREATE TABLE IF NOT EXISTS vendor_accounts (
        id INTEGER PRIMARY KEY,
        name VARCHAR(200),
        default_payment_term_id INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS purchase_orders (
        id INTEGER PRIMARY KEY,
        order_no VARCHAR(30),
        supplier_account_id INTEGER,
        supplier_party_id INTEGER,
        currency_id INTEGER,
        org_id INTEGER,
        purchase_org_id INTEGER,
        payment_term_id INTEGER,
        header_surcharge_amount NUMERIC(18,4),
        header_discount_amount NUMERIC(18,4),
        status VARCHAR(20) DEFAULT 'confirmed'
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
        unit_price NUMERIC(18,6),
        tax_rate_percent NUMERIC(18,6)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY,
        receipt_no VARCHAR(30),
        document_type_id INTEGER,
        status VARCHAR(20) DEFAULT 'posted'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS purchase_order_schedules (
        id INTEGER PRIMARY KEY,
        order_id INTEGER,
        line_id INTEGER,
        schedule_kind VARCHAR(20) DEFAULT 'delivery',
        promised_qty NUMERIC(18,4) DEFAULT 0,
        returned_qty NUMERIC(18,4) DEFAULT 0,
        status VARCHAR(20) DEFAULT 'planned',
        created_at DATETIME,
        updated_at DATETIME
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
        status VARCHAR(20) DEFAULT 'posted',
        created_at DATETIME,
        updated_at DATETIME
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
    """
    CREATE TABLE IF NOT EXISTS tax_rates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tax_code_id INTEGER,
        rate_percent NUMERIC(9,4),
        effective_from DATE,
        effective_to DATE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS type_definitions (
        id INTEGER PRIMARY KEY,
        code VARCHAR(40),
        scope_bo VARCHAR(60),
        document_role VARCHAR(20),
        document_category VARCHAR(30),
        direction INTEGER DEFAULT 1,
        reversal_type_id INTEGER,
        level VARCHAR(20) DEFAULT 'header',
        is_default INTEGER DEFAULT 0,
        number_sequence_id INTEGER,
        status VARCHAR(20) DEFAULT 'active'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS number_sequences (
        id INTEGER PRIMARY KEY,
        code VARCHAR(30) UNIQUE,
        name VARCHAR(50),
        pattern VARCHAR(80),
        scope_fields TEXT,
        date_field VARCHAR(30) DEFAULT 'order_date',
        start_value INTEGER DEFAULT 1,
        on_exhaust VARCHAR(20) DEFAULT 'error',
        preview VARCHAR(40),
        status VARCHAR(20) DEFAULT 'active',
        description TEXT,
        created_at DATETIME
    )
    """,
    # W8-P1：费用分摊（规则 / 留痕 / 币种）
    """
    CREATE TABLE IF NOT EXISTS currencies (
        id INTEGER PRIMARY KEY,
        code VARCHAR(3) UNIQUE NOT NULL,
        name VARCHAR(50) NOT NULL,
        decimal_places INTEGER NOT NULL DEFAULT 2
    )
    """,
    # v271：付款条件（AP Payment Plan 期次推算依赖）
    """
    CREATE TABLE IF NOT EXISTS payment_terms (
        id INTEGER PRIMARY KEY,
        code VARCHAR(32),
        name VARCHAR(128),
        basis_date_rule VARCHAR(32) DEFAULT 'invoice_date',
        cutoff_day INTEGER,
        status VARCHAR(20) DEFAULT 'active'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS payment_term_lines (
        id INTEGER PRIMARY KEY,
        payment_term_id INTEGER,
        seq INTEGER,
        percentage NUMERIC(9,4),
        offset_months INTEGER DEFAULT 0,
        fixed_day_of_month INTEGER,
        offset_days INTEGER DEFAULT 0,
        discount_days INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS allocation_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code VARCHAR(50) UNIQUE NOT NULL,
        name VARCHAR(100) NOT NULL,
        basis VARCHAR(200) NOT NULL DEFAULT 'equal',
        manual_factor REAL,
        group_by VARCHAR(100),
        rounding VARCHAR(20),
        floor REAL,
        target VARCHAR(200) NOT NULL DEFAULT 'cost',
        description TEXT,
        created_at DATETIME,
        updated_at DATETIME
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS allocation_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code VARCHAR(50) UNIQUE NOT NULL,
        document_type VARCHAR(50) NOT NULL,
        document_id INTEGER NOT NULL,
        document_line_id INTEGER,
        parent_id INTEGER NOT NULL,
        level VARCHAR(200) NOT NULL,
        sequence INTEGER NOT NULL DEFAULT 0,
        amount REAL NOT NULL,
        net_amount REAL NOT NULL,
        currency VARCHAR(10) DEFAULT 'CNY',
        sign VARCHAR(200) NOT NULL DEFAULT '+',
        allocation_rule_id INTEGER NOT NULL,
        allocation_basis VARCHAR(200) NOT NULL,
        allocation_basis_field VARCHAR(100),
        group_by VARCHAR(100),
        rounding VARCHAR(20),
        floor_value REAL,
        origin VARCHAR(200) NOT NULL DEFAULT 'unplanned',
        charge_source VARCHAR(50),
        source_document_type VARCHAR(50),
        source_document_id INTEGER,
        target VARCHAR(20),
        status VARCHAR(200) NOT NULL DEFAULT 'active',
        created_at DATETIME,
        updated_at DATETIME
    )
    """,
)

RULES = (
    {
        'rule_id': 'po_schedule_to_vendor_invoice_line',
        'source_bo': 'purchase_order_schedule',
        'target_bo': 'vendor_invoice_line',
        'source_qty_field': 'promised_qty',
        'target_qty_field': 'qty',
        'pool': 'billing',
    },
    {
        'rule_id': 'receipt_line_to_vendor_invoice_line',
        'source_bo': 'receipt_line',
        'target_bo': 'vendor_invoice_line',
        'source_qty_field': 'qty_received',
        'target_qty_field': 'qty',
        'pool': 'ap_match',
    },
    {
        'rule_id': 'vendor_invoice_line_to_credit_memo_line',
        'source_bo': 'vendor_invoice_line',
        'target_bo': 'vendor_invoice_line',
        'source_qty_field': 'qty',
        'target_qty_field': 'qty',
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


#: v252 基线的行表 DDL 只允许 4 个 match_status；W10-1 新增 no_receipt。
#: 生产由 `sync_schema --execute` 按 YAML 枚举重建 CHECK，这里同步模拟。
LINE_STATUS_CHECK_OLD = (
    "CHECK (match_status IN "
    "('unmatched', 'matched', 'exception', 'overridden'))")
LINE_STATUS_CHECK_NEW = (
    "CHECK (match_status IN "
    "('unmatched', 'matched', 'exception', 'overridden', 'no_receipt'))")
LINE_DDL_CURRENT = LINE_DDL.replace(LINE_STATUS_CHECK_OLD, LINE_STATUS_CHECK_NEW)


def make_env(tmp_path):
    """建一个带全部依赖表的临时库，返回已连接的 SQLiteAdapter。"""
    ds = SQLiteAdapter()
    ds.connect(path=str(tmp_path / 'vendor_invoice_match.db'))
    ds.execute(HEADER_DDL)
    if LINE_DDL_CURRENT == LINE_DDL:
        raise RuntimeError('v252 LINE_DDL 的 match_status CHECK 已变更，需同步本夹具')
    ds.execute(LINE_DDL_CURRENT)
    # v258 补列（HEADER_DDL 是 v252 基线，生产库由迁移追加）
    if 'reversal_reason' not in ds.get_table_columns(HEADER_TABLE):
        ds.execute(
            'ALTER TABLE vendor_invoices ADD COLUMN reversal_reason VARCHAR(256)')
    # v259 调整单三列
    columns = ds.get_table_columns(HEADER_TABLE)
    if 'adjustment_of_invoice_id' not in columns:
        ds.execute(
            'ALTER TABLE vendor_invoices ADD COLUMN adjustment_of_invoice_id INTEGER')
    if 'adjustment_direction' not in columns:
        ds.execute(
            'ALTER TABLE vendor_invoices ADD COLUMN adjustment_direction VARCHAR(10)')
    if 'adjustment_reason' not in columns:
        ds.execute(
            'ALTER TABLE vendor_invoices ADD COLUMN adjustment_reason VARCHAR(256)')
    # v262 行价格追溯两列（HEADER_DDL 是 v252 基线，生产库由迁移追加）
    line_columns = ds.get_table_columns('vendor_invoice_lines')
    if 'price_source' not in line_columns:
        ds.execute(
            'ALTER TABLE vendor_invoice_lines ADD COLUMN price_source VARCHAR(20)')
    if 'price_trace' not in line_columns:
        ds.execute('ALTER TABLE vendor_invoice_lines ADD COLUMN price_trace TEXT')
    # v260 金额冻结列（直录税额 / 含税毛额 / 税率快照）
    if 'supplier_gross_amount' not in ds.get_table_columns(HEADER_TABLE):
        ds.execute(
            'ALTER TABLE vendor_invoices ADD COLUMN supplier_gross_amount NUMERIC(18,4)')
    if 'rounding_diff' not in ds.get_table_columns(HEADER_TABLE):
        ds.execute(
            'ALTER TABLE vendor_invoices ADD COLUMN rounding_diff NUMERIC(18,4)')
    if 'tax_rate_percent' not in line_columns:
        ds.execute(
            'ALTER TABLE vendor_invoice_lines ADD COLUMN tax_rate_percent NUMERIC(9,4)')
    # v268 费用分摊派生列（W8-P1）
    if 'allocated_charge_amount' not in ds.get_table_columns(
            'vendor_invoice_lines'):
        ds.execute(
            'ALTER TABLE vendor_invoice_lines ADD COLUMN '
            'allocated_charge_amount NUMERIC(18,4) NOT NULL DEFAULT 0')
    # v271 应付期次（AP Payment Plan）
    if 'payment_term_id' not in ds.get_table_columns(HEADER_TABLE):
        ds.execute(
            'ALTER TABLE vendor_invoices ADD COLUMN payment_term_id INTEGER')
    ds.execute(SCHEDULE_DDL)
    for _name, ddl in SCHEDULE_INDEXES:
        ds.execute(ddl)
    for ddl in SUPPORT_DDL:
        ds.execute(ddl)
    create_audit_logs(ds)
    ensure_doc_flow_edge_tables(ds)
    ensure_doc_flow_rule_table(ds)
    upsert_rules(ds, list(RULES))
    seed_params(ds)
    create_return_open_view(ds)
    ds.commit()
    return ds


def create_return_open_view(ds):
    """建 v273 退货贷项余量视图（测试态直接执行生产 DDL）。"""
    ds.execute(RETURN_OPEN_DDL)
    ds.commit()


def seed_type_definitions(ds, *, reversal_type_id=RED_TYPE_ID):
    """发票（正）/ 红字贷项（-1）/ 红字借项（+1）/ 调整单 / 退货收货单。"""
    ds.execute('DELETE FROM type_definitions WHERE scope_bo IN (?, ?)',
               ['vendor_invoice', 'receipt'])
    _seed_sequence(ds, VI_SEQUENCE_ID, 'VI', 'VI-{DATE:yyyymm}-{SEQ:5}')
    _seed_sequence(ds, VCM_SEQUENCE_ID, 'VCM', 'VCM-{DATE:yyyymm}-{SEQ:5}')
    _seed_sequence(ds, VIA_SEQUENCE_ID, 'VIA', 'VIA-{DATE:yyyymm}-{SEQ:5}')
    _seed_sequence(ds, VDM_SEQUENCE_ID, 'VDM', 'VDM-{DATE:yyyymm}-{SEQ:5}')
    _seed_sequence(ds, VRT_SEQUENCE_ID, 'VRT', 'VRT-{DATE:yyyymm}-{SEQ:5}')
    ds.execute(
        'INSERT INTO type_definitions '
        '(id, code, scope_bo, document_role, document_category, direction, '
        ' reversal_type_id, level, is_default, number_sequence_id, status) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [DOC_TYPE_ID, 'VENDOR_INVOICE', 'vendor_invoice', 'invoice',
         'invoice', 1, reversal_type_id, 'header', 1, VI_SEQUENCE_ID, 'active'],
    )
    # R-VI-52：贷项的红字类型 = 借项（direction +1）
    ds.execute(
        'INSERT INTO type_definitions '
        '(id, code, scope_bo, document_role, document_category, direction, '
        ' reversal_type_id, level, is_default, number_sequence_id, status) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [RED_TYPE_ID, 'VENDOR_CREDIT_MEMO', 'vendor_invoice', 'credit_memo',
         'credit_memo', -1, DEBIT_TYPE_ID, 'header', 0, VCM_SEQUENCE_ID, 'active'],
    )
    ds.execute(
        'INSERT INTO type_definitions '
        '(id, code, scope_bo, document_role, document_category, direction, '
        ' reversal_type_id, level, is_default, number_sequence_id, status) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [DEBIT_TYPE_ID, 'VENDOR_DEBIT_MEMO', 'vendor_invoice', 'debit_memo',
         'debit_memo', 1, RED_TYPE_ID, 'header', 0, VDM_SEQUENCE_ID, 'active'],
    )
    ds.execute(
        'INSERT INTO type_definitions '
        '(id, code, scope_bo, document_role, document_category, direction, '
        ' reversal_type_id, level, is_default, number_sequence_id, status) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [ADJUSTMENT_TYPE_ID, 'VENDOR_INVOICE_ADJUSTMENT', 'vendor_invoice',
         'adjustment', 'adjustment', 1, None, 'header', 0, VIA_SEQUENCE_ID,
         'active'],
    )
    # R-VI-51：退货收货单类型（v273 视图按 scope_bo='receipt' + category='return' 识别）
    ds.execute(
        'INSERT INTO type_definitions '
        '(id, code, scope_bo, document_role, document_category, direction, '
        ' reversal_type_id, level, is_default, number_sequence_id, status) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [RECEIPT_RETURN_TYPE_ID, 'RCV_RETURN', 'receipt', 'return_line',
         'return', -1, None, 'header', 0, VRT_SEQUENCE_ID, 'active'],
    )
    # W6 行类型种子（Spec §22.10）：测试态 type_definitions 无 name /
    # line_category / delivery_relevant 列，只写公共列；费用行判定只看 code。
    for type_id, code, is_default in (
            (LINE_TYPE_ID, 'VI_LINE_GOODS', 1),
            (LINE_TYPE_SERVICE_ID, 'VI_LINE_SERVICE', 0),
            (LINE_TYPE_FREIGHT_ID, 'VI_LINE_FREIGHT', 0),
            (LINE_TYPE_SURCHARGE_ID, 'VI_LINE_SURCHARGE', 0),
            (LINE_TYPE_DISCOUNT_ID, 'VI_LINE_DISCOUNT', 0),
    ):
        ds.execute(
            'INSERT INTO type_definitions '
            '(id, code, scope_bo, level, is_default, status) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            [type_id, code, 'vendor_invoice', 'line', is_default, 'active'],
        )
    ds.commit()


def _seed_sequence(ds, sequence_id, code, pattern):
    ds.execute(
        'INSERT OR REPLACE INTO number_sequences '
        '(id, code, name, pattern, scope_fields, date_field, start_value, '
        ' on_exhaust, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [sequence_id, code, code, pattern, '', 'invoice_date', 1, 'error',
         'active'],
    )


def get_header(ds, invoice_id):
    rows = ds.query('SELECT * FROM vendor_invoices WHERE id = ?', [invoice_id])
    return rows[0] if rows else None


def set_supplier_gross(ds, invoice_id, amount):
    """写入原票票面总额（验证调整单不继承该字段）。"""
    ds.execute(
        'UPDATE vendor_invoices SET supplier_gross_amount = ? WHERE id = ?',
        [amount, invoice_id])
    ds.commit()


def get_lines(ds, invoice_id):
    return ds.query(
        'SELECT * FROM vendor_invoice_lines WHERE invoice_id = ? ORDER BY line_no',
        [invoice_id])


def seed_params(ds):
    for code, value, basis in PARAMS:
        ds.execute(
            'INSERT INTO control_parameter_defs '
            '(code, name, domain, value_type, default_value, '
            ' tolerance_direction, tolerance_basis, status) '
            "VALUES (?, ?, 'procurement', 'decimal', ?, 'upper', ?, 'active')",
            [code, code, value, basis],
        )


def set_param(ds, code, value):
    """按用例调整控制参数默认值（四维未命中时的回落值）。"""
    ds.execute(
        'UPDATE control_parameter_defs SET default_value = ? WHERE code = ?',
        [str(value), code])
    ds.commit()


def set_param_direction(ds, code, direction):
    """调整控制参数容差方向（R-VI-47：upper / lower / both）。"""
    ds.execute(
        'UPDATE control_parameter_defs SET tolerance_direction = ? WHERE code = ?',
        [direction, code])
    ds.commit()


def seed_charge_params(ds, *, tax_mode='line_direct', tax_tolerance='0.01',
                       freight_tolerance='0.00'):
    """W6 控制参数（Spec §22.10 / v264 同构）。"""
    rows = (
        ('vi_tax_mode', '采购发票税额模式', 'tax', 'enum', tax_mode, None, None),
        ('vi_tax_tolerance_abs', '采购发票税额绝对容差', 'tolerance', 'decimal',
         tax_tolerance, 'both', 'absolute'),
        ('vi_freight_tolerance_abs', '采购发票费用行绝对容差', 'tolerance',
         'decimal', freight_tolerance, 'both', 'absolute'),
        ('vi_po_tax_compare', '采购发票税额与订单比对', 'tax', 'bool',
         'false', None, None),
    )
    for code, name, domain, value_type, default, direction, basis in rows:
        ds.execute(
            "INSERT INTO control_parameter_defs "
            "(code, name, domain, value_type, default_value, "
            " tolerance_direction, tolerance_basis, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'active') "
            "ON CONFLICT(code) DO UPDATE SET default_value = excluded.default_value",
            [code, name, domain, value_type, default, direction, basis],
        )
    ds.commit()


def seed_pricing_mode_param(ds, default_value='po_price'):
    """v263 定价模式参数定义（vi_match_pricing_mode）。"""
    ds.execute(
        "INSERT OR IGNORE INTO control_parameter_defs "
        "(code, name, domain, value_type, target_bo, default_value, status) "
        "VALUES ('vi_match_pricing_mode', '采购发票定价模式', 'procurement', "
        "'enum', 'vendor_invoice', ?, 'active')",
        [default_value])
    ds.execute(
        "UPDATE control_parameter_defs SET default_value = ? "
        "WHERE code = 'vi_match_pricing_mode'", [default_value])
    ds.commit()


def seed_tax_rate(ds, *, tax_code_id, rate_percent,
                  effective_from='2020-01-01', effective_to=None):
    ds.execute(
        'INSERT INTO tax_rates '
        '(tax_code_id, rate_percent, effective_from, effective_to) '
        'VALUES (?, ?, ?, ?)',
        [tax_code_id, rate_percent, effective_from, effective_to])
    ds.commit()


def seed_purchase_order(ds, *, promised_qty=10.0, returned_qty=0.0,
                        unit_price=10.0, line_type_id=LINE_TYPE_ID,
                        header_surcharge_amount=0.0, header_discount_amount=0.0,
                        payment_term_id=None, po_id=PO_ID, order_no='PO-0001',
                        po_line_id=PO_LINE_ID, schedule_id=SCHEDULE_ID,
                        uom_id=UOM_ID, status='confirmed',
                        tax_rate_percent=None):
    ds.execute(
        'INSERT OR REPLACE INTO purchase_orders '
        '(id, order_no, supplier_account_id, supplier_party_id, currency_id, '
        ' org_id, purchase_org_id, payment_term_id, header_surcharge_amount, '
        ' header_discount_amount, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [po_id, order_no, SUPPLIER_ACCOUNT_ID, SUPPLIER_PARTY_ID,
         CURRENCY_ID, ORG_ID, PURCHASE_ORG_ID, payment_term_id,
         header_surcharge_amount, header_discount_amount, status],
    )
    ds.execute(
        'INSERT OR REPLACE INTO purchase_order_lines '
        '(id, order_id, line_no, item_id, item_group_id, line_type_id, uom_id, '
        ' unit_price, tax_rate_percent) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [po_line_id, po_id, 1, ITEM_ID, None, line_type_id, uom_id, unit_price,
         tax_rate_percent],
    )
    ds.execute(
        'INSERT OR REPLACE INTO purchase_order_schedules '
        '(id, order_id, line_id, schedule_kind, promised_qty, returned_qty, '
        ' status) VALUES (?, ?, ?, ?, ?, ?, ?)',
        [schedule_id, po_id, po_line_id, 'delivery', promised_qty,
         returned_qty, 'confirmed'],
    )
    ds.commit()


def seed_receipt_line(ds, *, qty_received=10.0, qty_rejected=0.0,
                      disposition=None, receipt_id=RECEIPT_ID,
                      receipt_line_id=RECEIPT_LINE_ID,
                      receipt_status='posted', schedule_id=SCHEDULE_ID,
                      order_line_id=PO_LINE_ID, uom_id=UOM_ID,
                      document_type_id=None):
    ds.execute(
        'INSERT OR REPLACE INTO receipts (id, receipt_no, document_type_id, status) '
        'VALUES (?, ?, ?, ?)',
        [receipt_id, 'GR-{0}'.format(receipt_id), document_type_id, receipt_status],
    )
    ds.execute(
        'INSERT OR REPLACE INTO receipt_lines '
        '(id, receipt_id, schedule_id, order_line_id, item_id, uom_id, '
        ' qty_received, qty_rejected, rejection_disposition, status) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [receipt_line_id, receipt_id, schedule_id, order_line_id, ITEM_ID,
         uom_id, qty_received, qty_rejected, disposition, 'posted'],
    )
    ds.commit()


def insert_invoice(ds, *, invoice_no='VI-0001', category='invoice',
                   direction=1, status='draft', supplier_invoice_no=None,
                   match_mode='gr_based', pricing_mode='po_price',
                   net_amount=100.0, tax_amount=13.0, gross_amount=113.0,
                   invoice_date='2026-11-01', document_type_id=DOC_TYPE_ID,
                   payment_term_id=None, reversal_of_invoice_id=None,
                   adjustment_of_invoice_id=None, currency_id=CURRENCY_ID,
                   exchange_rate=None):
    ds.execute(
        'INSERT INTO vendor_invoices '
        '(invoice_no, document_type_id, document_category, direction, '
        ' invoice_date, status, match_mode, supplier_account_id, '
        ' supplier_party_id, currency_id, exchange_rate, org_id, '
        ' supplier_invoice_no, net_amount, tax_amount, gross_amount, '
        ' match_pricing_mode, payment_term_id, reversal_of_invoice_id, '
        ' adjustment_of_invoice_id) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [invoice_no, document_type_id, category, direction, invoice_date,
         status, match_mode, SUPPLIER_ACCOUNT_ID, SUPPLIER_PARTY_ID,
         currency_id, exchange_rate, ORG_ID, supplier_invoice_no or invoice_no,
         net_amount, tax_amount, gross_amount, pricing_mode, payment_term_id,
         reversal_of_invoice_id, adjustment_of_invoice_id],
    )
    rows = ds.query('SELECT id FROM vendor_invoices WHERE invoice_no = ?',
                    [invoice_no])
    return rows[0]['id']


def insert_line(ds, invoice_id, *, line_no=1, qty=10.0, unit_price=10.0,
                net_amount=100.0, tax_amount=13.0, gross_amount=113.0,
                schedule_id=None, receipt_line_id=None, invoice_line_id=None,
                return_line_id=None, po_unit_price=None,
                item_id=ITEM_ID, uom_id=UOM_ID, line_type_id=LINE_TYPE_ID,
                match_status='unmatched', override_reason=None,
                price_includes_tax=0, tax_code_id=None,
                price_source=None, price_trace=None, tax_rate_percent=None):
    ds.execute(
        'INSERT INTO vendor_invoice_lines '
        '(invoice_id, line_no, schedule_id, receipt_line_id, invoice_line_id, '
        ' return_line_id, item_id, line_type_id, qty, uom_id, unit_price, '
        ' po_unit_price, net_amount, tax_amount, gross_amount, match_status, '
        ' override_reason, price_includes_tax, tax_code_id, '
        ' price_source, price_trace, tax_rate_percent) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [invoice_id, line_no, schedule_id, receipt_line_id, invoice_line_id,
         return_line_id, item_id, line_type_id, qty, uom_id, unit_price,
         po_unit_price, net_amount, tax_amount, gross_amount, match_status,
         override_reason, price_includes_tax, tax_code_id,
         price_source, price_trace, tax_rate_percent],
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


def update_edge_quantity(ds, rule_id, target_line_id, quantity):
    """改写指定原行某规则的 normal 边数量（模拟一条发票行分属多条计划行）。"""
    ds.execute(
        'UPDATE doc_flow_edges SET quantity = ? WHERE rule_id = ? AND target_id = ?',
        [quantity, rule_id, str(target_line_id)])
    ds.commit()


# ------------------------------------------------------------------ W8-P1

def seed_allocation_rule(ds, *, code='VI_CHARGE_BY_NET_VALUE', name='按净值摊费用',
                         basis='value', manual_factor=None, group_by=None,
                         rounding='round', floor=None, target='cost'):
    """v268 依赖的分摊规则（生产由 allocation_rules 维护）。"""
    ds.execute(
        'INSERT OR REPLACE INTO allocation_rules '
        '(code, name, basis, manual_factor, group_by, rounding, floor, target) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        [code, name, basis, manual_factor, group_by, rounding, floor, target])
    ds.commit()
    return ds.query('SELECT id FROM allocation_rules WHERE code = ?', [code])[0]['id']


def seed_charge_allocation_params(ds, *, enabled=False, rule_code='',
                                  org_id=ORG_ID):
    """v268 参数定义 + 组织级取值（vi_charge_allocation_*）。"""
    defs = (
        ('vi_charge_allocation_enabled', '采购发票费用分摊开关', 'bool', 'false'),
        ('vi_charge_allocation_rule_code', '采购发票费用分摊规则', 'string', ''),
    )
    ids = {}
    for code, name, value_type, default in defs:
        ds.execute(
            "INSERT INTO control_parameter_defs "
            "(code, name, domain, value_type, target_bo, default_value, status) "
            "VALUES (?, ?, 'procurement', ?, 'vendor_invoice', ?, 'active') "
            "ON CONFLICT(code) DO UPDATE SET default_value = excluded.default_value",
            [code, name, value_type, default])
        ids[code] = ds.query(
            'SELECT id FROM control_parameter_defs WHERE code = ?', [code])[0]['id']
    for code, value in (
            ('vi_charge_allocation_enabled', 'true' if enabled else 'false'),
            ('vi_charge_allocation_rule_code', rule_code)):
        ds.execute(
            'DELETE FROM control_parameter_values WHERE control_parameter_id = ?',
            [ids[code]])
        if value:
            ds.execute(
                'INSERT INTO control_parameter_values '
                '(control_parameter_id, org_id, specificity_rank, value, status) '
                "VALUES (?, ?, 1, ?, 'active')", [ids[code], org_id, value])
    ds.commit()


def seed_currency(ds, *, currency_id=CURRENCY_ID, code='CNY',
                  name='人民币', decimal_places=2):
    ds.execute(
        'INSERT OR REPLACE INTO currencies (id, code, name, decimal_places) '
        'VALUES (?, ?, ?, ?)', [currency_id, code, name, decimal_places])
    ds.commit()


# ------------------------------------------------------------------ v271 AP 期次

PAYMENT_TERM_ID = 6001


def seed_vendor_account(ds, *, account_id=SUPPLIER_ACCOUNT_ID,
                        default_payment_term_id=None):
    ds.execute(
        'INSERT OR REPLACE INTO vendor_accounts '
        '(id, name, default_payment_term_id) VALUES (?, ?, ?)',
        [account_id, '供应商{0}'.format(account_id), default_payment_term_id])
    ds.commit()


def seed_payment_term(ds, *, term_id=PAYMENT_TERM_ID, code='NT30',
                      basis_date_rule='invoice_date', cutoff_day=None,
                      lines=()):
    """付款条件头 + 分期行。

    lines 元素: (seq, percentage, offset_months, fixed_day_of_month, offset_days)
    """
    ds.execute(
        'INSERT OR REPLACE INTO payment_terms '
        '(id, code, name, basis_date_rule, cutoff_day, status) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        [term_id, code, code, basis_date_rule, cutoff_day, 'active'])
    ds.execute('DELETE FROM payment_term_lines WHERE payment_term_id = ?',
               [term_id])
    for seq, percentage, offset_months, fixed_day, offset_days in lines:
        ds.execute(
            'INSERT INTO payment_term_lines '
            '(payment_term_id, seq, percentage, offset_months, '
            ' fixed_day_of_month, offset_days) VALUES (?, ?, ?, ?, ?, ?)',
            [term_id, seq, percentage, offset_months, fixed_day, offset_days])
    ds.commit()


def set_payment_term(ds, invoice_id, term_id):
    """改写发票头付款条件（验证显式值不被带出链覆盖）。"""
    ds.execute(
        'UPDATE vendor_invoices SET payment_term_id = ? WHERE id = ?',
        [term_id, invoice_id])
    ds.commit()


def get_schedules(ds, invoice_id):
    return ds.query(
        'SELECT * FROM vendor_invoice_schedules WHERE invoice_id = ? '
        'ORDER BY schedule_no', [invoice_id])


def audit_actions(ds, object_id, object_type='vendor_invoice'):
    """按对象读取审计动作序列（新 → 旧不保证，按自增 id 升序）。"""
    rows = ds.query(
        'SELECT action FROM audit_logs WHERE object_type = ? AND object_id = ? '
        'ORDER BY id', [object_type, object_id])
    return [row['action'] for row in rows]