# -*- coding: utf-8 -*-
"""INV-2 S2：预留幂等 / 状态机 / 硬钉 / ATP / 销售订单同步。"""

import os

import pytest

os.environ.setdefault('ALLOW_RAW_SQL', '1')

from meta.services.inventory_guard_service import InventoryError
from meta.services.inventory_posting_service import InventoryPostingService
from meta.services.inventory_reservation_service import (
    InventoryReservationService,
)
from meta.tests.inventory_test_doubles import (
    BATCH_ID,
    ITEM_ID,
    LOCATION_ID,
    ORG_ID,
    MemDS,
    build_db,
    seed,
)

UOM_ID = 3
SO_LINE_ID = 501
PROJECT_ID = 301
TASK_ID = 201


def _conn(with_balance=10):
    conn = seed(build_db())
    if with_balance:
        posting = InventoryPostingService(MemDS(conn))
        posting.post([{
            'transaction_type': 'RCV_PO',
            'transaction_date': '2026-11-04',
            'org_id': ORG_ID,
            'location_id': LOCATION_ID,
            'item_id': ITEM_ID,
            'uom_id': UOM_ID,
            'qty': with_balance,
            'batch_id': BATCH_ID,
            'stock_status': 'unrestricted',
            'source_line_id': 1,
        }], {
            'source_doc_type': 'test',
            'source_doc_id': 1,
            'source_event_key': 'seed-balance',
        })
    return conn


def _payload(key, qty, peg_type='soft', demand_id=SO_LINE_ID, **extra):
    payload = {
        'reservation_key': key,
        'org_id': ORG_ID,
        'item_id': ITEM_ID,
        'uom_id': UOM_ID,
        'location_id': LOCATION_ID,
        'batch_id': BATCH_ID,
        'qty_reserved': qty,
        'peg_type': peg_type,
        'demand_object_type': 'sales_order_line',
        'demand_object_id': demand_id,
        'demand_line_id': demand_id,
        'source_doc_type': 'sales_order',
        'source_doc_id': 1,
        'source_line_id': demand_id,
    }
    payload.update(extra)
    return payload


def _service(conn):
    return InventoryReservationService(MemDS(conn))


def test_create_is_idempotent_by_key():
    conn = _conn()
    service = _service(conn)
    first = service.create_reservation(_payload('RSV-A', 4))
    assert first['created'] is True
    assert first['reservation']['reservation_no'].startswith('RSV-')
    assert first['reservation']['status'] == 'open'

    second = service.create_reservation(_payload('RSV-A', 4))
    assert second['created'] is False
    assert second['reservation']['id'] == first['reservation']['id']
    assert conn.execute(
        'SELECT COUNT(*) FROM inventory_reservations').fetchone()[0] == 1


def test_available_on_hand_after_create_and_release():
    conn = _conn(10)
    service = _service(conn)
    query = {'org_id': ORG_ID, 'item_id': ITEM_ID}
    assert service.available_on_hand(query)['available_on_hand'] == pytest.approx(10)

    created = service.create_reservation(_payload('RSV-B', 4))
    atp = service.available_on_hand(query)
    assert atp['on_hand'] == pytest.approx(10)
    assert atp['reserved'] == pytest.approx(4)
    assert atp['available_on_hand'] == pytest.approx(6)

    released = service.release_reservation(created['reservation']['id'],
                                           reason='测试释放')
    assert released['status'] == 'cancelled'
    assert service.available_on_hand(query)['available_on_hand'] == pytest.approx(10)

    with pytest.raises(InventoryError) as exc:
        service.release_reservation(created['reservation']['id'])
    assert exc.value.code == 'INV_RESERVATION_STATE_INVALID'


def test_fulfill_partial_then_full_and_over_fulfill():
    conn = _conn(10)
    service = _service(conn)
    created = service.create_reservation(_payload('RSV-C', 5))
    rid = created['reservation']['id']

    partial = service.fulfill_reservation(rid, 2)
    assert partial['status'] == 'partially_fulfilled'
    assert float(partial['qty_fulfilled']) == pytest.approx(2)
    atp = service.available_on_hand({'org_id': ORG_ID, 'item_id': ITEM_ID})
    assert atp['reserved'] == pytest.approx(3)

    done = service.fulfill_reservation(rid, 3)
    assert done['status'] == 'fulfilled'
    assert service.available_on_hand(
        {'org_id': ORG_ID, 'item_id': ITEM_ID}
    )['available_on_hand'] == pytest.approx(10)

    with pytest.raises(InventoryError) as exc:
        service.fulfill_reservation(rid, 1)
    assert exc.value.code == 'INV_RESERVATION_STATE_INVALID'


