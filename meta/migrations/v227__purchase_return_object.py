# -*- coding: utf-8 -*-
"""v227 - 采购退货正向对象（RTV）

依据: docs/specs/spec-reversal-platform-2026-11-06.md §11 / §12 D6
      docs/specs/d6-purchase-return/spec.md

背景:
  采购退货是**正向新事实**（退货采购单 + 退货出库），不走 ReversalOrchestrator；
  `document_category` 三值化后，`return` 表示业务退货（独立过账），
  `red` 表示红字纠错（不独立过账，必须挂原单）。

范围:
  1. `type_definitions`：`RCV_RETURN` 由 return → red；新增 `RETURN_PO` / `VENDOR_RETURN`。
  2. `number_sequences`：新增 `RPO` / `RTV` 并绑定到上述两个新类型。
  3. `inventory_transaction_types`：新增 `RETURN_TO_VENDOR`（issue / out）。
  4. `doc_flow_rule`：新增 `receipt_line_to_return_out_txn`（pool=inventory_return_out）。
  5. ALTER：purchase_orders 三列 / purchase_order_schedules.returned_qty /
     receipts.return_to（先查后用）。
  6. 重建 `v_demand_trace_graph`：signed_qty 增加退货出库分支（列数仍 17）。

幂等:
  类型 / 序列 / 事务类型 / 规则先查后用；列存在性守卫；视图 DROP + CREATE。

[ALLOW_DESTRUCTIVE] upgrade 会 DROP VIEW IF EXISTS；只重建投影，不动表数据。
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime

MIGRATION_NAME = 'v227__purchase_return_object'

TYPE_DEF_TABLE = 'type_definitions'
SEQ_TABLE = 'number_sequences'
TYPES_TABLE = 'inventory_transaction_types'
RULE_TABLE = 'doc_flow_rule'
ORDER_TABLE = 'purchase_orders'
SCHEDULE_TABLE = 'purchase_order_schedules'
RECEIPT_TABLE = 'receipts'

#: 红字收货单类型：语义由「业务退货」修正为「红字纠错」
RED_RECEIPT_TYPE = ('RCV_RETURN', '红字收货单', 'red')

#: (code, name, scope_bo, level, document_category, description)
NEW_TYPES = (
    ('RETURN_PO', '退货采购单', 'purchase_order', 'header', 'return',
     '采购退货业务单：必须回指原采购订单 / 原收货单（SAP 路线，原 PO 不重开）'),
    ('VENDOR_RETURN', '采购退货出库单', 'receipt', 'header', 'return',
     '采购退货出库事实：复用收货单对象，方向由 document_category=return 决定'),
)

#: (code, name, pattern, date_field, description)
NEW_SEQUENCES = (
    ('RPO', '退货采购单编号', 'RPO-{DATE:yyyymm}-{SEQ:6}', 'order_date',
     '退货采购单取号：RPO-年月-6 位流水'),
    ('RTV', '采购退货出库单编号', 'RTV-{DATE:yyyymm}-{SEQ:6}', 'receipt_date',
     '采购退货出库单取号：RTV-年月-6 位流水'),
)

#: 新类型 → 序列绑定
TYPE_SEQUENCE_BINDING = (
    ('purchase_order', 'RETURN_PO', 'RPO'),
    ('receipt', 'VENDOR_RETURN', 'RTV'),
)

RETURN_OUT = ('RETURN_TO_VENDOR', '退货给供应商出库', 'issue', 'out', 1, 71,
              '采购退货出库形成的库存减少（业务退货，新事实；不等于红字冲销）')

SERIAL_TX_TABLE = 'serial_transactions'

SERIAL_TX_DDL = """
CREATE TABLE serial_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    serial_id INTEGER NOT NULL,
    inventory_transaction_id INTEGER,
    txn_type VARCHAR(20) NOT NULL,
    txn_date DATETIME NOT NULL,
    org_from_id INTEGER,
    org_to_id INTEGER,
    location_from_id INTEGER,
    location_to_id INTEGER,
    batch_from_id INTEGER,
    batch_to_id INTEGER,
    usage_from VARCHAR(20),
    usage_to VARCHAR(20),
    quality_from VARCHAR(20),
    quality_to VARCHAR(20),
    doc_type VARCHAR(30),
    doc_id INTEGER,
    line_id INTEGER,
    remark VARCHAR(255),
    created_by VARCHAR(200),
    created_at DATETIME,
    CHECK (txn_type IN ('create', 'receive', 'issue', 'transfer_out',
                        'transfer_in', 'ship', 'return_to_vendor', 'return',
                        'adjust', 'status_change', 'scrap')),
    FOREIGN KEY (serial_id) REFERENCES serial_numbers(id)
)
"""

SERIAL_TX_DDL_LEGACY = SERIAL_TX_DDL.replace(
    "'ship', 'return_to_vendor', 'return'", "'ship', 'return'")


def _do_serial_txn_check(conn):
    if not _table_exists(conn, SERIAL_TX_TABLE):
        print('  - [SKIP] 缺表 %s' % SERIAL_TX_TABLE)
        return
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        [SERIAL_TX_TABLE]).fetchone()
    if row and 'return_to_vendor' in (row[0] or ''):
        print('  - [SKIP] %s 已含 return_to_vendor' % SERIAL_TX_TABLE)
        return
    columns = [r[1] for r in conn.execute(
        'PRAGMA table_info(%s)' % SERIAL_TX_TABLE)]
    conn.execute('ALTER TABLE %s RENAME TO %s_old' % (SERIAL_TX_TABLE, SERIAL_TX_TABLE))
    conn.execute(SERIAL_TX_DDL)
    conn.execute(
        'INSERT INTO %s (%s) SELECT %s FROM %s_old'
        % (SERIAL_TX_TABLE, ', '.join(columns), ', '.join(columns),
           SERIAL_TX_TABLE))
    conn.execute('DROP TABLE %s_old' % SERIAL_TX_TABLE)
    print('  - [ALTER] %s 扩列出库退货事件' % SERIAL_TX_TABLE)


RETURN_RULE = {
    'rule_id': 'receipt_line_to_return_out_txn',
    'source_bo': 'receipt_line',
    'target_bo': 'inventory_transaction',
    'source_qty_field': 'qty',
    'pool': 'inventory_return_out',
}

#: 收货详情「退货」动作权限（双段式，与 v186 一致）
RETURN_PERMISSION = (
    'receipt:receipt_create_vendor_return',
    '收货单-生成采购退货',
    'receipt',
    'receipt_create_vendor_return',
)
GRANT_TO_SETS = ('admin', 'default')

RULE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS doc_flow_rule (
    rule_id          TEXT PRIMARY KEY,
    source_bo        TEXT NOT NULL,
    target_bo        TEXT NOT NULL,
    source_qty_field TEXT NOT NULL DEFAULT 'quantity',
    pool             TEXT NOT NULL DEFAULT 'default',
    status           TEXT NOT NULL DEFAULT 'active',
    check_hook       TEXT,
    map_hook         TEXT,
    create_hook      TEXT,
    field_map        TEXT NOT NULL DEFAULT '{}',
    split_key        TEXT NOT NULL DEFAULT '[]',
    target_line_bo   TEXT NOT NULL DEFAULT '',
    head_fk_field    TEXT NOT NULL DEFAULT '',
    created_at       TEXT,
    updated_at       TEXT
)
"""

