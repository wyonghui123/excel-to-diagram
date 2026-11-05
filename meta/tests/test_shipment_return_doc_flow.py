# -*- coding: utf-8 -*-
"""退货交货（方案 A）端到端验收：AC-19 ~ AC-23

依据: docs/specs/spec-doc-flow-end-to-end-2026-11-05.md §5.1 / §6 阶段 5

覆盖:
  · AC-19 退货交货确认 → RETURN_IN / direction='in' / 事件键 :return / 入库余额增加
           + 转单边走 shipment_line_to_return_in_txn（池 inventory_return）
  · AC-20 类型类别守卫：交货单 return 与来源订单 standard 不一致 → DN_CATEGORY_MISMATCH
           （拒绝发运、无事务无边、状态不回写）；抬头缺类型时继承订单类别
  · AC-21 池隔离：正向出库与退货入库各自消耗，互不占用额度
  · AC-22 退货 ≠ 冲销：原出库边保持 active；视图 signed_qty 出库 +、退货 −
  · AC-23 对账：退货事务纳入 ORPHAN_TXN / DANGLING_EDGE 检测
  · v222 迁移幂等 + 视图重建为 17 列且含退货符号映射
"""

import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.core.doc_flow_reconcile import scan
from meta.core.doc_flow_rule_store import upsert_rules
from meta.migrations import v214__doc_flow_shipment_issue_rule as v214
from meta.migrations import v222__doc_flow_return_shipment_rule as v222
from meta.services.shipment_service import ShipmentError, ShipmentService
from meta.tests import inventory_test_doubles as inv

ISSUE_RULE_ID = v214.RULE_ID
RETURN_RULE_ID = v222.RETURN_RULE['rule_id']

_ORDER_ID = 10
_ORDER_LINE_ID = 100
_SCHEDULE_ID = 1

_STD_TYPE_ID = 900
_RETURN_TYPE_ID = 901

# 在 v214 测试 DDL 基础上补 document_type_id 与类型表类别列
_SHIPMENT_DDL = """
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY,
    order_no TEXT,
    org_id INTEGER,
    order_date TEXT,
    status TEXT,
    ship_to_party_id INTEGER,
    ship_to_address_text TEXT,
    document_type_id INTEGER,
    fulfillment_status TEXT DEFAULT 'not_started',
    fulfillment_derived_at TEXT,
    updated_at TEXT
);
CREATE TABLE sales_order_lines (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    line_type_id INTEGER,
    item_id INTEGER,
    uom_id INTEGER,
    project_task_id INTEGER NOT NULL DEFAULT 0,
    status TEXT,
    fulfillment_status TEXT DEFAULT 'not_started',
    fulfillment_derived_at TEXT,
    updated_at TEXT
);
CREATE TABLE sales_order_schedules (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    line_id INTEGER,
    schedule_kind TEXT,
    plant_location_id INTEGER,
    promised_date TEXT,
    promised_qty REAL,
    delivered_qty REAL DEFAULT 0,
    delivery_id INTEGER,
    status TEXT,
    updated_at TEXT
);
CREATE TABLE type_definitions (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT,
    scope_bo TEXT,
    level TEXT,
    document_category TEXT,
    line_category TEXT,
    delivery_relevant INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',
    description TEXT,
    created_at TEXT
);
CREATE TABLE shipments (
    id INTEGER PRIMARY KEY,
    delivery_no TEXT,
    order_id INTEGER,
    document_type_id INTEGER,
    ship_from_location_id INTEGER,
    ship_to_party_id INTEGER,
    ship_to_address_text TEXT,
    carrier_name TEXT,
    tracking_no TEXT,
    waybill_no TEXT,
    planned_ship_date TEXT,
    actual_ship_date TEXT,
    actual_arrival_date TEXT,
    signature_ref TEXT,
    status TEXT,
    source TEXT,
    remark TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE shipment_lines (
    id INTEGER PRIMARY KEY,
    delivery_id INTEGER,
    schedule_id INTEGER,
    order_line_id INTEGER,
    item_id INTEGER,
    uom_id INTEGER,
    qty REAL,
    lot_no TEXT,
    serial_no TEXT,
    project_task_id INTEGER NOT NULL DEFAULT 0,
    status TEXT,
    created_at TEXT,
    updated_at TEXT
);
"""


