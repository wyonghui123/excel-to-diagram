# -*- coding: utf-8 -*-
"""[v231 2026-11-09] 销售发票对象模型（S8 Wave A）

依据:
  docs/specs/s8-customer-invoice-wave-a/spec.md
  docs/specs/spec-sales-order-billing-object-model-2026-11-07.md §4-§11 / §30 / §31

范围:
  1. 建 3 张表：
       customer_invoices / customer_invoice_lines / customer_invoice_schedules
     （表由 meta/schemas/customer_invoice{,_line,_schedule}.yaml 声明，
      本迁移做兜底 CREATE + 显式索引，防止仅 sync_schema 漏建）
  2. 派生列（8 个）:
       sales_order_lines     + billing_relevance / billed_qty / billed_amount
       sales_order_schedules + billed_amount / billing_status
       shipment_lines        + billed_qty
       sales_orders          + billing_status / billing_derived_at
  3. type_definitions 种子：
       头 SINV / SCR / SDN；行 INV_ITEM / INV_SERVICE / INV_DISCOUNT
     （行类型加 INV_ 前缀：type_definitions.code 全局唯一，避免与销售订单 ITEM 冲突）
  4. number_sequences 种子 SINV / SCR / SDN + 回填头类型绑定；
     SINV 绑定默认行类型 INV_ITEM
  5. 回填 sales_order_lines.billing_relevance
  6. doc_flow_rule 种子 shipment_to_customer_invoice（pool=billing）
  7. permissions 双段式 customer_invoice:customer_invoice_{action}，授予 admin / default

幂等:
  表 / 列 / 索引 / 类型 / 序列 / 规则 / 权限先查后用；重复执行打印 [SKIP]。
  不建 accounting_event 表（D6 只留 hook）；不建 settlement_block_code（D28）。

回滚:
  丢索引 + 删表；解除类型序列绑定后删序列；
  类型 / 权限 / 规则行保留（可能已被单据或角色引用）；派生列不自动回退（业务数据）。
"""
import sqlite3
from datetime import datetime
from pathlib import Path

MIGRATION_NAME = 'v231__customer_invoice'

HEADER_TABLE = 'customer_invoices'
LINE_TABLE = 'customer_invoice_lines'
SCHEDULE_TABLE = 'customer_invoice_schedules'

ORDER_TABLE = 'sales_orders'
ORDER_LINE_TABLE = 'sales_order_lines'
ORDER_SCHEDULE_TABLE = 'sales_order_schedules'
SHIPMENT_LINE_TABLE = 'shipment_lines'

SCOPE_BO = 'customer_invoice'

#: 头类型 (code, name, document_category, sequence_code, description)
HEADER_TYPES = (
    ('SINV', '标准销售发票', 'standard', 'SINV',
     '销售发票默认单据类型（发货 / 手工开票）'),
    ('SCR', '红字销售发票', 'credit_memo', 'SCR',
     '红冲生成的负向发票，必须回指原发票（reversal_of_invoice_id）'),
    ('SDN', '销售借项通知单', 'debit_memo', 'SDN',
     '正向调整单据（Wave A 不启用，仅占位类型）'),
)

#: 行类型 (code, name, line_category, delivery_relevant, description)
LINE_TYPES = (
    ('INV_ITEM', '物料行', 'material', 1, '按发货行 / 订单行开票的标准物料行'),
    ('INV_SERVICE', '服务行', 'service', 0, '服务类开票行（item_id 可空）'),
    ('INV_DISCOUNT', '折扣行', 'discount', 0, '折扣 / 让价行（允许负金额）'),
)

