# -*- coding: utf-8 -*-
"""发运确认 → 出库过账 + DOC_FLOW 转单边（P0 阶段 1 验收）

依据: docs/specs/spec-doc-flow-end-to-end-2026-11-05.md §5.1 / §6 阶段 1

覆盖:
  · 过账总开关关闭 → 发运成功但不写事务/边（过渡期不阻断）
  · 过账开启 → ISSUE_TO_SHIP 事务 + 余额扣减 + 唯一来源事件键
  · 过账开启 + 规则在线 → 每行一条 doc_flow 边（attach 库存事务），
    数量/池/derived_by/7 元组正确，消耗视图可聚合
  · 规则未注册 → 只过账不写边（降级为告警，发运不阻断）
  · 负库存 → 发运被拒、状态不回写、无边残留（先过账后写边的顺序保证）
  · 重复发运确认 → 幂等，不产生重复事务/边
"""

import os
import sqlite3

# 与项目测试同口径：只用内存库，不触碰真实库
os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.core.doc_flow_rule_store import upsert_rules
from meta.migrations import v214__doc_flow_shipment_issue_rule as v214
from meta.services.shipment_service import ShipmentError, ShipmentService
from meta.tests import inventory_test_doubles as inv

RULE_ID = v214.RULE_ID

_ORDER_ID = 10
_ORDER_LINE_ID = 100
_SCHEDULE_ID = 1

