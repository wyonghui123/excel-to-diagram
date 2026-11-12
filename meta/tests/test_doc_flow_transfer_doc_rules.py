# -*- coding: utf-8 -*-
"""v231 调拨单据流两条断链补边验收

依据: docs/specs/spec-doc-flow-end-to-end-2026-11-05.md §1「单据 → 单据必须接」

覆盖:
  · 迁移幂等：两条规则注册且 active，数量字段按实际 schema（qty / qty_received）；
  · 调拨发货建单 → 调拨行 → 发货行边（pool=transfer_shipment）；
  · 调拨发货取消 → 边释放（status=reversed，消耗视图不再占用）；
  · 调拨收货建单 → 调拨行 → 收货行边（pool=transfer_receipt，qty_received）。
"""

import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.core.doc_flow_rule_store import upsert_rules
from meta.migrations import v231__doc_flow_transfer_doc_rules as v231
from meta.services.receipt_service import ReceiptService
from meta.services.transfer_shipment_service import TransferShipmentService
from meta.tests.transfer_order_test_doubles import (
    MemDS, release_transfer_order, seeded_db,
)

ORDER_ID = 1
LINE_ID = 100


class _DS(MemDS):
    """MemDS + insert（derive 引擎写边走 ds.insert）。"""

    def insert(self, table, data):
        cols = list(data)
        cur = self.conn.execute(
            'INSERT INTO %s (%s) VALUES (%s)'
            % (table, ', '.join(cols), ', '.join('?' * len(cols))),
            [data[c] for c in cols])
        return cur.lastrowid


def _flow_enabled(conn):
    """在 doubles 库上补齐 doc_flow 表 / 视图并注册 v231 规则。"""
    conn.execute(v231.RULE_TABLE_DDL)
    conn.execute(v231.EDGE_TABLE_DDL)
    for _name, ddl in v231.EDGE_INDEXES:
        conn.execute(ddl)
    conn.execute(v231.CONSUMED_VIEW_DDL)
    upsert_rules(_DS(conn), [dict(rule) for rule in v231.RULES])
    conn.commit()


def _edges(conn, rule_id):
    return MemDS(conn).query(
        'SELECT * FROM doc_flow_edges WHERE rule_id = ? ORDER BY id',
        [rule_id])


def _shipment_svc(conn):
    ds = _DS(conn)
    return TransferShipmentService(ds, platform_data_source=ds)


def test_migration_upserts_two_transfer_rules(tmp_path):
    db_path = str(tmp_path / 'platform.db')
    sqlite3.connect(db_path).close()

    v231.migrate(db_path)
    v231.migrate(db_path)  # 幂等重放

    assert v231.verify(db_path)['ok'] is True

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            'SELECT rule_id, source_bo, target_bo, source_qty_field, '
            'target_qty_field, pool, status FROM doc_flow_rule '
            'ORDER BY rule_id').fetchall()
    finally:
        conn.close()
    assert rows == [
        ('transfer_order_line_to_receipt_line', 'transfer_order_line',
         'receipt_line', 'qty', 'qty_received', 'transfer_receipt', 'active'),
        ('transfer_order_line_to_transfer_shipment_line',
         'transfer_order_line', 'transfer_shipment_line', 'qty', 'qty',
         'transfer_shipment', 'active'),
    ]


def test_create_transfer_shipment_writes_order_line_edge():
    conn = seeded_db(line_qtys=(100.0,))
    release_transfer_order(conn, ORDER_ID)
    _flow_enabled(conn)

    result = _shipment_svc(conn).create(
        ORDER_ID, '2026-11-02',
        [{'transfer_order_line_id': LINE_ID, 'qty': 30}])

    line = MemDS(conn).query(
        'SELECT id FROM transfer_shipment_lines WHERE transfer_shipment_id = ?',
        [result['id']])[0]
    edges = _edges(conn, 'transfer_order_line_to_transfer_shipment_line')
    assert len(edges) == 1
    edge = edges[0]
    assert edge['source_bo'] == 'transfer_order_line'
    assert edge['source_id'] == str(LINE_ID)
    assert edge['target_bo'] == 'transfer_shipment_line'
    assert edge['target_id'] == str(line['id'])
    assert edge['quantity'] == pytest.approx(30.0)
    assert edge['pool'] == 'transfer_shipment'
    assert edge['status'] == 'active'
    assert edge['quantity_sign'] == 'normal'


def test_cancel_transfer_shipment_releases_edge():
    conn = seeded_db(line_qtys=(100.0,))
    release_transfer_order(conn, ORDER_ID)
    _flow_enabled(conn)
    service = _shipment_svc(conn)

    result = service.create(
        ORDER_ID, '2026-11-02',
        [{'transfer_order_line_id': LINE_ID, 'qty': 30}])
    service.cancel(result['id'])

    edges = _edges(conn, 'transfer_order_line_to_transfer_shipment_line')
    assert len(edges) == 1
    assert edges[0]['status'] == 'reversed'
    consumed = MemDS(conn).query(
        'SELECT consumed_qty FROM v_doc_flow_consumed_qty '
        'WHERE source_bo = ? AND source_id = ? AND pool = ?',
        ['transfer_order_line', str(LINE_ID), 'transfer_shipment'])
    assert float(consumed[0]['consumed_qty']) == pytest.approx(0.0)


def test_create_receipt_from_transfer_order_writes_edge():
    conn = seeded_db(line_qtys=(100.0,))
    release_transfer_order(conn, ORDER_ID, {LINE_ID: 40.0})
    _flow_enabled(conn)
    ds = _DS(conn)

    result = ReceiptService(ds, platform_data_source=ds).create_from_transfer_order(
        ORDER_ID)

    line = ds.query(
        'SELECT id, source_line_id, qty_received FROM receipt_lines '
        'WHERE receipt_id = ?', [result['id']])[0]
    assert result['line_ids'] == [line['id']]
    assert line['source_line_id'] == LINE_ID
    edges = _edges(conn, 'transfer_order_line_to_receipt_line')
    assert len(edges) == 1
    edge = edges[0]
    assert edge['source_bo'] == 'transfer_order_line'
    assert edge['source_id'] == str(LINE_ID)
    assert edge['target_bo'] == 'receipt_line'
    assert edge['target_id'] == str(line['id'])
    assert edge['quantity'] == pytest.approx(40.0)
    assert edge['pool'] == 'transfer_receipt'
    assert edge['status'] == 'active'