#: 编号序列 (code, name, pattern, date_field, start_value, on_exhaust, description)
SEQUENCES = (
    ('SINV', '销售发票编号', 'SINV-{DATE:yyyymm}-{SEQ:5}', 'invoice_date', 1,
     'error', '销售发票取号：SINV-年月-5 位流水，按月复位'),
    ('SCR', '红字销售发票编号', 'SCR-{DATE:yyyymm}-{SEQ:5}', 'invoice_date', 1,
     'error', '红字销售发票取号：SCR-年月-5 位流水，按月复位'),
    ('SDN', '销售借项通知单编号', 'SDN-{DATE:yyyymm}-{SEQ:5}', 'invoice_date', 1,
     'error', '销售借项通知单取号：SDN-年月-5 位流水，按月复位'),
)

#: 派生列（表名 → [(列名, DDL 片段)]）
NEW_COLUMNS = (
    (ORDER_LINE_TABLE, (
        ('billing_relevance', "VARCHAR(16) NOT NULL DEFAULT 'delivery'"),
        ('billed_qty', 'NUMERIC(18,4) NOT NULL DEFAULT 0'),
        ('billed_amount', 'NUMERIC(18,4) NOT NULL DEFAULT 0'),
    )),
    (ORDER_SCHEDULE_TABLE, (
        ('billed_amount', 'NUMERIC(18,4) NOT NULL DEFAULT 0'),
        ('billing_status', "VARCHAR(16) NOT NULL DEFAULT 'none'"),
    )),
    (SHIPMENT_LINE_TABLE, (
        ('billed_qty', 'NUMERIC(18,4) NOT NULL DEFAULT 0'),
    )),
    (ORDER_TABLE, (
        ('billing_status', "VARCHAR(16) NOT NULL DEFAULT 'none'"),
        ('billing_derived_at', 'DATETIME NULL'),
    )),
)

DOC_FLOW_RULE_ID = 'shipment_to_customer_invoice'
DOC_FLOW_RULE = {
    'rule_id': DOC_FLOW_RULE_ID,
    'source_bo': 'shipment_line',
    'target_bo': 'customer_invoice_line',
    'source_qty_field': 'qty',
    'pool': 'billing',
}

#: 权限（双段式）：本波 5 个动作
PERMISSIONS = tuple(
    ('customer_invoice:customer_invoice_{0}'.format(action),
     '销售发票{0}'.format(label), 'customer_invoice', action)
    for action, label in (
        ('view', '查看'),
        ('create', '创建'),
        ('post', '过账'),
        ('reverse', '红冲'),
        ('cancel', '取消'),
    )
)
GRANT_TO_SETS = ('admin', 'default')

HEADER_DDL = """
CREATE TABLE IF NOT EXISTS customer_invoices (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no VARCHAR(30) NOT NULL,
    document_type_id INTEGER NOT NULL,
    invoice_date DATETIME NOT NULL,
    posting_date DATETIME,
    status VARCHAR(20) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'submitted', 'posted', 'cancelled', 'reversed')),
    customer_account_id INTEGER NOT NULL,
    bill_to_account_id INTEGER,
    payer_account_id INTEGER,
    bill_to_address_text VARCHAR(512),
    tax_registration_no VARCHAR(64),
    currency_id INTEGER NOT NULL,
    exchange_rate NUMERIC(18,8),
    exchange_rate_type VARCHAR(20),
    exchange_rate_date DATETIME,
    payment_term_id INTEGER,
    incoterm_code VARCHAR(16),
    net_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
    tax_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
    gross_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
    org_id INTEGER NOT NULL,
    sales_org_id INTEGER,
    project_id INTEGER,
    reversal_of_invoice_id INTEGER,
    reversal_reason VARCHAR(256),
    remark TEXT,
    created_at DATETIME,
    updated_at DATETIME
)
"""

