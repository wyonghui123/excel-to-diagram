# ALLOW_RAW_SQL: 本文件含裸 SQL 构造迁移前后的类型 / 发票数据，守卫豁免
# -*- coding: utf-8 -*-
"""v243 单据身份元数据迁移测试 —— 列 / 回填 / SRV / 索引 / 权限 / 回滚。

依据: docs/specs/s8-customer-invoice-wave-d/spec.md §6.1 / FR-1 / FR-2 / FR-5
夹具: meta/tests/factories/_customer_invoice_helpers.py（build_file）
"""
import sqlite3

import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v243__customer_invoice_document_role as v243
from meta.tests.factories._customer_invoice_helpers import (
    build_file,
    index_names,
    permission_exists,
    permission_grant_set_codes,
    seed_permission_sets,
    table_columns,
    type_id,
)

NEW_TYPE_COLUMNS = {name for name, _ddl in v243.NEW_TYPE_COLUMNS}
NEW_HEADER_COLUMNS = {name for name, _ddl in v243.NEW_HEADER_COLUMNS}


def _db_file(tmp_path):
    path = tmp_path / 'app.db'
    conn = build_file(path)
    seed_permission_sets(conn)
    conn.close()
    return path


def _insert_invoice(path, invoice_no, type_code, category):
    conn = sqlite3.connect(str(path))
    conn.execute(
        'INSERT INTO customer_invoices '
        '(invoice_no, document_type_id, document_category, invoice_date, '
        ' customer_account_id, currency_id, org_id) '
        'VALUES (?, ?, ?, ?, 900, 1, 10)',
        [invoice_no, type_id(conn, type_code), category, '2026-11-09'])
    conn.commit()
    conn.close()


def _insert_type(path, code, scope_bo, category):
    conn = sqlite3.connect(str(path))
    conn.execute(
        'INSERT INTO type_definitions '
        '(code, name, scope_bo, level, document_category, status) '
        "VALUES (?, ?, ?, 'header', ?, 'active')",
        [code, code, scope_bo, category])
    conn.commit()
    conn.close()


def _type_row(path, code, scope_bo='customer_invoice'):
    conn = sqlite3.connect(str(path))
    row = conn.execute(
        'SELECT id, name, document_role, direction, reversal_type_id, '
        'is_default, number_sequence_id FROM type_definitions '
        'WHERE scope_bo = ? AND level = ? AND code = ?',
        [scope_bo, 'header', code]).fetchone()
    conn.close()
    return row


def _type_exists(path, code, scope_bo='customer_invoice'):
    conn = sqlite3.connect(str(path))
    row = conn.execute(
        'SELECT id FROM type_definitions WHERE scope_bo = ? AND level = ? '
        'AND code = ?', [scope_bo, 'header', code]).fetchone()
    conn.close()
    return row is not None


def _header_direction(path, invoice_no):
    conn = sqlite3.connect(str(path))
    row = conn.execute(
        'SELECT direction FROM customer_invoices WHERE invoice_no = ?',
        [invoice_no]).fetchone()
    conn.close()
    return row[0]


def test_upgrade_adds_columns_and_invoice_type_roles(tmp_path):
    path = _db_file(tmp_path)

    assert v243.migrate(path, skip_backup=True) is True
    assert v243.verify(path) is True

    assert NEW_TYPE_COLUMNS <= table_columns(path, 'type_definitions')
    assert NEW_HEADER_COLUMNS <= table_columns(path, 'customer_invoices')

    srv = _type_row(path, 'SRV')
    assert srv is not None
    assert srv[0] == type_id(sqlite3.connect(str(path)), 'SRV')
    assert srv[2] == 'invoice'
    assert srv[3] == -1
    assert srv[5] == 0
    assert srv[6] is not None  # 已绑定 SRV 号段

    sinv = _type_row(path, 'SINV')
    assert (sinv[2], sinv[3], sinv[5]) == ('invoice', 1, 1)
    assert sinv[4] == srv[0]

    scr = _type_row(path, 'SCR')
    assert (scr[2], scr[3], scr[5]) == ('credit_memo', -1, 0)
    assert scr[1] == '销售贷项凭证'

    sdn = _type_row(path, 'SDN')
    assert (sdn[2], sdn[3], sdn[5]) == ('debit_memo', 1, 1)

    assert 'uq_type_default_role' in index_names(path)

    assert permission_exists(path, v243.DEBIT_PERMISSION) is True
    assert permission_grant_set_codes(
        path, v243.DEBIT_PERMISSION) == {'admin', 'default'}


