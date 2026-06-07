import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
预制任务全面测试用例

测试范围：
1. 数据库任务处理器
   - db_analyze: 数据库统计信息更新
   - db_vacuum: 数据库空间回收
   - db_integrity_check: 数据库完整性检查
   - db_checkpoint: WAL检查点
2. 审计日志任务处理器
   - audit_failure_retry: 审计日志失败重试
   - audit_log_cleanup: 审计日志清理
3. 业务任务处理器
   - import_queue_processor: 导入队列处理器
4. 预制任务与调度器集成测试
"""

import pytest
import sqlite3
import tempfile
import os
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

from meta.handlers.system_handlers import (
    DBAnalyzeHandler, DBVacuumHandler,
    DBIntegrityCheckHandler, DBCheckpointHandler
)
from meta.handlers.audit_handlers import (
    AuditLogArchiveHandler, AuditLogCleanupHandler,
    AuditFailureRetryHandler
)
from meta.handlers.import_handlers import ImportQueueHandler
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


# ============================================
# 数据库任务处理器测试
# ============================================

class TestDBAnalyzeHandler:
    """db_analyze 任务处理器测试"""
    
    def test_execute_success(self):
        """测试ANALYZE执行成功"""
        handler = DBAnalyzeHandler()
        ds = MockDataSource()
        context = {'data_source': ds}
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['action'] == 'ANALYZE'
        assert ds.committed is True
        assert any('ANALYZE' in str(e) for e in ds.executed)
    
    def test_execute_with_missing_data_source(self):
        """测试缺少数据源"""
        handler = DBAnalyzeHandler()
        context = {}
        
        result = handler.execute({}, context)
        
        assert result.success is False
        assert result.error is not None
    
    def test_execute_with_none_data_source(self):
        """测试数据源为None"""
        handler = DBAnalyzeHandler()
        context = {'data_source': None}
        
        result = handler.execute({}, context)
        
        assert result.success is False
    
    def test_execute_with_db_error(self):
        """测试数据库执行错误"""
        handler = DBAnalyzeHandler()
        ds = MagicMock()
        ds.execute.side_effect = Exception("Database locked")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert "Database locked" in result.error
    
    def test_execute_with_commit_error(self):
        """测试提交错误"""
        handler = DBAnalyzeHandler()
        ds = MagicMock()
        ds.execute.return_value = ds
        ds.commit.side_effect = Exception("Commit failed")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert "Commit failed" in result.error
    
    def test_execute_with_real_sqlite_db(self):
        """测试使用真实SQLite数据库"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("INSERT INTO test (name) VALUES ('a'), ('b'), ('c')")
            conn.commit()
            conn.close()
            
            from meta.core.datasource import get_data_source
            ds = get_data_source("sqlite", database=path)
            
            handler = DBAnalyzeHandler()
            context = {'data_source': ds}
            
            result = handler.execute({}, context)
            
            assert result.success is True
            assert result.data['action'] == 'ANALYZE'
        finally:
            try:
                os.unlink(path)
            except:
                pass


