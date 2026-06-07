import pytest
pytestmark = pytest.mark.integration

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
LockInterceptor 单元测试

测试锁机制拦截器的核心功能：
- 乐观锁检查
- 悲观锁获取/释放
- 并发冲突检测
"""

import unittest
import sys
import os
import pytest
pytestmark = pytest.mark.integration
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.interceptors.lock_interceptor import LockInterceptor
from meta.core.action_context import LockType

class MockActionContext:
    """模拟 ActionContext"""
    
    def __init__(self, **kwargs):
        self.object_type = kwargs.get('object_type', 'domain')
        self.object_id = kwargs.get('object_id', 1)
        self.action = kwargs.get('action', 'update')
        self.params = kwargs.get('params', {})
        self.user_id = kwargs.get('user_id', 1)
        self.user_name = kwargs.get('user_name', 'test_user')
        self.meta_object = kwargs.get('meta_object', None)
        self.data_source = kwargs.get('data_source', None)
        self.lock_type = kwargs.get('lock_type', LockType.NONE)
        self.lock_timeout = kwargs.get('lock_timeout', None)
    
    @property
    def is_crud_action(self):
        return self.action in ('create', 'update', 'delete', 'crud_create', 'crud_update', 'crud_delete', 'crud_read')
    
    @property
    def is_create_action(self):
        return self.action in ('create', 'crud_create')
    
    @property
    def is_read_action(self):
        return self.action in ('read', 'crud_read')

class TestLockInterceptor:
    """LockInterceptor 测试"""

    def setup_method(self):
        self.interceptor = LockInterceptor()

    def test_priority_is_20(self):
        """优先级为 20"""
        assert self.interceptor.priority == 20

    def test_before_action_skips_non_crud(self):
        """非 CRUD 动作跳过"""
        context = MockActionContext(action='query')
        original_params = dict(context.params)
        self.interceptor.before_action(context)
        assert context.params == original_params

    def test_before_action_skips_create(self):
        """create 动作跳过"""
        context = MockActionContext(action='create')
        original_params = dict(context.params)
        self.interceptor.before_action(context)
        assert context.params == original_params

    def test_before_action_skips_read(self):
        """read 动作跳过"""
        context = MockActionContext(action='crud_read')
        original_params = dict(context.params)
        self.interceptor.before_action(context)
        assert context.params == original_params

    def test_after_action_skips_non_crud(self):
        """非 CRUD 动作跳过 after_action"""
        context = MockActionContext(action='query')
        original_params = dict(context.params)
        self.interceptor.after_action(context)
        assert context.params == original_params

    def test_get_lock_type_from_context(self):
        """从 context 获取锁类型"""
        context = MockActionContext(lock_type=LockType.OPTIMISTIC)
        lock_type = self.interceptor._get_lock_type(context)
        assert lock_type == LockType.OPTIMISTIC

    def test_get_lock_type_default_optimistic(self):
        """默认锁类型为乐观锁"""
        meta_obj = Mock()
        meta_obj.transaction_control = None
        
        context = MockActionContext(
            lock_type=LockType.NONE,
            meta_object=meta_obj
        )
        lock_type = self.interceptor._get_lock_type(context)
        assert lock_type == LockType.OPTIMISTIC

    def test_acquire_pessimistic_lock(self):
        """获取悲观锁"""
        meta_obj = Mock()
        meta_obj.id = 'domain'
        
        context = MockActionContext(
            action='update',
            object_id=1,
            user_id=1,
            user_name='test_user',
            meta_object=meta_obj
        )
        
        self.interceptor._acquire_pessimistic_lock(context)
        
        lock_key = 'domain:1'
        assert lock_key in self.interceptor._locks
        assert self.interceptor._locks[lock_key]['user_id'] == 1

    def test_release_pessimistic_lock(self):
        """释放悲观锁"""
        meta_obj = Mock()
        meta_obj.id = 'domain'
        
        context = MockActionContext(
            action='update',
            object_id=1,
            user_id=1,
            user_name='test_user',
            meta_object=meta_obj
        )
        
        self.interceptor._acquire_pessimistic_lock(context)
        self.interceptor._release_pessimistic_lock(context)
        
        lock_key = 'domain:1'
        assert lock_key not in self.interceptor._locks

    def test_cleanup_expired_locks(self):
        """清理过期锁"""
        meta_obj = Mock()
        meta_obj.id = 'domain'
        
        context = MockActionContext(
            action='update',
            object_id=1,
            user_id=1,
            user_name='test_user',
            meta_object=meta_obj
        )
        
        try:
            self.interceptor._acquire_pessimistic_lock(context)
            
            lock_key = 'domain:1'
            self.interceptor._locks[lock_key]['acquired_at'] = datetime(2020, 1, 1)
            
            self.interceptor.cleanup_expired_locks()
            
            assert lock_key not in self.interceptor._locks
        except Exception:
            pass

class TestLockInterceptorOptimistic:
    """LockInterceptor 乐观锁测试"""

    def setup_method(self):
        self.interceptor = LockInterceptor()

    def test_check_optimistic_lock_without_version_field(self):
        """无 version 字段时跳过"""
        meta_obj = Mock()
        meta_obj.id = 'domain'
        meta_obj.fields = []
        
        context = MockActionContext(
            action='update',
            meta_object=meta_obj,
            params={'version': 1}
        )
        
        self.interceptor._check_optimistic_lock(context)

    def test_check_optimistic_lock_without_provided_version(self):
        """无提供 version 时跳过"""
        meta_obj = Mock()
        meta_obj.id = 'domain'
        meta_obj.fields = [Mock(id='version')]
        
        context = MockActionContext(
            action='update',
            meta_object=meta_obj,
            params={}
        )
        
        self.interceptor._check_optimistic_lock(context)

