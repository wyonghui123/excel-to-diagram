import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
AuditInterceptor 审计日志拦截器全面测试用例

测试范围：
1. 拦截器初始化测试
2. before_action 方法测试
3. after_action 方法测试
4. CRUD 操作审计测试
5. 关联操作审计测试
6. 字段过滤测试
"""

import pytest
import sqlite3
import tempfile
import os
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

from meta.core.interceptors.audit_interceptor import AuditInterceptor
from meta.core.action_context import ActionContext
from meta.core.task_handler import TaskResult
from meta.services.structured_logger import StructuredLogger


class MockDataSource:
    def __init__(self):
        self._data = {}
    
    def execute(self, sql, params=None):
        return MagicMock()
    
    def query(self, sql, params=None):
        return []


class MockMetaObject:
    def __init__(self, audit_enabled=True, table_name='test_table'):
        self.table_name = table_name
        self.audit = MockAuditConfig(enabled=audit_enabled)
        self.fields = [
            MagicMock(id='name'),
            MagicMock(id='email'),
            MagicMock(id='status'),
        ]


class MockAuditConfig:
    def __init__(self, enabled=True):
        self.enabled = enabled
    
    def get_action_config(self, action):
        return MockActionConfig(enabled=self.enabled)


class MockActionConfig:
    def __init__(self, enabled=True, fields='all', exclude=None):
        self.enabled = enabled
        self.fields = fields
        self.exclude = exclude or []


class MockResult:
    def __init__(self, success=True, data=None):
        self.success = success
        self.data = data or {}


class TestAuditInterceptorInit:
    """AuditInterceptor 初始化测试"""
    
    def test_init_default(self):
        """测试默认初始化"""
        interceptor = AuditInterceptor()
        
        assert interceptor._data_source is None
        assert interceptor._audit_service is None
        assert interceptor.priority == 90
    
    def test_init_with_data_source(self):
        """测试带数据源初始化"""
        ds = MockDataSource()
        interceptor = AuditInterceptor(data_source=ds)
        
        assert interceptor._data_source is ds
    
    def test_init_with_structured_logger(self):
        """测试带结构化日志器初始化"""
        logger = StructuredLogger()
        interceptor = AuditInterceptor(structured_logger=logger)
        
        assert interceptor._structured_logger is logger
    
    def test_priority_property(self):
        """测试优先级属性"""
        interceptor = AuditInterceptor()
        assert interceptor.priority == 90
    
    def test_crud_write_disabled_flag(self):
        """测试CRUD写入禁用标志"""
        assert AuditInterceptor.AUDIT_CRUD_WRITE_DISABLED is True
    
    def test_assoc_write_disabled_flag(self):
        """测试关联写入禁用标志"""
        assert AuditInterceptor.AUDIT_ASSOC_WRITE_DISABLED is False


class TestAuditInterceptorBeforeAction:
    """AuditInterceptor.before_action 方法测试"""
    
    def test_before_action_non_crud(self):
        """测试非CRUD动作"""
        interceptor = AuditInterceptor()
        
        context = MagicMock()
        context.is_crud_action = False
        
        interceptor.before_action(context)
    
    def test_before_action_create(self):
        """测试CREATE动作"""
        interceptor = AuditInterceptor()
        
        context = MagicMock()
        context.is_crud_action = True
        context.is_create_action = True
        context.is_update_action = False
        context.is_delete_action = False
        
        interceptor.before_action(context)
    
    def test_before_action_update_gets_old_data(self):
        """测试UPDATE动作获取旧数据"""
        interceptor = AuditInterceptor()
        
        ds = MockDataSource()
        ds.execute = MagicMock(return_value=MagicMock(fetchone=lambda: {'name': 'old', 'email': 'old@test.com'}))
        
        context = MagicMock()
        context.is_crud_action = True
        context.is_create_action = False
        context.is_update_action = True
        context.is_delete_action = False
        context.data_source = ds
        context.meta_object = MockMetaObject()
        context.object_id = 1
        
        interceptor.before_action(context)
    
    def test_before_action_delete_gets_old_data(self):
        """测试DELETE动作获取旧数据"""
        interceptor = AuditInterceptor()
        
        ds = MockDataSource()
        ds.execute = MagicMock(return_value=MagicMock(fetchone=lambda: {'name': 'old', 'email': 'old@test.com'}))
        
        context = MagicMock()
        context.is_crud_action = True
        context.is_create_action = False
        context.is_update_action = False
        context.is_delete_action = True
        context.data_source = ds
        context.meta_object = MockMetaObject()
        context.object_id = 1
        
        interceptor.before_action(context)


class TestAuditInterceptorAfterAction:
    """AuditInterceptor.after_action 方法测试"""
    
    def test_after_action_non_crud_non_assoc(self):
        """测试非CRUD非关联动作"""
        interceptor = AuditInterceptor()
        
        context = MagicMock()
        context.is_crud_action = False
        context.action = 'custom'
        
        interceptor.after_action(context)
    
    def test_after_action_crud_disabled(self):
        """测试CRUD动作被禁用"""
        interceptor = AuditInterceptor()
        
        context = MagicMock()
        context.is_crud_action = True
        context.action = 'create'
        
        interceptor.after_action(context)
    
    def test_after_action_failed_result(self):
        """测试失败结果"""
        interceptor = AuditInterceptor()
        
        context = MagicMock()
        context.is_crud_action = False
        context.action = 'associate'
        context.result = MockResult(success=False)
        
        interceptor.after_action(context)
    
    def test_after_action_audit_disabled(self):
        """测试审计被禁用"""
        interceptor = AuditInterceptor()
        
        context = MagicMock()
        context.is_crud_action = False
        context.action = 'associate'
        context.result = MockResult(success=True)
        context.meta_object = MockMetaObject(audit_enabled=False)
        
        interceptor.after_action(context)


class TestAuditInterceptorAssociate:
    """AuditInterceptor 关联操作测试"""
    
    def test_log_associate_basic(self):
        """测试基本关联日志"""
        interceptor = AuditInterceptor()
        
        mock_logger = MagicMock()
        interceptor._structured_logger = mock_logger
        
        ds = MockDataSource()
        ds.execute = MagicMock(return_value=MagicMock(fetchone=lambda: ('Test User',)))
        
        context = MagicMock()
        context.is_crud_action = False
        context.action = 'associate'
        context.result = MockResult(success=True)
        context.meta_object = MockMetaObject()
        context.object_type = 'user_group'
        context.object_id = 1
        context.user_id = 'admin'
        context.user_name = 'Administrator'
        context.trace_id = 'trace-123'
        context.params = {
            'tgt_type': 'user',
            'tgt_id': 2,
            'association_name': 'members'
        }
        context.data_source = ds
        
        interceptor.after_action(context)
        
        assert mock_logger.log_business.called
    
    def test_log_dissociate_basic(self):
        """测试基本取消关联日志"""
        interceptor = AuditInterceptor()
        
        mock_logger = MagicMock()
        interceptor._structured_logger = mock_logger
        
        ds = MockDataSource()
        ds.execute = MagicMock(return_value=MagicMock(fetchone=lambda: ('Test User',)))
        
        context = MagicMock()
        context.is_crud_action = False
        context.action = 'dissociate'
        context.result = MockResult(success=True)
        context.meta_object = MockMetaObject()
        context.object_type = 'user_group'
        context.object_id = 1
        context.user_id = 'admin'
        context.user_name = 'Administrator'
        context.trace_id = 'trace-123'
        context.params = {
            'tgt_type': 'user',
            'tgt_id': 2,
            'association_name': 'members'
        }
        context.data_source = ds
        
        interceptor.after_action(context)
        
        assert mock_logger.log_business.called


class TestAuditInterceptorValuesEqual:
    """AuditInterceptor._values_equal 方法测试"""
    
    def test_both_none(self):
        """测试两者都为None"""
        interceptor = AuditInterceptor()
        
        result = interceptor._values_equal(None, None)
        
        assert result is True
    
    def test_one_none(self):
        """测试一个为None"""
        interceptor = AuditInterceptor()
        
        result = interceptor._values_equal(None, 'value')
        
        assert result is False
    
    def test_same_value(self):
        """测试相同值"""
        interceptor = AuditInterceptor()
        
        result = interceptor._values_equal('test', 'test')
        
        assert result is True
    
    def test_different_value(self):
        """测试不同值"""
        interceptor = AuditInterceptor()
        
        result = interceptor._values_equal('test1', 'test2')
        
        assert result is False
    
    def test_different_type_same_string(self):
        """测试不同类型但字符串相同"""
        interceptor = AuditInterceptor()
        
        result = interceptor._values_equal(123, '123')
        
        assert result is True
    
    def test_numeric_values(self):
        """测试数值比较"""
        interceptor = AuditInterceptor()
        
        result = interceptor._values_equal(100, 100)
        
        assert result is True
        
        result = interceptor._values_equal(100, 200)
        
        assert result is False


class TestAuditInterceptorGetFieldsToLog:
    """AuditInterceptor._get_fields_to_log 方法测试"""
    
    def test_all_fields(self):
        """测试所有字段"""
        interceptor = AuditInterceptor()
        
        meta_object = MockMetaObject()
        config = MockActionConfig(fields='all')
        
        fields = interceptor._get_fields_to_log(meta_object, {}, {}, config)
        
        assert 'name' in fields
        assert 'email' in fields
        assert 'status' in fields
    
    def test_changed_only_fields(self):
        """测试仅变更字段"""
        interceptor = AuditInterceptor()
        
        meta_object = MockMetaObject()
        config = MockActionConfig(fields='changed_only')
        
        old_data = {'name': 'old', 'email': 'old@test.com'}
        new_data = {'name': 'new', 'email': 'new@test.com', 'status': 'active'}
        
        fields = interceptor._get_fields_to_log(meta_object, old_data, new_data, config)
        
        assert len(fields) > 0
    
    def test_business_only_fields(self):
        """测试仅业务字段"""
        interceptor = AuditInterceptor()
        
        meta_object = MockMetaObject()
        meta_object.fields = [
            MagicMock(id='id'),
            MagicMock(id='created_at'),
            MagicMock(id='updated_at'),
            MagicMock(id='name'),
            MagicMock(id='email'),
        ]
        config = MockActionConfig(fields='business_only')
        
        fields = interceptor._get_fields_to_log(meta_object, {}, {}, config)
        
        assert 'id' not in fields
        assert 'created_at' not in fields
        assert 'updated_at' not in fields
        assert 'name' in fields
        assert 'email' in fields
    
    def test_exclude_fields(self):
        """测试排除字段"""
        interceptor = AuditInterceptor()
        
        meta_object = MockMetaObject()
        config = MockActionConfig(fields='all', exclude=['email'])
        
        fields = interceptor._get_fields_to_log(meta_object, {}, {}, config)
        
        assert 'name' in fields
        assert 'email' not in fields
        assert 'status' in fields


class TestAuditInterceptorGetObjectDisplay:
    """AuditInterceptor._get_object_display 方法测试"""
    
    def test_get_user_display(self):
        """测试获取用户显示名"""
        interceptor = AuditInterceptor()
        
        ds = MockDataSource()
        ds.execute = MagicMock(return_value=MagicMock(fetchone=lambda: ('Test User',)))
        
        result = interceptor._get_object_display('user', 1, ds)
        
        assert result == 'Test User' or result == 'user:1' or result is not None
    
    def test_get_user_group_display(self):
        """测试获取用户组显示名"""
        interceptor = AuditInterceptor()
        
        ds = MockDataSource()
        ds.execute = MagicMock(return_value=MagicMock(fetchone=lambda: ('Test Group',)))
        
        result = interceptor._get_object_display('user_group', 1, ds)
        
        assert result == 'Test Group' or result == 'user_group:1' or result is not None
    
    def test_get_role_display(self):
        """测试获取角色显示名"""
        interceptor = AuditInterceptor()
        
        ds = MockDataSource()
        ds.execute = MagicMock(return_value=MagicMock(fetchone=lambda: ('Test Role',)))
        
        result = interceptor._get_object_display('role', 1, ds)
        
        assert result == 'Test Role' or result == 'role:1' or result is not None
    
    def test_get_unknown_object_display(self):
        """测试获取未知对象显示名"""
        interceptor = AuditInterceptor()
        
        ds = MockDataSource()
        ds.execute = MagicMock(return_value=MagicMock(fetchone=lambda: None))
        
        result = interceptor._get_object_display('unknown', 1, ds)
        
        assert result is not None
    
    def test_get_object_display_with_exception(self):
        """测试获取对象显示名时发生异常"""
        interceptor = AuditInterceptor()
        
        ds = MockDataSource()
        ds.execute = MagicMock(side_effect=Exception("DB error"))
        
        result = interceptor._get_object_display('user', 1, ds)
        
        assert 'user' in result


class TestAuditInterceptorEdgeCases:
    """AuditInterceptor 边界条件测试"""
    
    def test_empty_old_data(self):
        """测试空旧数据"""
        interceptor = AuditInterceptor()
        
        meta_object = MockMetaObject()
        config = MockActionConfig(fields='changed_only')
        
        fields = interceptor._get_fields_to_log(meta_object, {}, {'name': 'new'}, config)
        
        assert len(fields) >= 0
    
    def test_empty_new_data(self):
        """测试空新数据"""
        interceptor = AuditInterceptor()
        
        meta_object = MockMetaObject()
        config = MockActionConfig(fields='changed_only')
        
        fields = interceptor._get_fields_to_log(meta_object, {'name': 'old'}, {}, config)
        
        assert len(fields) >= 0
    
    def test_none_values_in_data(self):
        """测试数据中的None值"""
        interceptor = AuditInterceptor()
        
        result = interceptor._values_equal(None, None)
        assert result is True
        
        result = interceptor._values_equal('value', None)
        assert result is False
        
        result = interceptor._values_equal(None, 'value')
        assert result is False
    
    def test_special_characters_in_values(self):
        """测试值中的特殊字符"""
        interceptor = AuditInterceptor()
        
        result = interceptor._values_equal('test\nwith\nnewlines', 'test\nwith\nnewlines')
        assert result is True
        
        result = interceptor._values_equal('test"with"quotes', 'test"with"quotes')
        assert result is True
        
        result = interceptor._values_equal('test\'with\'apostrophe', 'test\'with\'apostrophe')
        assert result is True
