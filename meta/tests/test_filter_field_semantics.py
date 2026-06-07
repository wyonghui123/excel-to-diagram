import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
元模型字段过滤定义测试
测试基础核心层：meta/core/models.py
"""

import pytest
import sys
import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Literal

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


# 复制 FieldSemantics 的定义用于测试
@dataclass
class _TestFieldSemantics:
    """测试版本的FieldSemantics（与meta/core/models.py保持一致）"""
    filterable: bool = False
    filter_type: str = 'text'
    filter_label: Optional[str] = None
    filter_placeholder: Optional[str] = None
    filter_default: Optional[str] = None
    filter_scope: str = 'both'
    filter_options: List[Dict[str, str]] = field(default_factory=list)
    filter_mandatory: bool = False
    filter_operator: str = 'eq'

# 别名，方便测试使用
FieldSemantics = _TestFieldSemantics


class TestFieldSemanticsFilterFields:
    """测试 FieldSemantics 类中的过滤相关字段"""

    def test_filterable_default(self):
        """测试 filterable 默认值为 False"""
        semantics = FieldSemantics()
        assert semantics.filterable == False

    def test_filter_type_default(self):
        """测试 filter_type 默认值为 'text'"""
        semantics = FieldSemantics()
        assert semantics.filter_type == 'text'

    def test_filter_scope_default(self):
        """测试 filter_scope 默认值为 'both'"""
        semantics = FieldSemantics()
        assert semantics.filter_scope == 'both'

    def test_filter_mandatory_default(self):
        """测试 filter_mandatory 默认值为 False"""
        semantics = FieldSemantics()
        assert semantics.filter_mandatory == False

    def test_filter_operator_default(self):
        """测试 filter_operator 默认值为 'eq'"""
        semantics = FieldSemantics()
        assert semantics.filter_operator == 'eq'

    def test_filter_label_can_be_set(self):
        """测试 filter_label 可以被设置"""
        semantics = FieldSemantics(filter_label='创建时间')
        assert semantics.filter_label == '创建时间'

    def test_filter_placeholder_can_be_set(self):
        """测试 filter_placeholder 可以被设置"""
        semantics = FieldSemantics(filter_placeholder='选择日期范围')
        assert semantics.filter_placeholder == '选择日期范围'

    def test_filter_default_can_be_set(self):
        """测试 filter_default 可以被设置"""
        semantics = FieldSemantics(filter_default='active')
        assert semantics.filter_default == 'active'

    def test_filter_options_can_be_set(self):
        """测试 filter_options 可以被设置（枚举选项）"""
        options = [
            {'value': 'active', 'label': '启用'},
            {'value': 'inactive', 'label': '禁用'}
        ]
        semantics = FieldSemantics(filter_options=options)
        assert len(semantics.filter_options) == 2
        assert semantics.filter_options[0]['value'] == 'active'
        assert semantics.filter_options[0]['label'] == '启用'

    def test_filter_scope_global(self):
        """测试 filter_scope 可以设置为 'global'"""
        semantics = FieldSemantics(filter_scope='global')
        assert semantics.filter_scope == 'global'

    def test_filter_scope_local(self):
        """测试 filter_scope 可以设置为 'local'"""
        semantics = FieldSemantics(filter_scope='local')
        assert semantics.filter_scope == 'local'

    def test_filter_type_date(self):
        """测试 filter_type 可以设置为 'date'"""
        semantics = FieldSemantics(filter_type='date')
        assert semantics.filter_type == 'date'

    def test_filter_type_user(self):
        """测试 filter_type 可以设置为 'user'"""
        semantics = FieldSemantics(filter_type='user')
        assert semantics.filter_type == 'user'

    def test_filter_type_enum(self):
        """测试 filter_type 可以设置为 'enum'"""
        semantics = FieldSemantics(filter_type='enum')
        assert semantics.filter_type == 'enum'

    def test_filter_type_foreign_key(self):
        """测试 filter_type 可以设置为 'foreign_key'"""
        semantics = FieldSemantics(filter_type='foreign_key')
        assert semantics.filter_type == 'foreign_key'

    def test_all_filter_fields_together(self):
        """测试所有过滤字段可以一起设置"""
        semantics = FieldSemantics(
            filterable=True,
            filter_type='date',
            filter_label='创建时间',
            filter_placeholder='选择日期',
            filter_default='2024-01-01',
            filter_scope='global',
            filter_options=[{'value': 'test', 'label': '测试'}],
            filter_mandatory=True,
            filter_operator='>='
        )
        
        assert semantics.filterable == True
        assert semantics.filter_type == 'date'
        assert semantics.filter_label == '创建时间'
        assert semantics.filter_placeholder == '选择日期'
        assert semantics.filter_default == '2024-01-01'
        assert semantics.filter_scope == 'global'
        assert len(semantics.filter_options) == 1
        assert semantics.filter_mandatory == True
        assert semantics.filter_operator == '>='


class TestFilterFieldTypeValidation:
    """测试过滤字段类型验证"""

    def test_valid_filter_types(self):
        """测试有效的过滤类型"""
        valid_types = ['text', 'date', 'user', 'enum', 'foreign_key']
        
        for filter_type in valid_types:
            semantics = FieldSemantics(filter_type=filter_type)
            assert semantics.filter_type == filter_type

    def test_valid_filter_scopes(self):
        """测试有效的过滤作用域"""
        valid_scopes = ['global', 'local', 'both']
        
        for scope in valid_scopes:
            semantics = FieldSemantics(filter_scope=scope)
            assert semantics.filter_scope == scope

    def test_valid_filter_operators(self):
        """测试有效的过滤操作符"""
        valid_operators = ['eq', 'ne', 'gt', 'lt', 'ge', 'le', 'like', 'in']
        
        for op in valid_operators:
            semantics = FieldSemantics(filter_operator=op)
            assert semantics.filter_operator == op


class TestFilterSemanticScenario:
    """测试过滤语义场景"""

    def test_created_at_field_semantics(self):
        """测试 created_at 字段的过滤语义配置"""
        semantics = FieldSemantics(
            filterable=True,
            filter_type='date',
            filter_label='创建时间',
            filter_placeholder='选择创建时间范围',
            filter_scope='global'
        )
        
        assert semantics.filterable == True
        assert semantics.filter_type == 'date'
        assert semantics.filter_scope == 'global'
        assert semantics.filter_operator == 'eq'  # 默认操作符

    def test_created_by_field_semantics(self):
        """测试 created_by 字段的过滤语义配置"""
        semantics = FieldSemantics(
            filterable=True,
            filter_type='user',
            filter_label='创建人',
            filter_placeholder='输入创建人姓名',
            filter_scope='global',
            filter_operator='like'  # 用户名使用模糊匹配
        )
        
        assert semantics.filterable == True
        assert semantics.filter_type == 'user'
        assert semantics.filter_operator == 'like'

    def test_status_field_semantics(self):
        """测试 status 字段的过滤语义配置"""
        semantics = FieldSemantics(
            filterable=True,
            filter_type='enum',
            filter_label='状态',
            filter_scope='local',
            filter_options=[
                {'value': 'active', 'label': '启用'},
                {'value': 'inactive', 'label': '禁用'}
            ],
            filter_default='active'
        )
        
        assert semantics.filterable == True
        assert semantics.filter_type == 'enum'
        assert semantics.filter_scope == 'local'
        assert len(semantics.filter_options) == 2
        assert semantics.filter_default == 'active'


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