LINE_DDL = """
CREATE TABLE IF NOT EXISTS customer_invoice_lines (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    line_type_id INTEGER NOT NULL,
    source_doc_type VARCHAR(32) NOT NULL
        CHECK (source_doc_type IN ('shipment', 'sales_order', 'manual',
                                   'billing_schedule', 'service_confirmation')),
    source_doc_id INTEGER,
    source_line_id INTEGER,
    shipment_line_id INTEGER,
    schedule_id INTEGER,
    order_line_id INTEGER,
    item_id INTEGER,
    description VARCHAR(512) NOT NULL,
    uom_id INTEGER NOT NULL,
    qty NUMERIC(18,4) NOT NULL,
    billing_basis VARCHAR(16) NOT NULL DEFAULT 'quantity'
        CHECK (billing_basis IN ('quantity', 'percent', 'amount')),
    unit_price NUMERIC(18,6) NOT NULL,
    net_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
    tax_code_id INTEGER NOT NULL,
    tax_rate_percent NUMERIC(9,4) NOT NULL,
    tax_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
    gross_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
    project_id INTEGER,
    project_task_id INTEGER,
    billing_percent NUMERIC(9,4),
    billing_base_amount NUMERIC(18,4),
    price_source VARCHAR(16) NOT NULL DEFAULT 'order',
    order_unit_price NUMERIC(18,6),
    price_change_reason VARCHAR(256),
    price_change_approved_by VARCHAR(64),
    original_invoice_line_id INTEGER,
    created_at DATETIME,
    updated_at DATETIME,
    CHECK (
        (shipment_line_id IS NULL OR schedule_id IS NULL)
        AND (source_doc_type <> 'shipment' OR shipment_line_id IS NOT NULL)
        AND (source_doc_type <> 'billing_schedule' OR schedule_id IS NOT NULL)
        AND (source_doc_type IN ('shipment', 'billing_schedule')
             OR (shipment_line_id IS NULL AND schedule_id IS NULL))
    )
)
"""

SCHEDULE_DDL = """
CREATE TABLE IF NOT EXISTS customer_invoice_schedules (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    schedule_no INTEGER NOT NULL,
    payment_term_line_id INTEGER,
    ratio_percent NUMERIC(9,4) NOT NULL,
    due_date DATETIME NOT NULL,
    amount NUMERIC(18,4) NOT NULL,
    amount_applied NUMERIC(18,4) NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'partial', 'closed', 'cancelled')),
    created_at DATETIME,
    updated_at DATETIME
)
"""

TABLES = (
    (HEADER_TABLE, HEADER_DDL),
    (LINE_TABLE, LINE_DDL),
    (SCHEDULE_TABLE, SCHEDULE_DDL),
)

INDEXES = (
    ('uq_customer_invoice_no', HEADER_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_invoice_no '
     'ON customer_invoices(invoice_no)'),
    ('idx_customer_invoice_status_date', HEADER_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_customer_invoice_status_date '
     'ON customer_invoices(status, invoice_date)'),
    ('idx_customer_invoice_customer_status', HEADER_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_customer_invoice_customer_status '
     'ON customer_invoices(customer_account_id, status)'),
    ('idx_customer_invoice_document_type', HEADER_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_customer_invoice_document_type '
     'ON customer_invoices(document_type_id)'),
    ('idx_customer_invoice_reversal_of', HEADER_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_customer_invoice_reversal_of '
     'ON customer_invoices(reversal_of_invoice_id)'),
    ('idx_customer_invoice_project', HEADER_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_customer_invoice_project '
     'ON customer_invoices(project_id)'),
    ('uq_customer_invoice_line_no', LINE_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_invoice_line_no '
     'ON customer_invoice_lines(invoice_id, line_no)'),
    ('idx_customer_invoice_line_shipment', LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_customer_invoice_line_shipment '
     'ON customer_invoice_lines(shipment_line_id)'),
    ('idx_customer_invoice_line_schedule', LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_customer_invoice_line_schedule '
     'ON customer_invoice_lines(schedule_id)'),
    ('idx_customer_invoice_line_order', LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_customer_invoice_line_order '
     'ON customer_invoice_lines(order_line_id)'),
    ('uq_customer_invoice_schedule_no', SCHEDULE_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_invoice_schedule_no '
     'ON customer_invoice_schedules(invoice_id, schedule_no)'),
    ('idx_customer_invoice_schedule_invoice', SCHEDULE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_customer_invoice_schedule_invoice '
     'ON customer_invoice_schedules(invoice_id)'),
    ('idx_customer_invoice_schedule_status_due', SCHEDULE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_customer_invoice_schedule_status_due '
     'ON customer_invoice_schedules(status, due_date)'),
)

