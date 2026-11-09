# -*- coding: utf-8 -*-
"""开票计划到期清单工具测试（S8 Wave B，只读）。

依据: docs/specs/s8-customer-invoice-wave-b/spec.md §7.1 / §10.5
"""
import json

import pytest

pytestmark = pytest.mark.unit

from meta.tests.factories._customer_invoice_helpers import (
    BILLING_SCHEDULE_ID,
    ORDER_LINE_DELIVERY,
    build_file,
    make_billing_schedule,
    set_order_status,
    set_schedule_fields,
)
from meta.tools.billing_due_list import main, query_due

AS_OF_EARLY = '2026-11-01'
AS_OF_DUE = '2026-11-20'


def _db_file(tmp_path):
    path = tmp_path / 'warehouse.db'
    conn = build_file(path)
    conn.commit()
    return path, conn


def test_no_due_before_promised_date(tmp_path):
    path, conn = _db_file(tmp_path)

    assert query_due(str(path), AS_OF_EARLY) == []
    assert main(['--db', str(path), '--as-of', AS_OF_EARLY]) == 0
    conn.close()


def test_due_rows_include_amounts_and_exit_code(tmp_path):
    path, conn = _db_file(tmp_path)

    rows = query_due(str(path), AS_OF_DUE)

    assert len(rows) == 1
    row = rows[0]
    assert row['order_no'] == 'SO-0001'
    assert row['line_no'] == 12
    assert row['schedule_id'] == BILLING_SCHEDULE_ID
    assert float(row['period_amount']) == 1000.0
    assert float(row['remaining']) == 1000.0
    assert row['billing_status'] == 'none'
    # 有到期期次 → 退出码 2，便于脚本判断
    assert main(['--db', str(path), '--as-of', AS_OF_DUE]) == 2
    conn.close()


def test_excludes_full_cancelled_and_non_billable(tmp_path):
    path, conn = _db_file(tmp_path)

    set_schedule_fields(conn, BILLING_SCHEDULE_ID, billing_status='full')
    conn.commit()
    assert query_due(str(path), AS_OF_DUE) == []

    set_schedule_fields(conn, BILLING_SCHEDULE_ID,
                        billing_status='none', status='cancelled')
    conn.commit()
    assert query_due(str(path), AS_OF_DUE) == []

    set_schedule_fields(conn, BILLING_SCHEDULE_ID, status='planned')
    set_order_status(conn, 'draft')
    conn.commit()
    assert query_due(str(path), AS_OF_DUE) == []
    conn.close()


def test_non_billing_kind_is_excluded(tmp_path):
    path, conn = _db_file(tmp_path)

    # 播种一个日期已到的期次但改成 delivery kind，不应进入开票到期清单
    make_billing_schedule(conn, 90, percent=50, promised_date=AS_OF_EARLY)
    set_schedule_fields(conn, 90, schedule_kind='delivery')
    conn.commit()

    rows = query_due(str(path), AS_OF_DUE)
    assert [row['schedule_id'] for row in rows] == [BILLING_SCHEDULE_ID]
    conn.close()


def test_non_plan_line_is_excluded(tmp_path):
    path, conn = _db_file(tmp_path)

    # 非 plan 行（billing_relevance='delivery'）的期次不可按计划开票，不进清单
    make_billing_schedule(conn, 91, percent=50, promised_date=AS_OF_EARLY,
                          line_id=ORDER_LINE_DELIVERY)
    conn.commit()

    rows = query_due(str(path), AS_OF_DUE)
    assert [row['schedule_id'] for row in rows] == [BILLING_SCHEDULE_ID]


def test_json_output_shape(tmp_path, capsys):
    path, conn = _db_file(tmp_path)

    assert main(['--db', str(path), '--as-of', AS_OF_DUE, '--json']) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload['as_of'] == AS_OF_DUE
    assert payload['total'] == 1
    assert len(payload['items']) == 1
    conn.close()


def test_missing_database_returns_error(tmp_path):
    assert main(['--db', str(tmp_path / 'missing.db')]) == 1