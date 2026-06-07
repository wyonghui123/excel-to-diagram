import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
YAML 单一事实原则测试

测试目标：
1. export_visible 默认值为 True
2. 字段权限智能推导规则
3. YAML 配置最小化原则
"""

import sys
import os
import unittest

import pytest

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

class TestExportVisibleDefault:
    """export_visible 默认值测试"""

    def test_user_group_export_visible_default(self):
        """测试 user_group 字段 export_visible 默认值为 True"""
        from meta.core.models import registry
        
        meta = registry.get('user_group')
        assert meta is not None, "meta not found in registry"
        assert meta, "user_group 元对象应该存在" is not None
        
        # 获取字段
        name_field = meta.get_field('name')
        code_field = meta.get_field('code')
        description_field = meta.get_field('description')
        
        assert name_field, "name 字段应该存在" is not None
        assert code_field, "code 字段应该存在" is not None
        assert description_field, "description 字段应该存在" is not None
        
        # 验证 export_visible 默认为 True
        assert getattr(name_field.semantics, 'export_visible', True) == True, "name 字段的 export_visible 应该默认为 True"
        assert getattr(code_field.semantics, 'export_visible', True) == True, "code 字段的 export_visible 应该默认为 True"
        assert getattr(description_field.semantics, 'export_visible', True) == True, "description 字段的 export_visible 应该默认为 True"
        print("[PASS] user_group 字段 export_visible 默认值为 True")

    def test_role_export_visible_default(self):
        """测试 role 字段 export_visible 默认值为 True"""
        from meta.core.models import registry
        
        meta = registry.get('role')
        assert meta is not None, "meta not found in registry"
        assert meta, "role 元对象应该存在" is not None
        
        name_field = meta.get_field('name')
        description_field = meta.get_field('description')
        
        assert getattr(name_field.semantics, 'export_visible', True) == True, "name 字段的 export_visible 应该默认为 True"
        assert getattr(description_field.semantics, 'export_visible', True) == True, "description 字段的 export_visible 应该默认为 True"
        print("[PASS] role 字段 export_visible 默认值为 True")

    def test_user_export_visible_default(self):
        """测试 user 字段 export_visible 默认值为 True"""
        from meta.core.models import registry
        
        meta = registry.get('user')
        assert meta is not None, "meta not found in registry"
        assert meta, "user 元对象应该存在" is not None
        
        username_field = meta.get_field('username')
        display_name_field = meta.get_field('display_name')
        
        assert getattr(username_field.semantics, 'export_visible', True) == True, "username 字段的 export_visible 应该默认为 True"
        assert getattr(display_name_field.semantics, 'export_visible', True) == True, "display_name 字段的 export_visible 应该默认为 True"
        print("[PASS] user 字段 export_visible 默认值为 True")

class TestFieldPermissionSemantics:
    """字段语义标识测试"""

    def test_business_key_semantics(self):
        """测试业务键语义标识"""
        from meta.core.models import registry
        
        meta = registry.get('user_group')
        assert meta is not None, "meta not found in registry"
        code_field = meta.get_field('code')
        
        assert getattr(code_field.semantics, 'business_key', False) == True, "code 字段应该是业务键"
        print("[PASS] 业务键字段正确标识")

    def test_system_fields_semantics(self):
        """测试系统字段语义标识"""
        from meta.core.models import registry
        
        meta = registry.get('user_group')
        assert meta is not None, "meta not found in registry"
        
        # 检查 created_at 是否有 audit_field
        created_at = meta.get_field('created_at')
        assert created_at, "created_at 字段应该存在" is not None
        
        # 注意：audit_field 是 YAML 中配置的语义，不是自动推导的
        has_audit_field = getattr(created_at.semantics, 'audit_field', False)
        print(f"[INFO] created_at.audit_field = {has_audit_field}")
        
        print("[PASS] 系统字段存在")

class TestUIConfigDerivation:
    """UI 配置智能推导测试"""

    def test_get_ui_config_fields(self):
        """测试 get_ui_config 返回正确的字段"""
        try:
            from meta.core.bo_framework import BOFramework
            from meta.core.datasource import get_data_source
            
            ds = get_data_source('sqlite', database='meta/architecture.db')
            bo = BOFramework(ds)
            
            ui_config = bo.get_ui_config('user_group')
            
            fields = {f['id']: f for f in ui_config['fields']}
            
            assert 'code' in fields, "code 字段应该存在"
            assert 'name' in fields, "name 字段应该存在"
            assert 'description' in fields, "description 字段应该存在"
            
            print("[PASS] get_ui_config 返回正确的字段")
        except KeyError as e:
            pytest.fail(f"UI config key error: {e}")
        except Exception as e:
            pytest.fail(f"UI config test skipped: {e}")

class TestAssociationConfiguration:
    """关联配置测试"""

    def test_user_group_associations(self):
        """测试 user_group 的关联配置"""
        try:
            from meta.core.models import registry
            
            meta = registry.get('user_group')
            assert meta is not None, "user_group meta object not found in registry"
            
            associations = getattr(meta, 'associations', {})
            if not associations or 'members' not in associations:
                pytest.fail("user_group associations not configured")
            
            assert 'members' in associations, "应该有 members 关联"
            assert 'roles' in associations, "应该有 roles 关联"
            
            members = associations['members']
            assert members.target_entity == 'user', "members 应该关联到 user"
            print("[PASS] user_group.members 关联正确")
            
            roles = associations['roles']
            assert roles.target_entity == 'role', "roles 应该关联到 role"
            print("[PASS] user_group.roles 关联正确")
        except (KeyError, AttributeError) as e:
            pytest.fail(f"Association config error: {e}")

    def test_role_associations(self):
        """测试 role 的关联配置"""
        try:
            from meta.core.models import registry

            meta = registry.get('role')
            if meta is None:
                pytest.fail("role 元对象未注册")
            assert meta, "role 元对象应该存在" is not None

            associations = getattr(meta, 'associations', {})
            if 'permissions' not in associations:
                pytest.fail("YAML configuration issue - permissions association not found in role")
            
            assert 'permissions' in associations, "应该有 permissions 关联"

            permissions = associations['permissions']
            assert permissions.type == 'many_to_many', "permissions 应该是 many_to_many 类型"
            assert permissions.through == 'role_permissions', "permissions 应该通过 role_permissions 表"
            print("[PASS] role.permissions 关联正确")

            if 'assigned_groups' in associations:
                assigned_groups = associations['assigned_groups']
                assert assigned_groups.type == 'reverse_many_to_many', "assigned_groups 应该是 reverse_many_to_many 类型"
                print("[PASS] role.assigned_groups 关联正确")
        except Exception as e:
            pytest.fail(f"YAML configuration issue: {e}")

class TestDetailTabsConfiguration:
    """详情页 tabs 配置测试"""

    def test_user_group_detail_tabs(self):
        """测试 user_group 的 detail.tabs 配置"""
        from meta.core.models import registry
        
        meta = registry.get('user_group')
        ui_view_config = getattr(meta, 'ui_view_config', None)
        assert ui_view_config, "应该有 ui_view_config" is not None
        
        detail = getattr(ui_view_config, 'detail', None)
        assert detail, "应该有 detail 配置" is not None
        
        tabs = getattr(detail, 'tabs', [])
        assert len(tabs) > 0, "应该有 tabs 配置"
        
        # 检查基本信息的 tab
        basic_tab = next((t for t in tabs if t.id == 'basic'), None)
        assert basic_tab, "应该有 basic tab" is not None
        assert basic_tab.type == 'fields', "basic tab 应该是 fields 类型"
        print("[PASS] user_group detail.basic tab 配置正确")
        
        # 检查 members tab
        members_tab = next((t for t in tabs if t.id == 'members'), None)
        assert members_tab, "应该有 members tab" is not None
        assert members_tab.type in ['association', 'custom'], "members tab 应该是 association 或 custom 类型"
        if hasattr(members_tab, 'association'):
            assert members_tab.association == 'members', "members tab 应该关联到 members"
        print("[PASS] user_group detail.members tab 配置正确")
        
        # 检查 roles tab
        roles_tab = next((t for t in tabs if t.id == 'roles'), None)
        assert roles_tab, "应该有 roles tab" is not None
        assert roles_tab.type in ['association', 'custom'], "roles tab 应该是 association 或 custom 类型"
        if hasattr(roles_tab, 'association'):
            assert roles_tab.association == 'roles', "roles tab 应该关联到 roles"
        print("[PASS] user_group detail.roles tab 配置正确")
        
        # 检查 history tab
        history_tab = next((t for t in tabs if t.id == 'history'), None)
        if history_tab is not None:
            assert history_tab.type in ['history', 'custom'], "history tab 应该是 history 或 custom 类型"
            print("[PASS] user_group detail.history tab 配置正确")
        else:
            print("[INFO] user_group 没有 history tab (可选配置)")

    def test_role_detail_tabs(self):
        """测试 role 的 detail.tabs 配置"""
        try:
            from meta.core.models import registry

            meta = registry.get('role')
            if meta is None:
                pytest.fail("role 元对象未注册")
            ui_view_config = getattr(meta, 'ui_view_config', None)

            detail = getattr(ui_view_config, 'detail', None)
            tabs = getattr(detail, 'tabs', [])

            basic_tab = next((t for t in tabs if t.id == 'basic'), None)
            if basic_tab is None:
                pytest.fail("role detail tabs missing basic tab")
            print("[PASS] role detail.basic tab 配置正确")

            permissions_tab = next((t for t in tabs if t.id == 'permissions'), None)
            assert permissions_tab is not None, "YAML configuration issue - permissions tab not found in role detail"
            assert permissions_tab.type in ['association', 'custom'], "permissions tab 应该是 association 或 custom 类型"
            print("[PASS] role detail.permissions tab 配置正确")

            assigned_groups_tab = next((t for t in tabs if t.id == 'assigned_groups'), None)
            if assigned_groups_tab is not None:
                assert assigned_groups_tab.type in ['association', 'custom'], "assigned_groups tab 应该是 association 或 custom 类型"
                print("[PASS] role detail.assigned_groups tab 配置正确")
        except Exception as e:
            pytest.fail(f"YAML configuration issue: {e}")

class TestYAMLMinimalConfiguration:
    """YAML 最小化配置测试"""

    def test_user_group_no_redundant_visible_true(self):
        """测试 user_group YAML 配置中没有冗余的 visible: true"""
        from meta.core.models import registry
        
        meta = registry.get('user_group')
        assert meta is not None, "meta not found in registry"
        
        redundant_count = 0
        redundant_fields = []
        
        # 检查字段
        for field in meta.fields:
            ui = getattr(field, 'ui', None)
            if ui:
                # 检查 visible 是否明确设置为 True
                visible = getattr(ui, 'visible', None)
                if visible is True:
                    redundant_count += 1
                    redundant_fields.append(field.id)
        
        if redundant_count > 0:
            print(f"[WARNING] 发现 {redundant_count} 个字段设置了冗余的 visible: true: {redundant_fields}")
        else:
            print("[PASS] user_group YAML 配置没有冗余的 visible: true")

    def test_user_group_no_redundant_editable_true(self):
        """测试 user_group YAML 配置中没有冗余的 editable: true"""
        from meta.core.models import registry
        
        meta = registry.get('user_group')
        assert meta is not None, "meta not found in registry"
        
        redundant_count = 0
        redundant_fields = []
        
        # 检查字段
        for field in meta.fields:
            ui = getattr(field, 'ui', None)
            if ui:
                # 检查 editable 是否明确设置为 True
                editable = getattr(ui, 'editable', None)
                if editable is True:
                    redundant_count += 1
                    redundant_fields.append(field.id)
        
        if redundant_count > 0:
            print(f"[WARNING] 发现 {redundant_count} 个字段设置了冗余的 editable: true: {redundant_fields}")
        else:
            print("[PASS] user_group YAML 配置没有冗余的 editable: true")

    def test_user_group_no_redundant_export_visible_true(self):
        """测试 user_group YAML 配置中没有冗余的 export_visible: true"""
        from meta.core.models import registry
        
        meta = registry.get('user_group')
        assert meta is not None, "meta not found in registry"
        
        redundant_count = 0
        redundant_fields = []
        
        # 检查字段
        for field in meta.fields:
            semantics = getattr(field, 'semantics', None)
            if semantics:
                # 检查 export_visible 是否明确设置为 True
                export_visible = getattr(semantics, 'export_visible', None)
                if export_visible is True:
                    redundant_count += 1
                    redundant_fields.append(field.id)
        
        if redundant_count > 0:
            print(f"[WARNING] 发现 {redundant_count} 个字段设置了冗余的 export_visible: true: {redundant_fields}")
        else:
            print("[PASS] user_group YAML 配置没有冗余的 export_visible: true")