def test_over_fulfill_single_call_raises_qty_exceeded():
    conn = _conn(10)
    service = _service(conn)
    rid = service.create_reservation(_payload('RSV-D', 3))['reservation']['id']
    with pytest.raises(InventoryError) as exc:
        service.fulfill_reservation(rid, 4)
    assert exc.value.code == 'INV_RESERVATION_QTY_EXCEEDED'


def test_hard_peg_conflict_and_soft_overbooking():
    conn = _conn(10)
    service = _service(conn)
    service.create_reservation(_payload('RSV-H1', 8, peg_type='hard',
                                       demand_id=1))
    with pytest.raises(InventoryError) as exc:
        service.create_reservation(_payload('RSV-H2', 8, peg_type='hard',
                                           demand_id=2))
    assert exc.value.code == 'INV_HARD_PEG_CONFLICT'

    soft = service.create_reservation(_payload('RSV-S1', 12, demand_id=3))
    assert soft['created'] is True


def test_expire_reservations():
    conn = _conn()
    service = _service(conn)
    created = service.create_reservation(
        _payload('RSV-E', 2, valid_to='2026-01-01 00:00:00'))
    assert service.expire_reservations(now='2026-06-01 00:00:00') == 1
    row = service._load(created['reservation']['id'])
    assert row['status'] == 'expired'
    assert service.expire_reservations(now='2026-06-01 00:00:00') == 0


def test_available_on_hand_include_inbound_unsupported():
    conn = _conn(10)
    service = _service(conn)
    with pytest.raises(InventoryError) as exc:
        service.available_on_hand({'org_id': ORG_ID, 'item_id': ITEM_ID},
                                  include_inbound=True)
    assert exc.value.code == 'ATP_INBOUND_UNSUPPORTED'


def test_manual_reservation_exceeding_demand_rejected():
    conn = _conn(10)
    _create_so_tables(conn)
    service = _service(conn)
    service.create_reservation(_payload('RSV-D1', 8))
    with pytest.raises(InventoryError) as exc:
        service.create_reservation(_payload('RSV-D2', 4))
    assert exc.value.code == 'INV_RESERVATION_EXCEEDS_DEMAND'


def test_unknown_demand_qty_warns_and_allows(caplog):
    conn = _conn()
    service = _service(conn)
    with caplog.at_level('WARNING'):
        created = service.create_reservation(_payload('RSV-U1', 12,
                                                      demand_id=999))
    assert created['created'] is True
    assert 'INV_DEMAND_QTY_UNKNOWN' in caplog.text


def test_close_reservation_keeps_fulfilled_and_releases_rest():
    conn = _conn(10)
    service = _service(conn)
    rid = service.create_reservation(_payload('RSV-CL', 5))['reservation']['id']
    service.fulfill_reservation(rid, 2)

    closed = service.close_reservation(rid, reason='终止履行')
    assert closed['status'] == 'closed'
    assert float(closed['qty_fulfilled']) == pytest.approx(2)
    atp = service.available_on_hand({'org_id': ORG_ID, 'item_id': ITEM_ID})
    assert atp['reserved'] == pytest.approx(0)
    assert atp['available_on_hand'] == pytest.approx(10)

    with pytest.raises(InventoryError) as exc:
        service.fulfill_reservation(rid, 1)
    assert exc.value.code == 'INV_RESERVATION_CLOSED'
    with pytest.raises(InventoryError) as exc:
        service.release_reservation(rid)
    assert exc.value.code == 'INV_RESERVATION_CLOSED'