class _ShipDS(inv.MemDS):
    """在库存测试替身上补 derive 引擎需要的 insert（边表写入）。"""

    def insert(self, table, data):
        cols = list(data)
        cur = self.conn.execute(
            'INSERT INTO %s (%s) VALUES (%s)'
            % (table, ', '.join(cols), ', '.join('?' * len(cols))),
            [data[c] for c in cols])
        return cur.lastrowid


def _db(with_rule=True, return_in=False):
    """库存库 + 发运库 + DOC_FLOW 边表 + 单据类型（退货移动类型可选）。"""
    conn = inv.build_db()
    inv.seed(conn)
    conn.executescript(_SHIPMENT_DDL)
    conn.execute(v214.EDGE_TABLE_DDL)
    for _, ddl in v214.EDGE_INDEXES:
        conn.execute(ddl)
    conn.execute(v214.CONSUMED_VIEW_DDL)
    if with_rule:
        conn.execute(v214.RULE_TABLE_DDL)
        upsert_rules(_ShipDS(conn), [dict(v214.RULE), dict(v222.RETURN_RULE)])
    conn.execute(
        'INSERT INTO type_definitions (id, code, name, scope_bo, level, '
        "document_category, status) VALUES (?, 'STD', '标准交货单', 'shipment', "
        "'header', 'standard', 'active')", [_STD_TYPE_ID])
    conn.execute(
        'INSERT INTO type_definitions (id, code, name, scope_bo, level, '
        "document_category, status) VALUES (?, 'RETURN', '退货交货单', 'shipment', "
        "'header', 'return', 'active')", [_RETURN_TYPE_ID])
    if return_in:
        v222._do_return_in_type(conn)
    conn.commit()
    return conn


def _return_txn_type_id(conn):
    row = conn.execute(
        "SELECT id FROM inventory_transaction_types WHERE code='RETURN_IN'"
    ).fetchone()
    return row[0] if row else None


def _add_order(conn, document_type_id=None):
    conn.execute(
        'INSERT INTO sales_orders (id, order_no, org_id, order_date, status, '
        'ship_to_party_id, ship_to_address_text, document_type_id) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        [_ORDER_ID, 'SO-0001', inv.ORG_ID, '2026-10-20', 'confirmed', 500,
         '上海市浦东新区世纪大道 100 号', document_type_id])


def _add_order_line(conn, lid=_ORDER_LINE_ID):
    conn.execute(
        'INSERT INTO sales_order_lines (id, order_id, item_id, uom_id, '
        "project_task_id, status) VALUES (?, ?, ?, ?, 0, 'open')",
        [lid, _ORDER_ID, inv.ITEM_ID, inv.UOM_ID])


def _add_schedule(conn, promised_qty=100.0):
    conn.execute(
        'INSERT INTO sales_order_schedules (id, order_id, line_id, '
        'schedule_kind, plant_location_id, promised_date, promised_qty, '
        'delivered_qty, status) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)',
        [_SCHEDULE_ID, _ORDER_ID, _ORDER_LINE_ID, 'delivery', inv.LOCATION_ID,
         '2026-11-05', promised_qty, 'planned'])


def _seed_balance(conn, qty=100.0):
    conn.execute(
        'INSERT INTO inventory_balances (org_id, location_id, item_id, batch_id, '
        'stock_status, stock_segment_type, project_id, project_task_id, '
        'sales_order_line_id, owner_party_id, qty_on_hand, qty_reserved) '
        "VALUES (?, ?, ?, 0, 'unrestricted', 'owned', 0, 0, 0, 0, ?, 0)",
        [inv.ORG_ID, inv.LOCATION_ID, inv.ITEM_ID, qty])


