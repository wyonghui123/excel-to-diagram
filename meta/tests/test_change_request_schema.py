# -*- coding: utf-8 -*-
"""test_change_request_schema.py

M3 T6：变更申请 YAML 契约（FR-007 头/行表 + FR-008 状态机 + FR-011 派生字段）

覆盖：
  S1 change_request.yaml / change_request_line.yaml 可解析（不依赖 registry / DB）
  S2 5 条 state_transition 边：state_field == status、triggers 含 before_update、
     action_ref 非空且与边一一对应、ui_hints 三要素齐备（label/icon/confirm_message）
  S3 fail 边 ui_hints.hidden == True（仅系统内部使用）
  S4 draft→submitted / submitted→{approved,rejected} 三条边无 side_effects
  S5 FR-011：派生字段 fulfillment_status 作为 state_field ⇒ 加载期 ValueError
     （state_field == status 的对照 yaml 可正常解析）

设计取舍：
  - 用 parse_meta_object(直接 yaml.safe_load) 而不用 load_yaml_file，
    避免 YAML 缓存与 aspects/shared_props 解析干扰；
  - 只读契约，不落库。
"""
import os
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.models import RuleTrigger
from meta.core.yaml_loader import get_yaml_schema_dir, parse_meta_object


# (rule_id, from_state, to_state, action_ref)
EDGES = [
    ('submit_change_request', 'draft', 'submitted', 'change_request:submit'),
    ('approve_change_request', 'submitted', 'approved', 'change_request:approve'),
    ('reject_change_request', 'submitted', 'rejected', 'change_request:reject'),
    ('apply_change_request', 'approved', 'applied', 'change_request:apply'),
    ('fail_change_request', 'approved', 'failed', 'change_request:apply'),
]


def _load(name: str):
    path = Path(get_yaml_schema_dir()) / name
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    return parse_meta_object(data, source_file=str(path))


def _rules(obj):
    return {rule.id: rule for rule in obj.rules}


# ---------------------------------------------------------------- S1 可解析

class TestSchemaLoads:
    def test_s1_change_request_header(self):
        obj = _load('change_request.yaml')
        assert obj is not None
        assert obj.id == 'change_request'
        assert obj.table_name == 'change_requests'
        ids = {f.id for f in obj.fields}
        assert {'target_object_type', 'target_object_id',
                'target_revision_no', 'status'} <= ids

    def test_s1_change_request_line(self):
        obj = _load('change_request_line.yaml')
        assert obj is not None
        assert obj.id == 'change_request_line'
        assert obj.table_name == 'change_request_lines'
        assert obj.parent_object == 'change_request'
        assert obj.hierarchy['enabled'] is True
        assert obj.hierarchy['parent_field'] == 'change_request_id'
        ids = {f.id for f in obj.fields}
        assert {'change_request_id', 'line_key', 'field_name',
                'old_value', 'new_value'} <= ids


# ---------------------------------------------------------------- S2 5 条边

class TestStateTransitions:
    @pytest.mark.parametrize('rule_id,from_state,to_state,action_ref', EDGES)
    def test_s2_edge_contract(self, rule_id, from_state, to_state, action_ref):
        rule = _rules(_load('change_request.yaml'))[rule_id]
        assert rule.state_field == 'status'
        assert rule.from_states == [from_state]
        assert rule.to_state == to_state
        assert RuleTrigger.BEFORE_UPDATE in rule.triggers
        assert rule.action_ref == action_ref

        hints = rule.ui_hints
        assert hints is not None
        assert hints.label, '%s 缺 ui_hints.label' % rule_id
        assert hints.icon, '%s 缺 ui_hints.icon' % rule_id
        assert hints.confirm_message, '%s 缺 ui_hints.confirm_message' % rule_id

    def test_s2_five_edges_only(self):
        assert set(_rules(_load('change_request.yaml'))) == {e[0] for e in EDGES}

    def test_s3_fail_edge_hidden(self):
        rule = _rules(_load('change_request.yaml'))['fail_change_request']
        assert rule.ui_hints.hidden is True

    def test_s4_no_side_effects(self):
        """draft→submitted / submitted→approved / submitted→rejected 均无副作用声写。"""
        rules = _rules(_load('change_request.yaml'))
        for rule_id in ('submit_change_request', 'approve_change_request',
                        'reject_change_request'):
            assert rules[rule_id].side_effects == [], rule_id


# ---------------------------------------------------------------- S5 FR-011

def _probe_yaml(state_field: str) -> dict:
    return {
        'id': 'cr_probe',
        'name': '探针对象',
        'table_name': 'cr_probe',
        'fields': [
            {'id': 'id', 'name': 'ID', 'type': 'integer', 'db_column': 'id'},
            {'id': 'status', 'name': '状态', 'type': 'string', 'db_column': 'status'},
            {'id': 'fulfillment_status', 'name': '履约状态', 'type': 'string',
             'db_column': 'fulfillment_status'},
        ],
        'rules': [{
            'id': 'probe_transition',
            'name': '探针迁移',
            'type': 'state_transition',
            'state_field': state_field,
            'from_states': ['a'],
            'to_state': 'b',
            'triggers': ['before_update'],
        }],
    }


class TestDerivedStateField:
    def test_s5_derived_field_rejected_at_load_time(self, tmp_path):
        path = tmp_path / 'cr_probe.yaml'
        path.write_text(
            yaml.safe_dump(_probe_yaml('fulfillment_status'),
                           allow_unicode=True, sort_keys=False),
            encoding='utf-8',
        )

        with pytest.raises(ValueError) as ei:
            parse_meta_object(
                yaml.safe_load(path.read_text(encoding='utf-8')),
                source_file=str(path),
            )

        msg = str(ei.value)
        assert '派生字段' in msg
        assert 'fulfillment_status' in msg
        assert 'cr_probe.yaml' in msg

    def test_s5_status_field_control_passes(self, tmp_path):
        """对照：同一份 yaml 用 status 作 state_field 可正常解析（证明失败源自派生字段）。"""
        path = tmp_path / 'cr_probe_ok.yaml'
        path.write_text(
            yaml.safe_dump(_probe_yaml('status'), allow_unicode=True, sort_keys=False),
            encoding='utf-8',
        )
        obj = parse_meta_object(
            yaml.safe_load(path.read_text(encoding='utf-8')),
            source_file=str(path),
        )
        assert obj.rules[0].state_field == 'status'