def _create_so_tables(conn, so_flag=0):
    conn.execute('CREATE TABLE IF NOT EXISTS sales_orders '
                 '(id INTEGER PRIMARY KEY, status TEXT, org_id INTEGER, '
                 'sales_org_id INTEGER)')
    conn.execute('CREATE TABLE IF NOT EXISTS sales_order_lines '
                 '(id INTEGER PRIMARY KEY, order_id INTEGER, item_id INTEGER, '
                 'uom_id INTEGER, qty REAL, status TEXT, '
                 'plant_location_id INTEGER, project_id INTEGER, '
                 'project_task_id INTEGER)')
    conn.execute("INSERT INTO sales_orders (id, status, org_id) "
                 "VALUES (1, 'open', ?)", [ORG_ID])
    conn.execute("INSERT INTO sales_order_lines (id, order_id, item_id, "
                 "uom_id, qty, status, plant_location_id, project_id) "
                 "VALUES (?, 1, ?, ?, 10, 'open', ?, NULL)",
                 [SO_LINE_ID, ITEM_ID, UOM_ID, LOCATION_ID])
    conn.execute('UPDATE items SET so_segment_enabled = ?, '
                 'hard_peg_default = 0 WHERE id = ?', [so_flag, ITEM_ID])
    conn.commit()


# ----------------------------------------------------------------------
# 工单组件级 soft 预留
# ----------------------------------------------------------------------
def _create_work_order_tables(conn, status='New', project_id=0,
                              task_id=0, order_id=1):
    conn.execute('CREATE TABLE IF NOT EXISTS projects '
                 '(id INTEGER PRIMARY KEY, org_id INTEGER)')
    conn.execute('CREATE TABLE IF NOT EXISTS project_tasks '
                 '(id INTEGER PRIMARY KEY, project_id INTEGER)')
    conn.execute('CREATE TABLE IF NOT EXISTS work_orders '
                 '(id INTEGER PRIMARY KEY, status TEXT, project_id INTEGER, '
                 'project_task_id INTEGER, order_id INTEGER)')
    conn.execute('CREATE TABLE IF NOT EXISTS work_order_components '
                 '(id INTEGER PRIMARY KEY AUTOINCREMENT, work_order_id INTEGER, '
                 'structure_line_id INTEGER, component_item_id INTEGER, '
                 'qty_required REAL, project_task_id INTEGER DEFAULT 0)')
    try:
        conn.execute('ALTER TABLE items ADD COLUMN base_uom INTEGER DEFAULT 0')
    except Exception:
        pass
    conn.execute('UPDATE items SET base_uom = ? WHERE id = ?',
                 [UOM_ID, ITEM_ID])
    if project_id:
        conn.execute('INSERT INTO projects (id, org_id) VALUES (?, ?)',
                     [project_id, ORG_ID])
    if project_id and task_id:
        conn.execute('INSERT INTO project_tasks (id, project_id) '
                     'VALUES (?, ?)', [task_id, project_id])
    if order_id:
        conn.execute('CREATE TABLE IF NOT EXISTS sales_orders '
                     '(id INTEGER PRIMARY KEY, status TEXT, org_id INTEGER)')
        conn.execute("INSERT OR IGNORE INTO sales_orders "
                     "(id, status, org_id) VALUES (?, 'open', ?)",
                     [order_id, ORG_ID])
    conn.execute('INSERT INTO work_orders (id, status, project_id, '
                 'project_task_id, order_id) VALUES (1, ?, ?, ?, ?)',
                 [status, project_id, task_id, order_id])
    conn.commit()


def _add_component(conn, structure_line_id=1, item_id=ITEM_ID, qty=4.0,
                   task_id=0):
    cursor = conn.execute(
        'INSERT INTO work_order_components (work_order_id, '
        'structure_line_id, component_item_id, qty_required, project_task_id) '
        'VALUES (1, ?, ?, ?, ?)',
        [structure_line_id, item_id, qty, task_id])
    conn.commit()
    return cursor.lastrowid


def test_work_order_component_creates_soft_reservation():
    conn = _conn(10)
    _create_work_order_tables(conn)
    component_id = _add_component(conn, qty=4)
    service = _service(conn)
    result = service.sync_work_order_components(1)
    assert result['created'] == 1

    row = conn.execute(
        'SELECT demand_object_id, demand_object_type, peg_type, '
        'stock_segment_type FROM inventory_reservations').fetchone()
    assert row[1] == 'work_order_component'
    assert int(row[0]) == component_id
    assert row[2] == 'soft'
    assert row[3] == 'owned'

    atp = service.atp({'org_id': ORG_ID, 'item_id': ITEM_ID})
    assert atp['reserved'] == pytest.approx(4)
    assert atp['available_on_hand'] == pytest.approx(6)


