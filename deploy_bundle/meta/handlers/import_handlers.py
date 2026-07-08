# -*- coding: utf-8 -*-
import logging
from meta.core.task_handler import TaskHandler, TaskResult, TaskExecutionContext

logger = logging.getLogger(__name__)


class ImportQueueHandler(TaskHandler):
    
    def execute(self, params, context):
        try:
            from meta.services.async_import_service import AsyncImportService
            
            service = AsyncImportService()
            
            active_tasks = service.get_all_tasks()
            pending_count = sum(
                1 for t in active_tasks.values()
                if t.status.value == 'pending'
            )
            
            return TaskResult(
                success=True,
                data={
                    'active_tasks': len(active_tasks),
                    'pending_tasks': pending_count,
                }
            )
            
        except Exception as e:
            logger.error("Import queue processing failed: %s", e)
            return TaskResult(success=False, error=str(e))