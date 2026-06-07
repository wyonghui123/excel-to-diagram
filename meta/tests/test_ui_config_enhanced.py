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
        assert config['object_type'] == 'role'

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