def test_work_order_component_sync_idempotent_and_updates_qty():
    conn = _conn(10)
    _create_work_order_tables(conn)
    _add_component(conn, qty=4)
    service = _service(conn)
    service.sync_work_order_components(1)
    again = service.sync_work_order_components(1)
    assert again['created'] == 0
    assert again['updated'] == 0

    conn.execute('UPDATE work_order_components SET qty_required = 6')
    conn.commit()
    changed = service.sync_work_order_components(1)
    assert changed['updated'] == 1
    atp = service.atp({'org_id': ORG_ID, 'item_id': ITEM_ID})
    assert atp['reserved'] == pytest.approx(6)


def test_cancelled_work_order_releases_component_reservations():
    conn = _conn(10)
    _create_work_order_tables(conn)
    _add_component(conn, qty=4)
    service = _service(conn)
    service.sync_work_order_components(1)

    conn.execute("UPDATE work_orders SET status = 'Cancelled'")
    conn.commit()
    released = service.sync_work_order_components(1)
    assert released['released'] == 1
    assert service.atp({'org_id': ORG_ID,
                        'item_id': ITEM_ID})['reserved'] == pytest.approx(0)


def test_rebuilt_components_release_stale_reservation():
    conn = _conn(10)
    _create_work_order_tables(conn)
    _add_component(conn, structure_line_id=1, qty=4)
    service = _service(conn)
    service.sync_work_order_components(1)

    conn.execute('DELETE FROM work_order_components WHERE work_order_id = 1')
    _add_component(conn, structure_line_id=2, qty=5)
    result = service.sync_work_order_components(1)
    assert result['created'] == 1
    assert result['released'] == 1

    active = conn.execute(
        'SELECT reservation_key FROM inventory_reservations '
        'WHERE status IN (?, ?)', ['open', 'partially_fulfilled']).fetchall()
    assert [row[0] for row in active] == ['WO-COMP-1-2']


def test_work_order_component_uses_project_task_segment():
    conn = _conn(10)
    _create_work_order_tables(conn, project_id=PROJECT_ID, task_id=TASK_ID,
                              order_id=0)
    _add_component(conn, qty=3)
    result = _service(conn).sync_work_order_components(1)
    assert result['created'] == 1

    row = conn.execute('SELECT stock_segment_type, project_task_id, '
                       'project_id FROM inventory_reservations').fetchone()
    assert row[0] == 'project_task'
    assert int(row[2]) == PROJECT_ID
    assert int(row[1]) == TASK_ID


# ----------------------------------------------------------------------
# 关单前置校验
# ----------------------------------------------------------------------
def test_assert_source_closable_rejects_outstanding_commitment():
    conn = _conn(10)
    _create_work_order_tables(conn)
    _add_component(conn, qty=4)
    service = _service(conn)
    service.sync_work_order_components(1)

    with pytest.raises(InventoryError) as exc:
        service.assert_source_closable('work_order', 1)
    assert exc.value.code == 'INV_RESERVATION_ACTIVE_ON_CLOSE'
    assert exc.value.details['outstanding'] == pytest.approx(4)
    assert exc.value.details['count'] == 1

    conn.execute('UPDATE inventory_reservations SET qty_fulfilled = 4, '
                 "status = 'fulfilled'")
    conn.commit()
    service.assert_source_closable('work_order', 1)


def test_assert_source_closable_ignores_expired_and_cancelled():
    conn = _conn(10)
    _create_work_order_tables(conn)
    _add_component(conn, qty=4)
    service = _service(conn)
    service.sync_work_order_components(1)

    conn.execute('UPDATE inventory_reservations '
                 "SET valid_to = '2026-01-01 00:00:00'")
    conn.commit()
    service.assert_source_closable('work_order', 1)

    conn.execute("UPDATE inventory_reservations SET valid_to = NULL, "
                 "status = 'cancelled'")
    conn.commit()
    service.assert_source_closable('work_order', 1)


class _WorkOrderCtx:
    def __init__(self, conn, params, old_data, object_id=1):
        self.meta_object = type('Meta', (), {'id': 'work_order'})()
        self.action = 'crud_update'
        self.params = params
        self.old_data = old_data
        self.object_id = object_id
        self.data_source = MemDS(conn)