def _ship(conn, *, qty=10, order_type_id=None, ship_type_id=None,
          platform_ds=None, confirm=True):
    ds = _ShipDS(conn)
    svc = ShipmentService(ds, platform_data_source=platform_ds or ds)
    _add_order(conn, document_type_id=order_type_id)
    _add_order_line(conn)
    _add_schedule(conn)
    header = {'order_id': _ORDER_ID}
    if ship_type_id is not None:
        header['document_type_id'] = ship_type_id
    created = svc.create_shipment(
        header, [{'schedule_id': _SCHEDULE_ID, 'qty': qty}])
    svc.release(created['id'])
    svc.stage(created['id'])
    result = svc.ship_confirm(created['id']) if confirm else None
    return svc, created, result


def _count(conn, table, where='1=1', params=None):
    return conn.execute(
        'SELECT COUNT(*) FROM %s WHERE %s' % (table, where),
        list(params or [])).fetchone()[0]


def _rows(conn, sql, params=None):
    cur = conn.execute(sql, list(params or []))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _on_hand(conn):
    return conn.execute(
        'SELECT qty_on_hand FROM inventory_balances WHERE org_id=? AND '
        'location_id=? AND item_id=? AND batch_id=0',
        [inv.ORG_ID, inv.LOCATION_ID, inv.ITEM_ID]).fetchone()[0]


# ------------------------------------------------------------------ AC-19

def test_return_ship_confirm_posts_return_in_and_return_edge():
    conn = _db(return_in=True)
    _seed_balance(conn, 100.0)
    svc, created, result = _ship(conn, qty=10,
                                 order_type_id=_RETURN_TYPE_ID,
                                 ship_type_id=_RETURN_TYPE_ID)
    assert result['status'] == 'shipped'

    txns = _rows(conn, 'SELECT * FROM inventory_transactions')
    assert len(txns) == 1
    txn = txns[0]
    assert txn['transaction_type_id'] == _return_txn_type_id(conn)
    assert txn['direction'] == 'in'
    assert txn['source_doc_type'] == 'shipment'
    assert txn['source_doc_id'] == created['id']
    assert txn['source_event_key'] == 'shipment:%s:return' % created['id']
    assert txn['stock_segment_type'] == 'owned'

    assert _on_hand(conn) == 110.0

    edges = _rows(conn, 'SELECT * FROM doc_flow_edges')
    assert len(edges) == 1
    edge = edges[0]
    assert edge['rule_id'] == RETURN_RULE_ID
    assert edge['pool'] == 'inventory_return'
    assert edge['status'] == 'active'
    assert edge['quantity'] == 10.0
    assert edge['derived_by'] == 'shipment_service'
    assert edge['target_id'] == str(txn['id'])

    # 重放幂等：单事务 + 单边
    again = svc.ship_confirm(created['id'])
    assert again['idempotent'] is True
    assert _count(conn, 'inventory_transactions') == 1
    assert _count(conn, 'doc_flow_edges') == 1


def test_return_skips_issue_serial_validation_and_hu():
    """退货为入库方向：不走出库序列号校验，也不触发 HU / 预留核销。"""
    conn = _db(return_in=True)
    _seed_balance(conn, 100.0)
    svc, created, result = _ship(conn, qty=6,
                                 order_type_id=_RETURN_TYPE_ID,
                                 ship_type_id=_RETURN_TYPE_ID)
    assert result['status'] == 'shipped'
    # 无序列号 / HU 相关表也不会抛错（正向路径会校验序列号）
    assert _count(conn, 'inventory_transactions') == 1


# ------------------------------------------------------------------ AC-20

