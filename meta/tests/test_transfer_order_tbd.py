# -*- coding: utf-8 -*-
"""调拨单 TBD 收口验收（v191 / v193 / v194 / v195）。

覆盖：反向调拨链接、非交付行、超发 / 超收容差、调拨发货单、
需求分配转单回写、审批闸门、采购法人快照与收货法人一致性。
不触碰库存域；内存 SQLite 用 `transfer_order_test_doubles` 种子。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

from contextlib import contextmanager

import pytest

pytestmark = pytest.mark.unit

from meta.services.purchase_order_guard_service import (
    PurchaseOrderGuardError,
    PurchaseOrderGuardService,
)
from meta.services.receipt_service import ReceiptError
from meta.services.transfer_order_from_allocation import ConversionError
from meta.services.transfer_order_service import (
    TransferOrderError,
    TransferOrderService,
    resolve_tolerance_ratio,
)
from meta.services.transfer_shipment_service import (
    TransferShipmentError,
    TransferShipmentService,
)
from meta.tests.transfer_order_test_doubles import (
    MemDS,
    TO_GOODS_TYPE_ID,
    TO_SERVICE_TYPE_ID,
    TO_STANDARD_TYPE_ID,
    add_allocation,
    add_approval_policy,
    add_approval_step,
    add_master_data,
    add_org_tree,
    add_requisition_line,
    add_transfer_line,
    add_transfer_order,
    add_types,
    build_db,
    from_allocation_service,
    receipt_guard_svc,
    release_transfer_order,
    seeded_db,
    to_guard,
    to_service,
)

ORDER_ID = 1
LINE_ID = 100
SECOND_LINE_ID = 101

#: 采购订单头类型（采购守卫单测用；调拨 doubles 只种了 PO 行类型）
PO_STANDARD_TYPE_ID = 200

_PO_DDL = """
CREATE TABLE purchase_orders (
    id INTEGER PRIMARY KEY,
    order_no TEXT,
    status TEXT,
    document_type_id INTEGER,
    org_id INTEGER,
    purchase_org_id INTEGER,
    purchase_legal_entity_id INTEGER,
    supplier_party_id INTEGER,
    currency_id INTEGER,
    exchange_rate REAL,
    exchange_rate_type TEXT,
    exchange_rate_date TEXT,
    project_id INTEGER,
    deliver_to_location_id INTEGER,
    approval_status TEXT
);
"""


# ---------------------------------------------------------------------------
# 局部装置
# ---------------------------------------------------------------------------
def _add_control_value(conn, param_id, value, value_id=None):
    conn.execute(
        'INSERT INTO control_parameter_values (id, control_parameter_id, value, '
        "status) VALUES (?, ?, ?, 'active')",
        [value_id, param_id, str(value)])
    conn.commit()


def _shipment_svc(conn):
    return TransferShipmentService(MemDS(conn))


class _Result:
    def __init__(self, success=True, data=None, message=''):
        self.success = success
        self.data = data
        self.message = message


class _FakeFramework:
    """最小 BO 框架替身：记录对象写入并模拟事务。"""

    def __init__(self):
        self.calls = []
        self.committed = False
        self.rolled_back = False

    @contextmanager
    def transaction(self):
        try:
            yield self
        except Exception:
            self.rolled_back = True
            raise
        else:
            self.committed = True

    def execute(self, object_type, action, data):
        record = dict(data)
        record['id'] = len(self.calls) + 1
        self.calls.append({'object_type': object_type, 'action': action,
                           'data': record})
        return _Result(success=True, data=record)

    def payloads(self, object_type):
        return [c['data'] for c in self.calls
                if c['object_type'] == object_type]


def _allocation_db():
    conn = build_db()
    add_types(conn)
    add_org_tree(conn)
    add_master_data(conn)
    add_requisition_line(conn, lid=500, item_id=900, qty=100.0)
    add_requisition_line(conn, lid=501, item_id=900, qty=40.0, line_no='20')
    conn.commit()
    return conn


def _po_db():
    conn = seeded_db()
    conn.execute(_PO_DDL)
    conn.execute(
        'INSERT INTO type_definitions (id, code, name, scope_bo, level, '
        'document_category, status) '
        "VALUES (?, 'PO_STD', '标准采购订单', 'purchase_order', 'header', "
        "'standard', 'active')", [PO_STANDARD_TYPE_ID])
    conn.commit()
    return conn


def _renumber_seeded_order(conn):
    """种子单号占用 000001；挪到上一月份，避免反向单取号撞 UNIQUE。"""
    conn.execute(
        "UPDATE transfer_orders SET transfer_order_no = 'TRF-202610-000001' "
        'WHERE id = ?', [ORDER_ID])
    conn.commit()


def _add_po(conn, pid=1, org_id=1, purchase_org_id=2,
            purchase_legal_entity_id=1, status='draft'):
    conn.execute(
        'INSERT INTO purchase_orders (id, order_no, status, document_type_id, '
        'org_id, purchase_org_id, purchase_legal_entity_id, supplier_party_id, '
        'currency_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [pid, 'PO-0001', status, PO_STANDARD_TYPE_ID, org_id, purchase_org_id,
         purchase_legal_entity_id, 500, 1])
    conn.commit()


def _header(conn, oid=ORDER_ID):
    return MemDS(conn).query(
        'SELECT * FROM transfer_orders WHERE id = ?', [oid])[0]


def _line(conn, lid=LINE_ID):
    return MemDS(conn).query(
        'SELECT * FROM transfer_order_lines WHERE id = ?', [lid])[0]


def _tasks(conn):
    return MemDS(conn).query('SELECT * FROM tasks ORDER BY created_at')


# ===========================================================================
# 1. 反向调拨链接
# ===========================================================================
def test_create_reversal_swaps_orgs_and_locations():
    conn = seeded_db()
    _renumber_seeded_order(conn)
    svc = to_service(conn)

    result = svc.create_reversal(ORDER_ID)

    new = _header(conn, result['id'])
    original = _header(conn)
    assert new['reversal_of_transfer_id'] == ORDER_ID
    assert (new['from_org_id'], new['to_org_id']) == \
        (original['to_org_id'], original['from_org_id'])
    assert (new['from_location_id'], new['to_location_id']) == \
        (original['to_location_id'], original['from_location_id'])
    assert new['status'] == 'draft'
    assert new['transfer_order_no'].startswith('TRF-202611-')
    assert result['line_count'] == 2

    lines = MemDS(conn).query(
        'SELECT line_no, qty, qty_shipped, qty_received FROM '
        'transfer_order_lines WHERE transfer_order_id = ? ORDER BY line_no',
        [result['id']])
    assert [row['line_no'] for row in lines] == [10, 20]
    assert lines[0]['qty'] == pytest.approx(100.0)
    assert lines[0]['qty_shipped'] == pytest.approx(0.0)
    assert lines[0]['qty_received'] == pytest.approx(0.0)
    # 原单不变
    assert original['status'] == 'draft'


def test_create_reversal_rejects_missing_original():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_service(conn).create_reversal(999)
    assert exc.value.rule == 'TO_NOT_FOUND'


def test_create_reversal_rejects_cancelled_original():
    conn = seeded_db(status='cancelled')
    with pytest.raises(TransferOrderError) as exc:
        to_service(conn).create_reversal(ORDER_ID)
    assert exc.value.rule == 'TO_REVERSAL_ORIGINAL_CANCELLED'


def test_create_reversal_rejects_existing_reversal():
    conn = seeded_db()
    _renumber_seeded_order(conn)
    svc = to_service(conn)
    svc.create_reversal(ORDER_ID)

    with pytest.raises(TransferOrderError) as exc:
        svc.create_reversal(ORDER_ID)
    assert exc.value.rule == 'TO_REVERSAL_EXISTS'


def test_guard_rejects_manual_reversal_without_org_swap():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_create({
            'document_type_id': TO_STANDARD_TYPE_ID,
            'transfer_date': '2026-11-02',
            'from_org_id': 2,
            'to_org_id': 3,
            'reversal_of_transfer_id': ORDER_ID,
        })
    assert exc.value.rule == 'TO_REVERSAL_ORG_NOT_SWAPPED'


def test_guard_rejects_manual_reversal_without_location_swap():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_create({
            'document_type_id': TO_STANDARD_TYPE_ID,
            'transfer_date': '2026-11-02',
            'from_org_id': 3,
            'to_org_id': 2,
            'from_location_id': None,
            'to_location_id': 7,
            'reversal_of_transfer_id': ORDER_ID,
        })
    assert exc.value.rule == 'TO_REVERSAL_LOCATION_NOT_SWAPPED'


# ===========================================================================
# 2. 非交付行
# ===========================================================================
def test_release_closes_non_delivery_line():
    conn = seeded_db(line_qtys=(100.0,))
    add_transfer_line(conn, lid=SECOND_LINE_ID, oid=ORDER_ID, line_no=20,
                      line_type_id=TO_SERVICE_TYPE_ID, item_id=901, qty=5.0)
    conn.commit()

    result = to_service(conn).release(ORDER_ID)

    assert result['status'] == 'released'
    assert _line(conn, SECOND_LINE_ID)['status'] == 'closed'
    assert _line(conn)['status'] == 'open'


def test_all_received_ignores_closed_non_delivery_line():
    conn = seeded_db(line_qtys=(100.0,))
    add_transfer_line(conn, lid=SECOND_LINE_ID, oid=ORDER_ID, line_no=20,
                      line_type_id=TO_SERVICE_TYPE_ID, item_id=901, qty=5.0)
    conn.commit()
    svc = to_service(conn)
    svc.release(ORDER_ID)
    svc.ship(ORDER_ID, [{'line_id': LINE_ID, 'qty': 100}])

    result = svc.apply_receipt(
        ORDER_ID, [{'line_id': LINE_ID, 'qty_received': 100}])

    header = _header(conn)
    assert result['status'] == 'closed'
    assert header['status'] == 'closed'
    assert header['fulfillment_status'] == 'received'
    assert _line(conn, SECOND_LINE_ID)['status'] == 'closed'


def test_all_received_ignores_cancelled_line():
    conn = seeded_db(line_qtys=(100.0, 50.0))
    conn.execute(
        "UPDATE transfer_order_lines SET status = 'cancelled' WHERE id = ?",
        [SECOND_LINE_ID])
    conn.commit()
    svc = to_service(conn)
    svc.release(ORDER_ID)
    svc.ship(ORDER_ID, [{'line_id': LINE_ID, 'qty': 100}])

    result = svc.apply_receipt(
        ORDER_ID, [{'line_id': LINE_ID, 'qty_received': 100}])

    assert result['status'] == 'closed'
    assert _header(conn)['status'] == 'closed'
    assert _line(conn, SECOND_LINE_ID)['status'] == 'cancelled'


# ===========================================================================
# 3. 超发 / 超收容差
# ===========================================================================
@pytest.mark.parametrize('code,value,expected', [
    ('transfer_over_ship_percent', None, '0'),
    ('transfer_over_ship_percent', '0.05', '0.0005'),
    ('transfer_over_ship_percent', '5', '0.05'),
])
def test_resolve_tolerance_ratio_percent_to_ratio(code, value, expected):
    from decimal import Decimal

    conn = seeded_db()
    if value is not None:
        _add_control_value(conn, 1, value)
    ratio = resolve_tolerance_ratio(MemDS(conn), code, _header(conn))
    assert ratio == Decimal(expected)


def test_resolve_tolerance_ratio_defaults_zero_on_bad_input():
    conn = seeded_db()
    _add_control_value(conn, 1, 'abc')
    assert resolve_tolerance_ratio(MemDS(conn), 'unknown_param',
                                   _header(conn)) == 0
    assert resolve_tolerance_ratio(MemDS(conn),
                                   'transfer_over_ship_percent', None) == 0
    assert resolve_tolerance_ratio(MemDS(conn),
                                   'transfer_over_ship_percent',
                                   _header(conn)) == 0


def test_ship_strict_limit_without_tolerance():
    conn = seeded_db(line_qtys=(100.0,))
    release_transfer_order(conn, ORDER_ID, {LINE_ID: 0.0})

    with pytest.raises(TransferOrderError) as exc:
        to_service(conn).ship(ORDER_ID, [{'line_id': LINE_ID, 'qty': 101}])
    assert exc.value.rule == 'TO_SHIP_QTY_EXCEEDED'
    assert _line(conn)['qty_shipped'] == pytest.approx(0.0)


def test_ship_allows_overage_within_tolerance_and_rejects_beyond():
    conn = seeded_db(line_qtys=(100.0,))
    _add_control_value(conn, 1, '0.05')  # 0.05% → 上限 100.05
    release_transfer_order(conn, ORDER_ID, {LINE_ID: 0.0})
    svc = to_service(conn)

    svc.ship(ORDER_ID, [{'line_id': LINE_ID, 'qty': 100.02}])
    assert _line(conn)['qty_shipped'] == pytest.approx(100.02)

    with pytest.raises(TransferOrderError) as exc:
        svc.ship(ORDER_ID, [{'line_id': LINE_ID, 'qty': 0.04}])
    assert exc.value.rule == 'TO_SHIP_QTY_EXCEEDED'
    assert _line(conn)['qty_shipped'] == pytest.approx(100.02)


def test_receive_strict_limit_without_tolerance():
    conn = seeded_db(line_qtys=(100.0,))
    release_transfer_order(conn, ORDER_ID, {LINE_ID: 100.0})

    with pytest.raises(TransferOrderError) as exc:
        to_service(conn).apply_receipt(
            ORDER_ID, [{'line_id': LINE_ID, 'qty_received': 101}])
    assert exc.value.rule == 'TO_RECEIVE_EXCEEDED'
    assert _line(conn)['qty_received'] == pytest.approx(0.0)


def test_receive_allows_overage_within_tolerance_and_rejects_beyond():
    # 行需求量 200、实际只发 100：容差按已发量 100 × (1 + 5%) = 105 计
    conn = seeded_db(line_qtys=(200.0,))
    _add_control_value(conn, 2, '5')
    release_transfer_order(conn, ORDER_ID, {LINE_ID: 100.0})
    svc = to_service(conn)

    svc.apply_receipt(ORDER_ID, [{'line_id': LINE_ID, 'qty_received': 104.5}])
    assert _line(conn)['qty_received'] == pytest.approx(104.5)

    with pytest.raises(TransferOrderError) as exc:
        svc.apply_receipt(
            ORDER_ID, [{'line_id': LINE_ID, 'qty_received': 1}])
    assert exc.value.rule == 'TO_RECEIVE_EXCEEDED'
    assert _line(conn)['qty_received'] == pytest.approx(104.5)


# ===========================================================================
# 4. 调拨发货单
# ===========================================================================
def test_create_shipment_draft_with_trs_number():
    conn = seeded_db(line_qtys=(100.0,))
    release_transfer_order(conn, ORDER_ID)

    result = _shipment_svc(conn).create(
        ORDER_ID, '2026-11-02', [{'transfer_order_line_id': LINE_ID,
                                  'qty': 30}])

    assert result['status'] == 'draft'
    assert result['shipment_no'].startswith('TRS-202611-')
    assert result['line_count'] == 1
    header = MemDS(conn).query(
        'SELECT * FROM transfer_shipments WHERE id = ?', [result['id']])[0]
    assert header['status'] == 'draft'
    # 建单不动调拨行已发量
    assert _line(conn)['qty_shipped'] == pytest.approx(0.0)


def test_create_shipment_requires_released_order():
    conn = seeded_db(line_qtys=(100.0,))
    with pytest.raises(TransferShipmentError) as exc:
        _shipment_svc(conn).create(
            ORDER_ID, '2026-11-02', [{'transfer_order_line_id': LINE_ID,
                                      'qty': 10}])
    assert exc.value.rule == 'TRS_ORDER_NOT_RELEASED'


def test_create_shipment_rejects_foreign_line():
    conn = seeded_db(line_qtys=(100.0,))
    add_transfer_order(conn, oid=2, order_no='TRF-202611-000002')
    add_transfer_line(conn, lid=200, oid=2, line_no=10, qty=50.0)
    conn.commit()
    release_transfer_order(conn, ORDER_ID)

    with pytest.raises(TransferShipmentError) as exc:
        _shipment_svc(conn).create(
            ORDER_ID, '2026-11-02', [{'transfer_order_line_id': 200,
                                      'qty': 10}])
    assert exc.value.rule == 'TRS_LINE_NOT_FOUND'


def test_create_shipment_rejects_qty_over_remaining():
    conn = seeded_db(line_qtys=(100.0,))
    release_transfer_order(conn, ORDER_ID, {LINE_ID: 90.0})

    with pytest.raises(TransferShipmentError) as exc:
        _shipment_svc(conn).create(
            ORDER_ID, '2026-11-02', [{'transfer_order_line_id': LINE_ID,
                                      'qty': 20}])
    assert exc.value.rule == 'TRS_SHIP_QTY_EXCEEDED'


def test_post_accumulates_to_order_and_marks_posted():
    conn = seeded_db(line_qtys=(100.0,))
    release_transfer_order(conn, ORDER_ID)
    svc = _shipment_svc(conn)
    shipment = svc.create(
        ORDER_ID, '2026-11-02',
        [{'transfer_order_line_id': LINE_ID, 'qty': 30}],
        carrier_name='顺丰', waybill_no='SF001')

    result = svc.post(shipment['id'])

    assert result['status'] == 'posted'
    assert result['fulfillment_status'] == 'partially_shipped'
    assert _line(conn)['qty_shipped'] == pytest.approx(30.0)
    assert _header(conn)['actual_ship_date'] == '2026-11-02'
    row = MemDS(conn).query(
        'SELECT * FROM transfer_shipments WHERE id = ?', [shipment['id']])[0]
    assert row['status'] == 'posted'


def test_post_failure_keeps_shipment_draft():
    conn = seeded_db(line_qtys=(100.0,))
    release_transfer_order(conn, ORDER_ID)
    svc = _shipment_svc(conn)
    first = svc.create(
        ORDER_ID, '2026-11-02', [{'transfer_order_line_id': LINE_ID,
                                  'qty': 100}])
    second = svc.create(
        ORDER_ID, '2026-11-02', [{'transfer_order_line_id': LINE_ID,
                                  'qty': 100}])

    svc.post(first['id'])
    with pytest.raises(TransferOrderError) as exc:
        svc.post(second['id'])
    assert exc.value.rule == 'TO_SHIP_QTY_EXCEEDED'

    second_row = MemDS(conn).query(
        'SELECT status FROM transfer_shipments WHERE id = ?',
        [second['id']])[0]
    assert second_row['status'] == 'draft'
    assert _line(conn)['qty_shipped'] == pytest.approx(100.0)


def test_cancel_shipment_only_draft():
    conn = seeded_db(line_qtys=(100.0,))
    release_transfer_order(conn, ORDER_ID)
    svc = _shipment_svc(conn)
    posted = svc.create(
        ORDER_ID, '2026-11-02', [{'transfer_order_line_id': LINE_ID,
                                  'qty': 20}])
    svc.post(posted['id'])

    with pytest.raises(TransferShipmentError) as exc:
        svc.cancel(posted['id'])
    assert exc.value.rule == 'TRS_STATE_INVALID'

    draft = svc.create(
        ORDER_ID, '2026-11-03', [{'transfer_order_line_id': LINE_ID,
                                  'qty': 10}])
    result = svc.cancel(draft['id'])
    assert result['status'] == 'cancelled'
    assert _line(conn)['qty_shipped'] == pytest.approx(20.0)


# ===========================================================================
# 5. 需求分配转单（跨场景）
# ===========================================================================
def test_converted_allocations_write_back_same_transfer_line():
    conn = _allocation_db()
    add_allocation(conn, aid=200, demand_line_id=500, qty=60.0)
    add_allocation(conn, aid=201, demand_line_id=501, qty=40.0)
    conn.commit()
    framework = _FakeFramework()
    svc = from_allocation_service(conn, framework)

    svc.create_from_allocation([200, 201], from_org_id=2, to_org_id=3,
                               transfer_date='2026-11-01')

    rows = MemDS(conn).query(
        'SELECT id, target_bo, target_id, target_line_id, qty '
        'FROM demand_allocations WHERE id IN (200, 201) ORDER BY id')
    assert [row['target_bo'] for row in rows] == \
        ['transfer_order', 'transfer_order']
    assert rows[0]['target_id'] == rows[1]['target_id'] == 1
    assert rows[0]['target_line_id'] == rows[1]['target_line_id'] == 2
    assert float(rows[0]['qty']) + float(rows[1]['qty']) == pytest.approx(100.0)


def test_second_conversion_after_write_back_is_rejected():
    conn = _allocation_db()
    add_allocation(conn, aid=200, demand_line_id=500, qty=100.0)
    conn.commit()
    framework = _FakeFramework()
    svc = from_allocation_service(conn, framework)

    svc.create_from_allocation([200], from_org_id=2, to_org_id=3,
                               transfer_date='2026-11-01')
    calls_after_first = len(framework.calls)

    with pytest.raises(ConversionError) as exc:
        svc.create_from_allocation([200], from_org_id=2, to_org_id=3,
                                   transfer_date='2026-11-01')
    assert exc.value.code == 'ALLOCATION_ALREADY_CONVERTED'
    # 第二次转换在校验阶段拒绝，未再写任何对象
    assert len(framework.calls) == calls_after_first
    assert len(framework.payloads('transfer_order')) == 1


# ===========================================================================
# 6. 审批闸门
# ===========================================================================
def _approval_conn():
    conn = seeded_db(line_qtys=(100.0,), status='draft')
    add_approval_policy(conn)
    add_approval_step(conn)
    conn.commit()
    return conn


def test_submit_requires_approval_sets_pending_and_creates_task():
    conn = _approval_conn()
    result = to_service(conn).submit(ORDER_ID)

    assert result['approval_status'] == 'pending'
    assert result['required'] is True
    assert result['task_id']
    assert _header(conn)['approval_status'] == 'pending'
    tasks = _tasks(conn)
    assert len(tasks) == 1
    assert tasks[0]['type'] == 'approval'
    assert tasks[0]['status'] == 'waiting_approval'
    assert tasks[0]['doc_ref'] == str(ORDER_ID)


def test_submit_without_policy_sets_approved():
    conn = seeded_db(line_qtys=(100.0,))
    result = to_service(conn).submit(ORDER_ID)

    assert result['approval_status'] == 'approved'
    assert result['required'] is False
    assert result['task_id'] is None
    assert _tasks(conn) == []


def test_submit_is_rejected_when_pending_or_approved():
    conn = _approval_conn()
    svc = to_service(conn)
    svc.submit(ORDER_ID)
    with pytest.raises(TransferOrderError) as exc:
        svc.submit(ORDER_ID)
    assert exc.value.rule == 'TO_APPROVAL_PENDING'

    other = seeded_db(line_qtys=(100.0,))
    other_svc = to_service(other)
    other_svc.submit(ORDER_ID)
    with pytest.raises(TransferOrderError) as exc:
        other_svc.submit(ORDER_ID)
    assert exc.value.rule == 'TO_APPROVAL_ALREADY_APPROVED'


def test_withdraw_only_from_pending():
    conn = _approval_conn()
    svc = to_service(conn)
    svc.submit(ORDER_ID)

    result = svc.withdraw(ORDER_ID)
    assert result['approval_status'] == 'not_required'
    assert _header(conn)['approval_status'] == 'not_required'
    assert _tasks(conn)[0]['status'] == 'cancelled'

    with pytest.raises(TransferOrderError) as exc:
        svc.withdraw(ORDER_ID)
    assert exc.value.rule == 'TO_APPROVAL_NOT_PENDING'

    approved = seeded_db(line_qtys=(100.0,))
    to_service(approved).submit(ORDER_ID)
    with pytest.raises(TransferOrderError) as exc:
        to_service(approved).withdraw(ORDER_ID)
    assert exc.value.rule == 'TO_APPROVAL_NOT_PENDING'


def test_approve_and_reject_handlers_move_approval_status(monkeypatch):
    import meta.services.transfer_order_actions as actions

    approve_conn = _approval_conn()
    to_service(approve_conn).submit(ORDER_ID)
    monkeypatch.setattr(
        actions, 'TransferOrderService',
        lambda *args, **kwargs: TransferOrderService(MemDS(approve_conn)))

    result = actions.approve_handler({'transfer_order_id': ORDER_ID}, {})
    assert result['success'] is True
    assert _header(approve_conn)['approval_status'] == 'approved'
    assert _tasks(approve_conn)[0]['status'] == 'done'

    reject_conn = _approval_conn()
    to_service(reject_conn).submit(ORDER_ID)
    monkeypatch.setattr(
        actions, 'TransferOrderService',
        lambda *args, **kwargs: TransferOrderService(MemDS(reject_conn)))

    result = actions.reject_handler({'id': ORDER_ID}, {})
    assert result['success'] is True
    assert _header(reject_conn)['approval_status'] == 'rejected'
    assert _tasks(reject_conn)[0]['status'] == 'failed'

    result = actions.approve_handler({'id': ORDER_ID}, {})
    assert result['success'] is False
    assert result['code'] == 'TO_APPROVAL_NOT_PENDING'
    assert _header(reject_conn)['approval_status'] == 'rejected'


def test_validate_release_respects_approval_gate():
    pending = _approval_conn()
    to_service(pending).submit(ORDER_ID)
    with pytest.raises(TransferOrderError) as exc:
        to_guard(pending).validate_release(ORDER_ID)
    assert exc.value.rule == 'TO_APPROVAL_PENDING'

    rejected = _approval_conn()
    conn = rejected
    conn.execute(
        "UPDATE transfer_orders SET approval_status = 'rejected' WHERE id = ?",
        [ORDER_ID])
    conn.commit()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(rejected).validate_release(ORDER_ID)
    assert exc.value.rule == 'TO_APPROVAL_REJECTED'

    for approval in ('not_required', 'approved'):
        conn = _approval_conn()
        conn.execute(
            'UPDATE transfer_orders SET approval_status = ? WHERE id = ?',
            [approval, ORDER_ID])
        conn.commit()
        assert to_guard(conn).validate_release(ORDER_ID) is None


# ===========================================================================
# 7.5 库位组织归属（TBD-7 / v198）
# ===========================================================================
def _location_header(**extra):
    data = {
        'document_type_id': TO_STANDARD_TYPE_ID,
        'transfer_date': '2026-11-02',
        'from_org_id': 2,
        'to_org_id': 3,
        'from_location_id': None,
        'to_location_id': None,
    }
    data.update(extra)
    return data


def test_location_org_allows_unassigned_locations():
    """库位 6 / 7 的 org_id 为空（共享场地）⇒ 归属校验放行。"""
    conn = seeded_db()
    header = to_guard(conn).validate_create(
        _location_header(from_location_id=6, to_location_id=7))
    assert (header['from_location_id'], header['to_location_id']) == (6, 7)


def test_location_org_accepts_matching_orgs():
    """库位 9 属组织 2 / 库位 10 属组织 3 ⇒ 与 from_org / to_org 一致。"""
    conn = seeded_db()
    header = to_guard(conn).validate_create(
        _location_header(from_location_id=9, to_location_id=10))
    assert header['from_org_id'] == 2 and header['to_org_id'] == 3


@pytest.mark.parametrize('field', ['from_location_id', 'to_location_id'])
def test_location_org_rejects_mismatch(field):
    """库位 11 属组织 4 ⇒ 与 from_org 2 / to_org 3 均不一致。"""
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_create(_location_header(**{field: 11}))
    assert exc.value.rule == 'TO_LOCATION_ORG_MISMATCH'
    assert exc.value.field_name == field


# ===========================================================================
# 7. 采购法人一致性（v195）
# ===========================================================================
def _po_write_data(**extra):
    data = {
        'document_type_id': PO_STANDARD_TYPE_ID,
        'order_no': 'PO-0001',
        'org_id': 1,
        'purchase_org_id': 2,
        'supplier_party_id': 500,
        'currency_id': 1,
    }
    data.update(extra)
    return data


def test_po_create_writes_legal_entity_snapshot():
    conn = _po_db()
    data = _po_write_data()

    PurchaseOrderGuardService(MemDS(conn)).validate_order_write(
        data, None, is_create=True)

    assert data['purchase_legal_entity_id'] == 1


def test_po_update_recomputes_snapshot_when_org_changed():
    conn = _po_db()
    guard = PurchaseOrderGuardService(MemDS(conn))
    old = {'status': 'draft', 'purchase_org_id': 2,
           'purchase_legal_entity_id': 1}
    data = {'purchase_org_id': 10}

    guard.validate_order_write(data, old, is_create=False)

    assert data['purchase_legal_entity_id'] == 10


def test_po_update_keeps_snapshot_when_org_unchanged():
    conn = _po_db()
    guard = PurchaseOrderGuardService(MemDS(conn))
    old = {'status': 'draft', 'purchase_org_id': 2,
           'purchase_legal_entity_id': 1}
    data = {'purchase_org_id': 2, 'remark': '补录备注'}

    guard.validate_order_write(data, old, is_create=False)

    assert 'purchase_legal_entity_id' not in data


def test_receipt_rejects_org_mismatching_po_legal_entity():
    conn = _po_db()
    _add_po(conn, org_id=1, purchase_legal_entity_id=10)

    with pytest.raises(ReceiptError) as exc:
        receipt_guard_svc(conn).prepare_create({
            'source_doc_type': 'purchase_order',
            'source_doc_id': 1,
            'document_type_id': 1,
            'receipt_date': '2026-11-02',
        })
    assert exc.value.rule == 'RC_LEGAL_ENTITY_MISMATCH'


def test_receipt_allows_null_legal_entity_snapshot():
    conn = _po_db()
    _add_po(conn, org_id=1, purchase_legal_entity_id=None)

    header = receipt_guard_svc(conn).prepare_create({
        'source_doc_type': 'purchase_order',
        'source_doc_id': 1,
        'document_type_id': 1,
        'receipt_date': '2026-11-02',
    })

    assert header['org_id'] == 1
    assert header['receipt_no'].startswith('RCV-202611-')