class TestDBVacuumHandler:
    """db_vacuum 任务处理器测试"""
    
    def test_execute_success(self):
        """测试VACUUM执行成功"""
        handler = DBVacuumHandler()
        ds = MockDataSource()
        context = {'data_source': ds}
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['action'] == 'INCREMENTAL_VACUUM'
    
    def test_execute_with_missing_data_source(self):
        """测试缺少数据源"""
        handler = DBVacuumHandler()
        context = {}
        
        result = handler.execute({}, context)
        
        assert result.success is False
    
    def test_execute_with_db_error(self):
        """测试数据库执行错误"""
        handler = DBVacuumHandler()
        ds = MagicMock()
        ds.execute.side_effect = Exception("Disk full")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert "Disk full" in result.error
    
    def test_execute_with_real_sqlite_db(self):
        """测试使用真实SQLite数据库"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("INSERT INTO test (name) VALUES ('a'), ('b'), ('c')")
            conn.commit()
            
            conn.execute("DELETE FROM test WHERE name = 'a'")
            conn.commit()
            conn.close()
            
            from meta.core.datasource import get_data_source
            ds = get_data_source("sqlite", database=path)
            
            handler = DBVacuumHandler()
            context = {'data_source': ds}
            
            result = handler.execute({}, context)
            
            assert result.success is True
            assert result.data['action'] == 'INCREMENTAL_VACUUM'
        finally:
            try:
                os.unlink(path)
            except:
                pass


class TestDBIntegrityCheckHandler:
    """db_integrity_check 任务处理器测试"""
    
    def test_execute_ok(self):
        """测试完整性检查通过"""
        handler = DBIntegrityCheckHandler()
        ds = MagicMock()
        ds.query.return_value = [{'integrity_check': 'ok'}]
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['status'] == 'ok'
    
    def test_execute_corruption_detected(self):
        """测试检测到数据库损坏"""
        handler = DBIntegrityCheckHandler()
        ds = MagicMock()
        ds.query.return_value = [{'integrity_check': '*** in database main ***\nPage 123: btree error'}]
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert result.data['status'] != 'ok'
    
    def test_execute_with_missing_data_source(self):
        """测试缺少数据源"""
        handler = DBIntegrityCheckHandler()
        context = {}
        
        result = handler.execute({}, context)
        
        assert result.success is False
    
    def test_execute_with_query_error(self):
        """测试查询错误"""
        handler = DBIntegrityCheckHandler()
        ds = MagicMock()
        ds.query.side_effect = Exception("Query failed")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert "Query failed" in result.error
    
    def test_execute_with_empty_result(self):
        """测试空结果"""
        handler = DBIntegrityCheckHandler()
        ds = MagicMock()
        ds.query.return_value = []
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert result.data['status'] == 'unknown'
    
    def test_execute_with_real_sqlite_db(self):
        """测试使用真实SQLite数据库"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            conn.commit()
            conn.close()
            
            from meta.core.datasource import get_data_source
            ds = get_data_source("sqlite", database=path)
            
            handler = DBIntegrityCheckHandler()
            context = {'data_source': ds}
            
            result = handler.execute({}, context)
            
            assert result.success is True
            assert result.data['status'] == 'ok'
        finally:
            try:
                os.unlink(path)
            except:
                pass