RULE_TABLE = 'doc_flow_rule'
PERMISSION_TABLE = 'permissions'


def _table_exists(conn, name):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn, table):
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(
        'PRAGMA table_info(%s)' % table).fetchall()}


def _index_exists(conn, name):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _do_tables(conn):
    for name, ddl in TABLES:
        if _table_exists(conn, name):
            print('  - [SKIP] 表 %s 已存在' % name)
        else:
            conn.execute(ddl)
            print('  - [CREATE] 表 %s' % name)


def _do_indexes(conn):
    for name, table, sql in INDEXES:
        if _index_exists(conn, name):
            print('  - [SKIP] 索引 %s 已存在' % name)
            continue
        if not _table_exists(conn, table):
            print('  - [SKIP] 索引 %s 依赖表 %s 不存在' % (name, table))
            continue
        conn.execute(sql)
        print('  - [ADD] 索引 %s' % name)


def _do_columns(conn):
    for table, columns in NEW_COLUMNS:
        if not _table_exists(conn, table):
            print('  - [SKIP] 表 %s 不存在，跳过加列' % table)
            continue
        have = _columns(conn, table)
        for column, ddl in columns:
            if column in have:
                print('  - [SKIP] 列 %s.%s 已存在' % (table, column))
                continue
            conn.execute('ALTER TABLE %s ADD COLUMN %s %s' % (table, column, ddl))
            print('  - [ALTER] 列 %s.%s' % (table, column))


def _type_id(conn, code, level):
    row = conn.execute(
        'SELECT id FROM type_definitions WHERE scope_bo=? AND level=? AND code=?',
        (SCOPE_BO, level, code)).fetchone()
    return row[0] if row else None


def _ensure_type(conn, code, name, level, document_category, line_category,
                 delivery_relevant, description):
    existing = _type_id(conn, code, level)
    if existing:
        print('  - [SKIP] 类型 %s/%s/%s 已存在 (id=%s)'
              % (SCOPE_BO, level, code, existing))
        return int(existing)

    now = conn.execute("SELECT datetime('now')").fetchone()[0]
    if level == 'header':
        cur = conn.execute(
            'INSERT INTO type_definitions '
            '(code, name, scope_bo, level, document_category, status, description, '
            ' created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (code, name, SCOPE_BO, level, document_category, 'active',
             description, now))
    else:
        cur = conn.execute(
            'INSERT INTO type_definitions '
            '(code, name, scope_bo, level, line_category, delivery_relevant, '
            ' status, description, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (code, name, SCOPE_BO, level, line_category, delivery_relevant,
             'active', description, now))
    new_id = int(cur.lastrowid)
    print('  - [NEW] 类型 %s/%s/%s (id=%s)' % (SCOPE_BO, level, code, new_id))
    return new_id


def _do_types(conn):
    if not _table_exists(conn, 'type_definitions'):
        print('  - type_definitions 表不存在, 跳过类型种子')
        return {}
    ids = {}
    for code, name, category, _seq, desc in HEADER_TYPES:
        ids[code] = _ensure_type(conn, code, name, 'header', category,
                                 None, 1, desc)
    for code, name, line_category, delivery_relevant, desc in LINE_TYPES:
        ids[code] = _ensure_type(conn, code, name, 'line', None,
                                 line_category, delivery_relevant, desc)
    return ids


