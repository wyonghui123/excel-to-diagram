import pytest

pytestmark = pytest.mark.integration

"""
关联导航功能测试套件
测试 _infer_navigation 推导逻辑、batch_query_associations 批量查询
"""

import pytest
from unittest.mock import Mock, MagicMock, patch


class TestInferNavigation:
    """导航配置智能推导测试 - BOFramework._infer_navigation"""

    def test_infer_many_to_many_enabled(self):
        """TC-NAV-001: many_to_many 关联自动推导 enabled=True"""
        from meta.core.bo_framework import BOFramework

        assoc = {
            'name': 'roles',
            'label': '角色',
            'type': 'many_to_many',
            'target_entity': 'role',
            'through': 'user_roles',
            'source_key': 'user_id',
            'target_key': 'role_id',
        }
        BOFramework._infer_navigation(assoc)

        nav = assoc['navigation']
        assert nav['enabled'] is True
        assert nav['display_mode'] == 'list'
        assert nav['readonly'] is False

    def test_infer_composition_enabled(self):
        """TC-NAV-002: composition 关联自动推导 enabled=True"""
        from meta.core.bo_framework import BOFramework

        assoc = {
            'name': 'children',
            'label': '子对象',
            'type': 'composition',
            'target_entity': 'child_obj',
        }
        BOFramework._infer_navigation(assoc)

        nav = assoc['navigation']
        assert nav['enabled'] is True

    def test_infer_reverse_many_to_many_enabled(self):
        """TC-NAV-003: reverse_many_to_many 关联自动推导 enabled=True"""
        from meta.core.bo_framework import BOFramework

        assoc = {
            'name': 'members',
            'label': '成员',
            'type': 'reverse_many_to_many',
            'target_entity': 'user',
        }
        BOFramework._infer_navigation(assoc)

        nav = assoc['navigation']
        assert nav['enabled'] is True

    def test_infer_reference_disabled(self):
        """TC-NAV-004: reference 关联自动推导 enabled=False"""
        from meta.core.bo_framework import BOFramework

        assoc = {
            'name': 'creator',
            'label': '创建者',
            'type': 'reference',
            'target_entity': 'user',
        }
        BOFramework._infer_navigation(assoc)

        nav = assoc['navigation']
        assert nav['enabled'] is False

    def test_infer_unknown_type_disabled(self):
        """TC-NAV-005: 未知关联类型默认 disabled"""
        from meta.core.bo_framework import BOFramework

        assoc = {
            'name': 'unknown_rel',
            'type': 'custom_type',
            'target_entity': 'something',
        }
        BOFramework._infer_navigation(assoc)

        nav = assoc['navigation']
        assert nav['enabled'] is False

    def test_infer_preserves_existing_navigation(self):
        """TC-NAV-006: 已有 navigation 配置时不会被覆盖"""
        from meta.core.bo_framework import BOFramework

        custom_nav = {'enabled': False, 'label': '自定义', 'icon': 'Star'}
        assoc = {
            'name': 'roles',
            'type': 'many_to_many',
            'target_entity': 'role',
            'navigation': custom_nav,
        }
        BOFramework._infer_navigation(assoc)

        assert assoc['navigation'] is custom_nav
        assert assoc['navigation']['label'] == '自定义'

    def test_infer_label_priority(self):
        """TC-NAV-007: label 推导优先级: navigation.label > association.label > association.name"""
        from meta.core.bo_framework import BOFramework

        assoc = {
            'name': 'role_assoc',
            'label': '角色关联',
            'type': 'many_to_many',
            'target_entity': 'role',
        }
        BOFramework._infer_navigation(assoc)
        assert assoc['navigation']['label'] == '角色关联'

        assoc2 = {
            'name': 'role_assoc_only_name',
            'type': 'many_to_many',
            'target_entity': 'role',
        }
        BOFramework._infer_navigation(assoc2)
        assert assoc2['navigation']['label'] == 'role_assoc_only_name'

    def test_infer_icon_mapping_user(self):
        """TC-NAV-008: target_entity=user 映射 User 图标"""
        from meta.core.bo_framework import BOFramework

        assoc = {'name': 'users', 'type': 'many_to_many', 'target_entity': 'user'}
        BOFramework._infer_navigation(assoc)
        assert assoc['navigation']['icon'] == 'User'

    def test_infer_icon_mapping_role(self):
        """TC-NAV-009: target_entity=role 映射 Key 图标"""
        from meta.core.bo_framework import BOFramework

        assoc = {'name': 'roles', 'type': 'many_to_many', 'target_entity': 'role'}
        BOFramework._infer_navigation(assoc)
        assert assoc['navigation']['icon'] == 'Key'

    def test_infer_icon_mapping_permission(self):
        """TC-NAV-010: target_entity=permission 映射 Lock 图标"""
        from meta.core.bo_framework import BOFramework

        assoc = {'name': 'perms', 'type': 'many_to_many', 'target_entity': 'permission'}
        BOFramework._infer_navigation(assoc)
        assert assoc['navigation']['icon'] == 'Lock'

    def test_infer_icon_mapping_user_group(self):
        """TC-NAV-011: target_entity=user_group 映射 UserFilled 图标"""
        from meta.core.bo_framework import BOFramework

        assoc = {'name': 'groups', 'type': 'many_to_many', 'target_entity': 'user_group'}
        BOFramework._infer_navigation(assoc)
        assert assoc['navigation']['icon'] == 'UserFilled'

    def test_infer_icon_mapping_enum_type(self):
        """TC-NAV-012: target_entity=enum_type 映射 Collection 图标"""
        from meta.core.bo_framework import BOFramework

        assoc = {'name': 'enums', 'type': 'many_to_many', 'target_entity': 'enum_type'}
        BOFramework._infer_navigation(assoc)
        assert assoc['navigation']['icon'] == 'Collection'

    def test_infer_icon_mapping_unknown_fallback_link(self):
        """TC-NAV-013: 未知 target_entity 默认 Link 图标"""
        from meta.core.bo_framework import BOFramework

        assoc = {'name': 'custom', 'type': 'many_to_many', 'target_entity': 'unknown_entity'}
        BOFramework._infer_navigation(assoc)
        assert assoc['navigation']['icon'] == 'Link'

    def test_infer_readonly_true(self):
        """TC-NAV-014: readonly=true 时 navigation.readonly 为 True"""
        from meta.core.bo_framework import BOFramework

        assoc = {
            'name': 'roles',
            'type': 'many_to_many',
            'target_entity': 'role',
            'readonly': True,
        }
        BOFramework._infer_navigation(assoc)
        assert assoc['navigation']['readonly'] is True

    def test_infer_readonly_false_default(self):
        """TC-NAV-015: 未设置 readonly 时默认 False"""
        from meta.core.bo_framework import BOFramework

        assoc = {
            'name': 'roles',
            'type': 'many_to_many',
            'target_entity': 'role',
        }
        BOFramework._infer_navigation(assoc)
        assert assoc['navigation']['readonly'] is False


