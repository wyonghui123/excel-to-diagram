# -*- coding: utf-8 -*-
"""审批策略快照结构校验测试（G-13-6 / spec-approval-workflow §9.13.3）

覆盖：
  ① 合法快照零问题（含 schema_version）；
  ② 缺必填键 / 类型错（steps 非列表、metrics 非字典、amount 布尔、resolved_at 非 ISO）；
  ③ 步骤级：缺 approver_ref、step_no / stage_no 非正整数、approve_mode 非法；
  ④ 版本常量可用（写入方从此取值，避免各处硬编码）。
"""

import pytest

pytestmark = pytest.mark.unit

from meta.core.policy_snapshot import (
    SNAPSHOT_SCHEMA_VERSION, build_snapshot_header, snapshot_problems_for_log,
    validate_snapshot)


def _valid_snapshot(**overrides):
    snapshot = {
        'schema_version': SNAPSHOT_SCHEMA_VERSION,
        'object_type': 'purchase_order',
        'trigger_action': 'submit',
        'policy_id': 1,
        'policy_code': 'PO-DEFAULT',
        'policy_name': '采购订单默认审批',
        'policy_version': 1,
        'priority': 10,
        'task_type': 'approval',
        'hit_policy': 'first',
        'amount': 12000.0,
        'steps': [
            {'stage_no': 1, 'step_no': 1, 'approver_type': 'role',
             'approver_ref': 'procurement_manager', 'approve_mode': 'any',
             'sla_hours': 24, 'min_amount': None, 'max_amount': None},
        ],
        'conditions': [{'field_id': 'gross_amount', 'operator': 'ge', 'value': 1000}],
        'conditions_explain': [
            {'field': 'gross_amount', 'op': 'ge', 'expected': 1000, 'actual': 12000,
             'passed': True},
        ],
        'metrics': {'gross_amount': 12000.0},
        'resolved_at': '2026-11-16T10:00:00',
    }
    snapshot.update(overrides)
    return snapshot


class TestValidSnapshot:
    def test_合法快照无问题(self):
        assert validate_snapshot(_valid_snapshot()) == []

    def test_空步骤列表合法(self):
        assert validate_snapshot(_valid_snapshot(steps=[])) == []

    def test_amount_允许_None(self):
        assert validate_snapshot(_valid_snapshot(amount=None)) == []

    def test_非字典直接报错(self):
        assert validate_snapshot(['not-a-dict']) == ['快照不是字典']


class TestFieldLevel:
    def test_缺必填键(self):
        snapshot = _valid_snapshot()
        snapshot.pop('steps')
        snapshot.pop('policy_id')
        problems = validate_snapshot(snapshot)
        assert any('缺少字段 steps' in p for p in problems)
        assert any('缺少字段 policy_id' in p for p in problems)

    def test_schema_version_非法(self):
        problems = validate_snapshot(_valid_snapshot(schema_version=0))
        assert any('schema_version 非法' in p for p in problems)
        problems = validate_snapshot(_valid_snapshot(schema_version='1'))
        assert any('schema_version 非法' in p for p in problems)

    def test_steps_非列表(self):
        problems = validate_snapshot(_valid_snapshot(steps={'step_no': 1}))
        assert any('steps 必须是列表' in p for p in problems)

    def test_metrics_非字典(self):
        problems = validate_snapshot(_valid_snapshot(metrics=[]))
        assert any('metrics 必须是字典' in p for p in problems)

    def test_amount_布尔不算数字(self):
        problems = validate_snapshot(_valid_snapshot(amount=True))
        assert any('amount 必须是数字或 None' in p for p in problems)

    def test_hit_policy_必须非空字符串(self):
        problems = validate_snapshot(_valid_snapshot(hit_policy=''))
        assert any('hit_policy 必须是非空字符串' in p for p in problems)

    def test_resolved_at_非_ISO(self):
        problems = validate_snapshot(_valid_snapshot(resolved_at='昨天'))
        assert any('resolved_at 不是 ISO 时间' in p for p in problems)


class TestStepLevel:
    def test_步骤缺_approver_ref(self):
        step = _valid_snapshot()['steps'][0]
        step.pop('approver_ref')
        problems = validate_snapshot(_valid_snapshot(steps=[step]))
        assert any('steps[0] 缺少字段 approver_ref' in p for p in problems)

    def test_step_no_必须正整数(self):
        step = dict(_valid_snapshot()['steps'][0], step_no=0)
        problems = validate_snapshot(_valid_snapshot(steps=[step]))
        assert any('step_no 必须是 ≥1 的整数' in p for p in problems)

    def test_stage_no_必须正整数(self):
        step = dict(_valid_snapshot()['steps'][0], stage_no=0)
        problems = validate_snapshot(_valid_snapshot(steps=[step]))
        assert any('stage_no 必须是 ≥1 的整数' in p for p in problems)

    def test_stage_no_缺省不报错(self):
        step = dict(_valid_snapshot()['steps'][0])
        step.pop('stage_no')
        assert validate_snapshot(_valid_snapshot(steps=[step])) == []

    def test_approve_mode_非法(self):
        step = dict(_valid_snapshot()['steps'][0], approve_mode='first')
        problems = validate_snapshot(_valid_snapshot(steps=[step]))
        assert any('approve_mode 非法' in p for p in problems)

    def test_步骤元素非字典(self):
        problems = validate_snapshot(_valid_snapshot(steps=['x']))
        assert any('steps[0] 不是字典' in p for p in problems)


class TestHelpers:
    def test_版本常量可用(self):
        assert SNAPSHOT_SCHEMA_VERSION >= 1
        assert build_snapshot_header() == {'schema_version': SNAPSHOT_SCHEMA_VERSION}

    def test_问题清单可压成一行(self):
        snapshot = _valid_snapshot()
        snapshot.pop('steps')
        text = snapshot_problems_for_log(snapshot)
        assert '缺少字段 steps' in text
        assert '\n' not in text
