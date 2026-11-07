# -*- coding: utf-8 -*-
"""规则化收敛 M3 等价性与解释接口测试。

覆盖 FR-002 / FR-003 / FR-010 / FR-011：
  1. 六张层级映射运行时值与旧常量逐项相等；
  2. 层级深度由 profile 决定，授权链只认 scope_anchor；
  3. `dimension_levels` 声明完整；
  4. 组织边界候选推导 + 豁免理由校验；
  5. RuleProvider DB 门面委托；
  6. 统一 explain 四场景信封与只读性。
"""

import json
import os

import pytest

from meta.core import hierarchy_loader
from meta.core.models import registry
from meta.core.org_scope_validator import (
    candidate_org_scope_bos,
    load_exemptions,
    required_org_scope_bos,
)
from meta.core.yaml_loader import get_yaml_schema_dir


def _load_registry():
    if not registry.all():
        registry.reload(get_yaml_schema_dir())
    return registry


# ---------------------------------------------------------------------------
# FR-002：映射等价性
# ---------------------------------------------------------------------------

def test_table_parent_display_code_equivalent():
    expected_tables = {
        'product': 'products',
        'version': 'versions',
        'domain': 'domains',
        'sub_domain': 'sub_domains',
        'service_module': 'service_modules',
        'business_object': 'business_objects',
    }
    expected_parent_fk = {
        'version': 'product_id',
        'domain': 'version_id',
        'sub_domain': 'domain_id',
        'service_module': 'sub_domain_id',
        'business_object': 'service_module_id',
    }
    expected_display = {
        'product': 'name',
        'version': 'name',
        'domain': 'domain_name',
        'sub_domain': 'sub_domain_name',
        'service_module': 'name',
        'business_object': 'name',
    }

    assert hierarchy_loader.get_table_map() == expected_tables
    assert {
        obj: info[2] for obj, info in hierarchy_loader.get_parent_info_map().items()
    } == expected_parent_fk
    assert hierarchy_loader.get_display_field_map() == expected_display
    assert hierarchy_loader.get_code_field_map() == {
        obj: 'code' for obj in expected_tables
    }


def test_child_type_map_default_profile():
    assert hierarchy_loader.get_child_type_map('default') == {
        'product': ['version'],
        'version': ['domain'],
        'domain': ['sub_domain'],
        'sub_domain': [],
    }


def test_child_type_map_full_profile():
    full = hierarchy_loader.get_child_type_map('full', include_extra=True)
    assert full == {
        'product': ['version'],
        'version': ['domain'],
        'domain': ['sub_domain'],
        'sub_domain': ['service_module'],
        'service_module': ['business_object'],
        'business_object': [],
        'org': ['org'],
    }
    assert 'relationship' not in full


def test_scope_chain_is_four_layers():
    assert hierarchy_loader.get_scope_chain() == [
        'product', 'version', 'domain', 'sub_domain',
    ]


def test_dimension_levels_declared():
    levels = hierarchy_loader.get_dimension_levels()
    assert [lv.object for lv in levels] == [
        'product', 'version', 'domain', 'sub_domain',
        'service_module', 'business_object', 'relationship',
    ]
    for lv in levels:
        assert lv.level_type in ('entity', 'association')
        if lv.level_type == 'entity':
            assert lv.owner_field == 'owner_id'
        else:
            assert lv.owner_field is None
    assert [lv.level for lv in levels] == list(range(7))
    assert [lv.parent_level for lv in levels] == [None, 0, 1, 2, 3, 4, 5]
    assert [lv.scope_anchor for lv in levels] == [
        True, True, True, True, False, False, False,
    ]


def test_child_type_is_derived_not_literal():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    targets = [
        'meta/services/permission_dimension_engine.py',
        'meta/services/management_dimension_engine.py',
        'meta/services/condition_permission_service.py',
    ]
    for relative_path in targets:
        with open(os.path.join(root, relative_path), 'r', encoding='utf-8') as handle:
            text = handle.read()
        assert 'CHILD_TYPE_MAP = {' not in text, relative_path


def test_value_help_hierarchy_dims_derived():
    expected = {'version', 'domain', 'sub_domain', 'service_module', 'business_object'}
    derived = {
        lv.object for lv in hierarchy_loader.get_dimension_levels()
        if lv.level > 0 and lv.level_type == 'entity'
    }
    assert derived == expected

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(root, 'meta/core/value_help_providers.py'),
              'r', encoding='utf-8') as handle:
        text = handle.read()
    assert "'version', 'domain', 'sub_domain', 'service_module', 'business_object'" not in text


def test_unknown_dimension_profile_raises():
    assert hierarchy_loader.get_dimension_profiles() == {'default': 4, 'full': 6}
    with pytest.raises(ValueError):
        hierarchy_loader.get_dimension_profile_depth('nope')
    with pytest.raises(ValueError):
        hierarchy_loader.get_child_type_map('nope')


# ---------------------------------------------------------------------------
# FR-003：组织边界推导
# ---------------------------------------------------------------------------

def test_org_scope_candidates_are_derived():
    registry_obj = _load_registry()
    candidates = candidate_org_scope_bos(registry_obj)
    required = required_org_scope_bos(registry_obj)
    assert required
    assert required.issubset(candidates)
    assert len(required) == 43
    # 43 项已声明对象全部来自推导，不存在 Python 常量清单
    import meta.core.org_scope_validator as validator_module
    assert not hasattr(validator_module, 'REQUIRED_ORG_SCOPE_BOS')


