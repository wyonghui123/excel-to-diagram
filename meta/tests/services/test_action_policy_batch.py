# -*- coding: utf-8 -*-
"""动作可用性批量求值（B1-2 下沉）单元测试。

覆盖 `ActionPolicy.evaluate_action` / `evaluate_batch` 的判定顺序与 fail-closed 语义：
权限/条件检查器缺失或抛异常一律返回 `enabled=False`，不得放行。
"""

from unittest.mock import Mock

from meta.services.action_policy import (
    ActionPolicy,
    REASON_NO_PERMISSION,
    REASON_PRECONDITION_FALSE,
    REASON_READONLY_OBJECT,
    REASON_UNSUPPORTED,
)


def _make_meta_object(mutability=None):
    meta = Mock()
    meta.list_config = None
    meta.ui_view_config = None
    meta.import_export = None
    if mutability:
        semantics = Mock()
        semantics.mutability = mutability
        meta.semantics = semantics
    else:
        meta.semantics = None
    return meta


def _ok_permission(_code):
    return True


def _deny_permission(_code):
    return False


def _raise_permission(_code):
    raise RuntimeError('permission backend down')


def _ok_condition(_condition, _record=None):
    return True


def _false_condition(_condition, _record=None):
    return False


def _raise_condition(_condition, _record=None):
    raise RuntimeError('expression engine down')


class TestEvaluateAction:

    def test_plain_action_enabled(self):
        policy = ActionPolicy()
        result = policy.evaluate_action({'id': 'export'})
        assert result.enabled is True
        assert result.reason == ''

    def test_missing_action_id_unsupported(self):
        policy = ActionPolicy()
        result = policy.evaluate_action({'label': '无 id'})
        assert result.enabled is False
        assert result.reason == REASON_UNSUPPORTED

    def test_locked_object_blocks_write_action(self):
        policy = ActionPolicy(_make_meta_object(mutability='locked'))
        result = policy.evaluate_action({'id': 'edit'})
        assert result.enabled is False
        assert result.reason == REASON_READONLY_OBJECT

    def test_locked_object_allows_read_action(self):
        policy = ActionPolicy(_make_meta_object(mutability='locked'))
        result = policy.evaluate_action({'id': 'view'})
        assert result.enabled is True

    def test_permission_denied(self):
        policy = ActionPolicy()
        result = policy.evaluate_action(
            {'id': 'delete', 'permission': 'sales_order:delete'},
            permission_checker=_deny_permission,
        )
        assert result.enabled is False
        assert result.reason == REASON_NO_PERMISSION
        assert result.required_permission == 'sales_order:delete'

    def test_permission_checker_raises_fail_closed(self):
        policy = ActionPolicy()
        result = policy.evaluate_action(
            {'id': 'delete', 'permission': 'sales_order:delete'},
            permission_checker=_raise_permission,
        )
        assert result.enabled is False
        assert result.reason == REASON_NO_PERMISSION

    def test_missing_permission_checker_fail_closed(self):
        policy = ActionPolicy()
        result = policy.evaluate_action(
            {'id': 'delete', 'permission': 'sales_order:delete'})
        assert result.enabled is False
        assert result.reason == REASON_NO_PERMISSION

    def test_permission_granted_then_condition_false(self):
        policy = ActionPolicy()
        result = policy.evaluate_action(
            {'id': 'edit', 'permission': 'sales_order:edit',
             'condition': "self.status == 'draft'"},
            record={'status': 'released'},
            permission_checker=_ok_permission,
            condition_evaluator=_false_condition,
        )
        assert result.enabled is False
        assert result.reason == REASON_PRECONDITION_FALSE

    def test_condition_evaluator_raises_fail_closed(self):
        policy = ActionPolicy()
        result = policy.evaluate_action(
            {'id': 'edit', 'condition': "self.status == 'draft'"},
            record={'status': 'draft'},
            condition_evaluator=_raise_condition,
        )
        assert result.enabled is False
        assert result.reason == REASON_PRECONDITION_FALSE

    def test_missing_condition_evaluator_fail_closed(self):
        policy = ActionPolicy()
        result = policy.evaluate_action(
            {'id': 'edit', 'condition': "self.status == 'draft'"})
        assert result.enabled is False
        assert result.reason == REASON_PRECONDITION_FALSE

    def test_all_checks_pass_enabled(self):
        policy = ActionPolicy()
        result = policy.evaluate_action(
            {'id': 'edit', 'permission': 'sales_order:edit',
             'condition': "self.status == 'draft'"},
            record={'status': 'draft'},
            permission_checker=_ok_permission,
            condition_evaluator=_ok_condition,
        )
        assert result.enabled is True
        assert result.required_permission == 'sales_order:edit'


class TestEvaluateBatch:

    def test_empty_ids_uses_object_bucket(self):
        policy = ActionPolicy()
        actions = [{'id': 'import', 'permission': 'sales_order:create'}]
        result = policy.evaluate_batch(
            ids=[], actions=actions, permission_checker=_ok_permission)
        assert list(result.keys()) == ['_object']
        assert result['_object']['import']['enabled'] is True

    def test_records_dict_maps_by_id(self):
        policy = ActionPolicy()
        actions = [
            {'id': 'edit', 'condition': "self.status == 'draft'"},
            {'id': 'view'},
        ]
        result = policy.evaluate_batch(
            ids=[1, 2],
            actions=actions,
            condition_evaluator=_false_condition,
            records={'1': {'status': 'draft'}, '2': {'status': 'released'}},
        )
        assert result['1']['edit']['enabled'] is False
        assert result['1']['edit']['reason'] == REASON_PRECONDITION_FALSE
        assert result['2']['view']['enabled'] is True

    def test_records_list_aligned_with_ids(self):
        policy = ActionPolicy()
        actions = [{'id': 'edit', 'condition': "self.status == 'draft'"}]
        seen = {}

        def _record_condition(condition, record=None):
            seen[record['id']] = condition
            return record.get('status') == 'draft'

        result = policy.evaluate_batch(
            ids=['a', 'b'],
            actions=actions,
            condition_evaluator=_record_condition,
            records=[{'id': 'a', 'status': 'draft'},
                     {'id': 'b', 'status': 'released'}],
        )
        assert set(seen.keys()) == {'a', 'b'}
        assert result['a']['edit']['enabled'] is True
        assert result['b']['edit']['enabled'] is False

    def test_action_without_id_skipped(self):
        policy = ActionPolicy()
        result = policy.evaluate_batch(
            ids=[], actions=[{'label': 'no id'}, {'id': 'view'}])
        assert '_object' in result
        assert 'view' in result['_object']
        assert len(result['_object']) == 1

    def test_action_ids_are_lowercase_keys(self):
        policy = ActionPolicy()
        result = policy.evaluate_batch(ids=[], actions=[{'id': 'Export'}])
        assert 'export' in result['_object']