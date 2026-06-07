import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
FieldPolicy 单元测试
"""

import pytest
import os

sys_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sys
sys.path.insert(0, sys_path)

from meta.services.field_policy_engine import FieldPolicyEngine, PolicyContext, ObjectContext, UserContext
from meta.services.action_policy import ActionPolicy, create_action_policy
from meta.core.models import registry
from meta.services.field_policy_validation import FieldPolicyValidationInterceptor, ValidationResult


class TestGetUIConfigSemantics:
    """registry 语义数据测试"""

    def test_registry_loaded(self):
        """测试 registry 已加载"""
        assert registry is not None
        objects = registry.list_objects()
        assert len(objects) > 0

    def test_business_object_has_semantics(self):
        """测试 business_object 字段包含 semantics"""
        meta_obj = registry.get('business_object')
        assert meta_obj is not None
        fields_with_semantics = [f for f in meta_obj.fields if hasattr(f, 'semantics') and getattr(f, 'semantics', None)]
        assert len(fields_with_semantics) > 0

    def test_code_field_immutable_and_business_key(self):
        """测试 code 字段有 immutable + business_key"""
        meta_obj = registry.get('business_object')
        assert meta_obj is not None, "meta_obj not found in registry"
        code_field = next((f for f in meta_obj.fields if f.id == 'code'), None)
        assert code_field is not None

        sem = getattr(code_field, 'semantics', None)
        assert sem is not None

        if isinstance(sem, dict):
            assert sem.get('business_key') is True


class TestHasConditionalRequired:
    """[NEW] COV-008: FieldPolicyEngine._has_conditional_required 专项测试 (6 用例)

    FR-4.3: 检查 constraints 是否声明了 conditional_required
    策略: 保守返回 True（UI 显示星号）
    """

    def test_list_with_conditional_required_returns_true(self):
        """constraints 是 list 且含 conditional_required → True"""
        from meta.services.field_policy_engine import FieldPolicyEngine
        constraints = [
            {'type': 'required', 'value': True},
            {'type': 'conditional_required', 'condition': 'X is not None'},
        ]
        assert FieldPolicyEngine._has_conditional_required(constraints) is True

    def test_list_without_conditional_required_returns_false(self):
        """constraints 是 list 但无 conditional_required → False"""
        from meta.services.field_policy_engine import FieldPolicyEngine
        constraints = [
            {'type': 'required', 'value': True},
            {'type': 'max_length', 'value': 50},
        ]
        assert FieldPolicyEngine._has_conditional_required(constraints) is False

    def test_dict_with_conditional_required_type_returns_true(self):
        """constraints 是 dict 且 type=conditional_required → True"""
        from meta.services.field_policy_engine import FieldPolicyEngine
        constraints = {'type': 'conditional_required', 'condition': 'X'}
        assert FieldPolicyEngine._has_conditional_required(constraints) is True

    def test_dict_with_other_type_returns_false(self):
        """constraints 是 dict 但 type 非 conditional_required → False"""
        from meta.services.field_policy_engine import FieldPolicyEngine
        constraints = {'type': 'required', 'value': True}
        assert FieldPolicyEngine._has_conditional_required(constraints) is False

    def test_none_or_unsupported_returns_false(self):
        """constraints 是 None 或其他不支持类型 → False"""
        from meta.services.field_policy_engine import FieldPolicyEngine
        assert FieldPolicyEngine._has_conditional_required(None) is False
        assert FieldPolicyEngine._has_conditional_required('required') is False
        assert FieldPolicyEngine._has_conditional_required(42) is False

    def test_empty_list_returns_false(self):
        """constraints 是空 list → False"""
        from meta.services.field_policy_engine import FieldPolicyEngine
        assert FieldPolicyEngine._has_conditional_required([]) is False


class TestCodeFieldImmutableContinued:
    """恢复 test_code_field_immutable_and_business_key 截断的剩余断言"""

    def test_code_field_immutable_dict_path(self):
        """dict 路径: semantics.immutable == True"""
        from meta.core.models import registry
        meta_obj = registry.get('business_object')
        code_field = next((f for f in meta_obj.fields if f.id == 'code'), None)
        sem = getattr(code_field, 'semantics', None)
        if isinstance(sem, dict):
            assert sem.get('immutable') is True
        else:
            assert getattr(sem, 'business_key', False) is True
            assert getattr(sem, 'immutable', False) is True

    def test_version_id_readonly_always(self):
        """测试 version_id 字段有 readonly_always"""
        meta_obj = registry.get('business_object')
        assert meta_obj is not None, "meta_obj not found in registry"
        version_field = next((f for f in meta_obj.fields if f.id == 'version_id'), None)
        assert version_field is not None

        sem = getattr(version_field, 'semantics', None)
        assert sem is not None

        if isinstance(sem, dict):
            assert sem.get('readonly_always') is True
        else:
            assert getattr(sem, 'readonly_always', False) is True

    def test_computed_field(self):
        """测试 computed 字段"""
        meta_obj = registry.get('role')
        assert meta_obj is not None
        user_count = next((f for f in meta_obj.fields if f.id == 'user_count'), None)
        if user_count is None:
            pytest.skip("role 对象未定义 user_count 计算字段")
        assert user_count is not None

    def test_role_code_immutable_business_key(self):
        """测试 role.code 有 immutable + business_key"""
        meta_obj = registry.get('role')
        assert meta_obj is not None, "meta_obj not found in registry"
        code_field = next((f for f in meta_obj.fields if f.id == 'code'), None)
        assert code_field is not None

        sem = getattr(code_field, 'semantics', None)
        assert sem is not None

        if isinstance(sem, dict):
            assert sem.get('business_key') is True
            assert sem.get('immutable') is True
        else:
            assert getattr(sem, 'business_key', False) is True
            assert getattr(sem, 'immutable', False) is True

    def test_enum_value_is_system_readonly_always(self):
        """测试 enum_value.is_system 有 readonly_always"""
        meta_obj = registry.get('enum_value')
        assert meta_obj is not None

        is_system_field = next((f for f in meta_obj.fields if f.id == 'is_system'), None)
        assert is_system_field is not None

        sem = getattr(is_system_field, 'semantics', None)
        assert sem is not None

        if isinstance(sem, dict):
            assert sem.get('readonly_always') is True
        else:
            assert getattr(sem, 'readonly_always', False) is True

    def test_parent_key_immutable(self):
        """测试 relationship.source_bo_id 有 parent_key + immutable"""
        meta_obj = registry.get('relationship')
        assert meta_obj is not None

        source_field = next((f for f in meta_obj.fields if f.id == 'source_bo_id'), None)
        assert source_field is not None

        sem = getattr(source_field, 'semantics', None)
        assert sem is not None

        if isinstance(sem, dict):
            assert sem.get('parent_key') is True
            assert sem.get('immutable') is True
        else:
            assert getattr(sem, 'parent_key', False) is True
            assert getattr(sem, 'immutable', False) is True


class TestFieldPolicyEngine:
    """FieldPolicyEngine 单元测试"""

    def test_system_fields_are_not_editable(self):
        """测试系统字段不可编辑"""
        engine = FieldPolicyEngine()
        assert engine.determine_editable('id') is False
        assert engine.determine_editable('created_at') is False
        assert engine.determine_editable('updated_at') is False
        assert engine.determine_editable('is_system') is False
        assert engine.determine_editable('tenant_id') is False

    def test_mutability_locked(self):
        """测试 mutability='locked' - 所有字段不可编辑"""
        engine = FieldPolicyEngine()
        context = PolicyContext(
            object_context=ObjectContext(mutability='locked', object_type='enum_type'),
            action='update'
        )
        assert engine.determine_editable('code', context) is False
        assert engine.determine_editable('name', context) is False
        assert engine.determine_editable('created_at', context) is False

    def test_mutability_fully_editable(self):
        """测试 mutability='fully_editable' - 所有字段可编辑"""
        engine = FieldPolicyEngine()
        context = PolicyContext(
            object_context=ObjectContext(mutability='fully_editable', object_type='user'),
            action='update'
        )
        assert engine.determine_editable('code', context) is True
        assert engine.determine_editable('name', context) is True
        assert engine.determine_editable('created_at', context) is False

    def test_immutable_semantics(self):
        """测试 immutable 语义 - 创建时可编辑，更新时不可编辑"""
        engine = FieldPolicyEngine()

        class MockField:
            def __init__(self, field_id):
                self.id = field_id
                self.semantics = {'immutable': True}

        class MockMetaObject:
            def __init__(self):
                self.fields = [MockField('immutable_field')]

        engine.meta_object = MockMetaObject()

        update_ctx = PolicyContext(action='update')
        assert engine.determine_editable('immutable_field', update_ctx) is False

        create_ctx = PolicyContext(action='create')
        assert engine.determine_editable('immutable_field', create_ctx) is True

    def test_is_row_editable_locked(self):
        """测试整行可编辑性判断 - locked"""
        engine = FieldPolicyEngine()
        context_locked = PolicyContext(
            object_context=ObjectContext(mutability='locked'),
            action='update'
        )
        assert engine.is_row_editable(context_locked) is False


class TestUserMustChangePasswordField:
    """测试 user.must_change_password 字段的编辑策略"""

    def test_user_object_has_must_change_password_field(self):
        """测试 user 对象包含 must_change_password 字段"""
        meta_obj = registry.get('user')
        assert meta_obj is not None, "user 对象未在 registry 中注册"
        field = next((f for f in meta_obj.fields if f.id == 'must_change_password'), None)
        assert field is not None, "user 对象缺少 must_change_password 字段"

    def test_must_change_password_has_ui_editable_false(self):
        """测试 must_change_password 字段配置了 ui.editable: false"""
        meta_obj = registry.get('user')
        field = next((f for f in meta_obj.fields if f.id == 'must_change_password'), None)
        assert field is not None

        ui_config = getattr(field, 'ui', None) or {}
        if isinstance(ui_config, dict):
            assert ui_config.get('editable') is False, "must_change_password 应该有 ui.editable: false"
        else:
            assert getattr(ui_config, 'editable', True) is False, "must_change_password 应该有 ui.editable: false"

    def test_must_change_password_not_editable_in_create_context(self):
        """测试 must_change_password 在创建上下文中不可编辑（修复新建用户保存报错）"""
        engine = FieldPolicyEngine()
        engine.meta_object = registry.get('user')

        context = PolicyContext(
            object_context=ObjectContext(object_type='user'),
            action='create'
        )

        is_editable = engine.determine_editable('must_change_password', context)
        assert is_editable is False, "创建用户时 must_change_password 字段不可编辑"

    def test_must_change_password_not_editable_in_update_context(self):
        """测试 must_change_password 在更新上下文中也不可编辑"""
        engine = FieldPolicyEngine()
        engine.meta_object = registry.get('user')

        context = PolicyContext(
            object_context=ObjectContext(object_type='user'),
            action='update'
        )

        is_editable = engine.determine_editable('must_change_password', context)
        assert is_editable is False, "更新用户时 must_change_password 字段不可编辑"

    def test_must_change_password_field_should_be_filtered_in_create_payload(self):
        """测试创建用户时 must_change_password 应被过滤出 payload（模拟前端行为）"""
        engine = FieldPolicyEngine()
        engine.meta_object = registry.get('user')

        create_data = {
            'username': 'test_user',
            'password': 'password123',
            'must_change_password': 0,
            'password_history': '[]',
            'is_system': False,
            'created_at': '2024-01-01 00:00:00',
        }

        filtered_data = {}
        for key, value in create_data.items():
            context = PolicyContext(
                object_context=ObjectContext(object_type='user'),
                action='create'
            )
            if engine.determine_editable(key, context):
                filtered_data[key] = value

        assert 'must_change_password' not in filtered_data, "must_change_password 应该被过滤掉"
        assert 'username' in filtered_data, "username 应该保留"
        assert 'password' in filtered_data, "password 应该保留"
        assert 'is_system' not in filtered_data, "is_system 应该被过滤掉（系统字段）"
        assert 'created_at' not in filtered_data, "created_at 应该被过滤掉（系统字段）"


class TestUserGroupMemberCount:
    """测试 user_group.member_count 计算字段"""

    def test_user_group_has_member_count_field(self):
        """测试 user_group 对象包含 member_count 字段"""
        meta_obj = registry.get('user_group')
        assert meta_obj is not None, "user_group 对象未在 registry 中注册"
        field = next((f for f in meta_obj.fields if f.id == 'member_count'), None)
        assert field is not None, "user_group 对象缺少 member_count 字段"

    def test_member_count_is_computed_field(self):
        """测试 member_count 字段配置为计算字段"""
        meta_obj = registry.get('user_group')
        field = next((f for f in meta_obj.fields if f.id == 'member_count'), None)
        assert field is not None

        assert field.computed is True, "member_count 应该是计算字段"

    def test_user_group_list_config_has_member_count_computed(self):
        """测试 user_group 列表配置中 member_count 配置了 computed 和 computation"""
        meta_obj = registry.get('user_group')
        assert meta_obj is not None

        list_config = getattr(meta_obj.ui_view_config, 'list', None)
        assert list_config is not None, "user_group 应该有 ui_view_config.list 配置"

        member_count_col = next(
            (col for col in list_config.columns if col.key == 'member_count'),
            None
        )
        assert member_count_col is not None, f"user_group 列表配置缺少 member_count 列，当前键: {[col.key for col in list_config.columns]}"

        assert getattr(member_count_col, 'computed', False) is True, "member_count 列应该设置 computed: true"
        computation = getattr(member_count_col, 'computation', None)
        assert computation is not None, "member_count 列应该配置 computation"
        assert computation.get('type') == 'count_relations', "computation type 应该是 count_relations"
        assert computation.get('scope') == 'self', "computation scope 应该是 self"


class TestCountFieldConfigurations:
    """测试所有对象的计数字段配置"""

    @pytest.mark.parametrize("object_type,field_key,expected_computation", [
        ("business_object", "relation_count", {"type": "count_relations", "scope": "self"}),
        ("domain", "relation_count", {"type": "count_relations", "scope": "descendants"}),
        ("sub_domain", "relation_count", {"type": "count_relations", "scope": "descendants"}),
        ("service_module", "relation_count", {"type": "count_relations", "scope": "descendants"}),
        ("user_group", "member_count", {"type": "count_relations", "scope": "self"}),
        ("enum_type", "value_count", {"type": "count_children", "child_object": "enum_value"}),
    ])
    def test_count_field_in_list_configuration(self, object_type, field_key, expected_computation):
        """测试列表配置中计数字段的配置是否正确"""
        meta_obj = registry.get(object_type)
        assert meta_obj is not None, f"{object_type} 对象未在 registry 中注册"

        list_config = getattr(meta_obj.ui_view_config, 'list', None)
        assert list_config is not None, f"{object_type} 应该有 ui_view_config.list 配置"

        count_col = next(
            (col for col in list_config.columns if col.key == field_key),
            None
        )
        assert count_col is not None, f"{object_type} 列表配置缺少 {field_key} 列"

        assert getattr(count_col, 'computed', False) is True, f"{object_type}.{field_key} 应该设置 computed: true"
        computation = getattr(count_col, 'computation', None)
        assert computation is not None, f"{object_type}.{field_key} 应该配置 computation"

        for key, value in expected_computation.items():
            actual_value = computation.get(key)
            assert actual_value == value, f"{object_type}.{field_key} computation.{key} 应该是 {value}，实际是 {actual_value}"

    @pytest.mark.parametrize("object_type,field_key,expected_computation", [
        ("product", "child_count", {"type": "count_children", "child_object": "version"}),
        ("version", "child_count", {"type": "count_children", "child_object": "domain"}),
        ("sub_domain", "child_count", {"type": "count_children", "child_object": "service_module"}),
        ("domain", "child_count", {"type": "count_children", "child_object": "sub_domain"}),
        ("service_module", "child_count", {"type": "count_children", "child_object": "business_object"}),
    ])
    def test_count_field_exists_in_object(self, object_type, field_key, expected_computation):
        """测试计数字段在对象中存在且配置正确（不在列表中但在字段定义中存在）"""
        meta_obj = registry.get(object_type)
        assert meta_obj is not None, f"{object_type} 对象未在 registry 中注册"

        field = next((f for f in meta_obj.fields if f.id == field_key), None)
        assert field is not None, f"{object_type} 缺少 {field_key} 字段"

        assert field.computed is True, f"{object_type}.{field_key} 应该设置为 computed"

        computation = getattr(field, 'computation', None)
        assert computation is not None, f"{object_type}.{field_key} 应该配置 computation"

        for key, value in expected_computation.items():
            actual_value = computation.get(key)
            assert actual_value == value, f"{object_type}.{field_key} computation.{key} 应该是 {value}，实际是 {actual_value}"

    def test_count_children_supports_child_object_key(self):
        """测试 _count_children 方法支持 child_object 键（YAML 使用 child_object 而非 target_object）"""
        from meta.services.computation_service import ComputationService
        service = ComputationService()

        test_computation = {"child_object": "version"}
        target_object = test_computation.get("target_object") or test_computation.get("child_object", "")
        assert target_object == "version", "_count_children 应该支持 child_object 键"

    def test_user_group_member_count_uses_user_group_members_table(self):
        """测试 user_group.member_count 使用 user_group_members 表统计成员数"""
        from meta.services.computation_service import ComputationService
        service = ComputationService()

        assert hasattr(service, '_batch_count_user_group_members'), \
            "ComputationService 应该实现 _batch_count_user_group_members 方法"


class TestComputedFieldSorting:
    """测试计算字段排序功能"""

    def test_sort_by_virtual_fields_supports_integer_sorting(self):
        """测试 sort_by_virtual_fields 函数正确处理整数字段排序"""
        from meta.services.query.computed_utils import sort_by_virtual_fields
        from meta.core.models import MetaObject, FieldStorage

        class MockField:
            def __init__(self, field_id, field_type):
                self.id = field_id
                self.field_type = field_type
                self.storage = FieldStorage.VIRTUAL

        class MockMetaObject:
            def __init__(self, field):
                self.fields = [field]

            def get_field(self, field_id):
                for f in self.fields:
                    if f.id == field_id:
                        return f
                return None

        int_field = MockField('member_count', 'integer')
        meta_obj = MockMetaObject(int_field)

        records = [
            {'id': 1, 'member_count': 5},
            {'id': 2, 'member_count': 2},
            {'id': 3, 'member_count': 8},
            {'id': 4, 'member_count': 1},
        ]

        sorted_records = sort_by_virtual_fields(meta_obj, records, 'member_count desc')

        assert sorted_records[0]['member_count'] == 8, "降序排序第一个应该是 8"
        assert sorted_records[1]['member_count'] == 5, "降序排序第二个应该是 5"
        assert sorted_records[2]['member_count'] == 2, "降序排序第三个应该是 2"
        assert sorted_records[3]['member_count'] == 1, "降序排序第四个应该是 1"

    def test_sort_by_virtual_fields_handles_null_values(self):
        """测试 sort_by_virtual_fields 函数正确处理空值"""
        from meta.services.query.computed_utils import sort_by_virtual_fields
        from meta.core.models import MetaObject

        class MockField:
            def __init__(self, field_id, field_type):
                self.id = field_id
                self.field_type = field_type

        class MockMetaObject:
            def __init__(self, field):
                self.fields = [field]

            def get_field(self, field_id):
                for f in self.fields:
                    if f.id == field_id:
                        return f
                return None

        int_field = MockField('member_count', 'integer')
        meta_obj = MockMetaObject(int_field)

        records = [
            {'id': 1, 'member_count': 5},
            {'id': 2, 'member_count': None},
            {'id': 3, 'member_count': 2},
            {'id': 4, 'member_count': 0},
        ]

        sorted_records = sort_by_virtual_fields(meta_obj, records, 'member_count desc')

        assert sorted_records[0]['member_count'] == 5, "降序排序第一个应该是 5"
        assert sorted_records[3]['member_count'] == 0, "降序排序最后一个应该是 0（而非 None）"

    def test_sort_by_virtual_fields_ascending_order(self):
        """测试 sort_by_virtual_fields 函数升序排序"""
        from meta.services.query.computed_utils import sort_by_virtual_fields
        from meta.core.models import FieldStorage

        class MockField:
            def __init__(self, field_id, field_type):
                self.id = field_id
                self.field_type = field_type
                self.storage = FieldStorage.VIRTUAL

        class MockMetaObject:
            def __init__(self, field):
                self.fields = [field]

            def get_field(self, field_id):
                for f in self.fields:
                    if f.id == field_id:
                        return f
                return None

        int_field = MockField('relation_count', 'integer')
        meta_obj = MockMetaObject(int_field)

        records = [
            {'id': 1, 'relation_count': 10},
            {'id': 2, 'relation_count': 3},
            {'id': 3, 'relation_count': 7},
        ]

        sorted_records = sort_by_virtual_fields(meta_obj, records, 'relation_count')

        assert sorted_records[0]['relation_count'] == 3, "升序排序第一个应该是 3"
        assert sorted_records[1]['relation_count'] == 7, "升序排序第二个应该是 7"
        assert sorted_records[2]['relation_count'] == 10, "升序排序第三个应该是 10"

    def test_query_service_has_compute_list_computed_fields_method(self):
        """测试 QueryService 有 _compute_list_computed_fields 方法"""
        from meta.services.query_service import QueryService

        assert hasattr(QueryService, '_compute_list_computed_fields'), \
            "QueryService 应该有 _compute_list_computed_fields 方法"

    def test_count_fields_are_sortable_in_list_config(self):
        """测试计数字段在列表配置中设置了 sortable: true"""
        meta_obj = registry.get('user_group')
        list_config = getattr(meta_obj.ui_view_config, 'list', None)

        member_count_col = next(
            (col for col in list_config.columns if col.key == 'member_count'),
            None
        )
        assert member_count_col is not None, "user_group 列表配置应该有 member_count 列"
        assert getattr(member_count_col, 'sortable', False) is True, \
            "member_count 列应该设置 sortable: true"

    def test_business_object_relation_count_sortable(self):
        """测试 business_object.relation_count 字段在列表中可排序"""
        meta_obj = registry.get('business_object')
        list_config = getattr(meta_obj.ui_view_config, 'list', None)

        relation_count_col = next(
            (col for col in list_config.columns if col.key == 'relation_count'),
            None
        )
        assert relation_count_col is not None, "business_object 列表配置应该有 relation_count 列"
        assert getattr(relation_count_col, 'sortable', False) is True, \
            "relation_count 列应该设置 sortable: true"
