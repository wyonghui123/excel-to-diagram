import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

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
    
    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self
    
    def query(self, sql, params=None):
        self.queries.append((sql, params))
        return []
    
    def commit(self):
        self.committed = True
    
    def checkpoint(self, mode):
        self.executed.append((f"CHECKPOINT {mode}", None))


class TestDBAnalyzeHandler:
    
    def test_execute_success(self):
        handler = DBAnalyzeHandler()
        ds = MockDataSource()
        context = {'data_source': ds}
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['action'] == 'ANALYZE'
        assert ds.committed is True
        assert any('ANALYZE' in str(e) for e in ds.executed)
    
    def test_execute_with_error(self):
        handler = DBAnalyzeHandler()
        ds = MagicMock()
        ds.execute.side_effect = Exception("DB error")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert "DB error" in result.error


class TestDBVacuumHandler:
    
    def test_execute_success(self):
        handler = DBVacuumHandler()
        ds = MockDataSource()
        context = {'data_source': ds}
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['action'] == 'INCREMENTAL_VACUUM'
    
    def test_execute_with_error(self):
        handler = DBVacuumHandler()
        ds = MagicMock()
        ds.execute.side_effect = Exception("Vacuum failed")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False


class TestDBIntegrityCheckHandler:
    
    def test_execute_ok(self):
        handler = DBIntegrityCheckHandler()
        ds = MagicMock()
        ds.query.return_value = [{'integrity_check': 'ok'}]
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['status'] == 'ok'
    
    def test_execute_corruption_detected(self):
        handler = DBIntegrityCheckHandler()
        ds = MagicMock()
        ds.query.return_value = [{'integrity_check': '*** in database main ***\nPage 123: btree'}]
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False
        assert 'corruption' in result.data['status'].lower() or result.data['status'] != 'ok'
    
    def test_execute_with_error(self):
        handler = DBIntegrityCheckHandler()
        ds = MagicMock()
        ds.query.side_effect = Exception("Query failed")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False


class TestDBCheckpointHandler:
    
    def test_execute_success(self):
        handler = DBCheckpointHandler()
        ds = MockDataSource()
        context = {'data_source': ds}
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['action'] == 'WAL_CHECKPOINT'
    
    def test_execute_with_error(self):
        handler = DBCheckpointHandler()
        ds = MagicMock()
        ds.checkpoint.side_effect = Exception("Checkpoint failed")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False


class TestAuditLogArchiveHandler:
    
    def test_execute_success(self):
        handler = AuditLogArchiveHandler()
        ds = MockDataSource()
        context = {
            'data_source': ds,
            'handler_config': {'archive_days': 90}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert ds.committed is True
    
    def test_execute_default_archive_days(self):
        handler = AuditLogArchiveHandler()
        ds = MockDataSource()
        context = {'data_source': ds}
        
        result = handler.execute({}, context)
        
        assert result.success is True
    
    def test_execute_with_error(self):
        handler = AuditLogArchiveHandler()
        ds = MagicMock()
        ds.execute.side_effect = Exception("Archive failed")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False


class TestAuditLogCleanupHandler:
    
    def test_execute_success(self):
        handler = AuditLogCleanupHandler()
        ds = MockDataSource()
        retention = {
            'business': 365,
            'security': 2555,
            'operation': 90,
            'performance': 30,
            'system': 90,
        }
        context = {
            'data_source': ds,
            'handler_config': {'retention_days': retention}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert ds.committed is True
    
    def test_execute_default_retention(self):
        handler = AuditLogCleanupHandler()
        ds = MockDataSource()
        context = {'data_source': ds}
        
        result = handler.execute({}, context)
        
        assert result.success is True


class TestAuditFailureRetryHandler:
    
    def test_execute_success(self):
        handler = AuditFailureRetryHandler()
        ds = MagicMock()
        ds.query.return_value = [{'id': 1}, {'id': 2}]
        ds.commit = MagicMock()
        
        context = {
            'data_source': ds,
            'handler_config': {'batch_size': 100, 'max_retries': 3}
        }
        
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['retried'] == 2
    
    def test_execute_no_failed_logs(self):
        handler = AuditFailureRetryHandler()
        ds = MagicMock()
        ds.query.return_value = []
        ds.commit = MagicMock()
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is True
        assert result.data['retried'] == 0
    
    def test_execute_with_error(self):
        handler = AuditFailureRetryHandler()
        ds = MagicMock()
        ds.query.side_effect = Exception("Query failed")
        
        context = {'data_source': ds}
        result = handler.execute({}, context)
        
        assert result.success is False


class TestImportQueueHandler:
    
    def test_execute_success(self):
        handler = ImportQueueHandler()
        context = {}
        
        with patch('meta.services.async_import_service.AsyncImportService') as MockService:
            mock_instance = MagicMock()
            mock_instance.get_all_tasks.return_value = {
                'task1': MagicMock(status=MagicMock(value='pending')),
                'task2': MagicMock(status=MagicMock(value='completed')),
            }
            MockService.return_value = mock_instance
            
            result = handler.execute({}, context)
            
            assert result.success is True
            assert result.data['active_tasks'] == 2
    
    def test_execute_empty_queue(self):
        handler = ImportQueueHandler()
        context = {}
        
        with patch('meta.services.async_import_service.AsyncImportService') as MockService:
            mock_instance = MagicMock()
            mock_instance.get_all_tasks.return_value = {}
            MockService.return_value = mock_instance
            
            result = handler.execute({}, context)
            
            assert result.success is True
            assert result.data['active_tasks'] == 0
            assert result.data['pending_tasks'] == 0
    
    def test_execute_with_error(self):
        handler = ImportQueueHandler()
        context = {}
        
        with patch('meta.services.async_import_service.AsyncImportService') as MockService:
            MockService.side_effect = Exception("Service unavailable")
            
            result = handler.execute({}, context)
            
            assert result.success is False


class TestTaskResult:
    
    def test_success_result(self):
        result = TaskResult(success=True, data={'key': 'value'})
        assert result.success is True
        assert result.data == {'key': 'value'}
        assert result.error is None
    
    def test_failure_result(self):
        result = TaskResult(success=False, error="Something went wrong")
        assert result.success is False
        assert result.error == "Something went wrong"
    
    def test_ai_task_result(self):
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
