# -*- coding: utf-8 -*-
"""采购发票正向调整单（增减调整流程）测试。

覆盖:
  · 创建：方向 / 原因 / 原单已过账 / 原行回指 / 原行不重复
  · 金额口径：increase 正数、decrease 负数（数量仍为正数幅值）
  · 过账：increase 写 normal 边追加消耗，decrease 写红字边冲减
  · 严格校验：超额 / 无可用锚点 / 不可红冲
  · 动作注册与守卫拦截器接线
"""

import types

import pytest

pytestmark = pytest.mark.unit

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.vendor_invoice_guard_interceptor import (
    VendorInvoiceGuardInterceptor,
)
from meta.services.vendor_invoice_match_service import (
    VendorInvoiceError,
    VendorInvoiceMatchService,
)
from meta.tests.factories._vendor_invoice_helpers import (
    DOC_TYPE_ID,
    RED_TYPE_ID,
    RECEIPT_LINE_ID,
    SCHEDULE_ID,
    consumed_qty,
    count_edges,
    get_header,
    get_lines,
    insert_edge,
    insert_invoice,
    insert_line,
    make_env,
    seed_purchase_order,
    seed_receipt_line,
    seed_type_definitions,
    update_edge_quantity,
)


@pytest.fixture
def service(tmp_path, monkeypatch):
    ds = make_env(tmp_path)
    # 本组用例只验证调整语义，编号服务单测覆盖；固定给调整单号
    monkeypatch.setattr(
        VendorInvoiceMatchService, '_allocate_number',
        lambda self, invoice_date, document_type_id: 'VIA-T0001')
    # 平台库复用同一临时库：规则表与边表都在 make_env 中建好
    return VendorInvoiceMatchService(ds, platform_data_source=ds), ds


def _posted_invoice(ds, *, promised=10.0, received=10.0, qty=10.0,
                    net=100.0, tax=13.0, status='posted',
                    category='invoice', document_type_id=DOC_TYPE_ID,
                    direction=1, anchors=True):
    seed_type_definitions(ds)
    seed_purchase_order(ds, promised_qty=promised)
    seed_receipt_line(ds, qty_received=received)
    invoice_id = insert_invoice(
        ds, status=status, category=category, direction=direction,
        document_type_id=document_type_id, net_amount=net, tax_amount=tax,
        gross_amount=net + tax)
    line_id = insert_line(
        ds, invoice_id, qty=qty, net_amount=net, tax_amount=tax,
        gross_amount=net + tax,
        schedule_id=SCHEDULE_ID if anchors else None,
        receipt_line_id=RECEIPT_LINE_ID if anchors else None,
        match_status='matched')
    if anchors:
        insert_edge(
            ds, rule_id='po_schedule_to_vendor_invoice_line',
            source_bo='purchase_order_schedule', source_id=SCHEDULE_ID,
            target_line_id=line_id, quantity=qty, pool='billing', amount=net)
        insert_edge(
            ds, rule_id='receipt_line_to_vendor_invoice_line',
            source_bo='receipt_line', source_id=RECEIPT_LINE_ID,
            target_line_id=line_id, quantity=qty, pool='ap_match', amount=net)
    return invoice_id, line_id


def _ctx(ds, action, params, old_data=None):
    return types.SimpleNamespace(
        meta_object=types.SimpleNamespace(id='vendor_invoice'),
        action=action,
        params=params,
        old_data=old_data or {},
        extra={},
        data_source=ds,
        result=None,
    )


_INTERCEPTOR = VendorInvoiceGuardInterceptor()


# ---------------------------------------------------------------- 创建