def test_category_inherited_from_order_when_shipment_type_blank():
    conn = _db(return_in=True)
    _seed_balance(conn, 100.0)
    svc, created, result = _ship(conn, qty=5,
                                 order_type_id=_RETURN_TYPE_ID,
                                 ship_type_id=None)
    assert result['status'] == 'shipped'
    txn = _rows(conn, 'SELECT * FROM inventory_transactions')[0]
    assert txn['direction'] == 'in'
    assert txn['transaction_type_id'] == _return_txn_type_id(conn)


def test_category_mismatch_rejected_without_posting_or_edge():
    conn = _db(return_in=True)
    _seed_balance(conn, 100.0)
    svc, created, _ = _ship(conn, qty=10, order_type_id=_STD_TYPE_ID,
                            ship_type_id=_RETURN_TYPE_ID, confirm=False)

    with pytest.raises(ShipmentError) as exc:
        svc.ship_confirm(created['id'])
    assert exc.value.rule == 'DN_CATEGORY_MISMATCH'
    assert _count(conn, 'inventory_transactions') == 0
    assert _count(conn, 'doc_flow_edges') == 0
    status = conn.execute(
        'SELECT status FROM shipments WHERE id = ?', [created['id']]
    ).fetchone()[0]
    assert status == 'staged'


# ------------------------------------------------------------------ AC-21

def test_issue_and_return_pools_are_isolated():
    conn = _db(return_in=True)
    _seed_balance(conn, 100.0)
    _ship(conn, qty=10, order_type_id=_STD_TYPE_ID, ship_type_id=_STD_TYPE_ID)
    # 换一个订单/计划，避免与正向发运的行共享
    conn.execute('UPDATE sales_orders SET id = 11, document_type_id = ? '
                 'WHERE id = ?', [_RETURN_TYPE_ID, _ORDER_ID])
    conn.execute('UPDATE sales_order_lines SET id = 101, order_id = 11 '
                 'WHERE id = ?', [_ORDER_LINE_ID])
    conn.execute('UPDATE sales_order_schedules SET id = 2, order_id = 11, '
                 'line_id = 101 WHERE id = ?', [_SCHEDULE_ID])
    _ORDER = 11
    _SCHED = 2
    ds = _ShipDS(conn)
    svc = ShipmentService(ds, platform_data_source=ds)
    created = svc.create_shipment(
        {'order_id': _ORDER, 'document_type_id': _RETURN_TYPE_ID},
        [{'schedule_id': _SCHED, 'qty': 5}])
    svc.release(created['id'])
    svc.stage(created['id'])
    svc.ship_confirm(created['id'])

    issue = conn.execute(
        "SELECT SUM(consumed_qty) FROM v_doc_flow_consumed_qty "
        "WHERE pool='inventory_issue'").fetchone()[0]
    ret = conn.execute(
        "SELECT SUM(consumed_qty) FROM v_doc_flow_consumed_qty "
        "WHERE pool='inventory_return'").fetchone()[0]
    assert issue == 10.0
    assert ret == 5.0
    assert _on_hand(conn) == 95.0


# ------------------------------------------------------------------ AC-22

