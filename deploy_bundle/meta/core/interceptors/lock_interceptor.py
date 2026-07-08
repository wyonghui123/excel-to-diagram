# -*- coding: utf-8 -*-
"""
锁机制拦截器

实现乐观锁和悲观锁机制，防止并发修改冲突。
"""

import logging
import threading
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from meta.core.interceptors.base import Interceptor
from meta.core.action_context import ActionContext, LockType
from meta.core.exceptions import ConcurrentModificationError

logger = logging.getLogger(__name__)


class LockInterceptor(Interceptor):
    """
    锁机制拦截器
    
    实现乐观锁和悲观锁机制，防止并发修改冲突。
    
    优先级：20（在权限检查之前执行）
    
    锁类型：
    - OPTIMISTIC: 乐观锁，使用版本号检查
    - PESSIMISTIC: 悲观锁，使用数据库锁
    """
    
    @property
    def priority(self) -> int:
        return 20
    
    def __init__(self, lock_timeout: int = 30):
        """
        初始化锁拦截器
        
        Args:
            lock_timeout: 锁超时时间（秒）
        """
        self._lock_timeout = lock_timeout
        self._locks: Dict[str, Dict[str, Any]] = {}
        self._lock_mutex = threading.RLock()
    
    def before_action(self, context: ActionContext) -> None:
        """动作执行前：获取锁"""
        if not context.is_crud_action:
            return
        
        if context.is_create_action or context.is_read_action:
            return
        
        lock_type = self._get_lock_type(context)
        
        if lock_type == LockType.OPTIMISTIC:
            self._check_optimistic_lock(context)
        elif lock_type == LockType.PESSIMISTIC:
            self._acquire_pessimistic_lock(context)
    
    def after_action(self, context: ActionContext) -> None:
        """动作执行后：释放锁"""
        if not context.is_crud_action:
            return
        
        if context.is_create_action or context.is_read_action:
            return
        
        lock_type = self._get_lock_type(context)
        
        if lock_type == LockType.PESSIMISTIC:
            self._release_pessimistic_lock(context)
    
    def _get_lock_type(self, context: ActionContext) -> LockType:
        """获取锁类型"""
        if context.lock_type != LockType.NONE:
            return context.lock_type
        
        meta_object = context.meta_object
        if hasattr(meta_object, 'transaction_control'):
            tc = meta_object.transaction_control
            if tc and hasattr(tc, 'lock_strategy'):
                strategy = tc.lock_strategy
                if strategy == 'optimistic':
                    return LockType.OPTIMISTIC
                elif strategy == 'pessimistic':
                    return LockType.PESSIMISTIC
        
        return LockType.OPTIMISTIC
    
    def _check_optimistic_lock(self, context: ActionContext) -> None:
        """检查乐观锁（版本号）"""
        meta_object = context.meta_object
        object_id = context.object_id
        
        has_version_field = any(f.id == 'version' for f in meta_object.fields)
        
        if not has_version_field:
            return
        
        params = context.params
        provided_version = params.get('version')
        
        if provided_version is None:
            return
        
        current_data = self._get_current_data(context)
        if not current_data:
            return
        
        current_version = current_data.get('version')
        
        if current_version is not None and provided_version != current_version:
            raise ConcurrentModificationError(
                f"Concurrent modification detected: object {meta_object.id}/{object_id} "
                f"has been modified by another transaction (expected version {provided_version}, "
                f"current version {current_version})"
            )
        
        logger.debug(f"[LockInterceptor] Optimistic lock check passed: {meta_object.id}/{object_id}")
    
    def _acquire_pessimistic_lock(self, context: ActionContext) -> None:
        """获取悲观锁（线程安全）"""
        meta_object = context.meta_object
        object_id = context.object_id
        
        lock_key = f"{meta_object.id}:{object_id}"
        timeout = context.lock_timeout or self._lock_timeout
        
        with self._lock_mutex:
            self._cleanup_single_lock(lock_key)
            
            if lock_key in self._locks:
                lock_info = self._locks[lock_key]
                raise ConcurrentModificationError(
                    f"Record is locked by another user: {meta_object.id}/{object_id} "
                    f"(locked by {lock_info.get('user_name')} since {lock_info.get('acquired_at')})"
                )
            
            self._locks[lock_key] = {
                'user_id': context.user_id,
                'user_name': context.user_name,
                'acquired_at': datetime.now(),
                'expires_at': datetime.now() + timedelta(seconds=timeout),
            }
        
        logger.info(f"[LockInterceptor] Pessimistic lock acquired: {lock_key} by {context.user_name}")
    
    def _release_pessimistic_lock(self, context: ActionContext) -> None:
        """释放悲观锁（线程安全）"""
        lock_key = f"{context.meta_object.id}:{context.object_id}"
        
        with self._lock_mutex:
            self._locks.pop(lock_key, None)
        
        logger.info(f"[LockInterceptor] Pessimistic lock released: {lock_key}")
    
    def _get_current_data(self, context: ActionContext) -> Optional[Dict[str, Any]]:
        """获取当前数据"""
        table_name = context.meta_object.table_name
        object_id = context.object_id
        
        try:
            cursor = context.data_source.execute(
                f"SELECT * FROM {table_name} WHERE id = ?",
                [object_id]
            )
            row = cursor.fetchone()
            
            if row:
                if isinstance(row, dict):
                    return row
                cols = [desc[0] for desc in cursor.description]
                return dict(zip(cols, row))
        except Exception as e:
            logger.error(f"[LockInterceptor] Error getting current data: {e}")
        
        return None
    
    def _cleanup_single_lock(self, lock_key: str) -> None:
        """清理单个过期锁"""
        if lock_key in self._locks:
            lock_info = self._locks[lock_key]
            expires_at = lock_info.get('expires_at')
            if expires_at and datetime.now() > expires_at:
                del self._locks[lock_key]
                logger.info(f"[LockInterceptor] Expired lock auto-cleaned: {lock_key}")
    
    def cleanup_expired_locks(self):
        """清理所有过期锁"""
        with self._lock_mutex:
            expired_keys = []
            
            for lock_key, lock_info in self._locks.items():
                expires_at = lock_info.get('expires_at')
                if not expires_at:
                    acquired_at = lock_info.get('acquired_at')
                    timeout = lock_info.get('timeout')
                    if acquired_at and timeout:
                        from datetime import timedelta
                        expires_at = acquired_at + timedelta(seconds=timeout)
                if expires_at and datetime.now() > expires_at:
                    expired_keys.append(lock_key)
            
            for key in expired_keys:
                del self._locks[key]
                logger.info(f"[LockInterceptor] Expired lock cleaned up: {key}")
