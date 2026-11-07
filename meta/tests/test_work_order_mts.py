# -*- coding: utf-8 -*-
"""work_order MTS（按库存生产）测试 —— T9.3

依据: docs/specs/bo-metadata-gap-2026-11-06/tasks.md T9.3

覆盖:
  · manual 来源：无上游单据，item_id + planned_qty 必填，组件展开同口径；
  · 通用 BO CRUD 建单前置校验（validate_production_create）与服务建单一致；
  · 来源路径（计划行 / 订单行 / 项目任务）不受 MTS 变更影响。
"""

import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.project_task_guard_interceptor import (
    ProjectTaskGuardInterceptor,
)
from meta.services.work_order_service import (
    WorkOrderError,
    WorkOrderService,
)
from meta.tests.test_work_order_production import (
    _MemDS,
    _add_line,
    _add_structure,
    _count,
    _row,
    _db as _base_db,
)

#: v231 新增列（测试内联，模拟迁移后的真实表结构）
_NEW_COLUMNS = (('item_id', 'INTEGER'), ('planned_qty', 'REAL'))


def _db():
    conn = _base_db()
    for name, definition in _NEW_COLUMNS:
        conn.execute(
            'ALTER TABLE work_orders ADD COLUMN %s %s' % (name, definition))
    return conn


def _svc(conn):
    return WorkOrderService(_MemDS(conn))


def _manual(conn, **over):
    payload = {'order_type': 'production', 'source_demand_type': 'manual',
               'item_id': 500, 'planned_qty': 5}
    payload.update(over)
    return _svc(conn).create_work_order(payload)


def _ctx(conn, **params):
    from types import SimpleNamespace

    return SimpleNamespace(
        action='crud_create', params=dict(params), old_data=None, extra={},
        data_source=_MemDS(conn),
        meta_object=SimpleNamespace(id='work_order'), object_id=None,
        result=None)


# --------------------------------------------------------------- 服务建单


def test_manual_creates_with_item_and_planned_qty():
    conn = _db()
    _add_structure(conn, sid=1, item_id=500)
    _add_line(conn, 11, 1, 501, qty_per=2, line_no=10)

    result = _manual(conn)

    assert result['order_type'] == 'production'
    assert result['source_demand_type'] == 'manual'
    assert result['source_demand_id'] is None
    assert result['order_id'] is None
    assert result['order_line_id'] is None
    assert result['item_id'] == 500
    assert result['planned_qty'] == 5
    assert result['component_expansion']['code'] == 'expanded'
    assert result['component_expansion']['count'] == 1

    row = _row(
        conn,
        'SELECT order_id, order_line_id, source_demand_id, item_id, '
        'planned_qty FROM work_orders WHERE id = ?', [result['id']])[0]
    assert row == (None, None, None, 500, 5)

    # P-3：无 SLA 副作用；只写一条 change_event
    assert _count(conn, 'sla_milestones') == 0
    assert _count(conn, 'service_events') == 0
    assert _count(conn, 'change_events') == 1


def test_manual_requires_item_id():
    conn = _db()
    with pytest.raises(WorkOrderError) as err:
        _manual(conn, item_id=None)
    assert err.value.rule == 'ST_ITEM_REQUIRED'
    assert err.value.field_name == 'item_id'


def test_manual_requires_positive_qty():
    conn = _db()
    with pytest.raises(WorkOrderError) as err:
        _manual(conn, planned_qty=None)
    assert err.value.rule == 'ST_QTY_REQUIRED'

    for value in (0, -1, 'abc'):
        with pytest.raises(WorkOrderError) as err:
            _manual(conn, planned_qty=value)
        assert err.value.rule == 'ST_QTY_INVALID'


def test_manual_accepts_legacy_qty_key():
    conn = _db()
    result = _manual(conn, planned_qty=None, qty=7)
    assert result['planned_qty'] == 7


def test_manual_rejects_upstream_references():
    conn = _db()
    for field, value in (('source_demand_id', 100), ('order_id', 10),
                         ('order_line_id', 100), ('schedule_id', 1)):
        with pytest.raises(WorkOrderError) as err:
            _manual(conn, **{field: value})
        assert err.value.rule == 'ST_SOURCE_DEMAND_INVALID'
        assert err.value.field_name == field


def test_manual_without_structure_still_creates():
    conn = _db()
    result = _manual(conn)
    assert result['component_expansion']['code'] == 'no_structure'
    assert result['component_expansion']['count'] == 0
    assert _count(conn, 'work_orders') == 1


# --------------------------------------------------------------- CRUD 前置校验


def test_validate_production_create_normalizes_manual():
    conn = _db()
    normalized = _svc(conn).validate_production_create({
        'order_type': 'production', 'source_demand_type': 'manual',
        'item_id': 500, 'planned_qty': '3'})

    assert normalized['demand_type'] == 'manual'
    assert normalized['demand_id'] is None
    assert normalized['order_id'] is None
    assert normalized['order_line_id'] is None
    assert normalized['item_id'] == 500
    assert normalized['planned_qty'] == 3.0
    assert _count(conn, 'work_orders') == 0  # 只校验，不落库


def test_validate_production_create_backfills_source_path():
    conn = _db()
    normalized = _svc(conn).validate_production_create({
        'order_type': 'production',
        'source_demand_type': 'sales_order_line',
        'source_demand_id': 100})

    assert normalized['demand_type'] == 'sales_order_line'
    assert normalized['order_id'] == 10
    assert normalized['order_line_id'] == 100


def test_source_path_still_requires_demand_id():
    conn = _db()
    with pytest.raises(WorkOrderError) as err:
        _svc(conn).create_work_order({
            'order_type': 'production',
            'source_demand_type': 'sales_order_line'})
    assert err.value.rule == 'ST_SOURCE_DEMAND_REQUIRED'
    assert err.value.field_name == 'source_demand_id'


def test_crud_create_manual_backfills_normalized_fields():
    conn = _db()
    ctx = _ctx(conn, order_type='production', source_demand_type='manual',
               item_id=500, planned_qty=5)

    ProjectTaskGuardInterceptor().before_action(ctx)

    assert ctx.params['order_id'] is None
    assert ctx.params['order_line_id'] is None
    assert ctx.params['planned_qty'] == 5.0
    assert ctx.extra['work_order_production']['demand_type'] == 'manual'


def test_crud_create_manual_missing_item_raises():
    conn = _db()
    ctx = _ctx(conn, order_type='production', source_demand_type='manual',
               planned_qty=5)

    with pytest.raises(ValidationFailedError) as err:
        ProjectTaskGuardInterceptor().before_action(ctx)
    assert err.value.details[0]['rule'] == 'ST_ITEM_REQUIRED'


def test_crud_create_after_action_expands_components():
    conn = _db()
    _add_structure(conn, sid=1, item_id=500)
    _add_line(conn, 11, 1, 501, qty_per=2, line_no=10)
    ctx = _ctx(conn, order_type='production', source_demand_type='manual',
               item_id=500, planned_qty=5)
    ProjectTaskGuardInterceptor().before_action(ctx)

    from types import SimpleNamespace
    ctx.object_id = 1
    ctx.result = SimpleNamespace(success=True, data={'id': 1})

    ProjectTaskGuardInterceptor().after_action(ctx)

    qty = conn.execute(
        'SELECT qty_required FROM work_order_components '
        'WHERE work_order_id = 1').fetchone()[0]
    assert qty == pytest.approx(10.0)  # 2 × 5