# 仅补发运侧表（orgs/locations/items/uoms/batches 由 inventory_test_doubles 提供）
_SHIPMENT_DDL = """
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY,
    order_no TEXT,
    org_id INTEGER,
    order_date TEXT,
    status TEXT,
    ship_to_party_id INTEGER,
    ship_to_address_text TEXT,
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
    level TEXT,
    line_category TEXT,
    delivery_relevant INTEGER DEFAULT 1
);
CREATE TABLE shipments (
    id INTEGER PRIMARY KEY,
    delivery_no TEXT,
    order_id INTEGER,
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


def _db(with_rule=True):
    """库存库 + 发运库 + DOC_FLOW 边表（规则可选）。"""
    conn = inv.build_db()
    inv.seed(conn)
    conn.executescript(_SHIPMENT_DDL)
    conn.execute(v214.EDGE_TABLE_DDL)
    for _, ddl in v214.EDGE_INDEXES:
        conn.execute(ddl)
    conn.execute(v214.CONSUMED_VIEW_DDL)
    if with_rule:
        conn.execute(v214.RULE_TABLE_DDL)
        upsert_rules(_ShipDS(conn), [dict(v214.RULE)])
    conn.commit()
    return conn


def _add_order(conn):
    conn.execute(
        'INSERT INTO sales_orders (id, order_no, org_id, order_date, status, '
        'ship_to_party_id, ship_to_address_text) VALUES (?, ?, ?, ?, ?, ?, ?)',
        [_ORDER_ID, 'SO-0001', inv.ORG_ID, '2026-10-20', 'confirmed', 500,
         '上海市浦东新区世纪大道 100 号'])


def _add_order_line(conn, lid=_ORDER_LINE_ID, task_id=0):
    conn.execute(
        'INSERT INTO sales_order_lines (id, order_id, item_id, uom_id, '
        'project_task_id, status) VALUES (?, ?, ?, ?, ?, ?)',
        [lid, _ORDER_ID, inv.ITEM_ID, inv.UOM_ID, task_id, 'open'])


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


def _ship(conn, rows=None, platform_ds=None):
    ds = _ShipDS(conn)
    svc = ShipmentService(ds, platform_data_source=platform_ds or ds)
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    created = svc.create_shipment(
        {'order_id': _ORDER_ID},
        rows if rows is not None else [{'schedule_id': _SCHEDULE_ID, 'qty': 10}])
    svc.release(created['id'])
    svc.stage(created['id'])
    return svc, created, svc.ship_confirm(created['id'])


def _count(conn, table, where='1=1', params=None):
    if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            [table]).fetchone():
        return 0
    return conn.execute(
        'SELECT COUNT(*) FROM %s WHERE %s' % (table, where),
        list(params or [])).fetchone()[0]


# ---------------------------------------------------------------- 过账开关

def test_ship_confirm_skips_posting_when_switch_off():
    conn = _db()
    inv.enable_posting(conn, False)
    svc, created, result = _ship(conn)

    assert result['status'] == 'shipped'
    assert _count(conn, 'inventory_transactions') == 0
    assert _count(conn, 'doc_flow_edges') == 0


# ------------------------------------------------------------ 过账 + 写边

def test_ship_confirm_posts_issue_and_writes_edges():
    conn = _db()
    _seed_balance(conn, 100.0)
    svc, created, result = _ship(conn, rows=[
        {'schedule_id': _SCHEDULE_ID, 'qty': 4},
        {'schedule_id': _SCHEDULE_ID, 'qty': 6},
    ])
    assert result['status'] == 'shipped'

    txns = conn.execute(
        'SELECT * FROM inventory_transactions ORDER BY id').fetchall()
    txn_cols = [d[0] for d in conn.execute(
        'SELECT * FROM inventory_transactions').description]
    assert len(txns) == 2
    line_ids = sorted(
        row[0] for row in conn.execute(
            'SELECT id FROM shipment_lines WHERE delivery_id = ?',
            [created['id']]))
    assert sorted(dict(zip(txn_cols, t))['source_line_id'] for t in txns) == line_ids
    for raw in txns:
        row = dict(zip(txn_cols, raw))
        assert row['direction'] == 'out'
        assert row['source_doc_type'] == 'shipment'
        assert row['source_doc_id'] == created['id']
        assert row['source_event_key'] == 'shipment:%s:ship' % created['id']
        assert row['stock_segment_type'] == 'owned'

    balance = conn.execute(
        'SELECT qty_on_hand FROM inventory_balances WHERE org_id=? AND '
        'location_id=? AND item_id=? AND batch_id=0', [
            inv.ORG_ID, inv.LOCATION_ID, inv.ITEM_ID]).fetchone()[0]
    assert balance == 90.0

    edges = conn.execute('SELECT * FROM doc_flow_edges').fetchall()
    edge_cols = [d[0] for d in conn.execute('SELECT * FROM doc_flow_edges').description]
    assert len(edges) == 2
    for raw in edges:
        edge = dict(zip(edge_cols, raw))
        assert edge['source_bo'] == 'shipment_line'
        assert edge['source_id'] in {str(lid) for lid in line_ids}
        assert edge['target_bo'] == 'inventory_transaction'
        assert edge['rule_id'] == RULE_ID
        assert edge['pool'] == 'inventory_issue'
        assert edge['derived_by'] == 'shipment_service'
        assert edge['status'] == 'active'
        assert edge['quantity'] > 0

    consumed = conn.execute(
        "SELECT SUM(consumed_qty) FROM v_doc_flow_consumed_qty "
        "WHERE source_bo='shipment_line'").fetchone()[0]
    assert consumed == 10.0


def test_ship_confirm_without_rule_still_ships():
    """规则未注册：过账照常，边降级跳过（不阻断发运）。"""
    conn = _db(with_rule=False)
    _seed_balance(conn, 100.0)
    svc, created, result = _ship(conn)

    assert result['status'] == 'shipped'
    assert _count(conn, 'inventory_transactions') == 1
    assert _count(conn, 'doc_flow_edges') == 0


# ------------------------------------------------------- 失败不写边 / 幂等

def test_ship_confirm_negative_stock_rejected_without_edge():
    conn = _db()
    # 无期初余额 → 负库存拒绝
    svc = ShipmentService(_ShipDS(conn))
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    created = svc.create_shipment(
        {'order_id': _ORDER_ID}, [{'schedule_id': _SCHEDULE_ID, 'qty': 10}])
    svc.release(created['id'])
    svc.stage(created['id'])

    with pytest.raises(ShipmentError) as exc:
        svc.ship_confirm(created['id'])
    assert exc.value.rule == 'INV_NEGATIVE_STOCK'
    assert _count(conn, 'inventory_transactions') == 0
    assert _count(conn, 'doc_flow_edges') == 0
    status = conn.execute(
        'SELECT status FROM shipments WHERE id = ?', [created['id']]
    ).fetchone()[0]
    assert status == 'staged'


def test_ship_confirm_replay_keeps_single_transaction_and_edge():
    conn = _db()
    _seed_balance(conn, 100.0)
    svc, created, first = _ship(conn)
    again = svc.ship_confirm(created['id'])

    assert again['idempotent'] is True
    assert _count(conn, 'inventory_transactions') == 1
    assert _count(conn, 'doc_flow_edges') == 1


# ---------------------------------------------------------------- 迁移

def test_v214_migration_creates_rule_and_is_idempotent(tmp_path):
    db_path = str(tmp_path / 'mig.db')
    sqlite3.connect(db_path).close()

    v214.migrate(db_path)
    v214.migrate(db_path)  # 重跑必须幂等

    conn = sqlite3.connect(db_path)
    try:
        rules = conn.execute(
            'SELECT rule_id, source_bo, target_bo, source_qty_field, pool, '
            'status FROM doc_flow_rule').fetchall()
        assert len(rules) == 1
        assert rules[0] == (
            RULE_ID, 'shipment_line', 'inventory_transaction', 'qty',
            'inventory_issue', 'active')
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='doc_flow_edges'").fetchone()
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='view' "
            "AND name='v_doc_flow_consumed_qty'").fetchone()
        indexes = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='doc_flow_edges'")}
        assert {'uq_doc_flow_idem', 'idx_doc_flow_source',
                'idx_doc_flow_target'} <= indexes
    finally:
        conn.close()
