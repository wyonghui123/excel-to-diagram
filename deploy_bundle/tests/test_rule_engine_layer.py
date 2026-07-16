# -*- coding: utf-8 -*-
"""
规则引擎测试 - L2 Layer

测试目标：验证规则定义和执行的正确性
覆盖维度：
1. Validation 规则 - 校验规则
2. Constraint 规则 - 约束规则
3. Computation 规则 - 计算规则
4. Derivation 规则 - 派生规则
5. Trigger 规则 - 触发规则
6. State Transition 规则 - 状态转换规则
"""

import sys
import os
import tempfile
import shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.core.datasource import get_data_source
from meta.core.models import registry as meta_registry, RuleType, RuleTrigger
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
from meta.core.schema_generator import SchemaGenerator
from meta.core.action_executor import ActionRegistry
from meta.services.manage_service import CreateRequest, UpdateRequest


class TestRuleBase:
    """规则测试基类"""
    
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, 'test_rules.db')
        
        self.ds = get_data_source("sqlite", database=self.db_path)
        self._init_schema()
        
        self.executor = ActionRegistry(self.ds)
    
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


class TestRuleDefinition(TestRuleBase):
    """规则定义测试"""
    
    def test_object_has_rules(self):
        """测试对象有规则定义"""
        obj = meta_registry.get('domain')
        
        assert hasattr(obj, 'rules')
        assert isinstance(obj.rules, list)
    
    def test_rule_has_required_attributes(self):
        """测试规则有必要属性"""
        obj = meta_registry.get('domain')
        
        for rule in obj.rules:
            assert hasattr(rule, 'id')
            assert hasattr(rule, 'rule_type')
            assert hasattr(rule, 'triggers')
    
    def test_get_rules_by_type(self):
        """测试按类型获取规则"""
        obj = meta_registry.get('domain')
        
        validation_rules = obj.get_rules_by_type(RuleType.VALIDATION)
        
        assert isinstance(validation_rules, list)
    
    def test_get_rules_by_trigger(self):
        """测试按触发时机获取规则"""
        obj = meta_registry.get('domain')
        
        before_create_rules = obj.get_rules_by_trigger(RuleTrigger.BEFORE_CREATE)
        
        assert isinstance(before_create_rules, list)


class TestValidationRule(TestRuleBase):
    """校验规则测试"""
    
    def test_required_field_validation(self):
        """测试必填字段校验 - domain 的 code 是业务键，隐含必填（参考 SAP @ObjectModel.businessKey）"""
        obj = meta_registry.get('domain')
        data = {
            'name': '无编码领域',
            'version_id': 1,
        }
        result = self.executor.create(obj, data)
        
        assert not result.success, "缺少业务键 code 时应该拒绝创建"
    
    def test_business_key_validation(self):
        """测试业务键校验"""
        obj = meta_registry.get('domain')
        data1 = {
            'code': 'VAL001',
            'name': '第一个',
            'version_id': 1,
        }
        result1 = self.executor.create(obj, data1)
        assert result1.success
        
        data2 = {
            'code': 'VAL001',
            'name': '第二个重复',
            'version_id': 1,
        }
        result2 = self.executor.create(obj, data2)
        
        assert not result2.success, "业务键重复时应该拒绝创建"


class TestConstraintRule(TestRuleBase):
    """约束规则测试"""
    
    def test_unique_constraint(self):
        """测试唯一约束"""
        obj = meta_registry.get('domain')
        data1 = {
            'code': 'UNIQ001',
            'name': '唯一测试',
            'version_id': 1,
            'level': 1,
        }
        result1 = self.executor.create(obj, data1)
        assert result1.success
        
        data2 = {
            'code': 'UNIQ001',
            'name': '重复编码',
            'version_id': 1,
            'level': 1,
        }
        result2 = self.executor.create(obj, data2)
        
        assert not result2.success
    
    def test_fk_constraint(self):
        """测试外键约束"""
        obj = meta_registry.get('sub_domain')
        sub_domain_data = {
            'code': 'SUB_NO_PARENT',
            'name': '无父级子领域',
            'version_id': 1,
            'level': 2,
        }
        result = self.executor.create(obj, sub_domain_data)
        
        pass


class TestRuleTriggerOrder(TestRuleBase):
    """规则触发顺序测试"""
    
    def test_before_create_trigger(self):
        """测试创建前触发"""
        obj = meta_registry.get('domain')
        
        before_rules = obj.get_rules_by_trigger(RuleTrigger.BEFORE_CREATE)
        
        for rule in before_rules:
            assert RuleTrigger.BEFORE_CREATE in rule.triggers
    
    def test_after_create_trigger(self):
        """测试创建后触发"""
        obj = meta_registry.get('domain')
        
        after_rules = obj.get_rules_by_trigger(RuleTrigger.AFTER_CREATE)
        
        for rule in after_rules:
            assert RuleTrigger.AFTER_CREATE in rule.triggers
    
    def test_before_update_trigger(self):
        """测试更新前触发"""
        obj = meta_registry.get('domain')
        
        before_rules = obj.get_rules_by_trigger(RuleTrigger.BEFORE_UPDATE)
        
        for rule in before_rules:
            assert RuleTrigger.BEFORE_UPDATE in rule.triggers
    
    def test_before_delete_trigger(self):
        """测试删除前触发"""
        obj = meta_registry.get('domain')
        
        before_rules = obj.get_rules_by_trigger(RuleTrigger.BEFORE_DELETE)
        
        for rule in before_rules:
            assert RuleTrigger.BEFORE_DELETE in rule.triggers


class TestRuleSeverity(TestRuleBase):
    """规则严重级别测试"""
    
    def test_error_severity_stops_operation(self):
        """测试 ERROR 级别阻止操作 - 业务键缺失或重复"""
        obj = meta_registry.get('domain')
        
        # 测试1：业务键缺失
        data_no_code = {
            'name': '无编码领域',
            'version_id': 1,
        }
        result = self.executor.create(obj, data_no_code)
        assert not result.success, "业务键缺失应该阻止创建"
        
        # 测试2：业务键重复
        data1 = {
            'code': 'ERR001',
            'name': '第一个',
            'version_id': 1,
        }
        result1 = self.executor.create(obj, data1)
        assert result1.success
        
        data2 = {
            'code': 'ERR001',
            'name': '重复编码',
            'version_id': 1,
        }
        result2 = self.executor.create(obj, data2)
        assert not result2.success, "业务键重复应该阻止创建"
    
    def test_warning_severity_allows_operation(self):
        """测试 WARNING 级别允许操作（带警告）"""
        pass


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v', '-s']))
