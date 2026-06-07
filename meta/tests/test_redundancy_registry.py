import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
冗余注册表单元测试

测试 RedundancyRegistry 的核心功能：
1. 从元模型构建注册表
2. 按类型分类查询
3. 级联链分析
4. 统计信息
"""

import pytest
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import meta
from meta.core.redundancy_registry import (
    RedundancyRegistry,
    RedundancyDef,
    RedundancyType,
    ConsistencyStrategy,
    RepairStrategy,
    CascadeChain,
    JoinStep,
    ConsistencyConfig,
)


class TestRedundancyRegistryBuild:
    """测试注册表构建"""
    
    def test_build_from_registry(self):
        """测试从元模型注册表构建"""
        registry = RedundancyRegistry()
        
        assert not registry.is_built()
        
        count = registry.build_from_registry()
        
        assert registry.is_built()
        assert count > 0, "应该至少有一个冗余字段"
    
    def test_build_detects_stored_redundancies(self):
        """测试检测物理冗余字段"""
        registry = RedundancyRegistry()
        registry.build_from_registry()
        
        stored = registry.get_stored_redundancies()
        
        assert len(stored) >= 2, "relationship 应该有 source_code 和 target_code 两个物理冗余字段"
        
        field_ids = [r.field_id for r in stored]
        assert "source_code" in field_ids, "应该检测到 source_code"
        assert "target_code" in field_ids, "应该检测到 target_code"
    
    def test_build_detects_virtual_redundancies(self):
        """测试检测虚拟冗余字段"""
        registry = RedundancyRegistry()
        registry.build_from_registry()
        
        virtual = registry.get_virtual_redundancies()
        
        assert len(virtual) >= 8, "relationship 应该有多个虚拟冗余字段"
        
        field_ids = [r.field_id for r in virtual]
        assert "source_bo_name" in field_ids, "应该检测到 source_bo_name"
        assert "target_bo_name" in field_ids, "应该检测到 target_bo_name"
        assert "source_domain_name" in field_ids, "应该检测到 source_domain_name"
    
    def test_build_creates_cascade_chains(self):
        """测试构建级联链"""
        registry = RedundancyRegistry()
        registry.build_from_registry()
        
        chains = registry.get_all_cascade_chains()
        
        assert len(chains) >= 2, "应该有级联链（source_code 和 target_code）"
        
        chain_targets = [(c.source_object, c.target_field) for c in chains]
        assert any(
            c[0] == "business_object" and c[1] == "source_code" 
            for c in chain_targets
        ), "应该有 business_object.code → relationship.source_code 的级联链"


class TestRedundancyRegistryQueries:
    """测试注册表查询功能"""
    
    @pytest.fixture(autouse=True)
    def setup_registry(self):
        """每个测试前构建注册表"""
        self.registry = RedundancyRegistry()
        self.registry.build_from_registry()
    
    def test_get_redundancy_for_source_code(self):
        """测试获取 source_code 的冗余定义"""
        red_def = self.registry.get_redundancy("relationship", "source_code")
        
        assert red_def is not None
        assert red_def.redundancy_type == RedundancyType.STORED
        assert red_def.source_field == "source_bo_id"
        assert red_def.derived_from == "business_object.code"
        assert red_def.consistency.cascade_on_change == True
    
    def test_get_redundancy_for_target_code(self):
        """测试获取 target_code 的冗余定义"""
        red_def = self.registry.get_redundancy("relationship", "target_code")
        
        assert red_def is not None
        assert red_def.redundancy_type == RedundancyType.STORED
        assert red_def.source_field == "target_bo_id"
        assert red_def.derived_from == "business_object.code"
    
    def test_get_redundancy_for_virtual_field(self):
        """测试获取虚拟冗余字段的定义"""
        red_def = self.registry.get_redundancy("relationship", "source_bo_name")
        
        assert red_def is not None
        assert red_def.redundancy_type == RedundancyType.VIRTUAL
        assert red_def.source_field == "source_bo_id"
        assert red_def.derived_from == "business_object.name"
        assert len(red_def.join_path) == 1, "source_bo_name 应该有 1 步 JOIN"
    
    def test_get_redundancy_for_multi_layer_join(self):
        """测试获取多层JOIN虚拟字段的定义"""
        red_def = self.registry.get_redundancy("relationship", "source_domain_name")
        
        assert red_def is not None
        assert red_def.redundancy_type == RedundancyType.VIRTUAL
        assert red_def.derived_from == "domain.name"
        assert len(red_def.join_path) == 4, "source_domain_name 应该有 4 步 JOIN"
        
        tables = [step.table for step in red_def.join_path]
        assert "business_objects" in tables
        assert "service_modules" in tables
        assert "sub_domains" in tables
        assert "domains" in tables
    
    def test_get_object_redundancies(self):
        """测试获取对象的所有冗余定义"""
        obj_reds = self.registry.get_object_redundancies("relationship")
        
        assert len(obj_reds) >= 10, "relationship 应该有至少 10 个冗余字段"
        
        assert "source_code" in obj_reds
        assert "target_code" in obj_reds
        assert "source_bo_name" in obj_reds
        assert "target_bo_name" in obj_reds
        assert "source_domain_name" in obj_reds
    
    def test_get_nonexistent_redundancy(self):
        """测试获取不存在的冗余定义"""
        red_def = self.registry.get_redundancy("nonexistent_object", "nonexistent_field")
        
        assert red_def is None
    
    def test_get_cascade_chains_for_source(self):
        """测试获取源对象的级联链"""
        chains = self.registry.get_cascade_chains_for_source("business_object")
        
        assert len(chains) >= 2, "business_object 应该有至少 2 条级联链"
        
        target_fields = [c.target_field for c in chains]
        assert "source_code" in target_fields
        assert "target_code" in target_fields


class TestRedundancyDef:
    """测试 RedundancyDef 数据类"""
    
    def test_derived_table_and_field(self):
        """测试派生表和字段属性"""
        red_def = RedundancyDef(
            object_type="relationship",
            field_id="source_code",
            redundancy_type=RedundancyType.STORED,
            source_field="source_bo_id",
            derived_from="business_object.code",
        )
        
        assert red_def.derived_table == "business_object"
        assert red_def.derived_field == "code"
    
    def test_derived_from_malformed(self):
        """测试格式错误的 derived_from"""
        red_def = RedundancyDef(
            object_type="test",
            field_id="test_field",
            redundancy_type=RedundancyType.STORED,
            source_field="fk_id",
            derived_from="malformed_format",
        )
        
        assert red_def.derived_table == ""
        assert red_def.derived_field == ""
    
    def test_repr(self):
        """测试字符串表示"""
        red_def = RedundancyDef(
            object_type="relationship",
            field_id="source_code",
            redundancy_type=RedundancyType.STORED,
            source_field="source_bo_id",
            derived_from="business_object.code",
        )
        
        repr_str = repr(red_def)
        assert "relationship" in repr_str
        assert "source_code" in repr_str
        assert "stored" in repr_str


class TestJoinStep:
    """测试 JoinStep 数据类"""
    
    def test_join_step_creation(self):
        """测试创建 JOIN 步骤"""
        step = JoinStep(
            table="business_objects",
            from_field="source_bo_id",
            to_field="id",
            select="code",
        )
        
        assert step.table == "business_objects"
        assert step.from_field == "source_bo_id"
        assert step.to_field == "id"
        assert step.select == "code"


class TestConsistencyConfig:
    """测试一致性配置"""
    
    def test_default_values(self):
        """测试默认值"""
        config = ConsistencyConfig()
        
        assert config.strategy == ConsistencyStrategy.SYNC_ON_WRITE
        assert config.cascade_on_change == False
        assert config.allow_stale == False
        assert config.repair_strategy == RepairStrategy.RECOMPUTE
    
    def test_custom_values(self):
        """测试自定义值"""
        config = ConsistencyConfig(
            strategy=ConsistencyStrategy.EVENTUAL,
            cascade_on_change=True,
            allow_stale=True,
            repair_strategy=RepairStrategy.NULLIFY,
        )
        
        assert config.strategy == ConsistencyStrategy.EVENTUAL
        assert config.cascade_on_change == True
        assert config.allow_stale == True
        assert config.repair_strategy == RepairStrategy.NULLIFY


class TestRedundancyRegistryStats:
    """测试注册表统计功能"""
    
    @pytest.fixture(autouse=True)
    def setup_registry(self):
        """每个测试前构建注册表"""
        self.registry = RedundancyRegistry()
        self.registry.build_from_registry()
    
    def test_get_stats(self):
        """测试获取统计信息"""
        stats = self.registry.get_stats()
        
        assert stats["built"] == True
        assert stats["total_redundancies"] > 0
        assert stats["stored_count"] >= 2
        assert stats["virtual_count"] >= 8
        assert stats["cascade_chains"] >= 2
        assert "relationship" in stats["objects_with_redundancy"]
    
    def test_get_objects_with_stored_redundancy(self):
        """测试获取有物理冗余的对象"""
        objects = self.registry.get_objects_with_stored_redundancy()
        
        assert "relationship" in objects


class TestRedundancyRegistryClear:
    """测试注册表清理功能"""
    
    def test_clear(self):
        """测试清空注册表"""
        registry = RedundancyRegistry()
        registry.build_from_registry()
        
        assert registry.is_built()
        
        registry.clear()
        
        assert not registry.is_built()
        assert len(registry.get_stored_redundancies()) == 0
        assert len(registry.get_all_cascade_chains()) == 0


class TestRedundancyRegistryRebuild:
    """测试注册表重建功能"""

    def test_rebuild(self):
        """测试重建注册表"""
        registry = RedundancyRegistry()

        count1 = registry.build_from_registry()
        stats1 = registry.get_stats()

        count2 = registry.build_from_registry()
        stats2 = registry.get_stats()

        assert count1 == count2
        assert stats1["total_redundancies"] == stats2["total_redundancies"]


class TestBusinessObjectRedundancyFields:
    """测试 business_object 的冗余字段（回归测试）

    覆盖 2026-05-04 修复的关系分类 bug：
    - domain_id 和 sub_domain_id 缺少 redundancy 定义导致返回 null
    - 前端将跨领域关系错误分类为"同子领域跨服务"
    """

    @pytest.fixture(autouse=True)
    def setup_registry(self):
        """每个测试前构建注册表"""
        self.registry = RedundancyRegistry()
        self.registry.build_from_registry()

    def test_business_object_has_domain_id_redundancy(self):
        """测试 business_object.domain_id 已正确注册"""
        red_def = self.registry.get_redundancy("business_object", "domain_id")

        assert red_def is not None, "domain_id 必须在冗余注册表中"
        assert red_def.redundancy_type == RedundancyType.VIRTUAL
        assert red_def.source_field == "service_module_id"
        assert red_def.derived_from == "domain.id"

    def test_business_object_domain_id_join_path(self):
        """测试 domain_id 的 JOIN 路径: service_modules → sub_domains"""
        red_def = self.registry.get_redundancy("business_object", "domain_id")

        assert len(red_def.join_path) == 2, "domain_id 需要2步JOIN"

        step0 = red_def.join_path[0]
        assert step0.table == "service_modules"
        assert step0.select == "sub_domain_id"

        step1 = red_def.join_path[1]
        assert step1.table == "sub_domains"
        assert step1.select == "domain_id"

    def test_business_object_has_sub_domain_id_redundancy(self):
        """测试 business_object.sub_domain_id 已正确注册"""
        red_def = self.registry.get_redundancy("business_object", "sub_domain_id")

        assert red_def is not None, "sub_domain_id 必须在冗余注册表中"
        assert red_def.redundancy_type == RedundancyType.VIRTUAL
        assert red_def.source_field == "service_module_id"
        assert red_def.derived_from == "sub_domain.id"

    def test_business_object_sub_domain_id_join_path(self):
        """测试 sub_domain_id 的 JOIN 路径: service_modules"""
        red_def = self.registry.get_redundancy("business_object", "sub_domain_id")

        assert len(red_def.join_path) == 1, "sub_domain_id 需要1步JOIN"

        step0 = red_def.join_path[0]
        assert step0.table == "service_modules"
        assert step0.select == "sub_domain_id"

    def test_business_object_all_virtual_fields_registered(self):
        """测试 business_object 所有虚拟字段都已注册"""
        obj_reds = self.registry.get_object_redundancies("business_object")

        required_virtual_fields = [
            "domain_id",
            "sub_domain_id",
            "domain_name",
            "sub_domain_name",
            "service_module_name",
            "version_name",
        ]

        for field_id in required_virtual_fields:
            assert field_id in obj_reds, f"business_object.{field_id} 未注册"
            assert obj_reds[field_id].redundancy_type == RedundancyType.VIRTUAL

    def test_business_object_domain_id_vs_domain_name_distinction(self):
        """测试 domain_id (integer) 和 domain_name (string) 是不同的冗余定义"""
        domain_id_def = self.registry.get_redundancy("business_object", "domain_id")
        domain_name_def = self.registry.get_redundancy("business_object", "domain_name")

        assert domain_id_def.derived_from == "domain.id"
        assert domain_name_def.derived_from == "domain.name"

        assert len(domain_id_def.join_path) == 2
        assert len(domain_name_def.join_path) == 3, "domain_name 需要额外一步获取 name"


class TestRedundancyRegistryEdgeCases:
    """测试边界情况和容错处理"""

    def test_empty_registry_queries(self):
        """测试空注册表的查询"""
        registry = RedundancyRegistry()

        assert not registry.is_built()
        assert len(registry.get_stored_redundancies()) == 0
        assert len(registry.get_virtual_redundancies()) == 0
        assert len(registry.get_object_redundancies("anything")) == 0
        assert registry.get_redundancy("obj", "field") is None

    def test_unknown_redundancy_type_handling(self):
        """测试未知冗余类型的容错处理"""
        registry = RedundancyRegistry()

        malformed_redundancy = {
            "type": "unknown_type",
            "source_field": "test_field",
            "derived_from": "test.source",
        }

        result = registry._parse_redundancy("test_obj", "test_field", malformed_redundancy)
        assert result is None, "未知类型应返回 None"

    def test_malformed_join_step(self):
        """测试格式错误的 JOIN 步骤"""
        registry = RedundancyRegistry()

        redundancy_with_bad_join = {
            "type": "virtual",
            "source_field": "fk_id",
            "derived_from": "target.field",
            "join_path": [
                {"table": "", "from": "", "to": "", "select": ""}  # 空步骤
            ]
        }

        result = registry._parse_redundancy("test_obj", "test_field", redundancy_with_bad_join)
        assert result is not None, "格式错误的 JOIN 不应导致崩溃"

    def test_get_cascade_chains_for_target(self):
        """测试按目标对象查询级联链"""
        registry = RedundancyRegistry()
        registry.build_from_registry()

        chains = registry.get_cascade_chains_for_target("relationship")

        assert len(chains) >= 2, "relationship 应该有级联链指向它"

        source_objects = {c.source_object for c in chains}
        assert "business_object" in source_objects


class TestServiceModuleRedundancyFields:
    """测试 service_module 的冗余字段（回归测试）

    覆盖 2026-05-04 修复的 bug：
    - service_module.domain_id 缺少 redundancy 定义导致编辑页面无法回显领域
    """

    @pytest.fixture(autouse=True)
    def setup_registry(self):
        self.registry = RedundancyRegistry()
        self.registry.build_from_registry()

    def test_service_module_has_domain_id_redundancy(self):
        """测试 service_module.domain_id 已正确注册"""
        red_def = self.registry.get_redundancy("service_module", "domain_id")

        assert red_def is not None, "service_module.domain_id 必须在冗余注册表中"
        assert red_def.redundancy_type == RedundancyType.VIRTUAL
        assert red_def.source_field == "sub_domain_id"
        assert red_def.derived_from == "domain.id"

    def test_service_module_domain_id_join_path_single_step(self):
        """测试 domain_id 的 JOIN 路径: sub_domains (1步)

        service_module 直接有 sub_domain_id 物理字段，只需1步JOIN
        """
        red_def = self.registry.get_redundancy("service_module", "domain_id")

        assert len(red_def.join_path) == 1, "service_module.domain_id 只需1步JOIN"

        step0 = red_def.join_path[0]
        assert step0.table == "sub_domains"
        assert step0.select == "domain_id"

    def test_service_module_has_sub_domain_name_redundancy(self):
        """测试 service_module.sub_domain_name 已正确注册"""
        red_def = self.registry.get_redundancy("service_module", "sub_domain_name")

        assert red_def is not None, "service_module.sub_domain_name 必须在冗余注册表中"
        assert red_def.redundancy_type == RedundancyType.VIRTUAL
        assert red_def.source_field == "sub_domain_id"
        assert red_def.derived_from == "sub_domain.name"

    def test_service_module_has_domain_name_redundancy(self):
        """测试 service_module.domain_name 已正确注册"""
        red_def = self.registry.get_redundancy("service_module", "domain_name")

        assert red_def is not None, "service_module.domain_name 必须在冗余注册表中"
        assert red_def.redundancy_type == RedundancyType.VIRTUAL
        assert red_def.source_field == "sub_domain_id"
        assert red_def.derived_from == "domain.name"
        assert len(red_def.join_path) == 2, "domain_name 需要2步: sub_domains → domains"

    def test_service_module_all_virtual_fields_registered(self):
        """测试 service_module 所有虚拟字段都已注册"""
        obj_reds = self.registry.get_object_redundancies("service_module")

        required_virtual_fields = [
            "domain_id",
            "domain_name",
            "sub_domain_name",
            "version_name",
        ]

        for field_id in required_virtual_fields:
            assert field_id in obj_reds, f"service_module.{field_id} 未注册"
            assert obj_reds[field_id].redundancy_type == RedundancyType.VIRTUAL

    def test_service_module_vs_business_object_join_depth_difference(self):
        """验证 service_module 和 business_object 的 domain_id JOIN 深度不同

        - service_module: 1步 (sub_domain_id → sub_domains.domain_id)
        - business_object: 2步 (service_module_id → sub_domains → domains)
        """
        sm_def = self.registry.get_redundancy("service_module", "domain_id")
        bo_def = self.registry.get_redundancy("business_object", "domain_id")

        assert len(sm_def.join_path) < len(bo_def.join_path), \
            "service_module.domain_id JOIN 应该比 business_object 简单"
        assert len(sm_def.join_path) == 1
        assert len(bo_def.join_path) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