#: 新增列（表名 → [(列名, DDL 片段)]）
NEW_COLUMNS = (
    (ORDER_TABLE, (
        ('origin_purchase_order_id', 'INTEGER NULL'),
        ('origin_receipt_id', 'INTEGER NULL'),
        ('return_reason', 'TEXT NULL'),
    )),
    (SCHEDULE_TABLE, (
        ('returned_qty', 'REAL NOT NULL DEFAULT 0'),
    )),
    (RECEIPT_TABLE, (
        ('return_to', "TEXT NOT NULL DEFAULT 'supplier'"),
    )),
)

VIEW_NAME = 'v_demand_trace_graph'
EDGE_TABLE = 'doc_flow_edges'
TRACE_TABLE = 'demand_trace_links'

#: 退货出库边对源单履约量是负贡献；红字再取反（退货出库被冲销 ⇒ 恢复为正）
SIGNED_QTY_SQL = """\
    CASE
      WHEN e.rule_id IN ('shipment_line_to_return_in_txn',
                         'receipt_line_to_return_out_txn')
        THEN CASE WHEN e.quantity_sign = 'red' THEN e.quantity ELSE -e.quantity END
      ELSE CASE WHEN e.quantity_sign = 'red' THEN -e.quantity ELSE e.quantity END
    END AS signed_qty"""

