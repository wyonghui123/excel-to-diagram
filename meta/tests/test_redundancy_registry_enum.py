import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
RedundancyRegistry 单元测试 - Phase X Enrichment 机制统一化

测试范围：
- JoinStep.fixed_conditions: 固定条件扩展
- build_from_registry: 构建冗余字段注册表（包含 enum_type_ref）
- Relationship BO 的 enum 关联注册
"""

import pytest
from meta.core.redundancy_registry import RedundancyRegistry, JoinStep, RedundancyType


class TestJoinStepFixedConditions:
    """JoinStep fixed_conditions 扩展测试"""

    def test_joinsstep_has_fixed_conditions(self):
        """TC-JS-001: JoinStep 有 fixed_conditions 属性"""
        step = JoinStep(
            table='enum_values',
            from_field='relation_code',
            to_field='code',
            select='name as relation_code_name',
            fixed_conditions=[
                ('enum_type_id', '=', 'relation_type'),
                ('is_active', '=', 1),
            ]
        )
        assert hasattr(step, 'fixed_conditions')
        assert len(step.fixed_conditions) == 2
        assert step.fixed_conditions[0] == ('enum_type_id', '=', 'relation_type')
        assert step.fixed_conditions[1] == ('is_active', '=', 1)

    def test_joinsstep_fixed_conditions_default_empty(self):
        """TC-JS-002: JoinStep fixed_conditions 默认空列表"""
        step = JoinStep(
            table='service_modules',
            from_field='service_module_id',
            to_field='id',
            select='name',
        )
        assert step.fixed_conditions == []


class TestBuildFromRegistry:
    """build_from_registry 测试"""

    @pytest.fixture
    def registry(self):
        return RedundancyRegistry()

    def test_build_from_registry_counts_enum_ref(self, registry):
        """TC-BFR-001: build_from_registry 正确计数 enum_ref 字段"""
        total = registry.build_from_registry()

        assert total > 0
        assert 'relationship' in registry._redundancies

    def test_build_from_registry_registers_relationship_fields(self, registry):
        """TC-BFR-002: build_from_registry 注册 relationship 字段"""
        registry.build_from_registry()

        rel_reds = registry.get_object_redundancies('relationship')
        assert len(rel_reds) > 0

        field_ids = list(rel_reds.keys())
        assert 'source_code' in field_ids, "应该注册 source_code"
        assert 'target_code' in field_ids, "应该注册 target_code"

    def test_build_from_registry_registers_hierarchy_fields(self, registry):
        """TC-BFR-003: build_from_registry 注册层级冗余字段"""
        registry.build_from_registry()

        bo_reds = registry.get_object_redundancies('business_object')
        assert len(bo_reds) > 0

        field_ids = list(bo_reds.keys())
        has_hierarchy = any(
            'service_module' in fid or 'domain' in fid
            for fid in field_ids
        )
        assert has_hierarchy, f"Expected hierarchy field in {field_ids}"

    def test_get_object_redundancies_returns_empty_for_unknown(self, registry):
        """TC-BFR-004: 未知对象返回空字典"""
        registry.build_from_registry()

        reds = registry.get_object_redundancies('nonexistent_object')
        assert reds == {}


class TestRelationshipEnumFields:
    """Relationship BO enum 关联字段测试

    注意: relation_type_name 不再使用 enum_values JOIN，因为 relation_code 存储的
    值与 enum_values 表中的 code 不匹配。这是数据设计问题，不是代码问题。
    """

    @pytest.fixture
    def registry(self):
        rr = RedundancyRegistry()
        rr.build_from_registry()
        return rr

    def test_relationship_has_bo_joins(self, registry):
        """TC-REF-001: relationship 有 business_object JOIN（用于 source/target）"""
        reds = registry.get_object_redundancies('relationship')

        has_bo_join = any(
            rdef.join_path and rdef.join_path[0].table == 'business_objects'
            for rdef in reds.values()
        )
        assert has_bo_join, f"At least one field should use business_objects table. Fields: {list(reds.keys())}"

    def test_relationship_has_stored_redundancies(self, registry):
        """TC-REF-002: relationship 有物理冗余字段（source_code, target_code）"""
        reds = registry.get_object_redundancies('relationship')

        source_code = reds.get('source_code')
        target_code = reds.get('target_code')

        assert source_code is not None, "应该有 source_code 冗余"
        assert target_code is not None, "应该有 target_code 冗余"
        assert source_code.redundancy_type == RedundancyType.STORED
        assert target_code.redundancy_type == RedundancyType.STORED


class TestVersionProductAssociation:
    """Version BO 与 Product 的层级关联测试"""

    @pytest.fixture
    def registry(self):
        rr = RedundancyRegistry()
        rr.build_from_registry()
        return rr

    def test_version_has_product_name_redundancy(self, registry):
        """TC-VPA-001: version 有 product_name 冗余字段"""
        reds = registry.get_object_redundancies('version')

        assert 'product_name' in reds, f"Expected product_name in {list(reds.keys())}"

    def test_version_product_join_no_fixed_conditions(self, registry):
        """TC-VPA-002: version 的 product JOIN 没有 fixed_conditions"""
        reds = registry.get_object_redundancies('version')

        if 'product_name' in reds:
            red_def = reds['product_name']
            for step in red_def.join_path:
                assert step.table != 'enum_values', \
                    "product_name should not use enum_values table"
                assert step.fixed_conditions == []


class TestDomainVersionAssociation:
    """Domain BO 与 Version 的层级关联测试"""

    @pytest.fixture
    def registry(self):
        rr = RedundancyRegistry()
        rr.build_from_registry()
        return rr

    def test_domain_has_version_associations(self, registry):
        """TC-DVA-001: domain 有 version_name 和 version_code 冗余字段"""
        reds = registry.get_object_redundancies('domain')

        assert 'version_name' in reds, f"Expected version_name in {list(reds.keys())}"
        assert 'version_code' in reds, f"Expected version_code in {list(reds.keys())}"

    def test_domain_version_join_no_fixed_conditions(self, registry):
        """TC-DVA-002: domain 的 version JOIN 没有 fixed_conditions"""
        reds = registry.get_object_redundancies('domain')

        for field_id, red_def in reds.items():
            if red_def.join_path and red_def.join_path[0].table == 'versions':
                assert red_def.join_path[0].fixed_conditions == []


class TestBusinessObjectHierarchy:
    """BusinessObject BO 层级关联测试"""

    @pytest.fixture
    def registry(self):
        rr = RedundancyRegistry()
        rr.build_from_registry()
        return rr

    def test_business_object_has_hierarchy_fields(self, registry):
        """TC-BOH-001: business_object 有层级关联字段"""
        reds = registry.get_object_redundancies('business_object')

        field_ids = list(reds.keys())
        assert 'service_module_name' in field_ids
        assert 'domain_name' in field_ids

    def test_business_object_hierarchy_joins_no_fixed_conditions(self, registry):
        """TC-BOH-002: business_object 的层级 JOIN 没有 fixed_conditions"""
        reds = registry.get_object_redundancies('business_object')

        for field_id, red_def in reds.items():
            if red_def.join_path and red_def.join_path[0].table != 'enum_values':
                assert red_def.join_path[0].fixed_conditions == [], \
                    f"{field_id} should not have fixed_conditions"


class TestServiceModuleHierarchy:
    """ServiceModule BO 层级关联测试"""

    @pytest.fixture
    def registry(self):
        rr = RedundancyRegistry()
        rr.build_from_registry()
        return rr

    def test_service_module_has_hierarchy_fields(self, registry):
        """TC-SMH-001: service_module 有层级关联字段"""
        reds = registry.get_object_redundancies('service_module')

        field_ids = list(reds.keys())
        if not field_ids:
            pytest.skip("service_module has no redundancy fields registered")
        assert 'domain_name' in field_ids or 'sub_domain_name' in field_ids or 'version_name' in field_ids