def _do_sequences(conn):
    if not _table_exists(conn, 'number_sequences'):
        print('  - number_sequences 表不存在, 跳过编号序列种子')
        return {}
    ids = {}
    for code, name, pattern, date_field, start_value, on_exhaust, desc in SEQUENCES:
        row = conn.execute(
            'SELECT id FROM number_sequences WHERE code=?', (code,)).fetchone()
        if row:
            print('  - [SKIP] 编号序列 %s 已存在 (id=%s)' % (code, row[0]))
            ids[code] = int(row[0])
            continue
        cur = conn.execute(
            'INSERT INTO number_sequences '
            '(code, name, pattern, scope_fields, date_field, start_value, '
            ' on_exhaust, preview, status, description, created_at) '
            "VALUES (?, ?, ?, NULL, ?, ?, ?, NULL, 'active', ?, datetime('now'))",
            (code, name, pattern, date_field, start_value, on_exhaust, desc))
        ids[code] = int(cur.lastrowid)
        print('  - [NEW] 编号序列 %s (id=%s)' % (code, cur.lastrowid))
    return ids


def _do_type_bindings(conn, type_ids, sequence_ids):
    if not _table_exists(conn, 'type_definitions'):
        return
    for code, _name, _category, seq_code, _desc in HEADER_TYPES:
        type_id = type_ids.get(code)
        sequence_id = sequence_ids.get(seq_code)
        if not type_id or not sequence_id:
            continue
        row = conn.execute(
            'SELECT number_sequence_id FROM type_definitions WHERE id=?',
            (type_id,)).fetchone()
        if row and row[0]:
            print('  - [SKIP] 头类型 %s 已绑定编号序列' % code)
        else:
            conn.execute(
                'UPDATE type_definitions SET number_sequence_id=? WHERE id=?',
                (sequence_id, type_id))
            print('  - [BIND] 头类型 %s → 序列 %s' % (code, seq_code))

    header_id = type_ids.get('SINV')
    item_id = type_ids.get('INV_ITEM')
    if header_id and item_id:
        row = conn.execute(
            'SELECT default_type_id FROM type_definitions WHERE id=?',
            (header_id,)).fetchone()
        if row and row[0]:
            print('  - [SKIP] 头类型 SINV 已绑定默认行类型')
        else:
            conn.execute(
                'UPDATE type_definitions SET default_type_id=? WHERE id=?',
                (item_id, header_id))
            print('  - [BIND] 头类型 SINV → 默认行类型 INV_ITEM')


def _do_backfill(conn):
    if not _table_exists(conn, ORDER_LINE_TABLE):
        print('  - 表 %s 不存在, 跳过 billing_relevance 回填' % ORDER_LINE_TABLE)
        return
    has_schedule = _table_exists(conn, ORDER_SCHEDULE_TABLE)
    if not has_schedule:
        conn.execute(
            "UPDATE %s SET billing_relevance='delivery'" % ORDER_LINE_TABLE)
        print('  - [BACKFILL] 无计划表, 全部置 delivery')
        return
    conn.execute(
        """
        UPDATE {0}
           SET billing_relevance = CASE
                 WHEN billing_method = 'milestone'
                  AND EXISTS (SELECT 1 FROM {1} s
                               WHERE s.order_line_id = {0}.id
                                 AND s.schedule_kind = 'billing')
                 THEN 'plan'
                 ELSE 'delivery'
               END
        """.format(ORDER_LINE_TABLE, ORDER_SCHEDULE_TABLE))
    plan_rows = conn.execute(
        "SELECT COUNT(*) FROM %s WHERE billing_relevance='plan'"
        % ORDER_LINE_TABLE).fetchone()[0]
    print('  - [BACKFILL] billing_relevance: plan=%s' % plan_rows)