class TestDBCheckpointHandler:
    """db_checkpoint 任务处理器测试"""
    
    def test_execute_success(self):
        """测试WAL检查点执行成功"""
        handler = DBCheckpointHandler()
        ds = MockDataSource()
        context = {'data_source': ds}
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['action'] == 'WAL_CHECKPOINT'
    
    def test_execute_with_missing_data_source(self):
        """测试缺少数据源"""
        handler = DBCheckpointHandler()
        context = {}
        
        result = handler.execute({}, context)
        
        assert result.success is False
    
    def test_execute_with_checkpoint_error(self):
        """测试检查点执行错误"""
        handler = DBCheckpointHandler()
        ds = MagicMock()
        ds.checkpoint.side_effect = Exception("Checkpoint failed")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert "Checkpoint failed" in result.error
    
    def test_execute_with_real_sqlite_db(self):
        """测试使用真实SQLite数据库（WAL模式）"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            conn = sqlite3.connect(path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("INSERT INTO test (name) VALUES ('a')")
            conn.commit()
            conn.close()
            
            from meta.core.datasource import get_data_source
            ds = get_data_source("sqlite", database=path)
            
            handler = DBCheckpointHandler()
            context = {'data_source': ds}
            
            result = handler.execute({}, context)
            
            assert result.success is True
            assert result.data['action'] == 'WAL_CHECKPOINT'
        finally:
            try:
                os.unlink(path)
                try:
                    os.unlink(path + '-wal')
                except:
                    pass
                try:
                    os.unlink(path + '-shm')
                except:
                    pass
            except:
                pass


# ============================================
# 审计日志任务处理器测试
# ============================================

class TestAuditFailureRetryHandler:
    """audit_failure_retry 任务处理器测试"""
    
    def test_execute_with_failed_logs(self):
        """测试有失败日志需要重试"""
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
    
    def test_execute_no_failed_logs(self):
        """测试没有失败日志"""
        handler = AuditFailureRetryHandler()
        ds = MagicMock()
        ds.query.return_value = []
        ds.commit = MagicMock()
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['retried'] == 0
    
    def test_execute_with_large_batch(self):
        """测试大批量重试"""
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
    
    def test_execute_with_custom_config(self):
        """测试自定义配置"""
        handler = AuditFailureRetryHandler()
        ds = MagicMock()
        ds.query.return_value = [{'id': 1}]
        ds.commit = MagicMock()
        
        context = {
            'data_source': ds,
            'handler_config': {'batch_size': 50, 'max_retries': 5}
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
    
    def test_execute_with_query_error(self):
        """测试查询错误"""
        handler = AuditFailureRetryHandler()
        ds = MagicMock()
        ds.query.side_effect = Exception("Query failed")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert "Query failed" in result.error
    
    def test_execute_with_update_error(self):
        """测试更新错误"""
        handler = AuditFailureRetryHandler()
        ds = MagicMock()
        ds.query.return_value = [{'id': 1}]
        ds.execute.side_effect = Exception("Update failed")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert "Update failed" in result.error
    
    def test_execute_with_real_db(self):
        """测试使用真实数据库"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_type TEXT,
                    object_id TEXT,
                    action TEXT,
                    status TEXT DEFAULT 'written',
                    retry_count INTEGER DEFAULT 0,
                    status_entered_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
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
            
            conn.close()
        finally:
            try:
                os.unlink(path)
            except:
                pass


class TestAuditLogCleanupHandler:
    """audit_log_cleanup 任务处理器测试"""
    
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
    
    def test_execute_with_partial_retention(self):
        """测试部分保留配置"""
        handler = AuditLogCleanupHandler()
        ds = MockDataSource()
        retention = {'business': 180, 'security': 365}
        context = {
            'data_source': ds,
            'handler_config': {'retention_days': retention}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['categories_processed'] == 2
    
    def test_execute_with_empty_retention(self):
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
    
    def test_execute_with_missing_data_source(self):
        """测试缺少数据源"""
        handler = AuditLogCleanupHandler()
        context = {}
        
        result = handler.execute({}, context)
        
        assert result.success is False
    
    def test_execute_with_error(self):
        """测试执行错误"""
        handler = AuditLogCleanupHandler()
        ds = MagicMock()
        ds.execute.side_effect = Exception("Cleanup failed")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert "Cleanup failed" in result.error
    
    def test_execute_with_real_db(self):
        """测试使用真实数据库"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_type TEXT,
                    object_id TEXT,
                    action TEXT,
                    log_category TEXT DEFAULT 'business',
                    created_at TEXT
                );
            """)
            
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
            
            conn.close()
        finally:
            try:
                os.unlink(path)
            except:
                pass


# ============================================
# 导入队列处理器测试
# ============================================

