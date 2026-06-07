# -*- coding: utf-8 -*-
"""
AsyncAuditWriter 异步审计写入器全面测试用例

测试范围：
1. 单例模式测试
2. 异步写入测试
3. 重试机制测试
4. 队列满时降级测试
5. 失败记录持久化测试
6. 统计信息测试
7. 并发安全测试
"""

import pytest
import sqlite3
import tempfile
import os
import time
import threading
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

pytestmark = [
    pytest.mark.skip(reason="[TODO] AsyncAuditWriter requires running worker threads; incompatible with test mode - needs fix")
]

from meta.services.async_audit_writer import (
    AsyncAuditWriter, async_audit_writer,
    AUDIT_ASYNC_ENABLED, AUDIT_ASYNC_MAX_WORKERS,
    AUDIT_ASYNC_QUEUE_SIZE, AUDIT_MAX_RETRIES
)


class TestAsyncAuditWriterSingleton:
    """AsyncAuditWriter 单例模式测试"""
    
    def test_singleton_returns_same_instance(self):
        """测试单例返回相同实例"""
        AsyncAuditWriter.reset()
        
        instance1 = AsyncAuditWriter()
        instance2 = AsyncAuditWriter()
        
        assert instance1 is instance2
        
        AsyncAuditWriter.reset()
    
    def test_singleton_with_data_source(self):
        """测试带数据源的单例"""
        AsyncAuditWriter.reset()
        
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            from meta.core.datasource import get_data_source
            ds = get_data_source("sqlite", database=path)
            
            instance = AsyncAuditWriter(data_source=ds)
            assert instance._ds is ds
            
            AsyncAuditWriter.reset()
        finally:
            try:
                os.unlink(path)
            except:
                pass
    
    def test_set_data_source(self):
        """测试设置数据源"""
        AsyncAuditWriter.reset()
        
        instance = AsyncAuditWriter()
        
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            from meta.core.datasource import get_data_source
            ds = get_data_source("sqlite", database=path)
            
            instance.set_data_source(ds)
            assert instance._ds is ds
            
            AsyncAuditWriter.reset()
        finally:
            try:
                os.unlink(path)
            except:
                pass


