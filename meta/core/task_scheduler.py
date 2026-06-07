# -*- coding: utf-8 -*-
import os
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

from meta.core.cron_parser import CronParser
from meta.core.task_queue_manager import TaskQueueManager, QueueConfig
from meta.core.task_handler import TaskHandler, TaskResult, TaskExecutionContext

logger = logging.getLogger(__name__)

DISABLE_TASK_SCHEDULER = os.environ.get('DISABLE_TASK_SCHEDULER', '').lower() in ('true', '1', 'yes')


class TaskScheduler:
    
    def __init__(self, data_source=None, config: dict = None):
        self.data_source = data_source
        self.config = config or {}
        self.cron_parser = CronParser()
        self.queue_manager = TaskQueueManager(data_source)
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._tasks: Dict[int, dict] = {}
        self._handlers: Dict[str, TaskHandler] = {}
        self._interval = self.config.get('check_interval', 60)
    
    def register_handler(self, name: str, handler: TaskHandler):
        self._handlers[name] = handler
        self.queue_manager.register_handler(name, handler.execute)
        logger.info("Handler registered: %s", name)
    
    def register_queue(self, config: QueueConfig):
        self.queue_manager.register_queue(config)
    
    def load_tasks(self):
        if not self.data_source:
            logger.warning("No data_source, cannot load tasks")
            return
        
        try:
            rows = self.data_source.query(
                "SELECT * FROM scheduled_tasks WHERE enabled = 1"
            )
            self._tasks.clear()
            for row in rows:
                self._tasks[row['id']] = dict(row)
            
            logger.info("Loaded %d tasks from database", len(self._tasks))
            self._calculate_next_run()
            
        except Exception as e:
            logger.error("Failed to load tasks: %s", e)
    
    def _calculate_next_run(self):
        now = datetime.now()
        for task_id, task in self._tasks.items():
            if task.get('trigger_mode') != 'cron':
                continue
            schedule = task.get('schedule')
            if not schedule:
                continue
            
            next_run = self.cron_parser.get_next(schedule, now)
            if next_run:
                task['next_run_at'] = next_run.isoformat()
    
    def start(self):
        if DISABLE_TASK_SCHEDULER:
            logger.info("TaskScheduler disabled (test mode)")
            return
        logger.info("TaskScheduler starting...")
        
        self.queue_manager.load_queues_from_db()
        self.load_tasks()
        
        self._running = True
        self._thread = threading.Thread(
            target=self._scheduler_loop,
            name="task-scheduler",
            daemon=True
        )
        self._thread.start()
        logger.info("TaskScheduler started")
    
    def stop(self):
        logger.info("TaskScheduler stopping...")
        self._running = False
        
        if self._thread:
            self._thread.join(timeout=10)
        
        self.queue_manager.shutdown()
        logger.info("TaskScheduler stopped")
    
    def _scheduler_loop(self):
        while self._running:
            try:
                now = datetime.now()
                
                for task_id, task in list(self._tasks.items()):
                    if task.get('trigger_mode') != 'cron':
                        continue
                    if not task.get('enabled'):
                        continue
                    
                    next_run_str = task.get('next_run_at')
                    if not next_run_str:
                        continue
                    
                    try:
                        next_run = datetime.fromisoformat(next_run_str)
                    except (ValueError, TypeError):
                        continue
                    
                    if next_run <= now:
                        self._execute_task(task_id, task)
                        
                        schedule = task.get('schedule')
                        new_next = self.cron_parser.get_next(schedule, now)
                        if new_next:
                            task['next_run_at'] = new_next.isoformat()
                            try:
                                self.data_source.execute(
                                    "UPDATE scheduled_tasks SET "
                                    "last_run_at = ?, next_run_at = ? "
                                    "WHERE id = ?",
                                    (now.isoformat(), new_next.isoformat(), task_id)
                                )
                                self.data_source.commit()
                            except Exception as e:
                                logger.warning("Failed to update next_run: %s", e)
                
            except Exception as e:
                logger.error("Scheduler loop error: %s", e)
            
            time.sleep(self._interval)
    
    def _execute_task(self, task_id: int, task: dict):
        handler_name = task.get('handler')
        
        if handler_name not in self._handlers:
            logger.error("Handler not found: %s", handler_name)
            return
        
        execution_id = self._create_execution_record(task)
        if not execution_id:
            return
        
        context = TaskExecutionContext(
            task_id=task_id,
            execution_id=execution_id,
            trigger_type='cron',
            params=task.get('handler_config') or {}
        )
        
        start_time = datetime.now()
        self._update_execution_status(
            execution_id, 'running', started_at=start_time.isoformat()
        )
        
        queue_name = task.get('queue', 'business')
        
        def _callback(
            queue_name=None, handler_name=None,
            result=None, error=None, duration_ms=None
        ):
            now = datetime.now()
            if error:
                self._handle_execution_failure(execution_id, error, duration_ms)
            else:
                result_data = None
                if isinstance(result, TaskResult):
                    result_data = {
                        'success': result.success,
                        'data': result.data,
                        'error': result.error,
                        'tokens_used': result.tokens_used,
                        'cost': result.cost,
                    }
                
                self._update_execution_status(
                    execution_id, 'completed',
                    completed_at=now.isoformat(),
                    duration_ms=duration_ms,
                    result=str(result_data) if result_data else None
                )
        
        self.queue_manager.submit(
            queue_name=queue_name,
            handler_name=handler_name,
            params=task.get('handler_config') or {},
            context={
                'task_id': task_id,
                'execution_id': execution_id,
                'data_source': self.data_source,
                'handler_config': task.get('handler_config') or {},
            },
            callback=_callback
        )
    
    def _create_execution_record(self, task: dict) -> int:
        try:
            self.data_source.execute(
                "INSERT INTO task_executions "
                "(name, task_id, task_type, handler, status, trigger_type, "
                " queue, priority, timeout, max_retries, queued_at, created_at) "
                "VALUES (?, ?, ?, ?, 'pending', 'cron', ?, ?, ?, ?, ?, ?)",
                (
                    task.get('name', ''),
                    task.get('id'),
                    task.get('category', 'business'),
                    task.get('handler', ''),
                    task.get('queue', 'business'),
                    task.get('priority', 50),
                    task.get('timeout', 300),
                    task.get('max_retries', 3),
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                )
            )
            self.data_source.commit()
            
            result = self.data_source.query("SELECT last_insert_rowid() as id")
            return result[0]['id'] if result else 0
            
        except Exception as e:
            logger.error("Failed to create execution record: %s", e)
            return 0
    
    def _update_execution_status(self, execution_id: int, status: str, **kwargs):
        try:
            set_clauses = ["status = ?"]
            params = [status]
            
            field_mapping = {
                'started_at': 'started_at',
                'completed_at': 'completed_at',
                'duration_ms': 'duration_ms',
                'error_message': 'error_message',
                'retry_count': 'retry_count',
                'result': 'result',
            }
            
            for key, value in kwargs.items():
                db_field = field_mapping.get(key, key)
                set_clauses.append(f"{db_field} = ?")
                params.append(value)
            
            params.append(execution_id)
            
            sql = f"UPDATE task_executions SET {', '.join(set_clauses)} WHERE id = ?"
            self.data_source.execute(sql, tuple(params))
            self.data_source.commit()
            
        except Exception as e:
            logger.error("Failed to update execution status: %s", e)
    
    def _handle_execution_failure(self, execution_id: int, error: str, duration_ms: int):
        try:
            row = self.data_source.query(
                "SELECT retry_count, max_retries FROM task_executions WHERE id = ?",
                (execution_id,)
            )
            if not row:
                return
            
            current = row[0]
            retry_count = current.get('retry_count', 0) + 1
            max_retries = current.get('max_retries', 3)
            
            now = datetime.now().isoformat()
            
            if retry_count < max_retries:
                self._update_execution_status(
                    execution_id, 'pending',
                    error_message=error,
                    retry_count=retry_count,
                    completed_at=now,
                    duration_ms=duration_ms,
                )
            else:
                self._update_execution_status(
                    execution_id, 'failed',
                    completed_at=now,
                    duration_ms=duration_ms,
                    error_message=error,
                    retry_count=retry_count,
                )
        except Exception as e:
            logger.error("Failed to handle execution failure: %s", e)
    
    def trigger_task(self, task_code: str, params: dict = None):
        task = None
        for t in self._tasks.values():
            if t.get('code') == task_code:
                task = t
                break
        
        if not task:
            raise ValueError(f"Task not found: {task_code}")
        
        self._execute_task(task['id'], task)
    
    def get_status(self) -> dict:
        return {
            'running': self._running,
            'task_count': len(self._tasks),
            'queue_stats': self.queue_manager.get_queue_stats(),
        }
    
    def reload(self):
        self.load_tasks()
        logger.info("Task scheduler reloaded")
    
    def is_running(self) -> bool:
        return self._running