def test_create_increase_adjustment_keeps_original_posted(service):
    svc, ds = service
    invoice_id, line_id = _posted_invoice(ds)

    result = svc.create_adjustment(
        invoice_id, direction='increase', reason='补收运费',
        lines=[{'invoice_line_id': line_id, 'qty': 2,
                'net_amount': 20.0, 'tax_amount': 2.6}])

    header = get_header(ds, result['invoice_id'])
    assert header['status'] == 'draft'
    assert header['document_category'] == 'adjustment'
    assert header['adjustment_of_invoice_id'] == invoice_id
    assert header['adjustment_direction'] == 'increase'
    assert header['adjustment_reason'] == '补收运费'
    assert header['direction'] == 1
    assert header['net_amount'] == 20.0
    assert header['tax_amount'] == 2.6
    assert header['gross_amount'] == pytest.approx(22.6)

    line = get_lines(ds, result['invoice_id'])[0]
    assert line['invoice_line_id'] == line_id
    assert line['qty'] == 2.0
    assert line['net_amount'] == 20.0

    # 原票不受影响
    original = get_header(ds, invoice_id)
    assert original['status'] == 'posted'
    assert original['net_amount'] == 100.0
    assert original['adjustment_of_invoice_id'] is None


def test_create_decrease_adjustment_uses_negative_amounts(service):
    svc, ds = service
    invoice_id, line_id = _posted_invoice(ds)

    result = svc.create_adjustment(
        invoice_id, direction='decrease', reason='数量差异',
        lines=[{'invoice_line_id': line_id, 'qty': 4,
                'net_amount': 40.0, 'tax_amount': 5.2}])

    header = get_header(ds, result['invoice_id'])
    assert header['adjustment_direction'] == 'decrease'
    assert header['net_amount'] == -40.0
    assert header['tax_amount'] == pytest.approx(-5.2)
    assert header['gross_amount'] == pytest.approx(-45.2)
    line = get_lines(ds, result['invoice_id'])[0]
    # 数量存正数幅值，金额带符号
    assert line['qty'] == 4.0
    assert line['net_amount'] == -40.0


def test_create_rejects_increase_on_adjustment(service):
    """调整行不落锚点列，increase 无法解析锚点 → 创建期即拒绝。"""
    svc, ds = service
    invoice_id, line_id = _posted_invoice(ds, promised=12.0, received=12.0)
    base = svc.create_adjustment(
        invoice_id, direction='increase', reason='补量',
        lines=[{'invoice_line_id': line_id, 'qty': 1, 'net_amount': 10.0,
                'tax_amount': 1.3}])
    svc.submit(base['invoice_id'])
    svc.post(base['invoice_id'])
    adjustment_line = get_lines(ds, base['invoice_id'])[0]

    with pytest.raises(VendorInvoiceError) as error:
        svc.create_adjustment(
            base['invoice_id'], direction='increase', reason='再加',
            lines=[{'invoice_line_id': adjustment_line['id'], 'qty': 1}])
    assert error.value.rule == 'VI_ADJUSTMENT_INCREASE_UNSUPPORTED'


def test_decrease_on_adjustment_reverses_its_edges(service):
    """撤销调整单 = 对其创建反向（decrease）调整单，红字冲减其入边。"""
    svc, ds = service
    invoice_id, line_id = _posted_invoice(ds, promised=12.0, received=12.0)
    base = svc.create_adjustment(
        invoice_id, direction='increase', reason='补量',
        lines=[{'invoice_line_id': line_id, 'qty': 1, 'net_amount': 10.0,
                'tax_amount': 1.3}])
    svc.submit(base['invoice_id'])
    svc.post(base['invoice_id'])
    adjustment_line = get_lines(ds, base['invoice_id'])[0]

    undo = svc.create_adjustment(
        base['invoice_id'], direction='decrease', reason='撤销补量',
        lines=[{'invoice_line_id': adjustment_line['id'], 'qty': 1}])
    svc.submit(undo['invoice_id'])
    svc.post(undo['invoice_id'])

    assert get_header(ds, undo['invoice_id'])['status'] == 'posted'
    # 原票 + 调整单均保持 posted
    assert get_header(ds, invoice_id)['status'] == 'posted'
    assert get_header(ds, base['invoice_id'])['status'] == 'posted'
    assert consumed_qty(ds, 'purchase_order_schedule', SCHEDULE_ID, 'billing') == 10.0
    assert consumed_qty(ds, 'receipt_line', RECEIPT_LINE_ID, 'ap_match') == 10.0


def test_create_requires_reason(service):
    svc, ds = service
    invoice_id, _ = _posted_invoice(ds)
    with pytest.raises(VendorInvoiceError) as error:
        svc.create_adjustment(invoice_id, direction='increase', reason='  ')
    assert error.value.rule == 'VI_ADJUSTMENT_REASON_REQUIRED'


