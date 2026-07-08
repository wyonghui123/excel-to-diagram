# -*- coding: utf-8 -*-
import threading
import time
import logging
from typing import Dict, Optional, Callable
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


@dataclass
class QueueConfig:
    name: str
    priority: int
    max_workers: int = 5
    timeout: int = 300
    enabled: bool = True


class TaskQueueManager:
    
    def __init__(self, data_source=None):
        self.data_source = data_source
        self._queues: Dict[str, QueueConfig] = {}
        self._executors: Dict[str, ThreadPoolExecutor] = {}
        self._handlers: Dict[str, Callable] = {}
        self._lock = threading.Lock()
    
    def register_queue(self, config: QueueConfig):
        with self._lock:
            self._queues[config.name] = config
            if config.enabled:
                self._executors[config.name] = ThreadPoolExecutor(
                    max_workers=config.max_workers,
                    thread_name_prefix=f"queue_{config.name}"
                )
            logger.info(
                "Queue registered: %s (priority=%d, workers=%d)",
                config.name, config.priority, config.max_workers
            )
    
    def register_handler(self, handler_name: str, handler: Callable):
        self._handlers[handler_name] = handler
    
    def load_queues_from_db(self):
        try:
            if not self.data_source:
                logger.warning("No data_source configured, skipping queue load")
                return
            
            rows = self.data_source.query(
                "SELECT * FROM task_queues WHERE enabled = 1"
            )
            for row in rows:
                config = QueueConfig(
                    name=row['name'],
                    priority=row['priority'],
                    max_workers=row['max_workers'],
                    timeout=row['timeout'],
                    enabled=row['enabled']
                )
                self.register_queue(config)
        except Exception as e:
            logger.error("Failed to load queues from DB: %s", e)
    
    def _has_queue(self, queue_name: str) -> bool:
        return queue_name in self._executors
    
    def submit(
        self,
        queue_name: str,
        handler_name: str,
        params: dict = None,
        context: dict = None,
        callback: Callable = None
    ) -> bool:
        if not self._has_queue(queue_name):
            fallback = 'business'
            if self._has_queue(fallback):
                queue_name = fallback
            else:
                logger.error("Queue '%s' and fallback '%s' not found", queue_name, fallback)
                return False
        
        config = self._queues.get(queue_name)
        if not config or not config.enabled:
            return False
        
        executor = self._executors[queue_name]
        params = params or {}
        context = context or {}
        
        def _execute():
            start_time = time.time()
            try:
                handler = self._handlers.get(handler_name)
                if not handler:
                    logger.error("Handler %s not found", handler_name)
                    return
                
                result = handler(params, context)
                duration_ms = int((time.time() - start_time) * 1000)
                
                if callback:
                    callback(
                        queue_name=queue_name,
                        handler_name=handler_name,
                        result=result,
                        duration_ms=duration_ms
                    )
                    
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    "Task execution failed: %s on queue %s: %s",
                    handler_name, queue_name, e
                )
                if callback:
                    callback(
                        queue_name=queue_name,
                        handler_name=handler_name,
                        error=str(e),
                        duration_ms=duration_ms
                    )
        
        executor.submit(_execute)
        return True
    
    def get_queue_stats(self) -> list:
        stats = []
        for name, config in self._queues.items():
            executor = self._executors.get(name)
            stats.append({
                'name': name,
                'priority': config.priority,
                'max_workers': config.max_workers,
                'active_workers': (
                    executor._work_queue.qsize() if executor else 0
                ),
                'enabled': config.enabled
            })
        return stats
    
    def shutdown(self):
        for name, executor in self._executors.items():
            logger.info("Shutting down queue: %s", name)
            executor.shutdown(wait=True)