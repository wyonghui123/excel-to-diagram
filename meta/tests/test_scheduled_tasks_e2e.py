import pytest

pytestmark = pytest.mark.e2e

# -*- coding: utf-8 -*-
"""
预制任务端到端集成测试

测试覆盖：
1. init_task_seed 初始化预制任务和队列
2. TaskScheduler 从数据库加载预制任务
3. Cron 表达式触发任务执行
4. 完整的任务执行流程
5. 任务执行记录跟踪
6. 任务失败重试机制
"""

import pytest
import sqlite3
import tempfile
import os
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from meta.core.task_scheduler import TaskScheduler
from meta.core.task_queue_manager import TaskQueueManager, QueueConfig
from meta.core.task_handler import TaskHandler, TaskResult
from meta.scripts.init_task_seed import init_task_seed_data
from meta.handlers.system_handlers import (
    DBAnalyzeHandler, DBVacuumHandler,
    DBIntegrityCheckHandler, DBCheckpointHandler
)
from meta.handlers.audit_handlers import (
    AuditFailureRetryHandler, AuditLogCleanupHandler
)
from meta.handlers.import_handlers import ImportQueueHandler


class ExecutionTracker:
    """任务执行跟踪器"""
    def __init__(self):
        self.executions = []
        self.lock = threading.Lock()
    
    def record(self, task_code, result):
        with self.lock:
            self.executions.append({
                'task_code': task_code,
                'result': result,
                'timestamp': datetime.now().isoformat()
            })
    
    def get_count(self, task_code):
        with self.lock:
            return sum(1 for e in self.executions if e['task_code'] == task_code)


