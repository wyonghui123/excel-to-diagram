# -*- coding: utf-8 -*-
"""销售发票接入平台统一逆向引擎（doc_effect.reversal）的声明与执行测试。

覆盖 S8 Wave D T60-T63：
  · 声明完整性：逆向原语 / 红字创建器 / 冲销档位均已注册；
  · 执行：红冲副作用由编排器统一驱动（红票 posted、进度回滚、期次取消）；
  · 幂等：状态已 reversed 时编排器 replay=True，不重复建红票；
  · 错误映射：引擎错误码 → CustomerInvoiceError（rule 保留业务码）；
  · 缺声明 fail-closed，且不产生任何红字副作用。

夹具: meta/tests/factories/_customer_invoice_helpers.py（内存库，raw SQL 在工厂内）
"""
import pytest

pytestmark = pytest.mark.unit

from meta.core import reversal_orchestrator, reversal_profiles  # noqa: E402
from meta.core.reversal_orchestrator import ReversalError  # noqa: E402
from meta.core.reversal_primitives import (  # noqa: E402
    DOC_CREATORS,
    get_doc_creator,
    get_primitive,
)
from meta.services.customer_invoice_service import (  # noqa: E402
    CustomerInvoiceError,
    CustomerInvoiceService,
)
from meta.tests.factories._customer_invoice_helpers import (  # noqa: E402
    CURRENCY_ID,
    CUSTOMER_ID,
    INVOICE_DATE,
    ORG_ID,
    SHIP_LINE_ID,
    SHIPMENT_ID,
    build_conn,
    get_header,
    get_schedules,
    make_ds,
    shipment_billed,
    type_id,
    type_identity,
)

BASE_HEADER = {
    'invoice_date': INVOICE_DATE,
    'customer_account_id': CUSTOMER_ID,
    'currency_id': CURRENCY_ID,
    'org_id': ORG_ID,
}

FACE_PRIMITIVES = (
    'invoice_billed_release',
    'invoice_schedule_cancel',
    'invoice_doc_flow_red_edge',
    'recompute_customer_billing_status',
)


def _posted_invoice(conn):
    service = CustomerInvoiceService(make_ds(conn))
    result = service.create_from_shipment(
        dict(BASE_HEADER, shipment_id=SHIPMENT_ID,
             lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 40}]))
    service.submit(result['id'])
    service.post(result['id'])
    return service, result


# ---------------------------------------------------------------- 声明一致性

def test_declaration_registers_primitives_and_creator():
    assert reversal_orchestrator.supports('customer_invoice') is True
    for name in FACE_PRIMITIVES:
        assert get_primitive(name) is not None, name
    assert get_doc_creator('customer_invoice_red_letter') is not None
    assert 'customer_invoice_red_letter' in DOC_CREATORS


def test_declaration_profile_is_red_reverse():
    profile = reversal_profiles.get_profile('customer_invoice')
    assert profile['mode'] == reversal_profiles.MODE_RED_REVERSE
    assert profile['commitment'] == 'release_remaining'
    assert profile['reason_required'] is True


def test_only_forward_invoice_type_declares_reversal_target():
    """AC-10.5：补货 / 贷项 / 红字类型均不得配置 reversal_type_id。"""
    conn = build_conn()
    assert type_identity(conn, 'SINV')['reversal_type_id'] == type_id(conn, 'SRV')
    for code in ('SCR', 'SDN', 'SRV'):
        assert type_identity(conn, code)['reversal_type_id'] is None


def test_reverse_delegates_to_orchestrator(monkeypatch):
    """AC-10.1：红冲必须经 reversal_orchestrator.execute 执行。"""
    conn = build_conn()
    service, original = _posted_invoice(conn)
    calls = []
    real_execute = reversal_orchestrator.execute

    def _spy(ds, **kwargs):
        calls.append(kwargs)
        return real_execute(ds, **kwargs)

    monkeypatch.setattr(reversal_orchestrator, 'execute', _spy)

    result = service.reverse(original['id'], '客户退货')

    assert len(calls) == 1
    assert calls[0]['schema_id'] == 'customer_invoice'
    assert int(calls[0]['doc_id']) == int(original['id'])
    assert calls[0]['reason'] == '客户退货'
    assert calls[0]['params']['invoice_no'] == result['red_invoice_no']


# ---------------------------------------------------------------- 统一执行

def test_reverse_executes_declared_faces_and_projection():
    conn = build_conn()
    service, original = _posted_invoice(conn)

    result = service.reverse(original['id'], '客户退货')

    red = get_header(conn, result['red_invoice_id'])
    assert red['status'] == 'posted'
    assert red['direction'] == -1
    assert red['document_type_id'] == type_id(conn, 'SRV')
    assert red['reversal_of_invoice_id'] == original['id']
    assert get_header(conn, original['id'])['status'] == 'reversed'
    # 进度回滚（发货行 billed_qty 归零）+ 原期次取消 + 红票无期次
    assert shipment_billed(conn) == 0.0
    assert [row['status'] for row in get_schedules(conn, original['id'])] == [
        'cancelled', 'cancelled']
    assert get_schedules(conn, red['id']) == []


def test_engine_replay_does_not_create_second_red_invoice():
    conn = build_conn()
    ds = make_ds(conn)
    service = CustomerInvoiceService(ds)
    original = service.create_from_shipment(
        dict(BASE_HEADER, shipment_id=SHIPMENT_ID,
             lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 40}]))
    service.submit(original['id'])
    service.post(original['id'])
    first = service.reverse(original['id'], '第一次红冲')

    outcome = reversal_orchestrator.execute(
        ds, schema_id='customer_invoice', doc_id=original['id'],
        reason='重复调用')

    assert outcome.replay is True
    assert outcome.to_state == 'reversed'
    assert int(outcome.doc_id) == int(original['id'])
    red = service._find_red_invoice(original['id'])
    assert int(red['id']) == int(first['red_invoice_id'])


# ---------------------------------------------------------------- 错误映射

def test_reverse_maps_engine_rule_to_service_error(monkeypatch):
    conn = build_conn()
    service, original = _posted_invoice(conn)

    def _raise(*args, **kwargs):
        raise ReversalError('REVERSAL_FAILED', '期次取消失败',
                            field_name='status',
                            rule='INVOICE_AMOUNT_MISMATCH')

    monkeypatch.setattr(reversal_orchestrator, 'execute', _raise)

    with pytest.raises(CustomerInvoiceError) as error:
        service.reverse(original['id'], '红冲')
    assert error.value.rule == 'INVOICE_AMOUNT_MISMATCH'
    assert error.value.field_name == 'status'


def test_reverse_fails_closed_without_declaration(monkeypatch):
    conn = build_conn()
    service, original = _posted_invoice(conn)
    monkeypatch.setattr(reversal_orchestrator, 'supports', lambda schema_id: False)

    with pytest.raises(CustomerInvoiceError) as error:
        service.reverse(original['id'], '红冲')

    assert error.value.rule == 'REVERSAL_NOT_DECLARED'
    # 未声明时不得产生任何红字副作用（也未消耗单号）
    assert service._find_red_invoice(original['id']) is None
    assert get_header(conn, original['id'])['status'] == 'posted'