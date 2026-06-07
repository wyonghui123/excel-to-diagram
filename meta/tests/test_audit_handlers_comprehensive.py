import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
审计日志处理器全面测试用例

测试范围：
1. AuditLogArchiveHandler - 审计日志归档处理器
2. AuditLogCleanupHandler - 审计日志清理处理器
3. AuditFailureRetryHandler - 审计日志失败重试处理器
4. 边界条件测试
5. 错误处理测试
6. 并发安全测试
"""

import pytest
import sqlite3
import tempfile
import os
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

from meta.handlers.audit_handlers import (
    AuditLogArchiveHandler, AuditLogCleanupHandler, AuditFailureRetryHandler
)
from meta.core.task_handler import TaskResult


class MockDataSource:
    def __init__(self):
        self.executed = []
        self.committed = False
        self.queries = []
        self._in_transaction = False
    
    @property
    def in_transaction(self):
        return self._in_transaction
    
    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self
    
    def query(self, sql, params=None):
        self.queries.append((sql, params))
        return []
    
    def commit(self):
        self.committed = True
        self._in_transaction = False
    
    def checkpoint(self, mode):
        self.executed.append((f"CHECKPOINT {mode}", None))


class TestAuditLogArchiveHandlerComprehensive:
    """审计日志归档处理器全面测试"""
    
    def test_execute_with_default_archive_days(self):
        """测试使用默认归档天数"""
        handler = AuditLogArchiveHandler()
        ds = MockDataSource()
        context = {'data_source': ds}
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert ds.committed is True
        assert any('archived' in str(e) for e in ds.executed)
    
    def test_execute_with_custom_archive_days(self):
        """测试使用自定义归档天数"""
        handler = AuditLogArchiveHandler()
        ds = MockDataSource()
        context = {
            'data_source': ds,
            'handler_config': {'archive_days': 30}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert ds.committed is True
    
    def test_execute_with_zero_archive_days(self):
        """测试归档天数为0的边界条件"""
        handler = AuditLogArchiveHandler()
        ds = MockDataSource()
        context = {
            'data_source': ds,
            'handler_config': {'archive_days': 0}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
    
    def test_execute_with_negative_archive_days(self):
        """测试归档天数为负数的边界条件"""
        handler = AuditLogArchiveHandler()
        ds = MockDataSource()
        context = {
            'data_source': ds,
            'handler_config': {'archive_days': -1}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
    
    def test_execute_with_large_archive_days(self):
        """测试大归档天数"""
        handler = AuditLogArchiveHandler()
        ds = MockDataSource()
        context = {
            'data_source': ds,
            'handler_config': {'archive_days': 3650}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
    
    def test_execute_with_missing_data_source(self):
        """测试缺少数据源的情况"""
        handler = AuditLogArchiveHandler()
        context = {}
        
        result = handler.execute({}, context)
        
        assert result.success is False
        assert result.error is not None
    
    def test_execute_with_none_data_source(self):
        """测试数据源为None的情况"""
        handler = AuditLogArchiveHandler()
        context = {'data_source': None}
        
        result = handler.execute({}, context)
        
        assert result.success is False
    
    def test_execute_with_execute_exception(self):
        """测试执行时发生异常"""
        handler = AuditLogArchiveHandler()
        ds = MagicMock()
        ds.execute.side_effect = Exception("Database connection lost")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert "Database connection lost" in result.error
    
    def test_execute_with_commit_exception(self):
        """测试提交时发生异常"""
        handler = AuditLogArchiveHandler()
        ds = MagicMock()
        ds.execute.return_value = ds
        ds.commit.side_effect = Exception("Commit failed")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert "Commit failed" in result.error
    
    def test_execute_with_params_passed(self):
        """测试参数传递"""
        handler = AuditLogArchiveHandler()
        ds = MockDataSource()
        context = {'data_source': ds}
        params = {'extra': 'data'}
        
        result = handler.execute(params, context)
        
        assert result.success is True


class TestAuditLogCleanupHandlerComprehensive:
    """审计日志清理处理器全面测试"""
    
    def test_execute_with_default_retention(self):
        """测试使用默认保留天数"""
        handler = AuditLogCleanupHandler()
        ds = MockDataSource()
        context = {'data_source': ds}
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert ds.committed is True
    
    def test_execute_with_custom_retention(self):
        """测试使用自定义保留天数"""
        handler = AuditLogCleanupHandler()
        ds = MockDataSource()
        retention = {
            'business': 180,
            'security': 365,
            'operation': 60,
            'performance': 15,
            'system': 30,
        }
        context = {
            'data_source': ds,
            'handler_config': {'retention_days': retention}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['categories_processed'] == 5
    
    def test_execute_with_partial_retention_config(self):
        """测试部分保留配置"""
        handler = AuditLogCleanupHandler()
        ds = MockDataSource()
        retention = {
            'business': 180,
            'security': 365,
        }
        context = {
            'data_source': ds,
            'handler_config': {'retention_days': retention}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['categories_processed'] == 2
    
    def test_execute_with_empty_retention_config(self):
        """测试空保留配置"""
        handler = AuditLogCleanupHandler()
        ds = MockDataSource()
        context = {
            'data_source': ds,
            'handler_config': {'retention_days': {}}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['categories_processed'] == 0
    
    def test_execute_with_zero_retention_days(self):
        """测试保留天数为0"""
        handler = AuditLogCleanupHandler()
        ds = MockDataSource()
        retention = {'business': 0}
        context = {
            'data_source': ds,
            'handler_config': {'retention_days': retention}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
    
    def test_execute_with_very_large_retention_days(self):
        """测试非常大的保留天数"""
        handler = AuditLogCleanupHandler()
        ds = MockDataSource()
        retention = {'business': 3650}
        context = {
            'data_source': ds,
            'handler_config': {'retention_days': retention}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
    
    def test_execute_with_missing_data_source(self):
        """测试缺少数据源"""
        handler = AuditLogCleanupHandler()
        context = {}
        
        result = handler.execute({}, context)
        
        assert result.success is False
    
    def test_execute_with_execute_exception(self):
        """测试执行异常"""
        handler = AuditLogCleanupHandler()
        ds = MagicMock()
        ds.execute.side_effect = Exception("Cleanup failed")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert "Cleanup failed" in result.error
    
    def test_execute_with_additional_categories(self):
        """测试额外的日志分类"""
        handler = AuditLogCleanupHandler()
        ds = MockDataSource()
        retention = {
            'business': 365,
            'security': 2555,
            'operation': 90,
            'performance': 30,
            'system': 90,
            'custom_category': 120,
        }
        context = {
            'data_source': ds,
            'handler_config': {'retention_days': retention}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['categories_processed'] == 6


class TestAuditFailureRetryHandlerComprehensive:
    """审计日志失败重试处理器全面测试"""
    
    def test_execute_with_failed_logs(self):
        """测试有失败日志的情况"""
        handler = AuditFailureRetryHandler()
        ds = MagicMock()
        ds.query.return_value = [{'id': 1}, {'id': 2}, {'id': 3}]
        ds.commit = MagicMock()
        
        context = {
            'data_source': ds,
            'handler_config': {'batch_size': 100, 'max_retries': 3}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['retried'] == 3
    
    def test_execute_with_no_failed_logs(self):
        """测试没有失败日志的情况"""
        handler = AuditFailureRetryHandler()
        ds = MagicMock()
        ds.query.return_value = []
        ds.commit = MagicMock()
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['retried'] == 0
    
    def test_execute_with_large_batch(self):
        """测试大批量处理"""
        handler = AuditFailureRetryHandler()
        ds = MagicMock()
        failed_logs = [{'id': i} for i in range(100)]
        ds.query.return_value = failed_logs
        ds.commit = MagicMock()
        
        context = {
            'data_source': ds,
            'handler_config': {'batch_size': 100, 'max_retries': 3}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['retried'] == 100
    
    def test_execute_with_custom_batch_size(self):
        """测试自定义批次大小"""
        handler = AuditFailureRetryHandler()
        ds = MagicMock()
        ds.query.return_value = [{'id': 1}, {'id': 2}]
        ds.commit = MagicMock()
        
        context = {
            'data_source': ds,
            'handler_config': {'batch_size': 10, 'max_retries': 5}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['retried'] == 2
    
    def test_execute_with_max_retries_reached(self):
        """测试达到最大重试次数"""
        handler = AuditFailureRetryHandler()
        ds = MagicMock()
        ds.query.return_value = [{'id': 1}]
        ds.commit = MagicMock()
        
        context = {
            'data_source': ds,
            'handler_config': {'batch_size': 100, 'max_retries': 1}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['retried'] == 1
    
    def test_execute_with_missing_data_source(self):
        """测试缺少数据源"""
        handler = AuditFailureRetryHandler()
        context = {}
        
        result = handler.execute({}, context)
        
        assert result.success is False
    
    def test_execute_with_query_exception(self):
        """测试查询异常"""
        handler = AuditFailureRetryHandler()
        ds = MagicMock()
        ds.query.side_effect = Exception("Query failed")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert "Query failed" in result.error
    
    def test_execute_with_update_exception(self):
        """测试更新异常"""
        handler = AuditFailureRetryHandler()
        ds = MagicMock()
        ds.query.return_value = [{'id': 1}]
        ds.execute.side_effect = Exception("Update failed")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert "Update failed" in result.error
    
    def test_execute_with_commit_exception(self):
        """测试提交异常"""
        handler = AuditFailureRetryHandler()
        ds = MagicMock()
        ds.query.return_value = [{'id': 1}]
        ds.commit.side_effect = Exception("Commit failed")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert "Commit failed" in result.error


class TestAuditHandlersWithRealDatabase:
    """使用真实数据库的审计处理器测试"""
    
    @pytest.fixture
    def temp_db(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
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
                status_entered_at TEXT
            );
        """)
        conn.commit()
        yield conn, path
        conn.close()
        try:
            os.unlink(path)
        except:
            pass
    
    def test_archive_handler_real_db(self, temp_db):
        """测试归档处理器使用真实数据库"""
        conn, path = temp_db
        
        now = datetime.now().isoformat()
        old_date = (datetime.now() - timedelta(days=100)).isoformat()
        
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, status, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, ('user', '1', 'CREATE', 'written', old_date))
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, status, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, ('user', '2', 'UPDATE', 'written', now))
        conn.commit()
        
        from meta.core.datasource import get_data_source
        ds = get_data_source("sqlite", database=path)
        
        handler = AuditLogArchiveHandler()
        context = {
            'data_source': ds,
            'handler_config': {'archive_days': 90}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
        
        cursor = conn.execute("SELECT status FROM audit_logs WHERE object_id = '1'")
        row = cursor.fetchone()
        assert row['status'] == 'archived'
        
        cursor = conn.execute("SELECT status FROM audit_logs WHERE object_id = '2'")
        row = cursor.fetchone()
        assert row['status'] == 'written'
    
    def test_cleanup_handler_real_db(self, temp_db):
        """测试清理处理器使用真实数据库"""
        conn, path = temp_db
        
        old_date = (datetime.now() - timedelta(days=400)).isoformat()
        recent_date = (datetime.now() - timedelta(days=10)).isoformat()
        
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, log_category, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, ('user', '1', 'CREATE', 'business', old_date))
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, log_category, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, ('user', '2', 'UPDATE', 'business', recent_date))
        conn.commit()
        
        from meta.core.datasource import get_data_source
        ds = get_data_source("sqlite", database=path)
        
        handler = AuditLogCleanupHandler()
        context = {
            'data_source': ds,
            'handler_config': {'retention_days': {'business': 365}}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
        
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM audit_logs")
        row = cursor.fetchone()
        assert row['cnt'] == 1
    
    def test_retry_handler_real_db(self, temp_db):
        """测试重试处理器使用真实数据库"""
        conn, path = temp_db
        
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, status, retry_count)
            VALUES (?, ?, ?, ?, ?)
        """, ('user', '1', 'CREATE', 'failed', 0))
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, status, retry_count)
            VALUES (?, ?, ?, ?, ?)
        """, ('user', '2', 'UPDATE', 'failed', 2))
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, status, retry_count)
            VALUES (?, ?, ?, ?, ?)
        """, ('user', '3', 'DELETE', 'written', 0))
        conn.commit()
        
        from meta.core.datasource import get_data_source
        ds = get_data_source("sqlite", database=path)
        
        handler = AuditFailureRetryHandler()
        context = {
            'data_source': ds,
            'handler_config': {'batch_size': 100, 'max_retries': 3}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['retried'] == 2
        
        cursor = conn.execute("SELECT status, retry_count FROM audit_logs WHERE object_id = '1'")
        row = cursor.fetchone()
        assert row['status'] == 'pending'
        assert row['retry_count'] == 1


class TestAuditHandlersConcurrency:
    """审计处理器并发测试"""
    
    def test_archive_handler_thread_safety(self):
        """测试归档处理器的线程安全性"""
        results = []
        errors = []
        
        def run_handler():
            try:
                handler = AuditLogArchiveHandler()
                ds = MockDataSource()
                context = {'data_source': ds}
                result = handler.execute({}, context)
                results.append(result)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=run_handler) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(results) == 10
        assert all(r.success for r in results)
    
    def test_cleanup_handler_thread_safety(self):
        """测试清理处理器的线程安全性"""
        results = []
        errors = []
        
        def run_handler():
            try:
                handler = AuditLogCleanupHandler()
                ds = MockDataSource()
                context = {'data_source': ds}
                result = handler.execute({}, context)
                results.append(result)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=run_handler) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(results) == 10
        assert all(r.success for r in results)
    
    def test_retry_handler_thread_safety(self):
        """测试重试处理器的线程安全性"""
        results = []
        errors = []
        
        def run_handler():
            try:
                handler = AuditFailureRetryHandler()
                ds = MagicMock()
                ds.query.return_value = [{'id': 1}]
                ds.commit = MagicMock()
                context = {'data_source': ds}
                result = handler.execute({}, context)
                results.append(result)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=run_handler) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(results) == 10
        assert all(r.success for r in results)


class TestTaskResultComprehensive:
    """TaskResult 全面测试"""
    
    def test_success_result_with_data(self):
        """测试成功结果带数据"""
        result = TaskResult(success=True, data={'key': 'value', 'count': 10})
        assert result.success is True
        assert result.data == {'key': 'value', 'count': 10}
        assert result.error is None
    
    def test_failure_result_with_error(self):
        """测试失败结果带错误信息"""
        result = TaskResult(success=False, error="Something went wrong")
        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.data is None
    
    def test_result_with_ai_metadata(self):
        """测试带AI元数据的结果"""
        result = TaskResult(
            success=True,
            data={'response': 'Hello'},
            tokens_used=100,
            cost=0.001,
            model_used='gpt-4'
        )
        assert result.tokens_used == 100
        assert result.cost == 0.001
        assert result.model_used == 'gpt-4'
    
    def test_result_with_empty_data(self):
        """测试空数据结果"""
        result = TaskResult(success=True, data={})
        assert result.success is True
        assert result.data == {}
    
    def test_result_with_none_data(self):
        """测试None数据结果"""
        result = TaskResult(success=True)
        assert result.success is True
        assert result.data is None
    
    def test_result_with_complex_data(self):
        """测试复杂数据结果"""
        complex_data = {
            'nested': {
                'level1': {
                    'level2': ['a', 'b', 'c']
                }
            },
            'list': [1, 2, 3],
            'string': 'test'
        }
        result = TaskResult(success=True, data=complex_data)
        assert result.success is True
        assert result.data == complex_data
    
    def test_result_with_long_error_message(self):
        """测试长错误信息"""
        long_error = "Error: " + "x" * 1000
        result = TaskResult(success=False, error=long_error)
        assert result.success is False
        assert len(result.error) == 1007
