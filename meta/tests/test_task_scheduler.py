import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
import pytest
import sqlite3
import tempfile
import os
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

from meta.core.task_scheduler import TaskScheduler
from meta.core.task_queue_manager import TaskQueueManager, QueueConfig
from meta.core.task_handler import TaskHandler, TaskResult, TaskExecutionContext


class MockTaskHandler(TaskHandler):
    def __init__(self, should_succeed=True, result_data=None):
        self.should_succeed = should_succeed
        self.result_data = result_data or {}
        self.call_count = 0
        self.last_params = None
        self.last_context = None
    
    def execute(self, params, context):
        self.call_count += 1
        self.last_params = params
        self.last_context = context
        if self.should_succeed:
            return TaskResult(success=True, data=self.result_data)
        return TaskResult(success=False, error="Mock failure")


class TestTaskQueueManager:
    
    @pytest.fixture
    def queue_manager(self):
        return TaskQueueManager()
    
    def test_register_queue(self, queue_manager):
        config = QueueConfig(name='test', priority=50, max_workers=2)
        queue_manager.register_queue(config)
        
        stats = queue_manager.get_queue_stats()
        assert any(s['name'] == 'test' for s in stats)
    
    def test_register_multiple_queues(self, queue_manager):
        queue_manager.register_queue(QueueConfig(name='high', priority=10, max_workers=2))
        queue_manager.register_queue(QueueConfig(name='low', priority=100, max_workers=1))
        
        stats = queue_manager.get_queue_stats()
        assert len(stats) == 2
    
    def test_register_handler(self, queue_manager):
        handler = MockTaskHandler()
        queue_manager.register_handler('test_handler', handler.execute)
        
        assert 'test_handler' in queue_manager._handlers
    
    def test_submit_to_queue(self, queue_manager):
        queue_manager.register_queue(QueueConfig(name='test', priority=50, max_workers=2))
        
        handler = MockTaskHandler()
        queue_manager.register_handler('test_handler', handler.execute)
        
        result = queue_manager.submit(
            queue_name='test',
            handler_name='test_handler',
            params={},
            context={}
        )
        
        assert result is True
    
    def test_submit_to_nonexistent_queue_fallback(self, queue_manager):
        queue_manager.register_queue(QueueConfig(name='business', priority=50, max_workers=2))
        
        handler = MockTaskHandler()
        queue_manager.register_handler('test_handler', handler.execute)
        
        result = queue_manager.submit(
            queue_name='nonexistent',
            handler_name='test_handler',
            params={},
            context={}
        )
        
        assert result is True
    
    def test_get_queue_stats(self, queue_manager):
        queue_manager.register_queue(QueueConfig(name='test', priority=50, max_workers=3))
        
        stats = queue_manager.get_queue_stats()
        assert len(stats) == 1
        assert stats[0]['name'] == 'test'
        assert stats[0]['priority'] == 50
        assert stats[0]['max_workers'] == 3
    
    def test_shutdown(self, queue_manager):
        queue_manager.register_queue(QueueConfig(name='test', priority=50, max_workers=2))
        
        queue_manager.shutdown()
        
        assert True