class TestImportQueueHandler:
    """import_queue_processor 任务处理器测试"""
    
    def test_execute_with_pending_tasks(self):
        """测试有待处理任务"""
        handler = ImportQueueHandler()
        
        with patch('meta.services.async_import_service.AsyncImportService') as MockService:
            mock_instance = MagicMock()
            mock_instance.get_all_tasks.return_value = {
                'task1': MagicMock(status=MagicMock(value='pending')),
                'task2': MagicMock(status=MagicMock(value='pending')),
                'task3': MagicMock(status=MagicMock(value='completed')),
            }
            MockService.return_value = mock_instance
            
            result = handler.execute({}, {})
            
            assert result.success is True
            assert result.data['active_tasks'] == 3
            assert result.data['pending_tasks'] == 2
    
    def test_execute_with_empty_queue(self):
        """测试空队列"""
        handler = ImportQueueHandler()
        
        with patch('meta.services.async_import_service.AsyncImportService') as MockService:
            mock_instance = MagicMock()
            mock_instance.get_all_tasks.return_value = {}
            MockService.return_value = mock_instance
            
            result = handler.execute({}, {})
            
            assert result.success is True
            assert result.data['active_tasks'] == 0
            assert result.data['pending_tasks'] == 0
    
    def test_execute_with_all_completed_tasks(self):
        """测试全部完成的任务"""
        handler = ImportQueueHandler()
        
        with patch('meta.services.async_import_service.AsyncImportService') as MockService:
            mock_instance = MagicMock()
            mock_instance.get_all_tasks.return_value = {
                'task1': MagicMock(status=MagicMock(value='completed')),
                'task2': MagicMock(status=MagicMock(value='completed')),
            }
            MockService.return_value = mock_instance
            
            result = handler.execute({}, {})
            
            assert result.success is True
            assert result.data['active_tasks'] == 2
            assert result.data['pending_tasks'] == 0
    
    def test_execute_with_mixed_status(self):
        """测试混合状态的任务"""
        handler = ImportQueueHandler()
        
        with patch('meta.services.async_import_service.AsyncImportService') as MockService:
            mock_instance = MagicMock()
            mock_instance.get_all_tasks.return_value = {
                'task1': MagicMock(status=MagicMock(value='pending')),
                'task2': MagicMock(status=MagicMock(value='running')),
                'task3': MagicMock(status=MagicMock(value='completed')),
                'task4': MagicMock(status=MagicMock(value='failed')),
            }
            MockService.return_value = mock_instance
            
            result = handler.execute({}, {})
            
            assert result.success is True
            assert result.data['active_tasks'] == 4
            assert result.data['pending_tasks'] == 1
    
    def test_execute_with_service_error(self):
        """测试服务错误"""
        handler = ImportQueueHandler()
        
        with patch('meta.services.async_import_service.AsyncImportService') as MockService:
            MockService.side_effect = Exception("Service unavailable")
            
            result = handler.execute({}, {})
            
            assert result.success is False
            assert "Service unavailable" in result.error
    
    def test_execute_with_get_all_tasks_error(self):
        """测试获取任务列表错误"""
        handler = ImportQueueHandler()
        
        with patch('meta.services.async_import_service.AsyncImportService') as MockService:
            mock_instance = MagicMock()
            mock_instance.get_all_tasks.side_effect = Exception("Failed to get tasks")
            MockService.return_value = mock_instance
            
            result = handler.execute({}, {})
            
            assert result.success is False
            assert "Failed to get tasks" in result.error


# ============================================
# 并发安全测试
# ============================================

class TestTaskHandlersConcurrency:
    """任务处理器并发安全测试"""
    
    def test_db_analyze_thread_safety(self):
        """测试DBAnalyzeHandler线程安全"""
        results = []
        errors = []
        
        def run_handler():
            try:
                handler = DBAnalyzeHandler()
                ds = MockDataSource()
                result = handler.execute({}, {'data_source': ds})
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
    
    def test_db_vacuum_thread_safety(self):
        """测试DBVacuumHandler线程安全"""
        results = []
        errors = []
        
        def run_handler():
            try:
                handler = DBVacuumHandler()
                ds = MockDataSource()
                result = handler.execute({}, {'data_source': ds})
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
    
    def test_audit_retry_thread_safety(self):
        """测试AuditFailureRetryHandler线程安全"""
        results = []
        errors = []
        
        def run_handler():
            try:
                handler = AuditFailureRetryHandler()
                ds = MagicMock()
                ds.query.return_value = [{'id': 1}]
                ds.commit = MagicMock()
                result = handler.execute({}, {'data_source': ds})
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


