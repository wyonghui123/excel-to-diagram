# -*- coding: utf-8 -*-
"""[P2 2026-11-06] 聚合型派生事实声明：purchase_order.gross_amount。

验证四件事：
1. YAML 的 `semantics.redundancy.aggregate` 被解析为 AggregateSpec；
2. 声明能通过元数据校验（来源对象 / 维度键 / 被聚合列存在）；
3. 一致性审计器按明细聚合值比对缓存列，只报漂移行；
4. 审计为只读操作，不改写缓存列（写入仍由服务层负责）。
"""

from meta.core.consistency_guard import RedundancyAuditor
from meta.core.metadata_validator import MetadataValidator
from meta.core.models import registry
from meta.core.redundancy_registry import (
    ConsistencyStrategy,
    RedundancyType,
    redundancy_registry,
)
from meta.tests.factories._redundancy_helpers import (
    build_purchase_order_aggregate_fixture,
    repair_purchase_order_gross_amount,
)


def _aggregate_def():
    redundancy_registry.build_from_registry()
    return redundancy_registry.get_redundancy('purchase_order', 'gross_amount')


def test_purchase_order_declares_aggregate_redundancy():
    red_def = _aggregate_def()

    assert red_def is not None
    assert red_def.redundancy_type == RedundancyType.STORED
    assert red_def.consistency.strategy == ConsistencyStrategy.SYNC_ON_WRITE
    assert red_def.aggregate is not None
    assert red_def.aggregate.func == 'sum'
    assert red_def.aggregate.table == 'purchase_order_line'
    assert red_def.aggregate.group_key == 'order_id'
    assert red_def.aggregate.value == 'gross_amount'
    assert red_def.aggregate.tolerance == 0.0001


def test_declaration_passes_metadata_validation():
    _aggregate_def()

    report = MetadataValidator(registry).validate_object('purchase_order')

    aggregate_errors = [e for e in report.errors if '聚合冗余' in e.message]
    assert aggregate_errors == []


def test_auditor_reports_only_drifted_rows(tmp_path):
    from meta.core.sql_adapters import SQLiteAdapter

    _aggregate_def()

    ds = SQLiteAdapter()
    ds.connect(path=str(tmp_path / 'purchase_order_aggregate.db'))
    build_purchase_order_aggregate_fixture(ds)

    auditor = RedundancyAuditor(ds, redundancy_registry)
    violations = auditor.validate_object('purchase_order')

    seen = {(v.record_id, v.field_id) for v in violations}
    # 订单 2：缓存 90 vs 明细 100；订单 4：无明细但残留 50
    assert seen == {(2, 'gross_amount'), (4, 'gross_amount')}

    expected = {v.record_id: v.expected_value for v in violations}
    assert expected[2] == 100
    assert expected[4] == 0

    # 审计只读：修数前缓存列保持不变
    row = ds.execute(
        'SELECT gross_amount FROM purchase_orders WHERE id = 2').fetchone()
    assert row[0] == 90

    repair_purchase_order_gross_amount(ds)
    remaining = RedundancyAuditor(ds, redundancy_registry).validate_object(
        'purchase_order')
    assert {(v.record_id, v.field_id) for v in remaining} == {
        (4, 'gross_amount')}


def test_audit_entry_reports_violations(tmp_path):
    """meta.tools.redundancy_audit 是声明的运行入口，输出机读报告。"""
    from meta.core.sql_adapters import SQLiteAdapter
    from meta.tools.redundancy_audit import audit_all

    _aggregate_def()

    ds = SQLiteAdapter()
    ds.connect(path=str(tmp_path / 'audit_entry.db'))
    build_purchase_order_aggregate_fixture(ds)

    report = audit_all(
        database='audit_entry.db', object_ids=['purchase_order'], ds=ds)

    assert report['objects_with_stored_redundancy'] == 1
    assert report['violation_count'] == 2
    assert {(v['record_id'], v['field_id']) for v in report['violations']} == {
        (2, 'gross_amount'), (4, 'gross_amount')}