def _do_rule(conn):
    if not _table_exists(conn, RULE_TABLE):
        print('  - %s 表不存在, 跳过 doc_flow 规则' % RULE_TABLE)
        return
    now = datetime.now().isoformat(timespec='seconds')
    conn.execute(
        """
        INSERT INTO doc_flow_rule
            (rule_id, source_bo, target_bo, source_qty_field, pool, status,
             field_map, split_key, target_line_bo, head_fk_field,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'active', '{}', '[]', '', '', ?, ?)
        ON CONFLICT(rule_id) DO UPDATE SET
            source_bo=excluded.source_bo,
            target_bo=excluded.target_bo,
            source_qty_field=excluded.source_qty_field,
            pool=excluded.pool,
            status='active',
            updated_at=excluded.updated_at
        """,
        (DOC_FLOW_RULE['rule_id'], DOC_FLOW_RULE['source_bo'],
         DOC_FLOW_RULE['target_bo'], DOC_FLOW_RULE['source_qty_field'],
         DOC_FLOW_RULE['pool'], now, now))
    print('  - [UPSERT] doc_flow 规则 %s (pool=%s)'
          % (DOC_FLOW_RULE_ID, DOC_FLOW_RULE['pool']))


def _do_permissions(conn):
    if not _table_exists(conn, PERMISSION_TABLE):
        print('  - permissions 表不存在, 跳过权限写入')
        return
    created = 0
    for code, name, resource_type, action in PERMISSIONS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO permissions (code, name, resource_type, action) "
            "VALUES (?, ?, ?, ?)",
            (code, name, resource_type, action))
        if cur.rowcount:
            created += 1
            print('  - [NEW] 权限 %s (%s)' % (code, name))
    print('  - [SUMMARY] permissions: +%s 新增' % created)