#: 17 列；与 meta/schemas/demand_trace_graph.yaml 的 view_definition 逐字一致
VIEW_SQL = """\
SELECT
  'execution' AS layer,
  'E:' || e.id AS id,
  e.rule_id AS relation,
  e.source_bo AS source_object_type,
  e.source_id AS source_object_id,
  COALESCE(e.source_item, '') AS source_line_id,
  e.target_bo AS target_object_type,
  e.target_id AS target_object_id,
  COALESCE(e.target_item, '') AS target_line_id,
  e.quantity AS qty,
""" + SIGNED_QTY_SQL + """,
  e.status AS status,
  NULL AS peg_type,
  NULL AS plan_version,
  NULL AS valid_from,
  NULL AS valid_to,
  e.derived_at AS occurred_at
FROM doc_flow_edges e
UNION ALL
SELECT
  'plan' AS layer,
  'T:' || CAST(t.id AS TEXT) AS id,
  t.trace_type AS relation,
  t.supply_object_type AS source_object_type,
  CAST(t.supply_object_id AS TEXT) AS source_object_id,
  COALESCE(NULLIF(CAST(t.supply_line_id AS TEXT), '0'), '') AS source_line_id,
  t.demand_object_type AS target_object_type,
  CAST(t.demand_object_id AS TEXT) AS target_object_id,
  COALESCE(NULLIF(CAST(t.demand_line_id AS TEXT), '0'), '') AS target_line_id,
  t.allocated_qty AS qty,
  CASE WHEN t.valid_to IS NULL THEN t.allocated_qty ELSE 0 END AS signed_qty,
  CASE WHEN t.valid_to IS NULL THEN 'active' ELSE 'expired' END AS status,
  t.peg_type AS peg_type,
  t.plan_version AS plan_version,
  t.valid_from AS valid_from,
  t.valid_to AS valid_to,
  t.computed_at AS occurred_at
FROM demand_trace_links t"""

VIEW_DDL = 'CREATE VIEW IF NOT EXISTS {0} AS\n{1}'.format(VIEW_NAME, VIEW_SQL)


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", [name]
    ).fetchone()
    return bool(row)


def _view_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name=?", [name]
    ).fetchone()
    return bool(row)


def _columns(conn, table):
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute('PRAGMA table_info(%s)' % table)}


def _type_id(conn, scope_bo, code):
    row = conn.execute(
        'SELECT id FROM %s WHERE scope_bo=? AND level=? AND code=?'
        % TYPE_DEF_TABLE, [scope_bo, 'header', code]).fetchone()
    return row[0] if row else None


def _do_red_type(conn):
    if not _table_exists(conn, TYPE_DEF_TABLE):
        print('  - [SKIP] 缺表 %s，跳过红字类型修正' % TYPE_DEF_TABLE)
        return
    code, name, category = RED_RECEIPT_TYPE
    type_id = _type_id(conn, 'receipt', code)
    if not type_id:
        print('  - [SKIP] 收货类型 %s 不存在（v186 未执行）' % code)
        return
    conn.execute(
        'UPDATE %s SET name=?, document_category=? WHERE id=?'
        % TYPE_DEF_TABLE, [name, category, type_id])
    print('  - [UPDATE] 类型 receipt/%s → document_category=%s' % (code, category))


