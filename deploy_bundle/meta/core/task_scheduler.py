# -*- coding: utf-8 -*-
import os
import logging
import threading
import time
import random
from datetime import datetime, timedelta
from typing import Dict, Optional

from meta.core.cron_parser import CronParser
from meta.core.task_queue_manager import TaskQueueManager, QueueConfig
from meta.core.task_handler import TaskHandler, TaskResult, TaskExecutionContext

logger = logging.getLogger(__name__)

DISABLE_TASK_SCHEDULER = os.environ.get('DISABLE_TASK_SCHEDULER', '').lower() in ('true', '1', 'yes')

# [V007.38 BUG-FIX] 共享 retry 包裹器
# 写路径 (_create_execution_record, _update_execution_status, _handle_execution_failure) 都可能撞
# disk I/O error, 之前每个都只 logger.error 静默吞, 现在统一 retry
TASK_DB_RETRY_MAX = 5  # 跟 V007.34 一致
TASK_DB_RETRY_BASE_DELAY = 0.05  # 50ms 起步, 指数 backoff


def _is_retryable_db_error(err_str: str) -> bool:
    """[V007.38] 判断 db error 是否可重试"""
    err_lower = err_str.lower()
    return (
        'disk i/o' in err_lower or
        'database is locked' in err_lower or
        'database is busy' in err_lower
    )


def _retry_db_write(func, *args, **kwargs):
    """[V007.38] 统一 db 写操作 retry 包裹器

    Args:
        func: 实际执行 db 操作的 callable, 返回值会被传递
        *args, **kwargs: 传给 func

    Returns:
        func 的返回值, 或最后一次异常的 re-raise
    """
    last_error = None
    for attempt in range(TASK_DB_RETRY_MAX):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            is_retryable = _is_retryable_db_error(err_str)
            if is_retryable and attempt < TASK_DB_RETRY_MAX - 1:
                delay = TASK_DB_RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.02)
                logger.warning(
                    "[V007.38] db write retry %d/%d sleep %.3fs: %s",
                    attempt + 1, TASK_DB_RETRY_MAX, delay, err_str
                )
                time.sleep(delay)
                continue
            # 不可恢复 或 重试耗尽
            raise
    # 理论不会到这, 但保险
    raise last_error


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
        # [V007.38 BUG-FIX] 写路径 retry + 指数 backoff
        # 背景: task_scheduler 走 data_source.execute → _execute_via_write_queue → submit_and_wait
        #       但 WriteQueue retry 仅 retry 锁竞争, 不覆盖 disk I/O error 重建连接场景
        #       V007.35 mmap_size=256MB 让视图频繁失效, 写 task_executions 时撞 disk I/O error
        #       task_scheduler 之前只是 logger.error 静默吞掉, 后续 task 没记录 → 用户看不到
        # 修法: 用 _retry_db_write 统一包裹, 5 次 retry + 指数 backoff + jitter
        #       写后强制 PASSIVE checkpoint 减少 mmap 视图失效影响
        # [V007.38 BUG-FIX] 必须用 cursor.lastrowid, 不能用 SELECT last_insert_rowid()
        # 原因: data_source.execute 走读/写池, 每次可能不同 connection
        #       SELECT last_insert_rowid() 拿到的是 connection 自身 lastrowid, 不是 INSERT 后的
        #       V007.37 之前用单 connection 没问题, V007.38 retry 重建连接会丢 rowid
        def _do_insert():
            cursor = self.data_source.execute(
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
            # cursor.lastrowid 才是 INSERT 的实际 id
            if cursor and hasattr(cursor, 'lastrowid') and cursor.lastrowid:
                return cursor.lastrowid
            # 兜底: 如果 cursor 没 lastrowid 属性 (V007.20 之前), 用 SELECT (但有限制)
            # 不再 fallback 到 SELECT last_insert_rowid, 因为多连接下不准确
            return 0

        try:
            execution_id = _retry_db_write(_do_insert)
        except Exception as e:
            logger.error(
                "[V007.38] Failed to create execution record after %d retries: %s | task=%s",
                TASK_DB_RETRY_MAX, e, task.get('name', '?')
            )
            # [V007.38 BUG-FIX] 重试耗尽时记录 dead letter, 避免 task 静默丢失
            self._record_dead_letter(task, str(e))
            return 0

        # [V007.38 BUG-FIX] 写后强制 PASSIVE checkpoint
        # 减少 mmap 视图失效影响 (避免 20 个读连接全部 mark_error)
        if self.data_source and hasattr(self.data_source, '_pool') and self.data_source._pool:
            try:
                self.data_source._pool.force_passive_checkpoint()
            except Exception:
                pass  # 静默失败, 主流程不阻塞

        logger.info(
            "[V007.38] _create_execution_record success task=%s id=%d",
            task.get('name', '?'), execution_id
        )
        return execution_id

    def _record_dead_letter(self, task: dict, error_msg: str):
        """[V007.38] 写失败时记录 dead letter, 避免 task 静默丢失

        即使 execution_record 写不进 db, 也要留个 evidence 给排查
        """
        try:
            logger.error(
                "[V007.38] DEAD_LETTER task=%s handler=%s error=%s",
                task.get('name', '?'), task.get('handler', '?'), error_msg[:200]
            )
            # 写到本地文件 (兜底)
            import os
            dead_letter_path = "/opt/app/deployments/logs/task_scheduler_dead_letter.log"
            try:
                os.makedirs(os.path.dirname(dead_letter_path), exist_ok=True)
                with open(dead_letter_path, 'a') as f:
                    f.write(
                        f"{datetime.now().isoformat()}\ttask={task.get('name', '?')}\t"
                        f"handler={task.get('handler', '?')}\terror={error_msg[:200]}\n"
                    )
            except OSError:
                # 写不进文件也无所谓, 日志里已记录
                pass
        except Exception:
            # dead letter 自身失败不能影响主流程
            pass
    
    def _update_execution_status(self, execution_id: int, status: str, **kwargs):
        # [V007.38 BUG-FIX] 写路径加 retry (跟 _create_execution_record 同样的磁盘抖动)
        def _do_update():
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

        try:
            _retry_db_write(_do_update)
        except Exception as e:
            logger.error(
                "[V007.38] Failed to update execution status id=%d status=%s: %s",
                execution_id, status, e
            )
    
    def _handle_execution_failure(self, execution_id: int, error: str, duration_ms: int):
        # [V007.38 BUG-FIX] 写路径加 retry (跟 _create_execution_record 同样的磁盘抖动)
        def _do_handle():
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

        try:
            _retry_db_write(_do_handle)
        except Exception as e:
            logger.error(
                "[V007.38] Failed to handle execution failure id=%d: %s",
                execution_id, e
            )
    
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