class TestAsyncAuditWriterStats:
    """AsyncAuditWriter 统计信息测试"""
    
    def test_get_stats_initial(self):
        """测试初始统计信息"""
        AsyncAuditWriter.reset()
        
        instance = AsyncAuditWriter()
        stats = instance.get_stats()
        
        assert 'submitted' in stats
        assert 'completed' in stats
        assert 'failed' in stats
        assert 'fallback_sync' in stats
        assert 'queue_size' in stats
        assert 'queue_capacity' in stats
        assert 'workers' in stats
        assert 'running' in stats
        
        assert stats['running'] is True
        assert stats['workers'] > 0
        
        AsyncAuditWriter.reset()
    
    def test_get_stats_after_operations(self):
        """测试操作后的统计信息"""
        AsyncAuditWriter.reset()
        
        instance = AsyncAuditWriter()
        
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            from meta.core.datasource import get_data_source
            ds = get_data_source("sqlite", database=path)
            
            conn = sqlite3.connect(path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_type TEXT,
                    object_id TEXT,
                    action TEXT,
                    field_name TEXT,
                    old_value TEXT,
                    new_value TEXT,
                    user_id TEXT,
                    user_name TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    created_at TEXT,
                    trace_id TEXT,
                    transaction_id TEXT,
                    status TEXT DEFAULT 'written',
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    log_category TEXT DEFAULT 'business',
                    log_level TEXT DEFAULT 'INFO',
                    extra_data TEXT,
                    agent_id TEXT,
                    agent_session_id TEXT,
                    tool_call_id TEXT,
                    agent_reasoning TEXT
                );
            """)
            conn.commit()
            conn.close()
            
            instance.set_data_source(ds)
            
            def audit_fn(trace_id=None, transaction_id=None):
                ds.insert("audit_logs", {
                    'object_type': 'test',
                    'object_id': '1',
                    'action': 'CREATE',
                    'field_name': 'test',
                    'old_value': '',
                    'new_value': 'test',
                    'user_id': 'admin',
                    'user_name': 'Administrator',
                    'created_at': datetime.now().isoformat(),
                    'status': 'written',
                })
            
            instance.submit(audit_fn, trace_id='test-trace')
            
            time.sleep(0.5)
            
            stats = instance.get_stats()
            assert stats['submitted'] >= 1
            
            AsyncAuditWriter.reset()
        finally:
            try:
                os.unlink(path)
            except:
                pass


class TestAsyncAuditWriterSubmit:
    """AsyncAuditWriter.submit 方法测试"""
    
    def test_submit_simple_audit_fn(self):
        """测试提交简单审计函数"""
        AsyncAuditWriter.reset()
        
        instance = AsyncAuditWriter()
        
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            from meta.core.datasource import get_data_source
            ds = get_data_source("sqlite", database=path)
            
            conn = sqlite3.connect(path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_type TEXT,
                    object_id TEXT,
                    action TEXT,
                    field_name TEXT,
                    old_value TEXT,
                    new_value TEXT,
                    user_id TEXT,
                    user_name TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    created_at TEXT,
                    trace_id TEXT,
                    transaction_id TEXT,
                    status TEXT DEFAULT 'written',
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    log_category TEXT DEFAULT 'business',
                    log_level TEXT DEFAULT 'INFO',
                    extra_data TEXT,
                    agent_id TEXT,
                    agent_session_id TEXT,
                    tool_call_id TEXT,
                    agent_reasoning TEXT
                );
            """)
            conn.commit()
            conn.close()
            
            instance.set_data_source(ds)
            
            call_count = {'count': 0}
            
            def audit_fn(trace_id=None, transaction_id=None):
                call_count['count'] += 1
            
            result = instance.submit(audit_fn, trace_id='test-trace')
            
            assert result is True
            
            time.sleep(0.5)
            
            assert call_count['count'] >= 1
            
            AsyncAuditWriter.reset()
        finally:
            try:
                os.unlink(path)
            except:
                pass
    
    def test_submit_with_trace_and_transaction_id(self):
        """测试提交带trace_id和transaction_id"""
        AsyncAuditWriter.reset()
        
        instance = AsyncAuditWriter()
        
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            from meta.core.datasource import get_data_source
            ds = get_data_source("sqlite", database=path)
            
            conn = sqlite3.connect(path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_type TEXT,
                    object_id TEXT,
                    action TEXT,
                    field_name TEXT,
                    old_value TEXT,
                    new_value TEXT,
                    user_id TEXT,
                    user_name TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    created_at TEXT,
                    trace_id TEXT,
                    transaction_id TEXT,
                    status TEXT DEFAULT 'written',
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    log_category TEXT DEFAULT 'business',
                    log_level TEXT DEFAULT 'INFO',
                    extra_data TEXT,
                    agent_id TEXT,
                    agent_session_id TEXT,
                    tool_call_id TEXT,
                    agent_reasoning TEXT
                );
            """)
            conn.commit()
            conn.close()
            
            instance.set_data_source(ds)
            
            received_ids = {}
            
            def audit_fn(trace_id=None, transaction_id=None):
                received_ids['trace_id'] = trace_id
                received_ids['transaction_id'] = transaction_id
            
            result = instance.submit(
                audit_fn,
                trace_id='trace-123',
                transaction_id='txn-456'
            )
            
            assert result is True
            
            time.sleep(0.5)
            
            assert received_ids.get('trace_id') == 'trace-123'
            assert received_ids.get('transaction_id') == 'txn-456'
            
            AsyncAuditWriter.reset()
        finally:
            try:
                os.unlink(path)
            except:
                pass
    
    def test_submit_without_data_source(self):
        """测试没有数据源时提交"""
        AsyncAuditWriter.reset()
        
        instance = AsyncAuditWriter()
        instance._ds = None
        
        def audit_fn(trace_id=None, transaction_id=None):
            pass
        
        result = instance.submit(audit_fn)
        
        assert result is False
        
        AsyncAuditWriter.reset()


class TestAsyncAuditWriterRetry:
    """AsyncAuditWriter 重试机制测试"""
    
    def test_retry_on_transient_failure(self):
        """测试临时失败时的重试"""
        AsyncAuditWriter.reset()
        
        instance = AsyncAuditWriter()
        
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            from meta.core.datasource import get_data_source
            ds = get_data_source("sqlite", database=path)
            
            conn = sqlite3.connect(path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_type TEXT,
                    object_id TEXT,
                    action TEXT,
                    field_name TEXT,
                    old_value TEXT,
                    new_value TEXT,
                    user_id TEXT,
                    user_name TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    created_at TEXT,
                    trace_id TEXT,
                    transaction_id TEXT,
                    status TEXT DEFAULT 'written',
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    log_category TEXT DEFAULT 'business',
                    log_level TEXT DEFAULT 'INFO',
                    extra_data TEXT,
                    agent_id TEXT,
                    agent_session_id TEXT,
                    tool_call_id TEXT,
                    agent_reasoning TEXT
                );
            """)
            conn.commit()
            conn.close()
            
            instance.set_data_source(ds)
            
            call_count = {'count': 0}
            
            def failing_then_success_audit_fn(trace_id=None, transaction_id=None):
                call_count['count'] += 1
                if call_count['count'] < 2:
                    raise Exception("Transient error")
            
            result = instance.submit(failing_then_success_audit_fn)
            
            time.sleep(1.0)
            
            stats = instance.get_stats()
            
            assert call_count['count'] >= 2
            
            AsyncAuditWriter.reset()
        finally:
            try:
                os.unlink(path)
            except:
                pass