def test_interceptor_blocks_close_with_outstanding_component():
    conn = _conn(10)
    _create_work_order_tables(conn)
    _add_component(conn, qty=4)
    _service(conn).sync_work_order_components(1)

    from meta.core.exceptions import ValidationFailedError
    from meta.core.interceptors.project_task_guard_interceptor import (
        ProjectTaskGuardInterceptor,
    )
    context = _WorkOrderCtx(
        conn, {'status': 'Closed'},
        {'id': 1, 'status': 'Resolved', 'project_id': 0,
         'project_task_id': 0})
    with pytest.raises(ValidationFailedError) as exc:
        ProjectTaskGuardInterceptor().before_action(context)
    assert exc.value.details[0]['rule'] == \
        'INV_RESERVATION_ACTIVE_ON_CLOSE'


def test_interceptor_allows_close_after_release():
    conn = _conn(10)
    _create_work_order_tables(conn)
    _add_component(conn, qty=4)
    service = _service(conn)
    service.sync_work_order_components(1)
    reservation_id = conn.execute(
        'SELECT id FROM inventory_reservations').fetchone()[0]
    service.release_reservation(reservation_id, reason='关单前释放')

    from meta.core.interceptors.project_task_guard_interceptor import (
        ProjectTaskGuardInterceptor,
    )
    context = _WorkOrderCtx(
        conn, {'status': 'Closed'},
        {'id': 1, 'status': 'Resolved', 'project_id': 0,
         'project_task_id': 0})
    ProjectTaskGuardInterceptor().before_action(context)


def test_sync_sales_order_line_create_and_resize():
    conn = _conn(10)
    _create_so_tables(conn)
    service = _service(conn)
    result = service.sync_sales_order_line(SO_LINE_ID)
    assert result['created'] is True
    reservation = result['reservation']
    assert reservation['stock_segment_type'] == 'owned'
    assert float(reservation['qty_reserved']) == pytest.approx(10)

    conn.execute('UPDATE sales_order_lines SET qty = 12 WHERE id = ?',
                 [SO_LINE_ID])
    conn.commit()
    synced = service.sync_sales_order_line(SO_LINE_ID)
    assert synced['updated'] is True
    assert float(synced['reservation']['qty_reserved']) == pytest.approx(12)

    conn.execute("UPDATE sales_order_lines SET status = 'cancelled' "
                 'WHERE id = ?', [SO_LINE_ID])
    conn.commit()
    released = service.sync_sales_order_line(SO_LINE_ID)
    assert released['released'] == 1
    row = service._load(reservation['id'])
    assert row['status'] == 'cancelled'


def test_sync_sales_order_line_with_segment_flag():
    conn = _conn(10)
    _create_so_tables(conn, so_flag=1)
    service = _service(conn)
    result = service.sync_sales_order_line(SO_LINE_ID)
    assert result['created'] is True
    assert result['reservation']['stock_segment_type'] == 'sales_order_line'
    assert result['reservation']['sales_order_line_id'] == SO_LINE_ID


def test_sync_sales_order_line_with_project_task_segment():
    """G15 P2：任务行落 project_task 段；取消后释放预留。"""
    conn = _conn(10)
    _create_so_tables(conn)
    conn.execute('UPDATE sales_order_lines SET project_id = ?, '
                 'project_task_id = ? WHERE id = ?',
                 [PROJECT_ID, TASK_ID, SO_LINE_ID])
    conn.commit()
    service = _service(conn)

    result = service.sync_sales_order_line(SO_LINE_ID)
    assert result['created'] is True
    reservation = result['reservation']
    assert reservation['stock_segment_type'] == 'project_task'
    assert reservation['project_id'] == PROJECT_ID
    assert reservation['project_task_id'] == TASK_ID
    assert reservation['sales_order_line_id'] == 0

    conn.execute("UPDATE sales_order_lines SET status = 'cancelled' "
                 'WHERE id = ?', [SO_LINE_ID])
    conn.commit()
    released = service.sync_sales_order_line(SO_LINE_ID)
    assert released['released'] == 1
    row = service._load(reservation['id'])
    assert row['status'] == 'cancelled'
