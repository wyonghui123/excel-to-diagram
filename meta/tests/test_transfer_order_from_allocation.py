# -*- coding: utf-8 -*-
"""需求分配 → 调拨单转换（TBD-4）。

覆盖：整笔 / 按物料单位聚合、分配回写、行类型解析（transfer_order 域）、
默认头类型 + 事务外取号、已 peg / 已转 / 停用 / 超量 / 非法需求域等失败码。
不依赖真实 DB / BO 框架：`data_source` 用内存 SQLite 替身，`framework` 用假实现。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

from contextlib import contextmanager

import pytest

from meta.services.transfer_order_from_allocation import (
    ConversionError,
    TransferOrderFromAllocationService,
    create_from_allocation_handler,
)
from meta.tests.transfer_order_test_doubles import (
    TO_ASSET_TYPE_ID,
    TO_GOODS_TYPE_ID,
    TO_STANDARD_TYPE_ID,
    add_allocation,
    add_master_data,
    add_org_tree,
    add_requisition_line,
    add_types,
    build_db,
    from_allocation_service,
)

pytestmark = pytest.mark.unit


class _Result:
    def __init__(self, success=True, data=None, message=''):
        self.success = success
        self.data = data
        self.message = message


class _FakeFramework:
    def __init__(self):
        self.calls = []
        self.fail_on = None
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
        if self.fail_on and object_type == self.fail_on[0]:
            return _Result(success=False, message=self.fail_on[1])
        new_id = len(self.calls) + 1
        record = dict(data)
        record['id'] = new_id
        self.calls.append({'object_type': object_type, 'action': action,
                           'data': record})
        return _Result(success=True, data=record)

    def payloads(self, object_type):
        return [c['data'] for c in self.calls if c['object_type'] == object_type]


def _db():
    conn = build_db()
    add_types(conn)
    add_org_tree(conn)
    add_master_data(conn)
    add_requisition_line(conn, lid=500, item_id=900, qty=100.0)
    add_requisition_line(conn, lid=501, item_id=900, qty=40.0,
                         line_no='20')
    conn.commit()
    return conn


def _service(conn, framework=None):
    fw = framework or _FakeFramework()
    return from_allocation_service(conn, fw), fw


def _convert(svc, ids=(200,), **overrides):
    kwargs = dict(from_org_id=2, to_org_id=3,
                  transfer_date='2026-11-01')
    kwargs.update(overrides)
    return svc.create_from_allocation(list(ids), **kwargs)


def _allocation(conn, **overrides):
    params = dict(aid=200, demand_line_id=500, qty=100.0)
    params.update(overrides)
    add_allocation(conn, **params)
    conn.commit()


# ---------------------------------------------------------------------------
# 成功路径
# ---------------------------------------------------------------------------
def test_convert_single_allocation_creates_draft_header_and_line():
    conn = _db()
    _allocation(conn)
    svc, fw = _service(conn)

    result = _convert(svc, to_location_id=7, remark='需求转调拨')

    header = fw.payloads('transfer_order')[0]
    assert header['status'] == 'draft'
    assert header['document_type_id'] == TO_STANDARD_TYPE_ID
    assert header['legal_entity_id'] == 1
    assert header['transfer_order_no'].startswith('TRF-202611-')
    assert header['to_location_id'] == 7 and header['remark'] == '需求转调拨'

    line = fw.payloads('transfer_order_line')[0]
    assert line['line_no'] == 10
    assert line['item_id'] == 900 and line['uom_id'] == 3
    assert line['qty'] == 100.0 and line['status'] == 'open'
    assert line['line_type_id'] == TO_GOODS_TYPE_ID

    assert result['transfer_order_id'] == 1
    assert result['lines'][0]['allocation_ids'] == [200]
    assert fw.committed and not fw.rolled_back


def test_allocations_are_aggregated_by_item_and_uom():
    conn = _db()
    _allocation(conn, aid=200, demand_line_id=500, qty=60.0)
    _allocation(conn, aid=201, demand_line_id=501, qty=40.0)
    svc, fw = _service(conn)

    result = _convert(svc, ids=(200, 201))

    lines = fw.payloads('transfer_order_line')
    assert len(lines) == 1
    assert lines[0]['qty'] == 100.0
    assert result['lines'][0]['allocation_ids'] == [200, 201]


def test_write_back_points_allocation_to_transfer_order_line():
    conn = _db()
    _allocation(conn)
    svc, _ = _service(conn)

    _convert(svc)

    row = conn.execute(
        'SELECT target_bo, target_id, target_line_id, qty, status '
        'FROM demand_allocations WHERE id = 200').fetchone()
    assert row[0] == 'transfer_order'
    assert row[1] == 1          # 调拨单头 id
    assert row[2] == 2          # 调拨行 id（头 1 → 行 2）
    assert row[3] == 100.0
    assert row[4] == 'active'   # 真实枚举只有 active / reversed


def test_line_type_resolved_in_transfer_order_scope():
    conn = _db()
    conn.execute(
        'INSERT INTO line_type_assignments (document_type_id, item_group_id, '
        "specificity_rank, line_type_id, status) VALUES (?, 7, 100, ?, 'active')",
        [TO_STANDARD_TYPE_ID, TO_ASSET_TYPE_ID])
    conn.commit()
    _allocation(conn)
    svc, fw = _service(conn)

    _convert(svc)

    assert fw.payloads('transfer_order_line')[0]['line_type_id'] == \
        TO_ASSET_TYPE_ID


def test_qty_greater_than_demand_line_is_rejected():
    conn = _db()
    _allocation(conn, qty=120.0)
    svc, fw = _service(conn)

    with pytest.raises(ConversionError) as exc:
        _convert(svc)
    assert exc.value.code == 'QTY_EXCEEDS_DEMAND'
    assert fw.calls == []   # 校验在开事务前，未写任何对象


# ---------------------------------------------------------------------------
# 失败码
# ---------------------------------------------------------------------------
def test_inactive_allocation_is_rejected():
    conn = _db()
    _allocation(conn, status='reversed')
    svc, _ = _service(conn)
    with pytest.raises(ConversionError) as exc:
        _convert(svc)
    assert exc.value.code == 'ALLOCATION_NOT_ACTIVE'


def test_pegged_to_other_document_is_rejected():
    conn = _db()
    _allocation(conn, target_bo='purchase_order', target_id=88,
                target_line_id=99)
    svc, _ = _service(conn)
    with pytest.raises(ConversionError) as exc:
        _convert(svc)
    assert exc.value.code == 'ALLOCATION_ALREADY_PEGGED'


def test_already_converted_allocation_is_rejected():
    conn = _db()
    _allocation(conn, target_bo='transfer_order', target_id=1,
                target_line_id=1)
    svc, _ = _service(conn)
    with pytest.raises(ConversionError) as exc:
        _convert(svc)
    assert exc.value.code == 'ALLOCATION_ALREADY_CONVERTED'


def test_unknown_allocation_id_is_rejected():
    conn = _db()
    svc, _ = _service(conn)
    with pytest.raises(ConversionError) as exc:
        _convert(svc, ids=(999,))
    assert exc.value.code == 'ALLOCATION_NOT_FOUND'


def test_cross_legal_entity_is_rejected():
    conn = _db()
    _allocation(conn)
    svc, _ = _service(conn)
    with pytest.raises(ConversionError) as exc:
        _convert(svc, from_org_id=2, to_org_id=11)
    assert exc.value.code == 'TO_CROSS_LEGAL_ENTITY'


def test_non_requisition_demand_is_rejected():
    conn = _db()
    _allocation(conn, demand_bo='service_request')
    svc, _ = _service(conn)
    with pytest.raises(ConversionError) as exc:
        _convert(svc)
    assert exc.value.code == 'DEMAND_BO_UNSUPPORTED'


# ---------------------------------------------------------------------------
# BO Action 入口
# ---------------------------------------------------------------------------
def test_handler_requires_allocation_ids():
    assert create_from_allocation_handler({}) == {
        'success': False, 'data': None,
        'message': '缺少 allocation_ids', 'code': 'INVALID_ARGUMENT'}