def test_org_scope_exemptions_have_reason():
    exemptions = load_exemptions()
    assert exemptions
    assert all(reason.strip() for reason in exemptions.values())


# ---------------------------------------------------------------------------
# FR-010：Provider facade
# ---------------------------------------------------------------------------

def test_rule_provider_doc_flow_facade(monkeypatch):
    sentinel = {'rule_id': 'R-TEST', 'enabled': True}
    import meta.core.doc_flow_rule_store as store
    monkeypatch.setattr(store, 'get_rule', lambda data_source, rule_id: sentinel)

    from meta.core.rule_provider import get_doc_flow_rule
    assert get_doc_flow_rule(object(), 'R-TEST') is sentinel


# ---------------------------------------------------------------------------
# FR-011：统一 explain
# ---------------------------------------------------------------------------

EXPECTED_KEYS = {
    'ok', 'scenario', 'decision', 'rule_id', 'source', 'reason',
    'factors', 'elapsed_ms',
}


def test_explain_state_transition_allowed():
    from meta.core.rule_explainer import explain

    result = explain(
        'sales_order_schedule', 'state_transition',
        from_state='planned', to_state='confirmed',
    )
    assert set(result) == EXPECTED_KEYS
    assert result['ok'] is True
    assert result['decision'] == 'allowed'
    assert result['rule_id'] == 'confirm_sales_order_schedule'
    assert result['source'] == 'yaml'


def test_explain_state_transition_rejected():
    from meta.core.rule_explainer import explain

    result = explain(
        'sales_order_schedule', 'state_transition',
        from_state='planned', to_state='completed',
    )
    assert result['decision'] == 'rejected'
    assert result['reason'] == 'transition_undeclared'
    assert result['factors']['allowed_to_states'] == ['confirmed', 'cancelled']


def test_explain_state_transition_is_read_only():
    from meta.core.rule_explainer import explain

    class _NoExecuteDataSource:
        def execute(self, *args, **kwargs):  # pragma: no cover - 只读断言
            raise AssertionError('explain 不应访问数据库')

        def query(self, *args, **kwargs):  # pragma: no cover
            raise AssertionError('explain 不应访问数据库')

    result = explain(
        'sales_order_schedule', 'state_transition',
        from_state='planned', to_state='confirmed',
        data_source=_NoExecuteDataSource(),
    )
    assert result['decision'] == 'allowed'


def test_explain_default_envelope(monkeypatch):
    import meta.core.action_executor as action_executor
    import meta.core.rule_executor as rule_executor

    class _StubExecutor:
        def __init__(self, ds, engine):
            pass

        def dry_run_defaults(self, meta_obj, data, original_data=None):
            return {
                'success': True,
                'logs': [{
                    'rule_id': 'R-DEF-1',
                    'hit': True,
                    'value': 'X',
                    'target_field': 'code',
                    'skip_reason': None,
                }],
                'auto_filled_fields': {'code': 'X'},
            }

    monkeypatch.setattr(action_executor, 'ActionExecutor', _StubExecutor)
    monkeypatch.setattr(rule_executor, 'RuleEngine', lambda ds: object())

    from meta.core.rule_explainer import explain
    result = explain('item', 'default', data={})
    assert set(result) == EXPECTED_KEYS
    assert result['decision'] == 'applied'
    assert result['rule_id'] == 'R-DEF-1'


def test_explain_permission_envelope(monkeypatch):
    import meta.core.permission_explainer as permission_explainer

    class _StubExplainer:
        def explain(self, user_id, object_type, action_id):
            return {
                'granted': False,
                'steps': [{'step': 3, 'name': 'data_scope', 'passed': False}],
            }

    monkeypatch.setattr(
        permission_explainer, 'get_permission_explainer', lambda: _StubExplainer())

    from meta.core.rule_explainer import explain
    result = explain('item', 'permission', user_id=7, action_id='read')
    assert set(result) == EXPECTED_KEYS
    assert result['decision'] == 'denied'
    assert result['reason'] == 'step_3:data_scope'
    assert result['source'] == 'db'


def test_explain_approval_envelope(monkeypatch):
    import meta.services.document_approval_service as approval_service

    class _StubResolver:
        def __init__(self, data_source):
            pass

        def resolve(self, object_type, record_id):
            return {
                'required': True,
                'policy_code': 'AP-001',
                'amount': 1000,
                'steps': [{'level': 1}],
            }

    monkeypatch.setattr(
        approval_service, 'DocumentApprovalResolver', _StubResolver)

    from meta.core.rule_explainer import explain
    result = explain('purchase_order', 'approval', record_id=1)
    assert set(result) == EXPECTED_KEYS
    assert result['decision'] == 'matched'
    assert result['rule_id'] == 'AP-001'
    assert result['factors']['amount'] == 1000


def test_explain_invalid_input():
    from meta.core.rule_explainer import explain

    with pytest.raises(ValueError):
        explain('item', 'unknown_scenario')
    with pytest.raises(ValueError):
        explain('not_registered_object', 'state_transition',
                from_state='a', to_state='b')
    with pytest.raises(ValueError):
        explain('item', 'permission')


def test_explain_result_is_json_serializable():
    from meta.core.rule_explainer import explain

    result = explain(
        'sales_order_schedule', 'state_transition',
        from_state='planned', to_state='cancelled',
    )
    assert json.dumps(result, ensure_ascii=False)