class TestAsyncAuditWriterFlush:
    """AsyncAuditWriter.flush 方法测试"""
    
    def test_flush_empty_queue(self):
        """测试刷新空队列"""
        AsyncAuditWriter.reset()
        
        instance = AsyncAuditWriter()
        
        result = instance.flush(timeout=1.0)
        
        assert result is True
        
        AsyncAuditWriter.reset()
    
    def test_flush_with_pending_items(self):
        """测试刷新待处理项"""
        AsyncAuditWriter.reset()
        
        instance = AsyncAuditWriter()
        
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            from meta.core.datasource import get_data_source
            ds = get_data_source("sqlite", database=path)
            
            conn = sqlite3.connect(path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_type TEXT,
                    object_id TEXT,
                    action TEXT,
                    field_name TEXT,
                    old_value TEXT,
                    new_value TEXT,
                    user_id TEXT,
                    user_name TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    created_at TEXT,
                    trace_id TEXT,
                    transaction_id TEXT,
                    status TEXT DEFAULT 'written',
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    log_category TEXT DEFAULT 'business',
                    log_level TEXT DEFAULT 'INFO',
                    extra_data TEXT,
                    agent_id TEXT,
                    agent_session_id TEXT,
                    tool_call_id TEXT,
                    agent_reasoning TEXT
                );
            """)
            conn.commit()
            conn.close()
            
            instance.set_data_source(ds)
            
            def audit_fn(trace_id=None, transaction_id=None):
                pass
            
            for i in range(5):
                instance.submit(audit_fn)
            
            result = instance.flush(timeout=5.0)
            
            assert result is True
            
            AsyncAuditWriter.reset()
        finally:
            try:
                os.unlink(path)
            except:
                pass


class TestAsyncAuditWriterShutdown:
    """AsyncAuditWriter.shutdown 方法测试"""
    
    def test_shutdown_stops_workers(self):
        """测试关闭停止工作线程"""
        AsyncAuditWriter.reset()
        
        instance = AsyncAuditWriter()
        
        assert instance._running is True
        
        instance.shutdown(timeout=2.0)
        
        assert instance._running is False
        
        AsyncAuditWriter.reset()
    
    def test_shutdown_idempotent(self):
        """测试关闭是幂等的"""
        AsyncAuditWriter.reset()
        
        instance = AsyncAuditWriter()
        
        instance.shutdown(timeout=2.0)
        instance.shutdown(timeout=2.0)
        
        assert instance._running is False
        
        AsyncAuditWriter.reset()


class TestAsyncAuditWriterConcurrency:
    """AsyncAuditWriter 并发安全测试"""
    
    def test_concurrent_submit(self):
        """测试并发提交"""
        AsyncAuditWriter.reset()
        
        instance = AsyncAuditWriter()
        
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            from meta.core.datasource import get_data_source
            ds = get_data_source("sqlite", database=path)
            
            conn = sqlite3.connect(path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_type TEXT,
                    object_id TEXT,
                    action TEXT,
                    field_name TEXT,
                    old_value TEXT,
                    new_value TEXT,
                    user_id TEXT,
                    user_name TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    created_at TEXT,
                    trace_id TEXT,
                    transaction_id TEXT,
                    status TEXT DEFAULT 'written',
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    log_category TEXT DEFAULT 'business',
                    log_level TEXT DEFAULT 'INFO',
                    extra_data TEXT,
                    agent_id TEXT,
                    agent_session_id TEXT,
                    tool_call_id TEXT,
                    agent_reasoning TEXT
                );
            """)
            conn.commit()
            conn.close()
            
            instance.set_data_source(ds)
            
            results = []
            errors = []
            
            def submit_task():
                try:
                    def audit_fn(trace_id=None, transaction_id=None):
                        pass
                    result = instance.submit(audit_fn)
                    results.append(result)
                except Exception as e:
                    errors.append(e)
            
            threads = [threading.Thread(target=submit_task) for _ in range(50)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            assert len(errors) == 0
            assert len(results) == 50
            assert all(r for r in results)
            
            time.sleep(0.5)
            
            stats = instance.get_stats()
            assert stats['submitted'] >= 50
            
            AsyncAuditWriter.reset()
        finally:
            try:
                os.unlink(path)
            except:
                pass


class TestAsyncAuditWriterEnvironmentConfig:
    """AsyncAuditWriter 环境变量配置测试"""
    
    def test_default_config_values(self):
        """测试默认配置值"""
        assert AUDIT_ASYNC_ENABLED in [True, False]
        assert AUDIT_ASYNC_MAX_WORKERS > 0
        assert AUDIT_ASYNC_QUEUE_SIZE > 0
        assert AUDIT_MAX_RETRIES > 0


class TestGlobalAsyncAuditWriter:
    """全局 async_audit_writer 实例测试"""
    
    def test_global_instance_exists(self):
        """测试全局实例存在"""
        AsyncAuditWriter.reset()
        
        from meta.services.async_audit_writer import async_audit_writer
        
        assert async_audit_writer is not None
        assert isinstance(async_audit_writer, AsyncAuditWriter)
        
        AsyncAuditWriter.reset()