def _do_grants(conn):
    if not (_table_exists(conn, 'permissions')
            and _table_exists(conn, 'permission_sets')
            and _table_exists(conn, 'permission_set_permissions')):
        print('  - 权限集相关表缺失, 跳过授权')
        return
    cols = _columns(conn, 'permission_set_permissions')
    if 'permission_set_id' in cols:
        id_col = 'permission_set_id'
    elif 'role_id' in cols:
        id_col = 'role_id'
    else:
        print('  - permission_set_permissions 无 permission_set_id/role_id, 跳过授权')
        return
    has_code_col = 'permission_code' in cols
    has_granted = 'granted' in cols
    granted = 0
    for set_code in GRANT_TO_SETS:
        row = conn.execute(
            'SELECT id FROM permission_sets WHERE code=? AND is_active=1',
            (set_code,)).fetchone()
        if not row:
            continue
        permission_set_id = row[0]
        for code, _name, _rtype, _action in PERMISSIONS:
            prow = conn.execute(
                'SELECT id FROM permissions WHERE code=?', (code,)).fetchone()
            if not prow:
                continue
            params = [permission_set_id, prow[0]]
            where = '%s = ? AND permission_id = ?' % id_col
            if has_code_col:
                where += ' AND permission_code = ?'
                params.append(code)
            if conn.execute(
                    'SELECT 1 FROM permission_set_permissions WHERE ' + where,
                    params).fetchone():
                continue
            if has_code_col:
                conn.execute(
                    'INSERT INTO permission_set_permissions '
                    '(%s, permission_code, permission_id, granted, created_at) '
                    "VALUES (?, ?, ?, ?, datetime('now'))" % id_col,
                    (permission_set_id, code, prow[0], 1))
            elif has_granted:
                conn.execute(
                    'INSERT INTO permission_set_permissions '
                    '(%s, permission_id, granted, created_at) '
                    'VALUES (?, ?, 1, datetime(\'now\'))' % id_col,
                    (permission_set_id, prow[0]))
            else:
                conn.execute(
                    'INSERT INTO permission_set_permissions '
                    '(%s, permission_id, created_at) '
                    "VALUES (?, ?, datetime('now'))" % id_col,
                    (permission_set_id, prow[0]))
            granted += 1
    print('  - [SUMMARY] permission_set_permissions: +%s 授权' % granted)


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print('[v231] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v231] 开始: 销售发票对象模型（S8 Wave A）')
        _do_tables(conn)
        _do_indexes(conn)
        _do_columns(conn)
        type_ids = _do_types(conn)
        sequence_ids = _do_sequences(conn)
        _do_type_bindings(conn, type_ids, sequence_ids)
        _do_backfill(conn)
        _do_rule(conn)
        _do_permissions(conn)
        _do_grants(conn)
        conn.commit()
        print('[v231] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v231] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v231 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        required_cols = {
            HEADER_TABLE: (
                'invoice_no', 'document_type_id', 'invoice_date', 'posting_date',
                'status', 'customer_account_id', 'bill_to_account_id',
                'payer_account_id', 'bill_to_address_text', 'tax_registration_no',
                'currency_id', 'exchange_rate', 'exchange_rate_type',
                'exchange_rate_date', 'payment_term_id', 'incoterm_code',
                'net_amount', 'tax_amount', 'gross_amount', 'org_id',
                'sales_org_id', 'project_id', 'reversal_of_invoice_id',
                'reversal_reason', 'remark'),
            LINE_TABLE: (
                'invoice_id', 'line_no', 'line_type_id', 'source_doc_type',
                'source_doc_id', 'source_line_id', 'shipment_line_id',
                'schedule_id', 'order_line_id', 'item_id', 'description',
                'uom_id', 'qty', 'billing_basis', 'unit_price', 'net_amount',
                'tax_code_id', 'tax_rate_percent', 'tax_amount', 'gross_amount',
                'project_id', 'project_task_id', 'billing_percent',
                'billing_base_amount', 'price_source', 'order_unit_price',
                'price_change_reason', 'price_change_approved_by',
                'original_invoice_line_id'),
            SCHEDULE_TABLE: (
                'invoice_id', 'schedule_no', 'payment_term_line_id',
                'ratio_percent', 'due_date', 'amount', 'amount_applied',
                'status'),
        }
        for table, cols in required_cols.items():
            if not _table_exists(conn, table):
                print('[v231 verify] FAIL: 缺表 %s' % table)
                ok = False
                continue
            have = _columns(conn, table)
            for col in cols:
                if col not in have:
                    print('[v231 verify] FAIL: 缺列 %s.%s' % (table, col))
                    ok = False

        for name, _table, _sql in INDEXES:
            if not _index_exists(conn, name):
                print('[v231 verify] FAIL: 缺索引 %s' % name)
                ok = False

        for table, columns in NEW_COLUMNS:
            if not _table_exists(conn, table):
                print('[v231 verify] FAIL: 缺派生表 %s' % table)
                ok = False
                continue
            have = _columns(conn, table)
            for column, _ddl in columns:
                if column not in have:
                    print('[v231 verify] FAIL: 缺派生列 %s.%s' % (table, column))
                    ok = False

        if _table_exists(conn, 'type_definitions'):
            for code, _name, category, seq_code, _desc in HEADER_TYPES:
                type_id = _type_id(conn, code, 'header')
                if not type_id:
                    print('[v231 verify] FAIL: 缺头类型 %s' % code)
                    ok = False
                    continue
                row = conn.execute(
                    'SELECT number_sequence_id, document_category '
                    'FROM type_definitions WHERE id=?', (type_id,)).fetchone()
                if not row[0]:
                    print('[v231 verify] FAIL: 头类型 %s 未绑定编号序列' % code)
                    ok = False
                if (row[1] or '') != category:
                    print('[v231 verify] FAIL: 头类型 %s document_category 不符' % code)
                    ok = False
                if not conn.execute(
                        'SELECT 1 FROM number_sequences WHERE code=? AND id=?',
                        (seq_code, row[0])).fetchone():
                    print('[v231 verify] FAIL: 头类型 %s 序列绑定错误' % code)
                    ok = False
            for code, _name, line_category, _rel, _desc in LINE_TYPES:
                if not _type_id(conn, code, 'line'):
                    print('[v231 verify] FAIL: 缺行类型 %s' % code)
                    ok = False
                    continue
                row = conn.execute(
                    'SELECT line_category FROM type_definitions '
                    'WHERE scope_bo=? AND level=? AND code=?',
                    (SCOPE_BO, 'line', code)).fetchone()
                if (row[0] or '') != line_category:
                    print('[v231 verify] FAIL: 行类型 %s line_category 不符' % code)
                    ok = False
        else:
            print('[v231 verify] FAIL: 缺表 type_definitions')
            ok = False

        if _table_exists(conn, 'number_sequences'):
            for code, _name, _pattern, _date, _start, _exhaust, _desc in SEQUENCES:
                if not conn.execute(
                        'SELECT 1 FROM number_sequences WHERE code=?',
                        (code,)).fetchone():
                    print('[v231 verify] FAIL: 缺编号序列 %s' % code)
                    ok = False
        else:
            print('[v231 verify] FAIL: 缺表 number_sequences')
            ok = False

        if _table_exists(conn, RULE_TABLE):
            if not conn.execute(
                    'SELECT 1 FROM doc_flow_rule WHERE rule_id=?',
                    (DOC_FLOW_RULE_ID,)).fetchone():
                print('[v231 verify] FAIL: 缺 doc_flow 规则 %s' % DOC_FLOW_RULE_ID)
                ok = False
        else:
            print('[v231 verify] FAIL: 缺表 %s' % RULE_TABLE)
            ok = False

        if _table_exists(conn, PERMISSION_TABLE):
            for code, _name, _rtype, _action in PERMISSIONS:
                if not conn.execute(
                        'SELECT 1 FROM permissions WHERE code=?',
                        (code,)).fetchone():
                    print('[v231 verify] FAIL: 缺权限 %s' % code)
                    ok = False
            if _table_exists(conn, 'permission_sets') \
                    and _table_exists(conn, 'permission_set_permissions'):
                for set_code in GRANT_TO_SETS:
                    row = conn.execute(
                        'SELECT id FROM permission_sets WHERE code=? AND is_active=1',
                        (set_code,)).fetchone()
                    if not row:
                        continue
                    for code, _name, _rtype, _action in PERMISSIONS:
                        if not conn.execute(
                                'SELECT 1 FROM permission_set_permissions '
                                'WHERE permission_set_id=? AND permission_code=?',
                                (row[0], code)).fetchone():
                            print('[v231 verify] FAIL: 权限 %s 未授予 %s'
                                  % (code, set_code))
                            ok = False
        else:
            print('[v231 verify] FAIL: 缺表 permissions')
            ok = False

        if _table_exists(conn, ORDER_LINE_TABLE):
            bad = conn.execute(
                "SELECT COUNT(*) FROM %s "
                "WHERE billing_relevance NOT IN ('delivery', 'plan')"
                % ORDER_LINE_TABLE).fetchone()[0]
            if bad:
                print('[v231 verify] FAIL: billing_relevance 非法值 %s 行' % bad)
                ok = False
            if _table_exists(conn, ORDER_SCHEDULE_TABLE):
                bad = conn.execute(
                    """
                    SELECT COUNT(*) FROM {0} ol
                     WHERE ol.billing_relevance='plan'
                       AND NOT EXISTS (SELECT 1 FROM {1} s
                                        WHERE s.order_line_id=ol.id
                                          AND s.schedule_kind='billing')
                    """.format(ORDER_LINE_TABLE, ORDER_SCHEDULE_TABLE)
                ).fetchone()[0]
                if bad:
                    print('[v231 verify] FAIL: plan 行缺 billing 计划 %s 行' % bad)
                    ok = False

        print('[v231 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v231 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for name, _table, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute('DROP INDEX IF EXISTS %s' % name)
        for table, _ddl in TABLES:
            if _table_exists(conn, table):
                conn.execute('DROP TABLE IF EXISTS %s' % table)
        conn.execute('DELETE FROM doc_flow_rule WHERE rule_id=?', (DOC_FLOW_RULE_ID,))
        conn.commit()
        print('[v231 rollback] 已删除 3 张表 / 索引 / doc_flow 规则（类型与权限保留）')
        return True
    except Exception as e:
        conn.rollback()
        print('[v231 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()
