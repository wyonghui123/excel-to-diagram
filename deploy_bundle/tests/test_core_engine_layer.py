# -*- coding: utf-8 -*-
"""
核心引擎层测试 - L2 Layer

测试目标：验证核心引擎的正确性
覆盖维度：
1. ActionExecutor - CRUD 操作执行
2. RuleExecutor - 规则触发与执行
3. QueryBuilder - 查询构建
4. SchemaGenerator - Schema 生成
"""

import sys
import os
import tempfile
import shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.core.datasource import get_data_source
from meta.core.models import (
    MetaObject, MetaField, MetaRelation, MetaAction,
    ObjectType, FieldStorage, FieldSource, FieldType,
    SemanticAnnotation, UIAnnotation, RelationType,
    registry as meta_registry
)
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
from meta.core.action_executor import ActionExecutor, ActionRegistry, ActionResult
from meta.core.rule_executor import RuleExecutor, RuleEngine
from meta.core.query_builder import QueryBuilder
from meta.core.schema_generator import SchemaGenerator
from meta.services.manage_service import CreateRequest, UpdateRequest, DeleteRequest
from meta.services.query_service import QueryService, SearchRequest, QueryCondition


class TestEngineBase:
    """引擎测试基类"""
    
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, 'test_engine.db')
        
        self.ds = get_data_source("sqlite", database=self.db_path)
        self.ds.execute("PRAGMA foreign_keys = OFF")
        self._init_schema()
        
        self.executor = ActionRegistry(self.ds)
        self.query_service = QueryService(self.ds)
    
    def teardown_method(self):
        if hasattr(self, 'tmp_dir') and os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
    
    def _init_schema(self):
        schema_dir = get_yaml_schema_dir()
        register_from_directory(schema_dir)
        
        generator = SchemaGenerator(dialect='sqlite')
        
        for obj in meta_registry.get_all().values():
            if hasattr(obj, 'table_name') and obj.table_name:
                sql = generator.generate_create_table(obj)
                if sql:
                    self.ds.execute(sql)
                    
                indexes = generator.generate_create_index(obj)
                for idx_sql in indexes:
                    self.ds.execute(idx_sql)
        
        self.ds.commit()


class TestActionExecutor(TestEngineBase):
    """ActionExecutor 测试"""
    
    def test_create_action_success(self):
        """测试创建操作成功"""
        obj = meta_registry.get('domain')
        data = {
            'code': 'TEST001',
            'name': '测试领域',
            'version_id': 1,
            'level': 1,
            'sort_order': 1,
        }
        result = self.executor.create(obj, data)
        
        assert result.success
        assert result.last_insert_id is not None
    
    def test_create_action_with_validation_error(self):
        """测试创建操作校验失败"""
        obj = meta_registry.get('domain')
        data = {
            'name': '无编码领域',
        }
        result = self.executor.create(obj, data)
        
        assert not result.success
    
    def test_update_action_success(self):
        """测试更新操作成功"""
        obj = meta_registry.get('domain')
        create_data = {
            'code': 'UPD001',
            'name': '原始名称',
            'version_id': 1,
            'level': 1,
        }
        create_result = self.executor.create(obj, create_data)
        record_id = create_result.last_insert_id
        
        update_data = {'name': '更新后名称'}
        update_result = self.executor.update(obj, record_id, update_data)
        
        assert update_result.success
    
    def test_delete_action_success(self):
        """测试删除操作成功"""
        obj = meta_registry.get('domain')
        create_data = {
            'code': 'DEL001',
            'name': '待删除',
            'version_id': 1,
            'level': 1,
        }
        create_result = self.executor.create(obj, create_data)
        record_id = create_result.last_insert_id
        
        delete_result = self.executor.delete(obj, record_id)
        
        assert delete_result.success
    
    def test_business_key_validation_on_create(self):
        """测试创建时业务键校验"""
        obj = meta_registry.get('domain')
        data1 = {
            'code': 'BK001',
            'name': '第一个',
            'version_id': 1,
            'level': 1,
        }
        result1 = self.executor.create(obj, data1)
        assert result1.success
        
        data2 = {
            'code': 'BK001',
            'name': '第二个重复编码',
            'version_id': 1,
            'level': 1,
        }
        result2 = self.executor.create(obj, data2)
        
        assert not result2.success
    
    def test_update_preserves_self_business_key(self):
        """测试更新时保留自身业务键"""
        obj = meta_registry.get('domain')
        create_data = {
            'code': 'SELF001',
            'name': '原始',
            'version_id': 1,
            'level': 1,
        }
        create_result = self.executor.create(obj, create_data)
        record_id = create_result.last_insert_id
        
        update_data = {'name': '更新名称'}
        update_result = self.executor.update(obj, record_id, update_data)
        
        assert update_result.success


class TestQueryBuilder(TestEngineBase):
    """QueryBuilder 测试"""
    
    def test_simple_query_build(self):
        """测试简单查询构建"""
        obj = meta_registry.get('domain')
        builder = QueryBuilder(self.ds, obj)
        
        sql = builder.build()
        
        assert 'SELECT' in sql.upper()
        assert 'domains' in sql.lower()
    
    def test_query_with_filter(self):
        """测试带过滤条件的查询"""
        obj = meta_registry.get('domain')
        builder = QueryBuilder(self.ds, obj)
        
        sql = builder.where_eq('code', 'TEST001').build()
        
        assert 'WHERE' in sql.upper()
    
    def test_query_with_order(self):
        """测试带排序的查询"""
        obj = meta_registry.get('domain')
        builder = QueryBuilder(self.ds, obj)
        
        sql = builder.order_by('name', 'desc').build()
        
        assert 'ORDER BY' in sql.upper()