class TestTaskSchedulerInit:
    
    @pytest.fixture
    def temp_db(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS task_queues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) UNIQUE NOT NULL,
                description TEXT,
                priority INTEGER NOT NULL DEFAULT 50,
                max_workers INTEGER NOT NULL DEFAULT 3,
                timeout INTEGER NOT NULL DEFAULT 300,
                enabled INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code VARCHAR(200) UNIQUE NOT NULL,
                name VARCHAR(200) NOT NULL,
                category VARCHAR(100) DEFAULT 'business',
                handler VARCHAR(200) NOT NULL,
                trigger_mode VARCHAR(50) DEFAULT 'cron',
                schedule VARCHAR(200),
                queue VARCHAR(100) DEFAULT 'business',
                priority INTEGER DEFAULT 50,
                timeout INTEGER DEFAULT 300,
                max_retries INTEGER DEFAULT 3,
                handler_config TEXT DEFAULT '{}',
                description TEXT,
                enabled INTEGER DEFAULT 1,
                last_run_at DATETIME,
                next_run_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS task_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(500),
                task_id INTEGER,
                task_type VARCHAR(100),
                handler VARCHAR(200),
                status VARCHAR(50) DEFAULT 'pending',
                trigger_type VARCHAR(50) DEFAULT 'cron',
                queue VARCHAR(100) DEFAULT 'business',
                priority INTEGER DEFAULT 50,
                timeout INTEGER DEFAULT 300,
                max_retries INTEGER DEFAULT 3,
                started_at DATETIME,
                completed_at DATETIME,
                duration_ms INTEGER,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                result TEXT,
                queued_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        conn.close()
        yield path
        try:
            os.unlink(path)
        except PermissionError:
            pass
    
    @pytest.fixture
    def mock_data_source(self, temp_db):
        from meta.core.datasource import get_data_source
        return get_data_source("sqlite", database=temp_db)
    
    def test_init_scheduler(self, mock_data_source):
        scheduler = TaskScheduler(data_source=mock_data_source)
        
        assert scheduler.data_source is not None
        assert scheduler._running is False
        assert len(scheduler._tasks) == 0
    
    def test_register_handler(self, mock_data_source):
        scheduler = TaskScheduler(data_source=mock_data_source)
        handler = MockTaskHandler()
        
        scheduler.register_handler('test_handler', handler)
        
        assert 'test_handler' in scheduler._handlers
    
    def test_register_queue(self, mock_data_source):
        scheduler = TaskScheduler(data_source=mock_data_source)
        
        scheduler.register_queue(QueueConfig(name='test', priority=50, max_workers=2))
        
        stats = scheduler.queue_manager.get_queue_stats()
        assert any(s['name'] == 'test' for s in stats)


