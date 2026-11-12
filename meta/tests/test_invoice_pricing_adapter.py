# ALLOW_RAW_SQL: 本文件含裸 SQL 播种控制参数，守卫豁免
# -*- coding: utf-8 -*-
"""发票定价模式适配器测试 —— 解析优先级 / 回退 / 策略映射 / 建单快照。

依据: docs/specs/sales-invoice-pricing-spec-2026-11-10.md §3 FR-005
"""
import pytest

pytestmark = pytest.mark.unit

from meta.services import invoice_pricing_adapter as adapter
from meta.services.customer_invoice_service import CustomerInvoiceService
from meta.tests.factories._customer_invoice_helpers import (
    MemoryDataSource,
    build_file,
    type_id,
)

_META_DDL = """
CREATE TABLE IF NOT EXISTS control_parameter_defs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(64) UNIQUE,
    name VARCHAR(128),
    domain VARCHAR(32),
    value_type VARCHAR(16),
    enum_type_id VARCHAR(64),
    target_bo VARCHAR(64),
    default_value VARCHAR(128),
    status VARCHAR(16) DEFAULT 'active',
    description TEXT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS control_parameter_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    control_parameter_id INTEGER,
    org_id INTEGER,
    document_type_id INTEGER,
    line_type_id INTEGER,
    item_group_id INTEGER,
    specificity_rank INTEGER DEFAULT 0,
    value VARCHAR(128),
    status VARCHAR(16) DEFAULT 'active',
    created_at DATETIME
);
"""


def _database(tmp_path, *, default_value='copy_frozen', with_meta=True):
    path = tmp_path / 'app.db'
    conn = build_file(path)
    if not with_meta:
        return MemoryDataSource(conn), conn
    conn.executescript(_META_DDL)
    conn.execute(
        'INSERT INTO control_parameter_defs '
        '(code, name, domain, value_type, enum_type_id, default_value, status) '
        "VALUES ('billing_pricing_mode', '开票定价模式', 'billing', 'enum', "
        "'billing_pricing_mode', ?, 'active')",
        [default_value])
    conn.commit()
    return MemoryDataSource(conn), conn


def _add_value(conn, *, org_id=None, document_type_id=None, rank=0,
               value='copy_frozen', status='active'):
    conn.execute(
        'INSERT INTO control_parameter_values '
        '(control_parameter_id, org_id, document_type_id, specificity_rank, '
        ' value, status) VALUES (1, ?, ?, ?, ?, ?)',
        [org_id, document_type_id, rank, value, status])
    conn.commit()


def test_resolve_defaults_when_metadata_tables_missing(tmp_path):
    ds, _conn = _database(tmp_path, with_meta=False)
    assert adapter.resolve_billing_pricing_mode(ds) == adapter.DEFAULT_MODE


def test_resolve_type_level_value(tmp_path):
    ds, conn = _database(tmp_path)
    sinv = type_id(conn, 'SINV')
    _add_value(conn, document_type_id=sinv, rank=1,
               value='copy_frozen_redetermine_tax')

    assert adapter.resolve_billing_pricing_mode(
        ds, document_type_id=sinv, org_id=10) == 'copy_frozen_redetermine_tax'
    # 非该类型 → 回落控制参数 default_value
    assert adapter.resolve_billing_pricing_mode(
        ds, document_type_id=type_id(conn, 'SCR'), org_id=10) == 'copy_frozen'


def test_org_and_type_beats_type_level(tmp_path):
    ds, conn = _database(tmp_path)
    sinv = type_id(conn, 'SINV')
    _add_value(conn, document_type_id=sinv, rank=1, value='copy_frozen')
    _add_value(conn, org_id=10, document_type_id=sinv, rank=2,
               value='copy_reprice_all')

    assert adapter.resolve_billing_pricing_mode(
        ds, document_type_id=sinv, org_id=10) == 'copy_reprice_all'
    # 其他组织不命中组织级配置，退回类型级
    assert adapter.resolve_billing_pricing_mode(
        ds, document_type_id=sinv, org_id=20) == 'copy_frozen'


def test_org_specific_ignored_without_org_context(tmp_path):
    ds, conn = _database(tmp_path)
    _add_value(conn, org_id=10, rank=5, value='copy_scale_update')

    assert adapter.resolve_billing_pricing_mode(ds) == 'copy_frozen'
    assert adapter.resolve_billing_pricing_mode(
        ds, org_id=10) == 'copy_scale_update'


def test_inactive_and_unknown_values_are_ignored(tmp_path):
    ds, conn = _database(tmp_path)
    _add_value(conn, rank=9, value='copy_frozen', status='inactive')
    _add_value(conn, rank=9, value='not_a_mode')

    assert adapter.resolve_billing_pricing_mode(ds) == 'copy_frozen'


@pytest.mark.parametrize('mode,sap_control,copy_net,copy_tax,reprice,scale', [
    ('copy_frozen', 'D', True, True, 'none', False),
    ('copy_scale_update', 'A', True, True, 'none', True),
    ('copy_reprice_all', 'B', False, False, 'all', False),
    ('copy_manual_reprice_rest', 'C', False, False, 'except_manual', False),
    ('copy_frozen_redetermine_tax', 'G', True, False, 'none', False),
    ('legacy', None, True, True, 'none', False),
])
def test_strategy_mapping(mode, sap_control, copy_net, copy_tax, reprice, scale):
    strategy = adapter.resolve_copy_strategy(mode)
    assert strategy['sap_control'] == sap_control
    assert strategy['copy_net'] is copy_net
    assert strategy['copy_tax'] is copy_tax
    assert strategy['reprice'] == reprice
    assert strategy['scale_update'] is scale


def test_strategy_unknown_mode_falls_back_to_default():
    strategy = adapter.resolve_copy_strategy('does_not_exist')
    assert strategy == adapter.COPY_STRATEGIES[adapter.DEFAULT_MODE]
    assert strategy is not adapter.COPY_STRATEGIES[adapter.DEFAULT_MODE]


def _header_payload(document_type_id):
    return {
        'invoice_date': '2026-11-10',
        'customer_account_id': 900,
        'currency_id': 1,
        'org_id': 10,
        'document_type_id': document_type_id,
    }


def test_prepare_header_resolves_mode_from_control_parameter(tmp_path):
    ds, conn = _database(tmp_path)
    sinv = type_id(conn, 'SINV')
    _add_value(conn, document_type_id=sinv, rank=1,
               value='copy_frozen_redetermine_tax')

    service = CustomerInvoiceService(ds)
    header = service.prepare_header(_header_payload(sinv))
    assert header['billing_pricing_mode'] == 'copy_frozen_redetermine_tax'


def test_prepare_header_keeps_explicit_snapshot(tmp_path):
    ds, conn = _database(tmp_path)
    sinv = type_id(conn, 'SINV')
    _add_value(conn, document_type_id=sinv, rank=1,
               value='copy_frozen_redetermine_tax')

    service = CustomerInvoiceService(ds)
    payload = _header_payload(sinv)
    payload['billing_pricing_mode'] = 'copy_frozen'  # 红冲沿用原票快照
    header = service.prepare_header(payload)
    assert header['billing_pricing_mode'] == 'copy_frozen'


def test_prepare_header_rejects_unknown_explicit_mode(tmp_path):
    ds, _conn = _database(tmp_path)
    sinv = type_id(_conn, 'SINV')
    service = CustomerInvoiceService(ds)
    payload = _header_payload(sinv)
    payload['billing_pricing_mode'] = 'bogus_mode'
    header = service.prepare_header(payload)
    assert header['billing_pricing_mode'] == adapter.DEFAULT_MODE