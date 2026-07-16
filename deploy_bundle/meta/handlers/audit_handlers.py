# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timedelta
from meta.core.task_handler import TaskHandler, TaskResult, TaskExecutionContext

logger = logging.getLogger(__name__)


class AuditLogArchiveHandler(TaskHandler):
    
    def execute(self, params, context):
        try:
            ds = context.get('data_source')
            config = context.get('handler_config', {})
            archive_days = config.get('archive_days', 90)
            
            cutoff = (datetime.now() - timedelta(days=archive_days)).isoformat()
            
            affected = ds.execute(
                "UPDATE audit_logs SET status = 'archived' "
                "WHERE created_at < ? AND status = 'written'",
                (cutoff,)
            )
            ds.commit()
            
            return TaskResult(
                success=True,
                data={'archived': f'{cutoff} cutoff'}
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))


class AuditLogCleanupHandler(TaskHandler):
    
    def execute(self, params, context):
        try:
            ds = context.get('data_source')
            config = context.get('handler_config', {})
            retention = config.get('retention_days', {
                'business': 365,
                'security': 2555,
                'operation': 90,
                'performance': 30,
                'system': 90,
            })
            
            total_deleted = 0
            for category, days in retention.items():
                cutoff = (datetime.now() - timedelta(days=days)).isoformat()
                ds.execute(
                    "DELETE FROM audit_logs "
                    "WHERE log_category = ? AND created_at < ?",
                    (category, cutoff)
                )
                total_deleted += 1
            
            ds.commit()
            return TaskResult(success=True, data={'categories_processed': total_deleted})
        except Exception as e:
            return TaskResult(success=False, error=str(e))


class AuditFailureRetryHandler(TaskHandler):
    
    def execute(self, params, context):
        try:
            ds = context.get('data_source')
            config = context.get('handler_config', {})
            batch_size = config.get('batch_size', 100)
            max_retries = config.get('max_retries', 3)
            
            rows = ds.query(
                "SELECT id FROM audit_logs "
                "WHERE status = 'failed' AND retry_count < ? "
                "LIMIT ?",
                (max_retries, batch_size)
            )
            
            retried = 0
            for row in rows:
                ds.execute(
                    "UPDATE audit_logs SET status = 'pending', "
                    "retry_count = retry_count + 1, "
                    "status_entered_at = ? "
                    "WHERE id = ?",
                    (datetime.now().isoformat(), row['id'])
                )
                retried += 1
            
            ds.commit()
            return TaskResult(success=True, data={'retried': retried})
        except Exception as e:
            return TaskResult(success=False, error=str(e))