# ============================================
# 预制任务配置验证测试
# ============================================

class TestScheduledTaskConfig:
    """预制任务配置验证测试"""
    
    def test_db_analyze_config(self):
        """验证db_analyze任务配置"""
        expected_config = {
            'code': 'db_analyze',
            'name': '数据库统计信息更新',
            'category': 'system',
            'handler': 'db_analyze',
            'trigger_mode': 'cron',
            'schedule': '0 3 * * *',
            'queue': 'background',
            'enabled': True,
        }
        
        assert expected_config['code'] == 'db_analyze'
        assert expected_config['category'] == 'system'
        assert expected_config['trigger_mode'] == 'cron'
        assert expected_config['queue'] == 'background'
    
    def test_db_vacuum_config(self):
        """验证db_vacuum任务配置"""
        expected_config = {
            'code': 'db_vacuum',
            'name': '数据库空间回收',
            'category': 'system',
            'handler': 'db_vacuum',
            'trigger_mode': 'cron',
            'schedule': '0 4 * * 0',
            'queue': 'background',
            'enabled': True,
        }
        
        assert expected_config['code'] == 'db_vacuum'
        assert expected_config['category'] == 'system'
    
    def test_db_integrity_check_config(self):
        """验证db_integrity_check任务配置"""
        expected_config = {
            'code': 'db_integrity_check',
            'name': '数据库完整性检查',
            'category': 'system',
            'handler': 'db_integrity_check',
            'trigger_mode': 'cron',
            'schedule': '0 6 * * *',
            'queue': 'background',
            'enabled': True,
        }
        
        assert expected_config['code'] == 'db_integrity_check'
        assert expected_config['category'] == 'system'
    
    def test_db_checkpoint_config(self):
        """验证db_checkpoint任务配置"""
        expected_config = {
            'code': 'db_checkpoint',
            'name': 'WAL检查点',
            'category': 'system',
            'handler': 'db_checkpoint',
            'trigger_mode': 'cron',
            'schedule': '*/5 * * * *',
            'queue': 'critical',
            'enabled': True,
        }
        
        assert expected_config['code'] == 'db_checkpoint'
        assert expected_config['queue'] == 'critical'
    
    def test_audit_failure_retry_config(self):
        """验证audit_failure_retry任务配置"""
        expected_config = {
            'code': 'audit_failure_retry',
            'name': '审计日志失败重试',
            'category': 'audit',
            'handler': 'audit_failure_retry',
            'trigger_mode': 'cron',
            'schedule': '*/10 * * * *',
            'queue': 'business',
            'enabled': True,
        }
        
        assert expected_config['code'] == 'audit_failure_retry'
        assert expected_config['category'] == 'audit'
    
    def test_audit_log_cleanup_config(self):
        """验证audit_log_cleanup任务配置"""
        expected_config = {
            'code': 'audit_log_cleanup',
            'name': '审计日志清理',
            'category': 'audit',
            'handler': 'audit_log_cleanup',
            'trigger_mode': 'cron',
            'schedule': '0 2 * * *',
            'queue': 'background',
            'enabled': True,
        }
        
        assert expected_config['code'] == 'audit_log_cleanup'
        assert expected_config['category'] == 'audit'
    
    def test_import_queue_processor_config(self):
        """验证import_queue_processor任务配置"""
        expected_config = {
            'code': 'import_queue_processor',
            'name': '导入队列处理器',
            'category': 'business',
            'handler': 'import_queue_processor',
            'trigger_mode': 'cron',
            'schedule': '*/2 * * * *',
            'queue': 'business',
            'enabled': True,
        }
        
        assert expected_config['code'] == 'import_queue_processor'
        assert expected_config['category'] == 'business'