def _do_new_types(conn):
    if not _table_exists(conn, TYPE_DEF_TABLE):
        print('  - [SKIP] 缺表 %s，跳过退货类型' % TYPE_DEF_TABLE)
        return
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for code, name, scope, level, category, description in NEW_TYPES:
        if _type_id(conn, scope, code):
            print('  - [SKIP] 类型 %s/%s/%s 已存在' % (scope, level, code))
            continue
        cur = conn.execute(
            'INSERT INTO %s '
            '(code, name, scope_bo, level, document_category, status, description, '
            'created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)' % TYPE_DEF_TABLE,
            [code, name, scope, level, category, 'active', description, now])
        print('  - [NEW] 类型 %s/%s/%s (id=%s)'
              % (scope, level, code, cur.lastrowid))


def _do_sequences(conn):
    if not _table_exists(conn, SEQ_TABLE):
        print('  - [SKIP] 缺表 %s，跳过编号序列' % SEQ_TABLE)
        return
    for code, name, pattern, date_field, description in NEW_SEQUENCES:
        row = conn.execute(
            'SELECT id FROM %s WHERE code=?' % SEQ_TABLE, [code]).fetchone()
        if row:
            print('  - [SKIP] 编号序列 %s 已存在 (id=%s)' % (code, row[0]))
            continue
        conn.execute(
            'INSERT INTO %s '
            '(code, name, pattern, scope_fields, date_field, start_value, '
            ' on_exhaust, preview, status, description, created_at) '
            "VALUES (?, ?, ?, NULL, ?, 1, 'error', NULL, 'active', ?, ?)"
            % SEQ_TABLE,
            [code, name, pattern, date_field, description,
             datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        print('  - [NEW] 编号序列 %s' % code)


def _do_bindings(conn):
    if not (_table_exists(conn, SEQ_TABLE)
            and _table_exists(conn, TYPE_DEF_TABLE)):
        return
    for scope, type_code, seq_code in TYPE_SEQUENCE_BINDING:
        type_id = _type_id(conn, scope, type_code)
        seq = conn.execute(
            'SELECT id FROM %s WHERE code=?' % SEQ_TABLE, [seq_code]).fetchone()
        if not type_id or not seq:
            continue
        row = conn.execute(
            'SELECT number_sequence_id FROM %s WHERE id=?'
            % TYPE_DEF_TABLE, [type_id]).fetchone()
        if row and row[0]:
            print('  - [SKIP] 类型 %s 已绑定序列 (id=%s)' % (type_code, row[0]))
            continue
        conn.execute(
            'UPDATE %s SET number_sequence_id=? WHERE id=?'
            % TYPE_DEF_TABLE, [seq[0], type_id])
        print('  - [BIND] 类型 %s → 序列 %s' % (type_code, seq_code))


def _do_return_out_type(conn):
    if not _table_exists(conn, TYPES_TABLE):
        print('  - [SKIP] 缺表 %s，跳过 RETURN_TO_VENDOR' % TYPES_TABLE)
        return
    row = conn.execute(
        'SELECT id FROM %s WHERE code=?' % TYPES_TABLE, [RETURN_OUT[0]]).fetchone()
    if row:
        print('  - [SKIP] 移动类型 %s 已存在' % RETURN_OUT[0])
        return
    conn.execute(
        'INSERT INTO %s (code, name, category, direction, affects_on_hand, '
        'status, sort_order, description, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)' % TYPES_TABLE,
        [RETURN_OUT[0], RETURN_OUT[1], RETURN_OUT[2], RETURN_OUT[3],
         RETURN_OUT[4], 'active', RETURN_OUT[5], RETURN_OUT[6],
         datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    print('  - [ADD] 移动类型 %s（%s）' % (RETURN_OUT[0], RETURN_OUT[1]))


def _do_rule(conn):
    if not _table_exists(conn, RULE_TABLE):
        conn.execute(RULE_TABLE_DDL)
        print('  - [OK] 建表 %s' % RULE_TABLE)
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
            updated_at=excluded.updated_at
        """,
        [RETURN_RULE['rule_id'], RETURN_RULE['source_bo'],
         RETURN_RULE['target_bo'], RETURN_RULE['source_qty_field'],
         RETURN_RULE['pool'], now, now])
    print('  - [OK] upsert 规则 %s' % RETURN_RULE['rule_id'])


def _do_permission(conn):
    if not _table_exists(conn, 'permissions'):
        print('  - [SKIP] permissions 表不存在')
        return
    code, name, resource_type, action = RETURN_PERMISSION
    cur = conn.execute(
        'INSERT OR IGNORE INTO permissions (code, name, resource_type, action) '
        'VALUES (?, ?, ?, ?)', [code, name, resource_type, action])
    print('  - [%s] 权限 %s' % ('NEW' if cur.rowcount else 'SKIP', code))


def _do_grant(conn):
    if not all(_table_exists(conn, name) for name in
               ('permissions', 'permission_sets', 'permission_set_permissions')):
        print('  - [SKIP] 权限集相关表缺失')
        return
    cols = _columns(conn, 'permission_set_permissions')
    if 'permission_set_id' in cols:
        id_col = 'permission_set_id'
    elif 'role_id' in cols:
        id_col = 'role_id'
    else:
        print('  - [SKIP] 无 permission_set_id/role_id')
        return
    code = RETURN_PERMISSION[0]
    prow = conn.execute('SELECT id FROM permissions WHERE code=?', [code]).fetchone()
    if not prow:
        return
    for set_code in GRANT_TO_SETS:
        row = conn.execute(
            'SELECT id FROM permission_sets WHERE code=? AND is_active=1',
            [set_code]).fetchone()
        if not row:
            continue
        params = [row[0], prow[0]]
        where = '%s = ? AND permission_id = ?' % id_col
        if 'permission_code' in cols:
            where += ' AND permission_code = ?'
            params.append(code)
        if conn.execute('SELECT 1 FROM permission_set_permissions WHERE ' + where,
                        params).fetchone():
            continue
        if 'permission_code' in cols:
            conn.execute(
                'INSERT INTO permission_set_permissions '
                '(%s, permission_code, permission_id, granted, created_at) '
                "VALUES (?, ?, ?, 1, datetime('now'))" % id_col,
                [row[0], code, prow[0]])
        elif 'granted' in cols:
            conn.execute(
                'INSERT INTO permission_set_permissions '
                '(%s, permission_id, granted, created_at) '
                "VALUES (?, ?, 1, datetime('now'))" % id_col,
                [row[0], prow[0]])
        else:
            conn.execute(
                'INSERT INTO permission_set_permissions (%s, permission_id, '
                "created_at) VALUES (?, ?, datetime('now'))" % id_col,
                [row[0], prow[0]])
        print('  - [GRANT] %s → %s' % (code, set_code))


def _do_columns(conn):
    for table, columns in NEW_COLUMNS:
        if not _table_exists(conn, table):
            print('  - [SKIP] 缺表 %s，跳过新增列' % table)
            continue
        have = _columns(conn, table)
        for name, ddl in columns:
            if name in have:
                print('  - [SKIP] 列 %s.%s 已存在' % (table, name))
                continue
            conn.execute('ALTER TABLE %s ADD COLUMN %s %s' % (table, name, ddl))
            print('  - [ALTER] 列 %s.%s' % (table, name))


def _do_view(conn):
    if not (_table_exists(conn, EDGE_TABLE) and _table_exists(conn, TRACE_TABLE)):
        missing = [name for name in (EDGE_TABLE, TRACE_TABLE)
                   if not _table_exists(conn, name)]
        print('  - [SKIP] 缺基表 %s，不建视图 %s'
              % (', '.join(missing), VIEW_NAME))
        return
    if _view_exists(conn, VIEW_NAME):
        conn.execute('DROP VIEW %s' % VIEW_NAME)
        print('  - [OK] 重建视图 %s（DROP + CREATE）' % VIEW_NAME)
    else:
        print('  - [OK] 建视图 %s' % VIEW_NAME)
    conn.execute(VIEW_DDL)


def migrate(db_path, skip_backup=False):
    print('[v227] 采购退货正向对象（RTV）')
    if hasattr(db_path, 'exists') and callable(getattr(db_path, 'exists')):
        exists = db_path.exists()
    else:
        exists = os.path.exists(str(db_path))
    if not exists:
        print('  - [SKIP] 库不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_red_type(conn)
        _do_new_types(conn)
        _do_sequences(conn)
        _do_bindings(conn)
        _do_return_out_type(conn)
        _do_rule(conn)
        _do_permission(conn)
        _do_grant(conn)
        _do_columns(conn)
        _do_serial_txn_check(conn)
        _do_view(conn)
        conn.commit()
        print('[v227] 迁移提交完成')
        return True
    except Exception:
        conn.rollback()
        print('[v227] 失败，已回滚')
        raise
    finally:
        conn.close()


def verify(db_path):
    if not (os.path.exists(str(db_path))):
        return {'ok': False, 'error': 'db not found'}
    conn = sqlite3.connect(str(db_path))
    try:
        checks = {}
        has_types = _table_exists(conn, TYPE_DEF_TABLE)
        checks['red_receipt_type'] = (True if not has_types else
                                      (True if not _type_id(conn, 'receipt', 'RCV_RETURN')
                                       else bool(conn.execute(
                                           'SELECT 1 FROM %s WHERE id=? AND document_category=?'
                                           % TYPE_DEF_TABLE,
                                           [_type_id(conn, 'receipt', 'RCV_RETURN'), 'red']
                                       ).fetchone())))
        checks['return_types'] = (True if not has_types else
                                  all(_type_id(conn, scope, code) for _s, code, _c, _l, _cat, _d in NEW_TYPES))
        checks['type_sequences'] = (True if not (has_types and _table_exists(conn, SEQ_TABLE)) else
                                    all(conn.execute(
                                        'SELECT 1 FROM %s WHERE id=? AND number_sequence_id IS NOT NULL'
                                        % TYPE_DEF_TABLE,
                                        [_type_id(conn, scope, code)]).fetchone()
                                        for scope, code, _seq in TYPE_SEQUENCE_BINDING))
        checks['return_out_type'] = (True if not _table_exists(conn, TYPES_TABLE) else
                                     bool(conn.execute(
                                         'SELECT 1 FROM %s WHERE code=? AND category=? '
                                         'AND direction=? AND status=?'
                                         % TYPES_TABLE,
                                         [RETURN_OUT[0], 'issue', 'out', 'active']
                                     ).fetchone()))
        checks['return_rule'] = (True if not _table_exists(conn, RULE_TABLE) else
                                 bool(conn.execute(
                                     'SELECT 1 FROM %s WHERE rule_id=? AND pool=? AND status=?'
                                     % RULE_TABLE,
                                     [RETURN_RULE['rule_id'], RETURN_RULE['pool'], 'active']
                                 ).fetchone()))
        columns_ok = True
        for table, columns in NEW_COLUMNS:
            if not _table_exists(conn, table):
                continue
            have = _columns(conn, table)
            for name, _ddl in columns:
                if name not in have:
                    print('[v227 verify] FAIL: 缺列 %s.%s' % (table, name))
                    columns_ok = False
        checks['columns'] = columns_ok
        checks['return_permission'] = (
            True if not _table_exists(conn, 'permissions') else
            bool(conn.execute('SELECT 1 FROM permissions WHERE code=?',
                              [RETURN_PERMISSION[0]]).fetchone()))
        if _table_exists(conn, SERIAL_TX_TABLE):
            tx_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                [SERIAL_TX_TABLE]).fetchone()[0]
            checks['serial_txn_type'] = 'return_to_vendor' in (tx_sql or '')
        else:
            checks['serial_txn_type'] = True

        both_base = (_table_exists(conn, EDGE_TABLE)
                     and _table_exists(conn, TRACE_TABLE))
        view_exists = _view_exists(conn, VIEW_NAME)
        checks['view_exists_or_skipped'] = view_exists or not both_base
        if view_exists and both_base:
            cols = [row[1] for row in
                    conn.execute('PRAGMA table_info(%s)' % VIEW_NAME).fetchall()]
            checks['view_columns'] = len(cols) == 17
            sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='view' AND name=?",
                [VIEW_NAME]).fetchone()[0]
            checks['view_return_sign'] = RETURN_RULE['rule_id'] in (sql or '')
        else:
            checks['view_columns'] = True
            checks['view_return_sign'] = True

        ok = all(v for v in checks.values())
        print('[v227 verify] %s' % ('PASS' if ok else 'FAIL'))
        return bool(ok)
    finally:
        conn.close()


def rollback(db_path):
    """降级：删除新种子；新增列置 NULL 但保留（SQLite 降级安全）。"""
    if not os.path.exists(str(db_path)):
        print('[v227 rollback] DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if _table_exists(conn, RULE_TABLE):
            conn.execute('DELETE FROM doc_flow_rule WHERE rule_id=?',
                         [RETURN_RULE['rule_id']])
        if _table_exists(conn, TYPES_TABLE):
            conn.execute('DELETE FROM %s WHERE code=?' % TYPES_TABLE,
                         [RETURN_OUT[0]])
        if _table_exists(conn, TYPE_DEF_TABLE):
            for scope, code, _seq in TYPE_SEQUENCE_BINDING:
                type_id = _type_id(conn, scope, code)
                if type_id:
                    conn.execute('UPDATE %s SET number_sequence_id=NULL WHERE id=?'
                                 % TYPE_DEF_TABLE, [type_id])
                    conn.execute('DELETE FROM %s WHERE id=?' % TYPE_DEF_TABLE,
                                 [type_id])
            red_id = _type_id(conn, 'receipt', RED_RECEIPT_TYPE[0])
            if red_id:
                conn.execute(
                    'UPDATE %s SET name=?, document_category=? WHERE id=?'
                    % TYPE_DEF_TABLE, ['红字收货单', 'return', red_id])
        if _table_exists(conn, SEQ_TABLE):
            for code, _name, _pattern, _date, _desc in NEW_SEQUENCES:
                conn.execute('DELETE FROM %s WHERE code=?' % SEQ_TABLE, [code])
        if _table_exists(conn, 'permissions'):
            if _table_exists(conn, 'permission_set_permissions'):
                conn.execute(
                    'DELETE FROM permission_set_permissions WHERE permission_id IN '
                    '(SELECT id FROM permissions WHERE code=?)',
                    [RETURN_PERMISSION[0]])
            conn.execute('DELETE FROM permissions WHERE code=?',
                         [RETURN_PERMISSION[0]])
        for table, columns in NEW_COLUMNS:
            if not _table_exists(conn, table):
                continue
            for name, _ddl in columns:
                try:
                    conn.execute('UPDATE %s SET %s = NULL' % (table, name))
                except sqlite3.OperationalError:
                    pass
        if _view_exists(conn, VIEW_NAME):
            conn.execute('DROP VIEW %s' % VIEW_NAME)
        if _table_exists(conn, SERIAL_TX_TABLE):
            tx_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                [SERIAL_TX_TABLE]).fetchone()[0]
            if 'return_to_vendor' in (tx_sql or ''):
                columns = [r[1] for r in conn.execute(
                    'PRAGMA table_info(%s)' % SERIAL_TX_TABLE)]
                conn.execute('DELETE FROM %s WHERE txn_type=?'
                             % SERIAL_TX_TABLE, ['return_to_vendor'])
                conn.execute('ALTER TABLE %s RENAME TO %s_old'
                             % (SERIAL_TX_TABLE, SERIAL_TX_TABLE))
                conn.execute(SERIAL_TX_DDL_LEGACY)
                conn.execute(
                    'INSERT INTO %s (%s) SELECT %s FROM %s_old'
                    % (SERIAL_TX_TABLE, ', '.join(columns), ', '.join(columns),
                       SERIAL_TX_TABLE))
                conn.execute('DROP TABLE %s_old' % SERIAL_TX_TABLE)
        conn.commit()
        print('[v227 rollback] 完成（新增列保留为空）')
        return True
    except Exception as exc:  # noqa: BLE001 - 降级失败需返回 False
        conn.rollback()
        print('[v227 rollback] 失败: %s' % exc)
        return False
    finally:
        conn.close()


downgrade = rollback