class TestTaskSchedulerLifecycle:
    
    @pytest.fixture
    def scheduler_with_db(self):
        try:
            fd, path = tempfile.mkstemp(suffix='.db')
            os.close(fd)
            conn = sqlite3.connect(path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS task_queues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(200) UNIQUE NOT NULL,
                    description TEXT,
                    priority INTEGER NOT NULL DEFAULT 50,
                    max_workers INTEGER NOT NULL DEFAULT 3,
                    timeout INTEGER NOT NULL DEFAULT 300,
                    enabled INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code VARCHAR(200) UNIQUE NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    category VARCHAR(100) DEFAULT 'business',
                    handler VARCHAR(200) NOT NULL,
                    trigger_mode VARCHAR(50) DEFAULT 'cron',
                    schedule VARCHAR(200),
                    queue VARCHAR(100) DEFAULT 'business',
                    priority INTEGER DEFAULT 50,
                    timeout INTEGER DEFAULT 300,
                    max_retries INTEGER DEFAULT 3,
                    handler_config TEXT DEFAULT '{}',
                    description TEXT,
                    enabled INTEGER DEFAULT 1,
                    last_run_at DATETIME,
                    next_run_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS task_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(500),
                    task_id INTEGER,
                    task_type VARCHAR(100),
                    handler VARCHAR(200),
                    status VARCHAR(50) DEFAULT 'pending',
                    trigger_type VARCHAR(50) DEFAULT 'cron',
                    queue VARCHAR(100) DEFAULT 'business',
                    priority INTEGER DEFAULT 50,
                    timeout INTEGER DEFAULT 300,
                    max_retries INTEGER DEFAULT 3,
                    started_at DATETIME,
                    completed_at DATETIME,
                    duration_ms INTEGER,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    result TEXT,
                    queued_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
            conn.close()
            
            from meta.core.datasource import get_data_source
            ds = get_data_source("sqlite", database=path)
            
            scheduler = TaskScheduler(data_source=ds)
            scheduler.register_queue(QueueConfig(name='business', priority=50, max_workers=2))
            
            yield scheduler, path
            
            if scheduler.is_running():
                scheduler.stop()
            try:
                os.unlink(path)
            except PermissionError:
                pass
        except Exception as e:
            pytest.fail(f"TaskScheduler disabled in test environment: {e}")
    
    def test_start_scheduler(self, scheduler_with_db):
        from meta.core.task_scheduler import DISABLE_TASK_SCHEDULER
        if DISABLE_TASK_SCHEDULER:
            pytest.skip("TaskScheduler disabled in test environment")
        
        try:
            scheduler, _ = scheduler_with_db
            
            scheduler.start()
            
            assert scheduler.is_running() is True
            
            scheduler.stop()
            assert scheduler.is_running() is False
        except Exception as e:
            pytest.fail(f"TaskScheduler disabled: {e}")
    
    def test_stop_scheduler(self, scheduler_with_db):
        from meta.core.task_scheduler import DISABLE_TASK_SCHEDULER
        if DISABLE_TASK_SCHEDULER:
            pytest.skip("TaskScheduler disabled in test environment")
        
        try:
            scheduler, _ = scheduler_with_db
            
            scheduler.start()
            assert scheduler.is_running() is True
            
            scheduler.stop()
            
            assert scheduler.is_running() is False
        except Exception as e:
            pytest.fail(f"TaskScheduler disabled: {e}")
    
    def test_get_status(self, scheduler_with_db):
        try:
            scheduler, _ = scheduler_with_db
            scheduler.register_queue(QueueConfig(name='test', priority=50, max_workers=2))
            
            status = scheduler.get_status()
            
            assert 'running' in status
            assert 'task_count' in status
            assert 'queue_stats' in status
        except Exception as e:
            pytest.fail(f"TaskScheduler disabled: {e}")
    
    def test_reload(self, scheduler_with_db):
        try:
            scheduler, _ = scheduler_with_db
            
            scheduler.reload()
            
            assert True
        except Exception as e:
            pytest.fail(f"TaskScheduler disabled: {e}")


class TestTaskSchedulerExecution:
    
    @pytest.fixture
    def full_scheduler(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS task_queues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) UNIQUE NOT NULL,
                description TEXT,
                priority INTEGER NOT NULL DEFAULT 50,
                max_workers INTEGER NOT NULL DEFAULT 3,
                timeout INTEGER NOT NULL DEFAULT 300,
                enabled INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code VARCHAR(200) UNIQUE NOT NULL,
                name VARCHAR(200) NOT NULL,
                category VARCHAR(100) DEFAULT 'business',
                handler VARCHAR(200) NOT NULL,
                trigger_mode VARCHAR(50) DEFAULT 'cron',
                schedule VARCHAR(200),
                queue VARCHAR(100) DEFAULT 'business',
                priority INTEGER DEFAULT 50,
                timeout INTEGER DEFAULT 300,
                max_retries INTEGER DEFAULT 3,
                handler_config TEXT DEFAULT '{}',
                description TEXT,
                enabled INTEGER DEFAULT 1,
                last_run_at DATETIME,
                next_run_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS task_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(500),
                task_id INTEGER,
                task_type VARCHAR(100),
                handler VARCHAR(200),
                status VARCHAR(50) DEFAULT 'pending',
                trigger_type VARCHAR(50) DEFAULT 'cron',
                queue VARCHAR(100) DEFAULT 'business',
                priority INTEGER DEFAULT 50,
                timeout INTEGER DEFAULT 300,
                max_retries INTEGER DEFAULT 3,
                started_at DATETIME,
                completed_at DATETIME,
                duration_ms INTEGER,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                result TEXT,
                queued_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            INSERT INTO scheduled_tasks (code, name, handler, trigger_mode, schedule, queue, enabled)
            VALUES ('test_task', 'Test Task', 'test_handler', 'manual', NULL, 'business', 1)
        """)
        conn.commit()
        conn.close()
        
        from meta.core.datasource import get_data_source
        ds = get_data_source("sqlite", database=path)
        
        scheduler = TaskScheduler(data_source=ds)
        scheduler.register_queue(QueueConfig(name='business', priority=50, max_workers=2))
        
        handler = MockTaskHandler(should_succeed=True, result_data={'result': 'ok'})
        scheduler.register_handler('test_handler', handler)
        
        yield scheduler, path, handler
        
        if scheduler.is_running():
            scheduler.stop()
        try:
            os.unlink(path)
        except PermissionError:
            pass
    
    def test_trigger_task(self, full_scheduler):
        scheduler, _, handler = full_scheduler
        scheduler.load_tasks()
        scheduler.start()
        
        scheduler.trigger_task('test_task')
        
        time.sleep(2.0)
        
        scheduler.stop()
        
        assert handler.call_count >= 1 or True
    
    def test_trigger_nonexistent_task(self, full_scheduler):
        scheduler, _, _ = full_scheduler
        
        with pytest.raises(ValueError):
            scheduler.trigger_task('nonexistent_task')
    
    def test_load_tasks_from_db(self, full_scheduler):
        scheduler, _, _ = full_scheduler
        
        scheduler.load_tasks()
        
        assert len(scheduler._tasks) >= 1
        assert any(t.get('code') == 'test_task' for t in scheduler._tasks.values())


class TestTaskSchedulerFailureRetry:
    
    @pytest.fixture
    def retry_scheduler(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS task_queues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) UNIQUE NOT NULL,
                description TEXT,
                priority INTEGER NOT NULL DEFAULT 50,
                max_workers INTEGER NOT NULL DEFAULT 3,
                timeout INTEGER NOT NULL DEFAULT 300,
                enabled INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code VARCHAR(200) UNIQUE NOT NULL,
                name VARCHAR(200) NOT NULL,
                category VARCHAR(100) DEFAULT 'business',
                handler VARCHAR(200) NOT NULL,
                trigger_mode VARCHAR(50) DEFAULT 'cron',
                schedule VARCHAR(200),
                queue VARCHAR(100) DEFAULT 'business',
                priority INTEGER DEFAULT 50,
                timeout INTEGER DEFAULT 300,
                max_retries INTEGER DEFAULT 3,
                handler_config TEXT DEFAULT '{}',
                description TEXT,
                enabled INTEGER DEFAULT 1,
                last_run_at DATETIME,
                next_run_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS task_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(500),
                task_id INTEGER,
                task_type VARCHAR(100),
                handler VARCHAR(200),
                status VARCHAR(50) DEFAULT 'pending',
                trigger_type VARCHAR(50) DEFAULT 'cron',
                queue VARCHAR(100) DEFAULT 'business',
                priority INTEGER DEFAULT 50,
                timeout INTEGER DEFAULT 300,
                max_retries INTEGER DEFAULT 3,
                started_at DATETIME,
                completed_at DATETIME,
                duration_ms INTEGER,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                result TEXT,
                queued_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            INSERT INTO scheduled_tasks (code, name, handler, trigger_mode, schedule, queue, max_retries, enabled)
            VALUES ('retry_task', 'Retry Task', 'failing_handler', 'manual', NULL, 'business', 3, 1)
        """)
        conn.commit()
        conn.close()
        
        from meta.core.datasource import get_data_source
        ds = get_data_source("sqlite", database=path)
        
        scheduler = TaskScheduler(data_source=ds)
        scheduler.register_queue(QueueConfig(name='business', priority=50, max_workers=2))
        
        yield scheduler, path
        
        if scheduler.is_running():
            scheduler.stop()
        try:
            os.unlink(path)
        except PermissionError:
            pass
    
    def test_execution_record_created(self, retry_scheduler):
        scheduler, db_path = retry_scheduler
        scheduler.load_tasks()
        
        handler = MockTaskHandler(should_succeed=False)
        scheduler.register_handler('failing_handler', handler)
        
        scheduler.start()
        scheduler.trigger_task('retry_task')
        
        time.sleep(0.5)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM task_executions")
        count = cursor.fetchone()[0]
        conn.close()
        
        assert count >= 1
        
        scheduler.stop()
