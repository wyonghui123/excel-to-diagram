# -*- coding: utf-8 -*-
"""采购发票接入平台统一逆向引擎（`doc_effect.reversal`）测试。

覆盖:
  · schema 声明完整性（faces 原语 / create_document creator 均已注册）
  · 红冲主链：posted → reversed、红字贷项凭证、红字消耗边、可用量归零
  · 守卫：原因必填 / 状态非法 / 类型未声明 / 重复红冲
  · 红字边只允许贷项或取消凭证写
  · BO 动作 `vendor_invoice.reverse` 已注册
"""

import pytest

pytestmark = pytest.mark.unit

from meta.core import reversal_orchestrator, reversal_profiles
from meta.core.reversal_primitives import DOC_CREATORS, PRIMITIVES
from meta.services.bo_action_registrations import register_all_bo_actions
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
    get_header,
    get_lines,
    insert_edge,
    insert_invoice,
    insert_line,
    make_env,
    seed_purchase_order,
    seed_receipt_line,
    seed_type_definitions,
)


@pytest.fixture
def service(tmp_path, monkeypatch):
    ds = make_env(tmp_path)
    # 单号服务依赖 numbering 底座；本组用例只验证红冲语义，直接给红字单号
    monkeypatch.setattr(
        VendorInvoiceMatchService, '_allocate_number',
        lambda self, invoice_date, document_type_id: 'VCM-T0001')
    return VendorInvoiceMatchService(ds), ds


def _posted_invoice(ds, *, status='posted'):
    seed_type_definitions(ds)
    seed_purchase_order(ds)
    seed_receipt_line(ds)
    invoice_id = insert_invoice(
        ds, status=status, document_type_id=DOC_TYPE_ID)
    line_id = insert_line(
        ds, invoice_id, qty=10.0, schedule_id=SCHEDULE_ID,
        receipt_line_id=RECEIPT_LINE_ID, match_status='matched')
    insert_edge(
        ds, rule_id='po_schedule_to_vendor_invoice_line',
        source_bo='purchase_order_schedule', source_id=SCHEDULE_ID,
        target_line_id=line_id, quantity=10.0, pool='billing', amount=100.0)
    insert_edge(
        ds, rule_id='receipt_line_to_vendor_invoice_line',
        source_bo='receipt_line', source_id=RECEIPT_LINE_ID,
        target_line_id=line_id, quantity=10.0, pool='ap_match', amount=100.0)
    return invoice_id, line_id


# ---------------------------------------------------------------- 声明完整性

def test_doc_effect_reversal_declared_and_registered():
    assert reversal_orchestrator.supports('vendor_invoice') is True
    assert 'vendor_invoice_doc_flow_red_edge' in PRIMITIVES
    assert 'vendor_invoice_red_letter' in DOC_CREATORS
    profile = reversal_profiles.get_profile('vendor_invoice')
    assert profile['mode'] == reversal_profiles.MODE_RED_INK
    assert profile['reason_required'] is True


def test_vendor_reverse_action_registered():
    from meta.core.bo_action_registry import BoActionRegistry
    registry = BoActionRegistry()
    register_all_bo_actions(registry)
    meta = registry.get('vendor_invoice.reverse')
    assert meta is not None
    assert meta.object_type == 'vendor_invoice'
    assert meta.category == 'business'
    assert meta.permission_required == 'vendor_invoice:reverse'
    assert meta.requires_auth is True


# ---------------------------------------------------------------- 红冲主链

def test_reverse_creates_red_credit_memo_and_red_edges(service):
    svc, ds = service
    invoice_id, line_id = _posted_invoice(ds)

    result = svc.reverse(invoice_id, reason='供应商退货')

    assert result['status'] == 'reversed'
    assert result['red_invoice_id']
    assert get_header(ds, invoice_id)['status'] == 'reversed'

    red = get_header(ds, result['red_invoice_id'])
    assert red['document_category'] == 'credit_memo'
    assert red['document_type_id'] == RED_TYPE_ID
    assert red['direction'] == -1
    assert red['status'] == 'posted'
    assert red['reversal_of_invoice_id'] == invoice_id
    assert red['reversal_reason'] == '供应商退货'
    assert red['gross_amount'] == -113.0

    red_lines = get_lines(ds, result['red_invoice_id'])
    assert len(red_lines) == 1
    assert red_lines[0]['invoice_line_id'] == line_id
    assert red_lines[0]['qty'] == -10.0

    # 红字边冲减两条正向边，可用量归零
    assert consumed_qty(ds, 'purchase_order_schedule', SCHEDULE_ID, 'billing') == 0.0
    assert consumed_qty(ds, 'receipt_line', RECEIPT_LINE_ID, 'ap_match') == 0.0
    red_edges = ds.query(
        "SELECT * FROM doc_flow_edges WHERE quantity_sign = 'red' AND status = 'active'")
    assert len(red_edges) == 2
    # 红字边 quantity 仍为正数，聚合时按 quantity_sign='red' 取负
    assert all(edge['quantity'] == 10.0 for edge in red_edges)
    assert {str(edge['target_id']) for edge in red_edges} == {str(line_id)}


# ---------------------------------------------------------------- 守卫

def test_vendor_reverse_requires_reason(service):
    svc, ds = service
    invoice_id, _ = _posted_invoice(ds)
    with pytest.raises(VendorInvoiceError) as error:
        svc.reverse(invoice_id, reason='  ')
    assert error.value.rule == 'VI_REVERSAL_REASON_REQUIRED'


def test_reverse_rejects_draft_invoice(service):
    svc, ds = service
    invoice_id, _ = _posted_invoice(ds, status='draft')
    with pytest.raises(VendorInvoiceError) as error:
        svc.reverse(invoice_id, reason='x')
    assert error.value.rule == 'VI_STATE_INVALID'


def test_reverse_requires_declared_red_type(service):
    svc, ds = service
    invoice_id, _ = _posted_invoice(ds)
    seed_type_definitions(ds, reversal_type_id=None)
    with pytest.raises(VendorInvoiceError) as error:
        svc.reverse(invoice_id, reason='x')
    assert error.value.rule == 'VI_REVERSAL_NOT_DECLARED'


def test_reverse_twice_is_rejected(service):
    svc, ds = service
    invoice_id, _ = _posted_invoice(ds)
    svc.reverse(invoice_id, reason='第一次')
    with pytest.raises(VendorInvoiceError) as error:
        svc.reverse(invoice_id, reason='第二次')
    assert error.value.rule == 'VI_STATE_INVALID'


def test_red_edges_only_for_credit_or_cancellation(service):
    svc, ds = service
    invoice_id, _ = _posted_invoice(ds)
    with pytest.raises(VendorInvoiceError) as error:
        svc.write_red_edges_for_red_doc(invoice_id)
    assert error.value.rule == 'VI_RED_INK_INVALID'