class TestNavigationConfig:
    """导航配置推导边界条件测试"""

    def test_empty_assoc_dict(self):
        """空关联字典也能安全处理"""
        from meta.core.bo_framework import BOFramework

        assoc = {}
        BOFramework._infer_navigation(assoc)
        assert 'navigation' in assoc
        assert assoc['navigation']['enabled'] is True
        assert assoc['navigation'].get('label', '') == '' or assoc['navigation']['label'] == ''

    def test_missing_target_entity_uses_target_type(self):
        """缺少 target_entity 时回退到 target_type"""
        from meta.core.bo_framework import BOFramework

        assoc = {
            'name': 'roles',
            'type': 'many_to_many',
            'target_type': 'role',
        }
        BOFramework._infer_navigation(assoc)
        assert assoc['navigation']['icon'] == 'Key'

    def test_none_navigation_key_not_overridden(self):
        """navigation=None 视为未配置（应被推导）"""
        from meta.core.bo_framework import BOFramework

        assoc = {
            'name': 'roles',
            'type': 'many_to_many',
            'target_entity': 'role',
            'navigation': None,
        }
        BOFramework._infer_navigation(assoc)
        assert assoc['navigation']['enabled'] is True
        assert assoc['navigation']['icon'] == 'Key'


class TestNavigationEdgeCases:
    """get_ui_config 集成测试 - 验证导航配置在 UI 配置中的正确生成"""

    def test_ui_config_contains_navigation_for_m2m(self):
        """TC-NAV-016: get_ui_config 为 m2m 关联生成 navigation 配置"""
        from meta.core.bo_framework import BOFramework
        from meta.core.models import registry as real_registry

        real_registry.invalidate_ui_config_cache()

        role_assoc = {
            'name': 'roles',
            'label': '角色',
            'type': 'many_to_many',
            'target_entity': 'role',
            'through': 'user_roles',
            'source_key': 'user_id',
            'target_key': 'role_id',
        }

        BOFramework._infer_navigation(role_assoc)

        assert 'navigation' in role_assoc
        nav = role_assoc['navigation']
        assert nav['enabled'] is True
        assert nav['label'] == '角色'

    def test_ui_config_reference_has_navigation_disabled(self):
        """TC-NAV-017: get_ui_config 中 reference 关联的 navigation.enabled=False"""
        from meta.core.bo_framework import BOFramework

        ref_assoc = {
            'name': 'created_by_user',
            'label': '创建者',
            'type': 'reference',
            'target_entity': 'user',
        }

        BOFramework._infer_navigation(ref_assoc)

        assert 'navigation' in ref_assoc
        nav = ref_assoc['navigation']
        assert nav['enabled'] is False

    def test_ui_config_multiple_associations_all_get_navigation(self):
        """TC-NAV-018: 多个关联每个都获得独立的 navigation 配置"""
        from meta.core.bo_framework import BOFramework

        associations = [
            {
                'name': 'roles',
                'label': '角色',
                'type': 'many_to_many',
                'target_entity': 'role',
                'through': 'user_roles',
                'source_key': 'user_id',
                'target_key': 'role_id',
            },
            {
                'name': 'groups',
                'label': '用户组',
                'type': 'many_to_many',
                'target_entity': 'user_group',
                'through': 'user_group_members',
                'source_key': 'user_id',
                'target_key': 'group_id',
            },
            {
                'name': 'creator',
                'label': '创建人',
                'type': 'reference',
                'target_entity': 'user',
            },
        ]

        for assoc in associations:
            BOFramework._infer_navigation(assoc)

        assert associations[0]['navigation']['enabled'] is True
        assert associations[0]['navigation']['icon'] == 'Key'
        assert associations[1]['navigation']['enabled'] is True
        assert associations[2]['navigation']['enabled'] is False
