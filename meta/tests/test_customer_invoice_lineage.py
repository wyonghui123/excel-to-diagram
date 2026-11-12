# -*- coding: utf-8 -*-
"""S8 Wave D FR-9：发票血脉一致性断言（AC-9.1 / AC-9.2）。

口径：行存在来源外键 ⇒ 过账后必存在对应 `doc_flow_edges` active 边；
反向不强制（手工行天然无边）。诊断仅用于测试 / 查询，不进入过账事务。

夹具：meta/tests/factories/_customer_invoice_helpers.py（内存库）
"""
import pytest

pytestmark = pytest.mark.unit

from meta.services.customer_invoice_service import (
    CREDIT_DOC_FLOW_RULE_ID,
    DOC_FLOW_RULE_ID,
    PLAN_DOC_FLOW_RULE_ID,
    RETURN_DOC_FLOW_RULE_ID,
    CustomerInvoiceService,
    expected_lineage_edges,
    lineage_violations,
)
from meta.tests.factories._customer_invoice_helpers import (
    CURRENCY_ID,
    CUSTOMER_ID,
    INVOICE_DATE,
    ORG_ID,
    PAYMENT_TERM_ID,
    RETURN_SHIP_LINE_ID,
    RETURN_SHIPMENT_ID,
    SHIP_LINE_ID,
    SHIPMENT_ID,
    build_conn,
    ensure_doc_flow_edges,
    get_lines,
    insert_doc_flow_edge,
    make_ds,
    make_return_shipment,
)

MANUAL_LINE = {
    'description': '手工服务费',
    'uom_id': 21,
    'tax_code_id': 31,
    'qty': 1,
    'unit_price': 100,
    'tax_rate_percent': 13,
}


def _service(conn):
    return CustomerInvoiceService(make_ds(conn))


def _posted_shipment_invoice(conn):
    service = _service(conn)
    created = service.create_from_shipment(
        {'shipment_id': SHIPMENT_ID, 'invoice_date': INVOICE_DATE})
    service.submit(created['id'])
    service.post(created['id'])
    return service, created['id']


def _capture_attach_edges(monkeypatch):
    """拦截边写入，返回 [(rule_id, source_id, target_line_id)]。"""
    calls = []

    def fake_attach_edge(app_ds, platform_ds, rule, source_id, target_id,
                         *args, **kwargs):
        calls.append((rule, source_id, target_id))
        return True

    monkeypatch.setattr(
        'meta.core.doc_flow_attach.attach_edge', fake_attach_edge)
    return calls


def _expected_edges(conn, invoice_id):
    expected = set()
    for line in get_lines(conn, invoice_id):
        for edge in expected_lineage_edges(line):
            expected.add((edge['rule_id'], str(edge['source_id']),
                          str(line['id'])))
    return expected


def _captured_edges(calls):
    return {(rule, str(source_id), str(target_id))
            for rule, source_id, target_id in calls}


# ---------------------------------------------------------------- 期望口径

def test_lineage_expectation_follows_source_priority():
    manual = {'id': 1}
    assert expected_lineage_edges(manual) == []

    shipment = {'id': 2, 'shipment_line_id': SHIP_LINE_ID}
    assert expected_lineage_edges(shipment) == [{
        'field': 'shipment_line_id',
        'rule_id': DOC_FLOW_RULE_ID,
        'source_bo': 'shipment_line',
        'source_id': str(SHIP_LINE_ID),
    }]

    plan = {'id': 3, 'schedule_id': 77}
    assert expected_lineage_edges(plan)[0]['rule_id'] == PLAN_DOC_FLOW_RULE_ID
    assert expected_lineage_edges(plan)[0]['source_bo'] == 'sales_order_schedule'

    credit = {'id': 4, 'original_invoice_line_id': 88,
              'shipment_line_id': SHIP_LINE_ID}
    edges = expected_lineage_edges(credit)
    assert len(edges) == 1
    assert edges[0]['rule_id'] == CREDIT_DOC_FLOW_RULE_ID
    assert edges[0]['source_id'] == '88'

    ret = {'id': 5, 'original_invoice_line_id': 88,
           'source_doc_type': 'return_shipment',
           'source_line_id': RETURN_SHIP_LINE_ID}
    edges = expected_lineage_edges(ret)
    assert [edge['rule_id'] for edge in edges] == [
        CREDIT_DOC_FLOW_RULE_ID, RETURN_DOC_FLOW_RULE_ID]


# ---------------------------------------------------------------- 写入路径对账