def test_return_is_not_reversal_issue_edge_stays_active():
    conn = _db(return_in=True)
    _seed_balance(conn, 100.0)
    _ship(conn, qty=10, order_type_id=_STD_TYPE_ID, ship_type_id=_STD_TYPE_ID)
    conn.execute('UPDATE sales_orders SET id = 11, document_type_id = ? '
                 'WHERE id = ?', [_RETURN_TYPE_ID, _ORDER_ID])
    conn.execute('UPDATE sales_order_lines SET id = 101, order_id = 11 '
                 'WHERE id = ?', [_ORDER_LINE_ID])
    conn.execute('UPDATE sales_order_schedules SET id = 2, order_id = 11, '
                 'line_id = 101 WHERE id = ?', [_SCHEDULE_ID])
    ds = _ShipDS(conn)
    svc = ShipmentService(ds, platform_data_source=ds)
    created = svc.create_shipment(
        {'order_id': 11, 'document_type_id': _RETURN_TYPE_ID},
        [{'schedule_id': 2, 'qty': 4}])
    svc.release(created['id'])
    svc.stage(created['id'])
    svc.ship_confirm(created['id'])

    edges = _rows(conn, 'SELECT rule_id, status, quantity_sign, quantity '
                        'FROM doc_flow_edges ORDER BY id')
    assert sorted(e['rule_id'] for e in edges) == sorted(
        [ISSUE_RULE_ID, RETURN_RULE_ID])
    assert all(e['status'] == 'active' for e in edges)
    assert all(e['quantity_sign'] == 'normal' for e in edges)

    conn.execute(v222.VIEW_DDL)
    view = _rows(conn, "SELECT relation, signed_qty FROM %s "
                       "WHERE layer='execution'" % v222.VIEW_NAME)
    by_rule = {}
    for row in view:
        by_rule[row['relation']] = by_rule.get(row['relation'], 0.0) + \
            float(row['signed_qty'])
    assert by_rule[ISSUE_RULE_ID] == 10.0
    assert by_rule[RETURN_RULE_ID] == -4.0
    assert sum(by_rule.values()) == 6.0


# ------------------------------------------------------------------ AC-23

def test_reconcile_detects_orphan_return_txn_and_dangling_edge():
    conn = _db(return_in=True)
    _seed_balance(conn, 100.0)
    _ship(conn, qty=10, order_type_id=_RETURN_TYPE_ID,
          ship_type_id=_RETURN_TYPE_ID)

    clean = scan(conn)
    assert 'ORPHAN_TXN' not in clean.codes()
    assert 'DANGLING_EDGE' not in clean.codes()

    # 删边 → 退货事务成为孤儿
    conn.execute('DELETE FROM doc_flow_edges')
    orphan = scan(conn)
    assert 'ORPHAN_TXN' in orphan.codes()

    # 插悬空边 → DANGLING_EDGE
    conn.execute(
        "INSERT INTO doc_flow_edges (id, source_bo, source_id, source_item, "
        "target_bo, target_id, target_item, quantity, quantity_sign, rule_id, "
        "derived_at, derived_by, status, pool) VALUES (?, 'shipment_line', "
        "'1', '', 'inventory_transaction', '999999', '', 1, 'normal', ?, "
        "'2026-11-05', 'test', 'active', 'inventory_return')",
        ['E-dangling', RETURN_RULE_ID])
    dangling = scan(conn)
    assert 'DANGLING_EDGE' in dangling.codes()


# ---------------------------------------------------------------- 迁移

def test_v222_migration_seeds_and_is_idempotent(tmp_path):
    src = _db(return_in=False)
    db_path = str(tmp_path / 'v222.db')
    dst = sqlite3.connect(db_path)
    src.backup(dst)
    dst.close()

    v222.migrate(db_path)
    v222.migrate(db_path)  # 重跑必须幂等

    result = v222.verify(db_path)
    assert result['ok'] is True

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute(
            "SELECT 1 FROM inventory_transaction_types WHERE code='RETURN_IN' "
            "AND category='receipt' AND direction='in' AND status='active'"
        ).fetchone()
        assert conn.execute(
            "SELECT 1 FROM type_definitions WHERE scope_bo='shipment' "
            "AND level='header' AND code='RETURN' "
            "AND document_category='return'"
        ).fetchone()
        rules = conn.execute(
            'SELECT rule_id, pool, status FROM doc_flow_rule '
            'WHERE rule_id=?', [RETURN_RULE_ID]).fetchall()
        assert rules == [(RETURN_RULE_ID, 'inventory_return', 'active')]

        cols = [row[1] for row in conn.execute(
            'PRAGMA table_info(%s)' % v222.VIEW_NAME).fetchall()]
        assert len(cols) == 17
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='view' AND name=?",
            [v222.VIEW_NAME]).fetchone()[0]
        assert RETURN_RULE_ID in sql
    finally:
        conn.close()

    src.close()