def test_create_requires_valid_direction(service):
    svc, ds = service
    invoice_id, _ = _posted_invoice(ds)
    with pytest.raises(VendorInvoiceError) as error:
        svc.create_adjustment(invoice_id, direction='both', reason='x')
    assert error.value.rule == 'VI_ADJUSTMENT_DIRECTION_INVALID'


def test_create_rejects_unposted_source(service):
    svc, ds = service
    invoice_id, _ = _posted_invoice(ds, status='draft')
    with pytest.raises(VendorInvoiceError) as error:
        svc.create_adjustment(invoice_id, direction='increase', reason='x')
    assert error.value.rule == 'VI_ADJUSTMENT_SOURCE_NOT_POSTED'


def test_create_rejects_credit_memo_source(service):
    svc, ds = service
    invoice_id, _ = _posted_invoice(
        ds, category='credit_memo', direction=-1,
        document_type_id=RED_TYPE_ID, net=-100.0, tax=-13.0)
    with pytest.raises(VendorInvoiceError) as error:
        svc.create_adjustment(invoice_id, direction='increase', reason='x')
    assert error.value.rule == 'VI_ADJUSTMENT_SOURCE_INVALID'


def test_create_rejects_unknown_source_line(service):
    svc, ds = service
    invoice_id, _ = _posted_invoice(ds)
    with pytest.raises(VendorInvoiceError) as error:
        svc.create_adjustment(
            invoice_id, direction='increase', reason='x',
            lines=[{'invoice_line_id': 999999, 'qty': 1}])
    assert error.value.rule == 'VI_ADJUSTMENT_ANCHOR_REQUIRED'


def test_create_rejects_duplicate_source_line(service):
    svc, ds = service
    invoice_id, line_id = _posted_invoice(ds)
    with pytest.raises(VendorInvoiceError) as error:
        svc.create_adjustment(
            invoice_id, direction='increase', reason='x',
            lines=[{'invoice_line_id': line_id, 'qty': 1},
                   {'invoice_line_id': line_id, 'qty': 1}])
    assert error.value.rule == 'VI_ADJUSTMENT_LINE_DUPLICATE'


# ---------------------------------------------------------------- 过账边

def test_increase_post_writes_normal_edges(service):
    svc, ds = service
    # 原票消耗 10，订单 / 收货各剩 2
    invoice_id, line_id = _posted_invoice(ds, promised=12.0, received=12.0)

    created = svc.create_adjustment(
        invoice_id, direction='increase', reason='补收',
        lines=[{'invoice_line_id': line_id, 'qty': 2,
                'net_amount': 20.0, 'tax_amount': 2.6}])
    adjustment_id = created['invoice_id']
    svc.submit(adjustment_id)
    svc.post(adjustment_id)

    assert get_header(ds, adjustment_id)['status'] == 'posted'
    assert consumed_qty(ds, 'purchase_order_schedule', SCHEDULE_ID, 'billing') == 12.0
    assert consumed_qty(ds, 'receipt_line', RECEIPT_LINE_ID, 'ap_match') == 12.0
    red_edges = count_edges(ds, quantity_sign='red')
    assert red_edges == 0


def test_decrease_post_writes_red_edges(service):
    svc, ds = service
    invoice_id, line_id = _posted_invoice(ds)

    created = svc.create_adjustment(
        invoice_id, direction='decrease', reason='数量差异',
        lines=[{'invoice_line_id': line_id, 'qty': 3,
                'net_amount': 30.0, 'tax_amount': 3.9}])
    adjustment_id = created['invoice_id']
    svc.submit(adjustment_id)
    svc.post(adjustment_id)

    assert get_header(ds, adjustment_id)['status'] == 'posted'
    assert consumed_qty(ds, 'purchase_order_schedule', SCHEDULE_ID, 'billing') == 7.0
    assert consumed_qty(ds, 'receipt_line', RECEIPT_LINE_ID, 'ap_match') == 7.0
    red_edges = count_edges(ds, quantity_sign='red', status='active')
    assert red_edges == 2


