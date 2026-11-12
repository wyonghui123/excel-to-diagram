# -*- coding: utf-8 -*-
"""需求转采购订单契约（M3 / spec §14 步 23）

覆盖：只允许 approved 申请、开放行、分批与剩余量扣减、超量拒绝、
行类型映射、分配行落多态锚点、若干失败码。不依赖真实 DB / BO 框架：
`RequisitionToPoService` 的 `data_source` 与 `framework` 均可注入。
"""

from contextlib import contextmanager

import pytest

from meta.services.requisition_po_conversion import (
    ConversionError,
    RequisitionToPoService,
    create_from_requisition_handler,
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
        self.fail_on = None   # (object_type, message)
        self.rolled_back = False
        self.committed = False

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
        if object_type == 'purchase_order':
            record['order_no'] = 'PO-TEST-%04d' % new_id
        return _Result(success=True, data=record)

    def payloads(self, object_type):
        return [c['data'] for c in self.calls if c['object_type'] == object_type]


class _FakeDS:
    def __init__(self, requisition, lines, allocated=None, header_type_id=31):
        self.requisition = requisition
        self.lines = lines
        self.allocated = allocated or {}
        self.header_type_id = header_type_id

    def query(self, sql, params=None):
        params = params or []
        if 'FROM requisitions WHERE id' in sql:
            return [self.requisition] if params[0] == self.requisition['id'] else []
        if 'FROM requisition_lines' in sql:
            return [dict(r) for r in self.lines
                    if r['requisition_id'] == params[0]]
        if 'SUM(qty)' in sql:
            return [{'allocated': self.allocated.get(params[0], 0)}]
        if "scope_bo = 'purchase_order'" in sql and "level = 'line'" in sql:
            ids = {'PO_GOODS': 41, 'PO_SERVICE': 42}
            return [{'code': c, 'id': ids[c]} for c in params if c in ids]
        if "level = 'header'" in sql:
            return [{'id': self.header_type_id}] if self.header_type_id else []
        if 'number_sequence_id' in sql or 'FROM number_sequences' in sql:
            # 取号序列未挂载：转单不取号，由订单号必填校验兜底
            return []
        raise AssertionError('未覆盖的查询: %s' % sql)


def _requisition(status='approved'):
    return {
        'id': 11,
        'requisition_no': 'PR-202611-000001',
        'status': status,
        'requester_org_id': 7,
        'deliver_to_org_id': 8,
        'deliver_to_location_id': 3,
        'need_date': '2026-11-10',
        'description': '测试需求',
    }


LINES = [
    {'id': 21, 'requisition_id': 11, 'line_no': '0001', 'line_type': 'goods',
     'item_id': 101, 'description': '物料 A', 'qty': 10, 'uom_id': 1,
     'need_date': '2026-11-10', 'deliver_to_location_id': 3, 'cost_center_id': 5,
     'status': 'open'},
    {'id': 22, 'requisition_id': 11, 'line_no': '0002', 'line_type': 'service',
     'item_id': None, 'description': '安装服务', 'qty': 2, 'uom_id': 6,
     'need_date': '2026-11-12', 'deliver_to_location_id': None, 'cost_center_id': 5,
     'status': 'open'},
]


def _service(lines=None, status='approved', allocated=None, framework=None):
    ds = _FakeDS(_requisition(status), lines if lines is not None else LINES,
                 allocated=allocated)
    fw = framework or _FakeFramework()
    return RequisitionToPoService(data_source=ds, framework=fw), fw


def _header():
    return {'supplier_party_id': 501, 'currency_id': 1}


def test_convert_all_open_lines_creates_header_lines_and_allocations():
    svc, fw = _service()
    result = svc.convert(11, _header())

    assert result['purchase_order_id'] == 1
    assert result['order_no'] == 'PO-TEST-0001'
    assert len(fw.payloads('purchase_order')) == 1
    assert len(fw.payloads('purchase_order_line')) == 2
    assert len(fw.payloads('demand_allocation')) == 2

    header = fw.payloads('purchase_order')[0]
    assert header['supplier_party_id'] == 501
    assert header['purchase_org_id'] == 7 and header['org_id'] == 8
    assert header['document_type_id'] == 31
    assert header['requested_date'] == '2026-11-10'

    goods_line, service_line = fw.payloads('purchase_order_line')
    assert goods_line['line_no'] == '0001' and goods_line['line_type_id'] == 41
    assert goods_line['qty'] == 10 and goods_line['item_id'] == 101
    assert goods_line['unit_price'] == 0 and goods_line['net_amount'] == 0
    assert goods_line['requested_date'] == '2026-11-10'
    assert service_line['line_no'] == '0002' and service_line['line_type_id'] == 42
    assert service_line['qty'] == 2

    alloc_goods, alloc_service = fw.payloads('demand_allocation')
    assert alloc_goods['demand_bo'] == 'requisition'
    assert alloc_goods['demand_id'] == 11 and alloc_goods['demand_line_id'] == 21
    assert alloc_goods['target_bo'] == 'purchase_order' and alloc_goods['target_id'] == 1
    assert alloc_goods['target_line_id'] == 2   # 第 2 次 execute = 订单行 id
    assert alloc_goods['qty'] == 10 and alloc_goods['cost_center_id'] == 5
    assert alloc_goods['charge_basis'] == 'inventory'
    assert alloc_service['target_line_id'] == 4   # 头 1 → 行 2 → 分配 3 → 行 4
    assert fw.committed and not fw.rolled_back


def test_partial_convert_uses_requested_qty():
    svc, fw = _service()
    result = svc.convert(11, _header(), lines=[{'requisition_line_id': 21, 'qty': 3}])
    assert len(result['lines']) == 1
    assert result['lines'][0]['qty'] == 3
    assert [p['qty'] for p in fw.payloads('demand_allocation')] == [3]


def test_remaining_qty_is_reduced_by_active_allocations():
    svc, fw = _service(allocated={21: 8})
    result = svc.convert(11, _header(), lines=[{'requisition_line_id': 21}])
    assert result['lines'][0]['qty'] == 2
    assert fw.payloads('demand_allocation')[0]['qty'] == 2


def test_over_qty_is_rejected_not_truncated():
    svc, fw = _service(allocated={21: 8})
    with pytest.raises(ConversionError) as exc:
        svc.convert(11, _header(), lines=[{'requisition_line_id': 21, 'qty': 5}])
    assert exc.value.code == 'QTY_EXCEEDS_REMAINING'
    assert fw.calls == []   # 数量校验在开事务之前，未写任何对象


def test_requisition_must_be_approved():
    svc, _fw = _service(status='submitted')
    with pytest.raises(ConversionError) as exc:
        svc.convert(11, _header())
    assert exc.value.code == 'REQUISITION_NOT_APPROVED'


def test_closed_line_cannot_be_converted_explicitly():
    lines = [dict(LINES[0], status='closed'), LINES[1]]
    svc, _fw = _service(lines=lines)
    with pytest.raises(ConversionError) as exc:
        svc.convert(11, _header(), lines=[{'requisition_line_id': 21, 'qty': 1}])
    assert exc.value.code == 'REQUISITION_LINE_NOT_OPEN'


def test_missing_supplier_org_or_currency_is_rejected():
    svc, _fw = _service()
    with pytest.raises(ConversionError) as exc:
        svc.convert(11, {'currency_id': 1})
    assert exc.value.code == 'INVALID_ARGUMENT'

    svc, _fw = _service()
    with pytest.raises(ConversionError) as exc:
        svc.convert(11, {'supplier_party_id': 501})
    assert exc.value.code == 'INVALID_ARGUMENT'


def test_line_create_failure_rolls_back_whole_conversion():
    svc, fw = _service()
    fw.fail_on = ('purchase_order_line', '行类型必填')
    with pytest.raises(ConversionError) as exc:
        svc.convert(11, _header())
    assert exc.value.code == 'PURCHASE_ORDER_LINE_CREATE_FAILED'
    assert fw.rolled_back and not fw.committed
    # 失败前只写过 1 次头 + 1 次行
    assert len(fw.payloads('demand_allocation')) == 0


def test_handler_rejects_missing_requisition_id():
    out = create_from_requisition_handler({'supplier_party_id': 501})
    assert out['success'] is False and out['code'] == 'INVALID_ARGUMENT'
    assert 'requisition_id' in out['message']


def test_handler_success_envelope_with_injected_service(monkeypatch):
    svc, _fw = _service()
    monkeypatch.setattr(
        'meta.services.requisition_po_conversion.RequisitionToPoService',
        lambda: svc)
    out = create_from_requisition_handler({
        'requisition_id': 11, 'supplier_party_id': 501, 'currency_id': 1})
    assert out['success'] is True
    assert out['data']['order_no'] == 'PO-TEST-0001'
    assert 'PO-TEST-0001' in out['message']
