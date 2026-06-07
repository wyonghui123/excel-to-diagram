import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
ActionPolicy 单元测试

测试动作策略引擎的核心逻辑：
1. has_crud_action - CRUD 操作检测
2. should_show_action - 动作显示判断
3. should_show_import/export - 导入导出显示策略
4. should_show_create/edit/delete - CRUD 按钮显示策略
5. get_allowed_actions - 基于 mutability 的动作过滤
6. filter_actions_by_mutability - 动作列表过滤
7. get_default_actions - 默认动作生成
8. create_action_policy - 工厂函数
9. 无 meta_object 时的默认行为
"""

import pytest
from unittest.mock import Mock

from meta.services.action_policy import (
    ActionPolicy,
    ActionDefinition,
    ActionPolicyConfig,
    create_action_policy,
)


def _make_meta_object(actions=None, import_export=None, mutability=None):
    meta = Mock()
    list_config = Mock()
    list_config.actions = actions or []
    meta.list_config = list_config
    meta.import_export = import_export

    if mutability:
        semantics = Mock()
        semantics.mutability = mutability
        meta.semantics = semantics
    else:
        meta.semantics = None

    return meta


class TestActionPolicyInit:

    def test_init_without_meta_object(self):
        policy = ActionPolicy()
        assert policy.meta_object is None
        assert len(policy._existing_actions) == 0
        assert policy._import_export_enabled is False

    def test_init_with_meta_object(self):
        meta = _make_meta_object(
            actions=[{'id': 'create'}, {'id': 'edit'}],
            import_export={'enabled': True},
        )
        policy = ActionPolicy(meta)
        assert 'create' in policy._existing_actions
        assert 'edit' in policy._existing_actions
        assert policy._import_export_enabled is True

    def test_init_with_empty_actions(self):
        meta = _make_meta_object(actions=[])
        policy = ActionPolicy(meta)
        assert len(policy._existing_actions) == 0

    def test_init_with_none_list_config(self):
        meta = Mock()
        meta.list_config = None
        meta.import_export = None
        meta.semantics = None
        policy = ActionPolicy(meta)
        assert len(policy._existing_actions) == 0


class TestHasCrudAction:

    def test_has_create_action(self):
        meta = _make_meta_object(actions=[{'id': 'create'}])
        policy = ActionPolicy(meta)
        assert policy.has_crud_action('create') is True

    def test_has_new_action_as_create(self):
        meta = _make_meta_object(actions=[{'id': 'new'}])
        policy = ActionPolicy(meta)
        assert policy.has_crud_action('create') is True

    def test_has_add_action_as_create(self):
        meta = _make_meta_object(actions=[{'id': 'add'}])
        policy = ActionPolicy(meta)
        assert policy.has_crud_action('create') is True

    def test_has_update_action(self):
        meta = _make_meta_object(actions=[{'id': 'edit'}])
        policy = ActionPolicy(meta)
        assert policy.has_crud_action('update') is True

    def test_has_modify_action_as_update(self):
        meta = _make_meta_object(actions=[{'id': 'modify'}])
        policy = ActionPolicy(meta)
        assert policy.has_crud_action('update') is True

    def test_has_delete_action(self):
        meta = _make_meta_object(actions=[{'id': 'delete'}])
        policy = ActionPolicy(meta)
        assert policy.has_crud_action('delete') is True

    def test_has_remove_action_as_delete(self):
        meta = _make_meta_object(actions=[{'id': 'remove'}])
        policy = ActionPolicy(meta)
        assert policy.has_crud_action('delete') is True

    def test_no_create_action(self):
        meta = _make_meta_object(actions=[{'id': 'edit'}, {'id': 'delete'}])
        policy = ActionPolicy(meta)
        assert policy.has_crud_action('create') is False

    def test_no_meta_object(self):
        policy = ActionPolicy()
        assert policy.has_crud_action('create') is False

    def test_unknown_action_type(self):
        meta = _make_meta_object(actions=[{'id': 'create'}])
        policy = ActionPolicy(meta)
        assert policy.has_crud_action('unknown') is False

    def test_case_insensitive_action_id(self):
        meta = _make_meta_object(actions=[{'id': 'Create'}])
        policy = ActionPolicy(meta)
        assert policy.has_crud_action('create') is True


class TestShouldShowAction:

    def test_show_read_action(self):
        policy = ActionPolicy()
        assert policy.should_show_action('read') is True
        assert policy.should_show_action('view') is True
        assert policy.should_show_action('detail') is True

    def test_show_other_action(self):
        policy = ActionPolicy()
        assert policy.should_show_action('create') is True

    def test_empty_action_id(self):
        policy = ActionPolicy()
        assert policy.should_show_action('') is False

    def test_none_action_id(self):
        policy = ActionPolicy()
        assert policy.should_show_action(None) is False


class TestShouldShowImportExport:

    def test_show_import_when_enabled_and_has_create(self):
        meta = _make_meta_object(
            actions=[{'id': 'create'}],
            import_export={'enabled': True},
        )
        policy = ActionPolicy(meta)
        assert policy.should_show_import() is True

    def test_hide_import_when_no_create_action(self):
        meta = _make_meta_object(
            actions=[{'id': 'edit'}],
            import_export={'enabled': True},
        )
        policy = ActionPolicy(meta)
        assert policy.should_show_import() is False

    def test_hide_import_when_not_enabled(self):
        meta = _make_meta_object(
            actions=[{'id': 'create'}],
            import_export=None,
        )
        policy = ActionPolicy(meta)
        assert policy.should_show_import() is False

    def test_show_export_when_enabled(self):
        meta = _make_meta_object(
            import_export={'enabled': True},
        )
        policy = ActionPolicy(meta)
        assert policy.should_show_export() is True

    def test_hide_export_when_not_enabled(self):
        meta = _make_meta_object(import_export=None)
        policy = ActionPolicy(meta)
        assert policy.should_show_export() is False


class TestShouldShowCrud:

    def test_show_create(self):
        meta = _make_meta_object(actions=[{'id': 'create'}])
        policy = ActionPolicy(meta)
        assert policy.should_show_create() is True

    def test_hide_create(self):
        meta = _make_meta_object(actions=[{'id': 'edit'}])
        policy = ActionPolicy(meta)
        assert policy.should_show_create() is False

    def test_show_edit(self):
        meta = _make_meta_object(actions=[{'id': 'edit'}])
        policy = ActionPolicy(meta)
        assert policy.should_show_edit() is True

    def test_hide_edit(self):
        meta = _make_meta_object(actions=[{'id': 'create'}])
        policy = ActionPolicy(meta)
        assert policy.should_show_edit() is False

    def test_show_delete(self):
        meta = _make_meta_object(actions=[{'id': 'delete'}])
        policy = ActionPolicy(meta)
        assert policy.should_show_delete() is True

    def test_hide_delete(self):
        meta = _make_meta_object(actions=[{'id': 'create'}])
        policy = ActionPolicy(meta)
        assert policy.should_show_delete() is False


class TestGetAllowedActions:

    def test_locked_returns_readonly_actions(self):
        meta = _make_meta_object(
            actions=[{'id': 'create'}, {'id': 'edit'}, {'id': 'delete'}, {'id': 'view'}],
            mutability='locked',
        )
        policy = ActionPolicy(meta)
        allowed = policy.get_allowed_actions()
        assert 'read' in allowed
        assert 'view' in allowed
        assert 'export' in allowed
        assert 'detail' in allowed
        assert 'create' not in allowed
        assert 'edit' not in allowed
        assert 'delete' not in allowed

    def test_fully_editable_returns_all_actions(self):
        meta = _make_meta_object(
            actions=[{'id': 'create'}, {'id': 'edit'}, {'id': 'delete'}],
            mutability='fully_editable',
        )
        policy = ActionPolicy(meta)
        allowed = policy.get_allowed_actions()
        assert 'create' in allowed
        assert 'edit' in allowed
        assert 'delete' in allowed

    def test_extensible_returns_all_actions(self):
        meta = _make_meta_object(
            actions=[{'id': 'create'}, {'id': 'edit'}],
            mutability='extensible',
        )
        policy = ActionPolicy(meta)
        allowed = policy.get_allowed_actions()
        assert 'create' in allowed
        assert 'edit' in allowed

    def test_no_mutability_returns_all_actions(self):
        meta = _make_meta_object(
            actions=[{'id': 'create'}, {'id': 'edit'}],
        )
        policy = ActionPolicy(meta)
        allowed = policy.get_allowed_actions()
        assert 'create' in allowed
        assert 'edit' in allowed


class TestFilterActionsByMutability:

    def test_locked_filters_write_actions(self):
        meta = _make_meta_object(mutability='locked')
        policy = ActionPolicy(meta)
        actions = [
            {'id': 'create'}, {'id': 'edit'}, {'id': 'delete'},
            {'id': 'view'}, {'id': 'export'},
        ]
        filtered = policy.filter_actions_by_mutability(actions)
        filtered_ids = [a['id'] for a in filtered]
        assert 'create' not in filtered_ids
        assert 'edit' not in filtered_ids
        assert 'delete' not in filtered_ids
        assert 'view' in filtered_ids
        assert 'export' in filtered_ids

    def test_extensible_keeps_all(self):
        meta = _make_meta_object(mutability='extensible')
        policy = ActionPolicy(meta)
        actions = [
            {'id': 'create'}, {'id': 'edit'}, {'id': 'delete'},
        ]
        filtered = policy.filter_actions_by_mutability(actions)
        assert len(filtered) == 3

    def test_fully_editable_keeps_all(self):
        meta = _make_meta_object(mutability='fully_editable')
        policy = ActionPolicy(meta)
        actions = [
            {'id': 'create'}, {'id': 'edit'}, {'id': 'delete'},
        ]
        filtered = policy.filter_actions_by_mutability(actions)
        assert len(filtered) == 3

    def test_no_mutability_keeps_all(self):
        meta = _make_meta_object()
        policy = ActionPolicy(meta)
        actions = [
            {'id': 'create'}, {'id': 'edit'}, {'id': 'delete'},
        ]
        filtered = policy.filter_actions_by_mutability(actions)
        assert len(filtered) == 3

    def test_locked_filters_new_and_add(self):
        meta = _make_meta_object(mutability='locked')
        policy = ActionPolicy(meta)
        actions = [
            {'id': 'new'}, {'id': 'add'}, {'id': 'modify'},
            {'id': 'remove'}, {'id': 'view'},
        ]
        filtered = policy.filter_actions_by_mutability(actions)
        filtered_ids = [a['id'] for a in filtered]
        assert 'new' not in filtered_ids
        assert 'add' not in filtered_ids
        assert 'modify' not in filtered_ids
        assert 'remove' not in filtered_ids
        assert 'view' in filtered_ids


class TestGetDefaultActions:

    def test_generates_import_and_export(self):
        meta = _make_meta_object(
            actions=[{'id': 'create'}],
            import_export={'enabled': True},
        )
        policy = ActionPolicy(meta)
        actions = policy.get_default_actions()
        action_ids = [a.id for a in actions]
        assert 'import' in action_ids
        assert 'export' in action_ids

    def test_generates_only_export_when_no_create(self):
        meta = _make_meta_object(
            actions=[{'id': 'edit'}],
            import_export={'enabled': True},
        )
        policy = ActionPolicy(meta)
        actions = policy.get_default_actions()
        action_ids = [a.id for a in actions]
        assert 'import' not in action_ids
        assert 'export' in action_ids

    def test_generates_nothing_when_no_import_export(self):
        meta = _make_meta_object(actions=[{'id': 'create'}])
        policy = ActionPolicy(meta)
        actions = policy.get_default_actions()
        assert len(actions) == 0

    def test_action_definitions_have_correct_properties(self):
        meta = _make_meta_object(
            actions=[{'id': 'create'}],
            import_export={'enabled': True},
        )
        policy = ActionPolicy(meta)
        actions = policy.get_default_actions()
        import_action = next(a for a in actions if a.id == 'import')
        assert import_action.label == '导入'
        assert import_action.icon == 'upload'
        assert import_action.type == 'default'


class TestIsReadonly:

    def test_locked_is_readonly(self):
        meta = _make_meta_object(mutability='locked')
        policy = ActionPolicy(meta)
        assert policy.is_readonly() is True

    def test_fully_editable_is_not_readonly(self):
        meta = _make_meta_object(mutability='fully_editable')
        policy = ActionPolicy(meta)
        assert policy.is_readonly() is False

    def test_extensible_is_not_readonly(self):
        meta = _make_meta_object(mutability='extensible')
        policy = ActionPolicy(meta)
        assert policy.is_readonly() is False

    def test_no_mutability_is_not_readonly(self):
        meta = _make_meta_object()
        policy = ActionPolicy(meta)
        assert policy.is_readonly() is False

    def test_no_meta_object_is_not_readonly(self):
        policy = ActionPolicy()
        assert policy.is_readonly() is False


class TestCreateActionPolicyFactory:

    def test_creates_policy_with_meta_object(self):
        meta = _make_meta_object(actions=[{'id': 'create'}])
        policy = create_action_policy(meta)
        assert isinstance(policy, ActionPolicy)
        assert policy.meta_object is meta

    def test_creates_policy_without_meta_object(self):
        policy = create_action_policy()
        assert isinstance(policy, ActionPolicy)
        assert policy.meta_object is None


class TestActionDefinition:

    def test_default_values(self):
        action = ActionDefinition(id='test')
        assert action.id == 'test'
        assert action.label is None
        assert action.icon is None
        assert action.type == 'default'
        assert action.position is None
        assert action.confirm is None

    def test_custom_values(self):
        action = ActionDefinition(
            id='delete',
            label='删除',
            icon='trash',
            type='danger',
            position='row',
            confirm='确认删除？',
        )
        assert action.id == 'delete'
        assert action.label == '删除'
        assert action.icon == 'trash'
        assert action.type == 'danger'
        assert action.position == 'row'
        assert action.confirm == '确认删除？'


class TestMutabilityWithDictSemantics:

    def test_dict_semantics_mutability(self):
        meta = Mock()
        meta.list_config = None
        meta.import_export = None
        meta.semantics = {'mutability': 'locked'}
        policy = ActionPolicy(meta)
        assert policy._get_mutability() == 'locked'
        assert policy.is_readonly() is True

    def test_dict_semantics_no_mutability(self):
        meta = Mock()
        meta.list_config = None
        meta.import_export = None
        meta.semantics = {'other_key': 'value'}
        policy = ActionPolicy(meta)
        assert policy._get_mutability() is None
        assert policy.is_readonly() is False