def test_create_increase_with_qty_only_scales_amounts(service):
    """只覆盖数量时按原行比例折算金额，避免行金额仍是原行全额。"""
    svc, ds = service
    invoice_id, line_id = _posted_invoice(ds, promised=12.0, received=12.0)

    result = svc.create_adjustment(
        invoice_id, direction='increase', reason='补量',
        lines=[{'invoice_line_id': line_id, 'qty': 2}])

    header = get_header(ds, result['invoice_id'])
    assert header['net_amount'] == 20.0
    assert header['tax_amount'] == 2.6
    line = get_lines(ds, result['invoice_id'])[0]
    assert line['qty'] == 2.0
    assert line['net_amount'] == 20.0


def test_decrease_post_allocates_across_multiple_edges(service):
    """原行有多条 normal 边（分属多条计划行）时按累计可用量校验并逐条分摊。"""
    svc, ds = service
    invoice_id, line_id = _posted_invoice(ds)
    # 原边 10 拆成 4 + 6，模拟原发票行分属两条计划行
    update_edge_quantity(ds, 'po_schedule_to_vendor_invoice_line', line_id, 4.0)
    insert_edge(
        ds, rule_id='po_schedule_to_vendor_invoice_line',
        source_bo='purchase_order_schedule', source_id=SCHEDULE_ID + 1,
        target_line_id=line_id, quantity=6.0, pool='billing', amount=60.0)

    created = svc.create_adjustment(
        invoice_id, direction='decrease', reason='跨边冲减',
        lines=[{'invoice_line_id': line_id, 'qty': 7,
                'net_amount': 70.0, 'tax_amount': 9.1}])
    svc.submit(created['invoice_id'])
    svc.post(created['invoice_id'])

    # FIFO 分摊：先冲最早的 4，再冲后一条的 3
    assert consumed_qty(ds, 'purchase_order_schedule', SCHEDULE_ID, 'billing') == 0.0
    assert consumed_qty(ds, 'purchase_order_schedule', SCHEDULE_ID + 1, 'billing') == 3.0
    assert count_edges(ds, quantity_sign='red') == 3
    assert consumed_qty(ds, 'receipt_line', RECEIPT_LINE_ID, 'ap_match') == 3.0


def test_increase_post_rejects_exceeding_open_qty(service):
    svc, ds = service
    # 原票已全额消耗，无余量可追加
    invoice_id, line_id = _posted_invoice(ds)

    created = svc.create_adjustment(
        invoice_id, direction='increase', reason='补收',
        lines=[{'invoice_line_id': line_id, 'qty': 1,
                'net_amount': 10.0, 'tax_amount': 1.3}])
    svc.submit(created['invoice_id'])
    with pytest.raises(VendorInvoiceError) as error:
        svc.post(created['invoice_id'])
    assert error.value.rule == 'VI_ADJUSTMENT_EXCEEDED'
    assert get_header(ds, created['invoice_id'])['status'] == 'submitted'


def test_decrease_post_rejects_exceeding_red_available(service):
    svc, ds = service
    invoice_id, line_id = _posted_invoice(ds)

    created = svc.create_adjustment(
        invoice_id, direction='decrease', reason='超冲',
        lines=[{'invoice_line_id': line_id, 'qty': 11,
                'net_amount': 110.0, 'tax_amount': 14.3}])
    svc.submit(created['invoice_id'])
    with pytest.raises(VendorInvoiceError) as error:
        svc.post(created['invoice_id'])
    assert error.value.rule == 'VI_ADJUSTMENT_EXCEEDED'


def test_increase_post_rejects_missing_anchor(service):
    svc, ds = service
    invoice_id, line_id = _posted_invoice(ds, anchors=False)

    created = svc.create_adjustment(
        invoice_id, direction='increase', reason='补收',
        lines=[{'invoice_line_id': line_id, 'qty': 1,
                'net_amount': 10.0, 'tax_amount': 1.3}])
    svc.submit(created['invoice_id'])
    with pytest.raises(VendorInvoiceError) as error:
        svc.post(created['invoice_id'])
    assert error.value.rule == 'VI_ADJUSTMENT_ANCHOR_MISSING'