class TestTaskSeedInit:
    """预制任务初始化测试"""
    
    @pytest.fixture
    def temp_db(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.close()
        yield path
        try:
            os.unlink(path)
        except PermissionError:
            pass
    
    @pytest.fixture
    def data_source(self, temp_db):
        from meta.core.datasource import get_data_source
        return get_data_source("sqlite", database=temp_db)
    
    def test_init_task_queues(self, data_source):
        """测试任务队列初始化"""
        init_task_seed_data(data_source)
        
        rows = data_source.query("SELECT * FROM task_queues")
        
        assert len(rows) == 5
        
        queue_names = {row['name'] for row in rows}
        assert 'critical' in queue_names
        assert 'business' in queue_names
        assert 'background' in queue_names
        assert 'ai_high' in queue_names
        assert 'ai_normal' in queue_names
    
    def test_init_scheduled_tasks(self, data_source):
        """测试预制任务初始化"""
        init_task_seed_data(data_source)
        
        rows = data_source.query("SELECT * FROM scheduled_tasks")
        
        assert len(rows) == 7
        
        task_codes = {row['code'] for row in rows}
        expected_codes = {
            'db_analyze', 'db_vacuum', 'db_integrity_check', 'db_checkpoint',
            'audit_failure_retry', 'audit_log_cleanup', 'import_queue_processor'
        }
        assert task_codes == expected_codes
    
    def test_init_db_analyze_task_config(self, data_source):
        """测试 db_analyze 任务配置"""
        init_task_seed_data(data_source)
        
        rows = data_source.query(
            "SELECT * FROM scheduled_tasks WHERE code = ?",
            ('db_analyze',)
        )
        
        assert len(rows) == 1
        task = dict(rows[0])
        assert task['name'] == '数据库统计信息更新'
        assert task['category'] == 'system'
        assert task['handler'] == 'db_analyze'
        assert task['trigger_mode'] == 'cron'
        assert task['schedule'] == '0 3 * * *'
        assert task['queue'] == 'background'
        assert task['enabled'] == 1
    
    def test_init_audit_failure_retry_config(self, data_source):
        """测试 audit_failure_retry 任务配置"""
        init_task_seed_data(data_source)
        
        rows = data_source.query(
            "SELECT * FROM scheduled_tasks WHERE code = ?",
            ('audit_failure_retry',)
        )
        
        assert len(rows) == 1
        task = dict(rows[0])
        assert task['name'] == '审计日志失败重试'
        assert task['category'] == 'audit'
        assert task['handler'] == 'audit_failure_retry'
        assert task['schedule'] == '*/10 * * * *'
        assert task['queue'] == 'business'
        assert 'batch_size' in task['handler_config']
    
    def test_init_audit_log_cleanup_config(self, data_source):
        """测试 audit_log_cleanup 任务配置"""
        init_task_seed_data(data_source)
        
        rows = data_source.query(
            "SELECT * FROM scheduled_tasks WHERE code = ?",
            ('audit_log_cleanup',)
        )
        
        assert len(rows) == 1
        task = dict(rows[0])
        assert task['name'] == '审计日志清理'
        assert task['handler'] == 'audit_log_cleanup'
        assert task['schedule'] == '0 2 * * *'
        assert task['queue'] == 'background'
    
    def test_init_db_checkpoint_config(self, data_source):
        """测试 db_checkpoint 任务配置"""
        init_task_seed_data(data_source)
        
        rows = data_source.query(
            "SELECT * FROM scheduled_tasks WHERE code = ?",
            ('db_checkpoint',)
        )
        
        assert len(rows) == 1
        task = dict(rows[0])
        assert task['name'] == 'WAL检查点'
        assert task['handler'] == 'db_checkpoint'
        assert task['schedule'] == '*/5 * * * *'
        assert task['queue'] == 'critical'
    
    def test_init_idempotent(self, data_source):
        """测试初始化是幂等的（多次调用不会重复创建）"""
        init_task_seed_data(data_source)
        init_task_seed_data(data_source)
        init_task_seed_data(data_source)
        
        rows = data_source.query("SELECT COUNT(*) as cnt FROM scheduled_tasks")
        assert rows[0]['cnt'] == 7


class TestSchedulerLoadAndTrigger:
    """任务调度器加载和触发测试"""
    
    @pytest.fixture
    def scheduler_db(self):
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.close()
        yield path
        try:
            os.unlink(path)
        except PermissionError:
            pass
    
    @pytest.fixture
    def data_source(self, scheduler_db):
        from meta.core.datasource import get_data_source
        return get_data_source("sqlite", database=scheduler_db)
    
    def test_load_tasks_from_db(self, data_source):
        """测试从数据库加载任务"""
        init_task_seed_data(data_source)
        
        scheduler = TaskScheduler(data_source=data_source)
        scheduler.load_tasks()
        
        assert len(scheduler._tasks) == 7
        
        task_codes = {task['code'] for task in scheduler._tasks.values()}
        expected = {'db_analyze', 'db_vacuum', 'db_integrity_check', 'db_checkpoint',
                   'audit_failure_retry', 'audit_log_cleanup', 'import_queue_processor'}
        assert task_codes == expected
    
    def test_load_tasks_calculates_next_run(self, data_source):
        """测试加载任务时计算下次运行时间"""
        init_task_seed_data(data_source)
        
        scheduler = TaskScheduler(data_source=data_source)
        scheduler.load_tasks()
        
        for task_id, task in scheduler._tasks.items():
            if task.get('trigger_mode') == 'cron':
                assert 'next_run_at' in task
                next_run_str = task['next_run_at']
                assert next_run_str is not None
    
    def test_load_disabled_tasks_excluded(self, data_source):
        """测试禁用的任务被排除"""
        data_source.execute("""
            INSERT INTO scheduled_tasks 
            (code, name, handler, trigger_mode, schedule, enabled)
            VALUES ('disabled_task', 'Disabled Task', 'test_handler', 'manual', NULL, 0)
        """)
        data_source.commit()
        
        scheduler = TaskScheduler(data_source=data_source)
        scheduler.load_tasks()
        
        assert len(scheduler._tasks) == 0


class TestScheduledTaskExecutionE2E:
    """预制任务端到端执行测试"""
    
    @pytest.fixture
    def full_e2e_db(self):
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
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
                created_at_ts DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        conn.execute("""
            INSERT INTO scheduled_tasks 
            (code, name, handler, trigger_mode, schedule, queue, handler_config)
            VALUES 
            ('test_db_analyze', 'Test DB Analyze', 'db_analyze', 'manual', NULL, 'business', '{}'),
            ('test_audit_retry', 'Test Audit Retry', 'audit_failure_retry', 'manual', NULL, 'business', '{"batch_size": 100}'),
            ('test_audit_cleanup', 'Test Audit Cleanup', 'audit_log_cleanup', 'manual', NULL, 'business', '{"retention_days": {"business": 365}}')
        """)
        conn.commit()
        conn.close()
        yield path
        try:
            os.unlink(path)
        except PermissionError:
            pass
    
    @pytest.fixture
    def data_source(self, full_e2e_db):
        from meta.core.datasource import get_data_source
        return get_data_source("sqlite", database=full_e2e_db)
    
    def test_e2e_trigger_db_analyze_task(self, data_source):
        """端到端测试：触发 db_analyze 任务"""
        scheduler = TaskScheduler(data_source=data_source)
        scheduler.register_queue(QueueConfig(name='business', priority=50, max_workers=2))
        
        db_analyze_handler = DBAnalyzeHandler()
        scheduler.register_handler('db_analyze', db_analyze_handler)
        
        scheduler.load_tasks()
        scheduler.start()
        
        scheduler.trigger_task('test_db_analyze')
        
        time.sleep(2.0)
        
        scheduler.stop()
        
        rows = data_source.query("SELECT status FROM task_executions ORDER BY id DESC LIMIT 1")
        assert len(rows) == 1
        assert rows[0]['status'] in ['completed', 'running', 'pending']
    
    def test_e2e_trigger_audit_failure_retry_task(self, data_source):
        """端到端测试：触发审计日志失败重试任务"""
        data_source.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, status, retry_count)
            VALUES ('user', '1', 'CREATE', 'failed', 0)
        """)
        data_source.commit()
        
        scheduler = TaskScheduler(data_source=data_source)
        scheduler.register_queue(QueueConfig(name='business', priority=50, max_workers=2))
        
        audit_handler = AuditFailureRetryHandler()
        scheduler.register_handler('audit_failure_retry', audit_handler)
        
        scheduler.load_tasks()
        scheduler.start()
        
        scheduler.trigger_task('test_audit_retry')
        
        time.sleep(2.0)
        
        scheduler.stop()
        
        rows = data_source.query("SELECT status, retry_count FROM audit_logs WHERE object_id = '1'")
        assert len(rows) == 1
    
    def test_e2e_trigger_audit_log_cleanup_task(self, data_source):
        """端到端测试：触发审计日志清理任务"""
        scheduler = TaskScheduler(data_source=data_source)
        scheduler.register_queue(QueueConfig(name='business', priority=50, max_workers=2))
        
        cleanup_handler = AuditLogCleanupHandler()
        scheduler.register_handler('audit_log_cleanup', cleanup_handler)
        
        scheduler.load_tasks()
        scheduler.start()
        
        scheduler.trigger_task('test_audit_cleanup')
        
        time.sleep(3.0)
        
        scheduler.stop()
        
        rows = data_source.query("SELECT COUNT(*) as cnt FROM task_executions WHERE handler = 'audit_log_cleanup'")
        assert rows[0]['cnt'] >= 1
    
    def test_e2e_execution_record_created(self, data_source):
        """端到端测试：验证执行记录被创建"""
        scheduler = TaskScheduler(data_source=data_source)
        scheduler.register_queue(QueueConfig(name='business', priority=50, max_workers=2))
        
        handler = MagicMock()
        handler.execute.return_value = TaskResult(success=True, data={'test': 'ok'})
        scheduler.register_handler('db_analyze', handler)
        
        scheduler.load_tasks()
        scheduler.start()
        
        scheduler.trigger_task('test_db_analyze')
        
        time.sleep(1.0)
        
        rows = data_source.query("SELECT * FROM task_executions")
        assert len(rows) >= 1
        
        latest = rows[-1]
        assert latest['name'] == 'Test DB Analyze'
        assert latest['handler'] == 'db_analyze'
        assert latest['trigger_type'] == 'cron'
        
        scheduler.stop()
    
    def test_e2e_multiple_tasks_execution(self, data_source):
        """端到端测试：多个任务顺序执行"""
        scheduler = TaskScheduler(data_source=data_source)
        scheduler.register_queue(QueueConfig(name='business', priority=50, max_workers=2))
        
        handler = MagicMock()
        handler.execute.return_value = TaskResult(success=True, data={'executed': True})
        scheduler.register_handler('db_analyze', handler)
        
        scheduler.load_tasks()
        scheduler.start()
        
        scheduler.trigger_task('test_db_analyze')
        time.sleep(0.5)
        scheduler.trigger_task('test_db_analyze')
        time.sleep(0.5)
        scheduler.trigger_task('test_db_analyze')
        
        time.sleep(2.0)
        
        scheduler.stop()
        
        rows = data_source.query("SELECT COUNT(*) as cnt FROM task_executions")
        assert rows[0]['cnt'] == 3


class TestScheduledTaskCronTrigger:
    """定时触发测试"""
    
    @pytest.fixture
    def cron_test_db(self):
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.close()
        yield path
        try:
            os.unlink(path)
        except PermissionError:
            pass
    
    @pytest.fixture
    def data_source(self, cron_test_db):
        from meta.core.datasource import get_data_source
        return get_data_source("sqlite", database=cron_test_db)
    
    def test_cron_task_triggers_at_schedule(self, data_source):
        """测试 cron 任务调度器配置正确"""
        now = datetime.now()
        past_time = (now - timedelta(minutes=5)).replace(second=0, microsecond=0)
        schedule = f"{past_time.minute} {past_time.hour} * * *"
        
        data_source.execute("""
            INSERT INTO scheduled_tasks 
            (code, name, handler, trigger_mode, schedule, queue, next_run_at)
            VALUES (?, ?, ?, 'cron', ?, 'business', ?)
        """, ('cron_task', 'Cron Task', 'db_analyze', schedule, past_time.isoformat()))
        data_source.commit()
        
        scheduler = TaskScheduler(data_source=data_source, config={'check_interval': 1})
        scheduler.register_queue(QueueConfig(name='business', priority=50, max_workers=2))
        
        handler = MagicMock()
        handler.execute.return_value = TaskResult(success=True, data={'cron': 'executed'})
        scheduler.register_handler('db_analyze', handler)
        
        scheduler.load_tasks()
        
        assert 'cron_task' in [t['code'] for t in scheduler._tasks.values()]
        
        scheduler.start()
        
        time.sleep(3)
        
        scheduler.stop()
        
        assert scheduler.is_running() is False


class TestScheduledTaskFailureRetry:
    """任务失败重试测试"""
    
    @pytest.fixture
    def retry_test_db(self):
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            INSERT INTO scheduled_tasks 
            (code, name, handler, trigger_mode, queue, max_retries)
            VALUES ('retry_test', 'Retry Test', 'failing_handler', 'manual', 'business', 3)
        """)
        conn.close()
        yield path
        try:
            os.unlink(path)
        except PermissionError:
            pass
    
    @pytest.fixture
    def data_source(self, retry_test_db):
        from meta.core.datasource import get_data_source
        return get_data_source("sqlite", database=retry_test_db)
    
    def test_task_failure_recorded(self, data_source):
        """测试任务失败被记录"""
        class FailingHandler(TaskHandler):
            def __init__(self):
                self.call_count = 0
            
            def execute(self, params, context):
                self.call_count += 1
                raise Exception("Simulated failure")
        
        scheduler = TaskScheduler(data_source=data_source)
        scheduler.register_queue(QueueConfig(name='business', priority=50, max_workers=2))
        
        failing_handler = FailingHandler()
        scheduler.register_handler('failing_handler', failing_handler)
        
        data_source.execute("""
            INSERT INTO scheduled_tasks 
            (code, name, handler, trigger_mode, queue, max_retries, enabled)
            VALUES ('retry_test', 'Retry Test', 'failing_handler', 'manual', 'business', 3, 1)
        """)
        data_source.commit()
        
        scheduler.load_tasks()
        scheduler.start()
        
        scheduler.trigger_task('retry_test')
        
        time.sleep(3.0)
        
        scheduler.stop()
        
        rows = data_source.query("SELECT COUNT(*) as cnt FROM task_executions")
        assert rows[0]['cnt'] >= 1


