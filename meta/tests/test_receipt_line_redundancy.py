# -*- coding: utf-8 -*-
"""[P1-5 2026-11-06] 派生事实声明试点：receipt_line.order_id / order_line_id。

验证三件事：
1. YAML 的 `semantics.redundancy` 被解析进 redundancy_registry；
2. 声明能通过元数据校验（派生来源对象/字段存在）；
3. 一致性审计器能发现并区分缓存列与真源的漂移。
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
    build_receipt_line_fixture,
    repair_order_id,
)


def _defs():
    redundancy_registry.build_from_registry()
    return {
        'order_id': redundancy_registry.get_redundancy('receipt_line', 'order_id'),
        'order_line_id': redundancy_registry.get_redundancy(
            'receipt_line', 'order_line_id'),
    }


def test_receipt_line_declares_stored_redundancy():
    defs = _defs()

    for field_id, red_def in defs.items():
        assert red_def is not None, field_id
        assert red_def.redundancy_type == RedundancyType.STORED
        assert red_def.source_field == 'schedule_id'
        assert red_def.join_path[0].table == 'purchase_order_schedules'
        assert red_def.consistency.strategy == ConsistencyStrategy.SYNC_ON_WRITE

    assert defs['order_id'].derived_from == 'purchase_order_schedule.order_id'
    assert defs['order_line_id'].derived_from == 'purchase_order_schedule.line_id'


def test_declaration_passes_metadata_validation():
    report = MetadataValidator(registry).validate_object('receipt_line')

    derived_errors = [
        e for e in report.errors
        if '派生来源' in e.message or '冗余字段' in e.message
    ]
    assert derived_errors == []


def test_auditor_reports_only_drifted_rows(tmp_path):
    from meta.core.sql_adapters import SQLiteAdapter

    _defs()

    ds = SQLiteAdapter()
    ds.connect(path=str(tmp_path / 'receipt_line_redundancy.db'))
    build_receipt_line_fixture(ds)

    violations = RedundancyAuditor(ds, redundancy_registry).validate_object(
        'receipt_line')

    seen = {(v.record_id, v.field_id) for v in violations}
    assert seen == {(1, 'order_id'), (2, 'order_line_id')}

    repair_order_id(ds)
    remaining = RedundancyAuditor(ds, redundancy_registry).validate_object(
        'receipt_line')
    assert {(v.record_id, v.field_id) for v in remaining} == {(2, 'order_line_id')}