def test_upgrade_backfills_platform_header_types(tmp_path):
    path = _db_file(tmp_path)
    _insert_type(path, 'RCV_RETURN', 'receipt', 'return')
    _insert_type(path, 'RCV_STD', 'receipt', 'standard')

    assert v243.migrate(path, skip_backup=True) is True
    assert v243.verify(path) is True

    assert _type_row(path, 'RCV_RETURN', 'receipt')[2:4] == ('return', -1)
    assert _type_row(path, 'RCV_STD', 'receipt')[2:4] == ('invoice', 1)


def test_upgrade_backfills_existing_invoice_direction(tmp_path):
    path = _db_file(tmp_path)
    _insert_invoice(path, 'SINV-0001', 'SINV', 'invoice')
    _insert_invoice(path, 'SCR-0001', 'SCR', 'credit_memo')

    assert v243.migrate(path, skip_backup=True) is True
    assert v243.verify(path) is True

    assert _header_direction(path, 'SINV-0001') == 1
    assert _header_direction(path, 'SCR-0001') == -1


def test_migrate_is_idempotent(tmp_path):
    path = _db_file(tmp_path)

    assert v243.migrate(path, skip_backup=True) is True
    assert v243.migrate(path, skip_backup=True) is True

    assert v243.verify(path) is True
    conn = sqlite3.connect(str(path))
    count = conn.execute(
        "SELECT COUNT(*) FROM type_definitions "
        "WHERE scope_bo = 'customer_invoice' AND code = 'SRV'").fetchone()[0]
    seq = conn.execute(
        "SELECT COUNT(*) FROM number_sequences WHERE code = 'SRV'").fetchone()[0]
    conn.close()
    assert count == 1
    assert seq == 1


def test_verify_rejects_invalid_identity(tmp_path):
    path = _db_file(tmp_path)
    assert v243.migrate(path, skip_backup=True) is True

    conn = sqlite3.connect(str(path))
    conn.execute(
        "UPDATE type_definitions SET direction = 1 "
        "WHERE scope_bo = 'customer_invoice' AND code = 'SCR'")
    conn.commit()
    conn.close()
    assert v243.verify(path) is False

    conn = sqlite3.connect(str(path))
    conn.execute(
        "UPDATE type_definitions SET direction = -1 "
        "WHERE scope_bo = 'customer_invoice' AND code = 'SCR'")
    conn.execute('PRAGMA foreign_keys = OFF')
    conn.execute(
        'INSERT INTO customer_invoices '
        '(invoice_no, document_type_id, document_category, invoice_date, '
        ' customer_account_id, currency_id, org_id, direction) '
        "VALUES ('BAD-1', 1, 'invoice', '2026-11-09', 900, 1, 10, 0)")
    conn.commit()
    conn.close()
    assert v243.verify(path) is False


def test_rollback_removes_all(tmp_path):
    path = _db_file(tmp_path)
    assert v243.migrate(path, skip_backup=True) is True

    assert v243.rollback(path) is True

    assert not (NEW_TYPE_COLUMNS & table_columns(path, 'type_definitions'))
    assert not (NEW_HEADER_COLUMNS & table_columns(path, 'customer_invoices'))
    assert 'uq_type_default_role' not in index_names(path)
    assert permission_exists(path, v243.DEBIT_PERMISSION) is False
    assert _type_exists(path, 'SRV') is False
    conn = sqlite3.connect(str(path))
    seq = conn.execute(
        "SELECT COUNT(*) FROM number_sequences WHERE code = 'SRV'").fetchone()[0]
    conn.close()
    assert seq == 0
    assert v243.verify(path) is False

    # 回滚幂等
    assert v243.rollback(path) is True