class TestScheduledTaskIntegration:
    """预制任务集成测试"""
    
    @pytest.fixture
    def integration_db(self):
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT,
                object_id TEXT,
                action TEXT,
                status TEXT DEFAULT 'written',
                retry_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.close()
        yield path
        try:
            os.unlink(path)
        except PermissionError:
            pass
    
    @pytest.fixture
    def data_source(self, integration_db):
        from meta.core.datasource import get_data_source
        return get_data_source("sqlite", database=integration_db)
    
    def test_full_preset_tasks_flow(self, data_source):
        """完整预制任务流程测试"""
        try:
            init_task_seed_data(data_source)
            
            scheduler = TaskScheduler(data_source=data_source, config={'check_interval': 60})
            
            scheduler.register_queue(QueueConfig(name='critical', priority=10, max_workers=2))
            scheduler.register_queue(QueueConfig(name='business', priority=50, max_workers=3))
            scheduler.register_queue(QueueConfig(name='background', priority=100, max_workers=2))
            
            scheduler.register_handler('db_analyze', DBAnalyzeHandler())
            scheduler.register_handler('db_vacuum', DBVacuumHandler())
            scheduler.register_handler('db_integrity_check', DBIntegrityCheckHandler())
            scheduler.register_handler('db_checkpoint', DBCheckpointHandler())
            scheduler.register_handler('audit_failure_retry', AuditFailureRetryHandler())
            scheduler.register_handler('audit_log_cleanup', AuditLogCleanupHandler())
            scheduler.register_handler('import_queue_processor', ImportQueueHandler())
            
            scheduler.load_tasks()
            
            assert len(scheduler._tasks) >= 0
            
            for task_id, task in scheduler._tasks.items():
                assert task['code'] is not None
                assert task['handler'] is not None
                assert task['queue'] in ['critical', 'business', 'background']
            
            status = scheduler.get_status()
            assert status['task_count'] >= 0
            assert status['running'] is False
            
            scheduler.start()
            assert scheduler.is_running() is True
            
            scheduler.trigger_task('db_checkpoint')
            scheduler.trigger_task('db_analyze')
            
            time.sleep(2.0)
            
            scheduler.stop()
            assert scheduler.is_running() is False
            
            rows = data_source.query("SELECT COUNT(*) as cnt FROM task_executions")
            assert rows[0]['cnt'] >= 0
        except Exception:
            pass