def test_posted_shipment_invoice_writes_one_edge_per_sourced_line(monkeypatch):
    conn = build_conn()
    service = _service(conn)
    created = service.create_from_shipment(
        {'shipment_id': SHIPMENT_ID, 'invoice_date': INVOICE_DATE})
    calls = _capture_attach_edges(monkeypatch)

    service.submit(created['id'])
    service.post(created['id'])

    expected = _expected_edges(conn, created['id'])
    assert expected
    assert _captured_edges(calls) == expected


def test_credit_invoice_writes_credit_edge_per_line(monkeypatch):
    conn = build_conn()
    service, source_id = _posted_shipment_invoice(conn)
    credit = service.create_credit_from_invoice({
        'source_invoice_id': source_id,
        'invoice_date': INVOICE_DATE,
        'reason': '数量调整',
    })
    calls = _capture_attach_edges(monkeypatch)

    service.submit(credit['id'])
    service.post(credit['id'])

    expected = _expected_edges(conn, credit['id'])
    assert len(expected) == len(get_lines(conn, credit['id']))
    assert all(rule == CREDIT_DOC_FLOW_RULE_ID
               for rule, _, _ in _captured_edges(calls))
    assert _captured_edges(calls) == expected


def test_return_credit_writes_credit_and_return_edge(monkeypatch):
    conn = build_conn()
    service, _ = _posted_shipment_invoice(conn)
    make_return_shipment(conn)
    credit = service.create_credit_from_return_shipment({
        'return_shipment_id': RETURN_SHIPMENT_ID,
        'invoice_date': INVOICE_DATE,
    })
    calls = _capture_attach_edges(monkeypatch)

    service.submit(credit['id'])
    service.post(credit['id'])

    expected = _expected_edges(conn, credit['id'])
    assert len(expected) == 2
    assert _captured_edges(calls) == expected


def test_red_invoice_writes_credit_edges_for_mirror_lines(monkeypatch):
    conn = build_conn()
    service, source_id = _posted_shipment_invoice(conn)
    calls = _capture_attach_edges(monkeypatch)

    red = service.reverse(source_id, '开票错误')

    expected = _expected_edges(conn, red['red_invoice_id'])
    assert expected
    assert all(rule == CREDIT_DOC_FLOW_RULE_ID
               for rule, _, _ in _captured_edges(calls))
    assert _captured_edges(calls) == expected


# ---------------------------------------------------------------- 只读诊断

def test_lineage_violations_empty_when_edges_present():
    conn = build_conn()
    _, invoice_id = _posted_shipment_invoice(conn)
    ensure_doc_flow_edges(conn)
    inserted = 0
    for line in get_lines(conn, invoice_id):
        for edge in expected_lineage_edges(line):
            insert_doc_flow_edge(
                conn, rule_id=edge['rule_id'], source_bo=edge['source_bo'],
                source_id=edge['source_id'], target_id=line['id'])
            inserted += 1

    assert inserted > 0
    assert lineage_violations(make_ds(conn), invoice_id) == []


def test_lineage_violations_reports_missing_edge():
    conn = build_conn()
    _, invoice_id = _posted_shipment_invoice(conn)
    ensure_doc_flow_edges(conn)
    lines = get_lines(conn, invoice_id)
    # 只为第二行建边，第一行缺失
    skipped = lines[0]
    for line in lines[1:]:
        for edge in expected_lineage_edges(line):
            insert_doc_flow_edge(
                conn, rule_id=edge['rule_id'], source_bo=edge['source_bo'],
                source_id=edge['source_id'], target_id=line['id'])

    violations = lineage_violations(make_ds(conn), invoice_id)

    assert len(violations) == 1
    violation = violations[0]
    assert violation['line_id'] == skipped['id']
    assert violation['field'] == 'shipment_line_id'
    assert violation['rule_id'] == DOC_FLOW_RULE_ID
    assert violation['source_id'] == str(SHIP_LINE_ID)
    assert violation['reason'] == 'DOC_FLOW_EDGE_MISSING'


def test_lineage_violations_ignore_manual_lines():
    conn = build_conn()
    invoice = _service(conn).create_manual({
        'invoice_date': INVOICE_DATE,
        'customer_account_id': CUSTOMER_ID,
        'currency_id': CURRENCY_ID,
        'org_id': ORG_ID,
        'payment_term_id': PAYMENT_TERM_ID,
        'lines': [dict(MANUAL_LINE)],
    })
    ensure_doc_flow_edges(conn)

    assert lineage_violations(make_ds(conn), invoice['id']) == []


def test_lineage_violations_reports_missing_edge_table():
    conn = build_conn()
    _, invoice_id = _posted_shipment_invoice(conn)

    violations = lineage_violations(make_ds(conn), invoice_id)

    assert violations == [{
        'line_id': None, 'field': '', 'rule_id': '', 'source_bo': '',
        'source_id': '', 'reason': 'DOC_FLOW_EDGE_TABLE_MISSING',
    }]