# ---------------------------------------------------------------- 状态机 / 红冲边界

def test_adjustment_full_lifecycle(service):
    svc, ds = service
    invoice_id, line_id = _posted_invoice(ds, promised=12.0, received=12.0)
    created = svc.create_adjustment(
        invoice_id, direction='increase', reason='补收',
        lines=[{'invoice_line_id': line_id, 'qty': 2,
                'net_amount': 20.0, 'tax_amount': 2.6}])
    adjustment_id = created['invoice_id']

    assert svc.submit(adjustment_id)['status'] == 'submitted'
    assert svc.post(adjustment_id)['status'] == 'posted'

    # 调整单可作为来源继续创建调整单（原单链：回指调整行自身）
    follow = svc.create_adjustment(
        adjustment_id, direction='decrease', reason='再冲回',
        lines=[{'invoice_line_id': created['line_ids'][0], 'qty': 2,
                'net_amount': 20.0, 'tax_amount': 2.6}])
    assert follow['adjustment_of_invoice_id'] == adjustment_id


def test_posted_adjustment_cannot_be_reversed(tmp_path):
    ds = make_env(tmp_path)
    adjustment_id = insert_invoice(
        ds, invoice_no='VIA-0001', category='adjustment', status='posted',
        document_type_id=9105)

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            ds, 'crud_update',
            {'id': adjustment_id, 'status': 'reversed', 'reversal_reason': 'x'},
            old_data={'status': 'posted', 'document_category': 'adjustment'}))
    assert error.value.details[0]['rule'] == 'VI_ADJUSTMENT_NOT_REVERSIBLE'


# ---------------------------------------------------------------- 守卫 / 动作接线

def test_guard_adjustment_create_requires_direction(tmp_path):
    ds = make_env(tmp_path)
    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            ds, 'crud_create', {'document_category': 'adjustment'}))
    assert error.value.details[0]['rule'] == 'VI_ADJUSTMENT_DIRECTION_INVALID'


def test_guard_adjustment_create_requires_reason(tmp_path):
    ds = make_env(tmp_path)
    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            ds, 'crud_create',
            {'document_category': 'adjustment', 'adjustment_direction': 'increase'}))
    assert error.value.details[0]['rule'] == 'VI_ADJUSTMENT_REASON_REQUIRED'


def test_guard_adjustment_create_requires_posted_source(tmp_path):
    ds = make_env(tmp_path)
    seed_type_definitions(ds)
    original_id = insert_invoice(ds, status='draft', document_type_id=DOC_TYPE_ID)
    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            ds, 'crud_create',
            {'document_category': 'adjustment', 'adjustment_direction': 'increase',
             'adjustment_reason': 'x', 'adjustment_of_invoice_id': original_id}))
    assert error.value.details[0]['rule'] == 'VI_ADJUSTMENT_SOURCE_NOT_POSTED'


def test_create_adjustment_action_registered():
    from meta.core.bo_action_registry import BoActionRegistry
    from meta.services.bo_action_registrations import register_all_bo_actions

    registry = BoActionRegistry()
    register_all_bo_actions(registry)
    meta = registry.get('vendor_invoice.create_adjustment')
    assert meta is not None
    assert meta.object_type == 'vendor_invoice'
    assert meta.category == 'business'
    assert meta.permission_required == 'vendor_invoice:create'
    assert meta.requires_auth is True


def test_create_adjustment_handler_accepts_source_doc_id(service, monkeypatch):
    """通用派发（详情页 action）只带 source_doc_id 时应能定位原票。"""
    from meta.services import vendor_invoice_actions

    svc, ds = service
    invoice_id, _line_id = _posted_invoice(ds)
    monkeypatch.setattr(vendor_invoice_actions, '_service', lambda: svc)

    result = vendor_invoice_actions.create_adjustment_handler({
        'source_doc_id': invoice_id, 'direction': 'increase',
        'reason': '补收运费'})

    assert result['success'] is True
    assert result['data']['adjustment_of_invoice_id'] == invoice_id
    assert get_header(ds, result['data']['invoice_id'])['adjustment_reason'] == '补收运费'