class TestSchemaGenerator(TestEngineBase):
    """SchemaGenerator 测试"""
    
    def test_generate_create_table(self):
        """测试生成建表语句"""
        obj = meta_registry.get('domain')
        generator = SchemaGenerator(dialect='sqlite')
        
        sql = generator.generate_create_table(obj)
        
        assert sql is not None
        assert 'CREATE TABLE' in sql.upper()
        assert 'domain' in sql.lower()
    
    def test_generate_create_index(self):
        """测试生成索引语句"""
        obj = meta_registry.get('domain')
        generator = SchemaGenerator(dialect='sqlite')
        
        indexes = generator.generate_create_index(obj)
        
        assert isinstance(indexes, list)
    
    def test_field_column_mapping(self):
        """测试字段到列的映射"""
        obj = meta_registry.get('domain')
        
        for field in obj.fields:
            if field.storage.value == 'stored':
                assert field.db_column is not None


class TestRuleExecutor(TestEngineBase):
    """RuleExecutor 测试"""
    
    def test_rule_engine_initialization(self):
        """测试规则引擎初始化"""
        engine = RuleEngine()
        
        assert engine is not None
    
    def test_get_rules_by_trigger(self):
        """测试按触发时机获取规则"""
        obj = meta_registry.get('domain')
        
        from meta.core.models import RuleTrigger
        before_create_rules = obj.get_rules_by_trigger(RuleTrigger.BEFORE_CREATE)
        
        assert isinstance(before_create_rules, list)


class TestCompositeBusinessKeyEngine(TestEngineBase):
    """组合业务键引擎测试"""
    
    def _create_test_data(self):
        """创建测试数据"""
        domain_obj = meta_registry.get('domain')
        domain_data = {
            'code': 'CBK_DOM',
            'name': '组合键测试领域',
            'version_id': 1,
        }
        self.executor.create(domain_obj, domain_data)
        
        sub_obj = meta_registry.get('sub_domain')
        sub_domain_data = {
            'domain_id': 1,
            'code': 'CBK_SUB',
            'name': '子领域',
            'version_id': 1,
        }
        self.executor.create(sub_obj, sub_domain_data)
        
        sm_obj = meta_registry.get('service_module')
        sm_data = {
            'sub_domain_id': 1,
            'code': 'CBK_SM',
            'name': '服务模块',
            'version_id': 1,
        }
        self.executor.create(sm_obj, sm_data)
        
        bo_obj = meta_registry.get('business_object')
        bo1_data = {
            'service_module_id': 1,
            'code': 'BO_A',
            'name': '对象A',
            'version_id': 1,
        }
        self.executor.create(bo_obj, bo1_data)
        
        bo2_data = {
            'service_module_id': 1,
            'code': 'BO_B',
            'name': '对象B',
            'version_id': 1,
        }
        self.executor.create(bo_obj, bo2_data)
    
    def test_composite_bk_create_success(self):
        """测试组合业务键创建成功"""
        self._create_test_data()
        
        rel_obj = meta_registry.get('relationship')
        rel_data = {
            'source_bo_id': 1,
            'target_bo_id': 2,
            'source_code': 'BO_A',
            'target_code': 'BO_B',
            'relation_code': 'CALLS',
            'version_id': 1,
        }
        result = self.executor.create(rel_obj, rel_data)
        
        assert result.success, "组合业务键创建应该成功"
    
    def test_composite_bk_duplicate_fails(self):
        """测试组合业务键重复失败"""
        self._create_test_data()
        
        rel_obj = meta_registry.get('relationship')
        rel_data1 = {
            'source_bo_id': 1,
            'target_bo_id': 2,
            'source_code': 'BO_A',
            'target_code': 'BO_B',
            'relation_code': 'CALLS',
            'version_id': 1,
        }
        result1 = self.executor.create(rel_obj, rel_data1)
        assert result1.success
        
        rel_data2 = {
            'source_bo_id': 1,
            'target_bo_id': 2,
            'source_code': 'BO_A',
            'target_code': 'BO_B',
            'relation_code': 'CALLS',
            'version_id': 1,
        }
        result2 = self.executor.create(rel_obj, rel_data2)
        
        assert not result2.success, "组合业务键重复应该失败"
    
    def test_composite_bk_different_target_ok(self):
        """测试组合键不同目标合法"""
        self._create_test_data()
        
        bo_obj = meta_registry.get('business_object')
        bo3_data = {
            'service_module_id': 1,
            'code': 'BO_C',
            'name': '对象C',
            'version_id': 1,
        }
        self.executor.create(bo_obj, bo3_data)
        
        rel_obj = meta_registry.get('relationship')
        rel_data1 = {
            'source_bo_id': 1,
            'target_bo_id': 2,
            'source_code': 'BO_A',
            'target_code': 'BO_B',
            'relation_code': 'CALLS',
            'version_id': 1,
        }
        result1 = self.executor.create(rel_obj, rel_data1)
        assert result1.success
        
        rel_data2 = {
            'source_bo_id': 1,
            'target_bo_id': 3,
            'source_code': 'BO_A',
            'target_code': 'BO_C',
            'relation_code': 'CALLS',
            'version_id': 1,
        }
        result2 = self.executor.create(rel_obj, rel_data2)
        
        assert result2.success, "相同源不同目标的组合键应该合法"


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v', '-s']))
