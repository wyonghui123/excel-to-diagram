# -*- coding: utf-8 -*-
import logging
from meta.core.task_handler import TaskHandler, TaskResult, TaskExecutionContext

logger = logging.getLogger(__name__)


class DBAnalyzeHandler(TaskHandler):
    
    def execute(self, params, context):
        try:
            ds = context.get('data_source')
            ds.execute("ANALYZE")
            ds.commit()
            return TaskResult(success=True, data={'action': 'ANALYZE'})
        except Exception as e:
            return TaskResult(success=False, error=str(e))


class DBVacuumHandler(TaskHandler):
    
    def execute(self, params, context):
        try:
            ds = context.get('data_source')
            ds.execute("PRAGMA incremental_vacuum")
            return TaskResult(success=True, data={'action': 'INCREMENTAL_VACUUM'})
        except Exception as e:
            return TaskResult(success=False, error=str(e))


class DBIntegrityCheckHandler(TaskHandler):
    
    def execute(self, params, context):
        try:
            ds = context.get('data_source')
            result = ds.query("PRAGMA integrity_check")
            status = result[0]['integrity_check'] if result else 'unknown'
            return TaskResult(
                success=(status == 'ok'),
                data={'status': status}
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))


class DBCheckpointHandler(TaskHandler):
    
    def execute(self, params, context):
        try:
            ds = context.get('data_source')
            ds.checkpoint("FULL")
            ds.commit()
            return TaskResult(success=True, data={'action': 'WAL_CHECKPOINT'})
        except Exception as e:
            return TaskResult(success=False, error=str(e))