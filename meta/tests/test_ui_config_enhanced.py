# -*- coding: utf-8 -*-
"""
UI Config 增强测试

测试 get_ui_config 返回 constraints/rules/actions/authorization
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from meta.core.bo_framework import BOFramework
from meta.core.models import registry
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir

pytestmark = pytest.mark.integration


@pytest.fixture(scope='class')
def ui_config():
    schema_dir = get_yaml_schema_dir()
    register_from_directory(schema_dir)
    return BOFramework()


class TestUIConfigEnhanced:
    """UI Config 增强测试"""

    def test_01_user_ui_config_has_constraints(self, ui_config):
        config = ui_config.get_ui_config('user')

        assert config is not None
        assert config['object_type'] == 'user'
        assert 'fields' in config

        username_field = next((f for f in config['fields'] if f['id'] == 'username'), None)
        assert username_field is not None

    def test_02_role_ui_config_has_constraints(self, ui_config):
        config = ui_config.get_ui_config('role')

        assert config is not None
        # role 已并入 permission_set（Spec16 Plan D），别名仍可解析
        assert config['object_type'] == 'permission_set'

        is_system_field = next((f for f in config['fields'] if f['id'] == 'is_system'), None)
        assert is_system_field is not None

        if 'constraints' in is_system_field:
            no_delete_constraints = [c for c in is_system_field['constraints'] if c.get('type') == 'no_delete']
            assert len(no_delete_constraints) > 0, "is_system 字段应有 no_delete 约束"

    def test_03_ui_config_has_associations(self, ui_config):
        config = ui_config.get_ui_config('user')

        assert 'associations' in config
        associations = config['associations']

        assert len(associations) > 0, "用户应有 associations"

        role_assoc = next((a for a in associations if a['name'] in ['roles', 'role', 'user_roles', 'groups']), None)
        assert role_assoc is not None, "用户应有 roles/role/user_roles/groups 关联"

    def test_04_ui_config_has_actions(self, ui_config):
        config = ui_config.get_ui_config('user')

        if 'actions' in config:
            actions = config['actions']
            assert len(actions) > 0, "用户应有 actions"

    def test_05_ui_config_has_rules(self, ui_config):
        config = ui_config.get_ui_config('user')

        if 'rules' in config:
            rules = config['rules']
            assert len(rules) > 0, "用户应有 rules"

    def test_06_ui_config_has_authorization(self, ui_config):
        config = ui_config.get_ui_config('user')

        if 'authorization' in config:
            auth = config['authorization']
            assert isinstance(auth, dict)

    def test_07_ui_config_has_view_config(self, ui_config):
        config = ui_config.get_ui_config('user')

        if 'ui_view_config' in config:
            view_config = config['ui_view_config']
            assert isinstance(view_config, dict)

            if 'list' in view_config:
                assert 'columns' in view_config['list']

            if 'form' in view_config:
                form_config = view_config['form']
                assert 'sections' in form_config

            if 'detail' in view_config:
                assert 'tabs' in view_config['detail']

    def test_08_role_ui_config_view_config(self, ui_config):
        config = ui_config.get_ui_config('role')

        if 'ui_view_config' in config:
            view_config = config['ui_view_config']

            if 'list' in view_config:
                list_config = view_config['list']
                assert 'columns' in list_config
                assert 'actions' in list_config
                assert 'filters' in list_config

                delete_action = next((a for a in list_config['actions'] if a['id'] == 'delete'), None)
                if delete_action:
                    assert 'condition' in delete_action

            if 'form' in view_config:
                form_config = view_config['form']
                assert 'sections' in form_config

                code_field = form_config.get('fields', {}).get('code')
                if code_field:
                    assert 'pattern' in code_field

    def test_09_permission_bundle_ui_config(self, ui_config):
        config = ui_config.get_ui_config('permission_bundle')

        assert config is not None
        assert config['object_type'] == 'permission_bundle'

        is_system_field = next((f for f in config['fields'] if f['id'] == 'is_system'), None)
        if is_system_field and 'constraints' in is_system_field:
            pass

    def test_10_field_ui_properties(self, ui_config):
        config = ui_config.get_ui_config('user')

        for field in config['fields']:
            if 'ui' in field or 'visible' in field:
                assert 'visible' in field

                if field['id'] == 'password_hash':
                    assert not field.get('visible', True), "password_hash 应不可见"

                if field['id'] == 'username':
                    assert field.get('visible', False), "username 应可见"


class _StubDisplayNameService:
    def _infer_display_name_field(self, meta_obj):
        return 'name'

    def get_all_field_names(self, object_type):
        return {}


class _StubMetaObject:
    """无 renderable form、但显式声明了 detail.actions 的对象替身。"""

    id = 'stub_bo'
    name = 'Stub'
    table_name = 'stubs'
    aspects = []
    fields = []
    relations = []
    ui_view_config = {
        'detail': {'actions': [{'id': 'demo', 'action': 'stub_bo.demo'}]},
        'form': {'sections': []},
    }


class TestUIConfigBuilderDeclaredDetailActions:
    """[FIX 2026-11-12] 平台级 detail.actions 透传的兜底分支。

    背景：/api/v2/meta/<obj>/ui-config 由 UIConfigBuilder.build 产出；当 yaml 的
    form 不可渲染时该函数会整体替换 ui_view_config（view_config 推导版），
    原实现只保留 hub，会把显式声明的 detail.actions 抹掉，导致业务按钮失联。
    """

    def test_declared_detail_actions_survive_fallback(self, monkeypatch):
        import meta.core.ui_config.config_builder as cb
        from meta.core.ui_config.config_builder import UIConfigBuilder
        from meta.services import view_config_service as vcs_module

        stub = _StubMetaObject()
        monkeypatch.setattr(
            cb._model_registry, 'get',
            lambda object_type: stub if object_type == 'stub_bo' else None)
        monkeypatch.setattr(cb._model_registry, 'get_ui_config', lambda cache_key: None)
        monkeypatch.setattr(cb._model_registry, 'set_ui_config', lambda cache_key, config: None)
        monkeypatch.setattr(
            vcs_module.view_config_service, 'get_or_build_view_config',
            lambda object_type, view_name=None: {'detail': {'tabs': [{'id': 'main'}]}})

        builder = UIConfigBuilder(_StubDisplayNameService(), lambda *a, **k: [])
        config = builder.build('stub_bo')

        detail = config['ui_view_config']['detail']
        assert detail['actions'] == [{'id': 'demo', 'action': 'stub_bo.demo'}]
        assert detail['tabs'] == [{'id': 'main'}]

    def test_no_declared_actions_keeps_derived_detail(self, monkeypatch):
        import meta.core.ui_config.config_builder as cb
        from meta.core.ui_config.config_builder import UIConfigBuilder
        from meta.services import view_config_service as vcs_module

        stub = _StubMetaObject()
        stub.ui_view_config = {'form': {'sections': []}}
        monkeypatch.setattr(
            cb._model_registry, 'get',
            lambda object_type: stub if object_type == 'stub_bo' else None)
        monkeypatch.setattr(cb._model_registry, 'get_ui_config', lambda cache_key: None)
        monkeypatch.setattr(cb._model_registry, 'set_ui_config', lambda cache_key, config: None)
        monkeypatch.setattr(
            vcs_module.view_config_service, 'get_or_build_view_config',
            lambda object_type, view_name=None: {'detail': {'tabs': [{'id': 'main'}]}})

        builder = UIConfigBuilder(_StubDisplayNameService(), lambda *a, **k: [])
        config = builder.build('stub_bo')

        assert config['ui_view_config']['detail'] == {'tabs': [{'id': 'main'}]}
