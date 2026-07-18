"""
TaskExecutionFactory (P1-5a 新建)
==================================

任务执行记录工厂: 用于后台任务执行历史的测试

yaml: meta/schemas/task_execution.yaml
表名: task_executions
required 字段:
- name (任务名称)
- task_type (business/ai/system/action)
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class TaskExecutionFactory(BaseFactory):
    """任务执行记录工厂"""

    _OBJECT_TYPE = 'task_execution'

    # 标准 task_type
    TYPE_BUSINESS = 'business'
    TYPE_AI = 'ai'
    TYPE_SYSTEM = 'system'
    TYPE_ACTION = 'action'

    # 标准 status
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_QUEUED = 'queued'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        suffix = unique_str(4)
        return {
            'name': f'test_task_exec_{n}_{suffix}',
            'task_id': None,
            'task_type': cls.TYPE_BUSINESS,
            'status': cls.STATUS_PENDING,
            'progress': 0,
            'input_data': '{}',
            'output_data': None,
            'error_message': None,
            'retry_count': 0,
            'duration_ms': None,
            'started_at': None,
            'finished_at': None,
        }

    @classmethod
    def create_with_type(
        cls, task_type: str, name: str = None, cookie=None, **overrides
    ):
        """创建指定 task_type 的执行记录"""
        if name is None:
            n = cls._next_counter()
            name = f'task_{task_type}_{n}'
        return cls.create(
            cookie=cookie, name=name, task_type=task_type, **overrides
        )

    @classmethod
    def create_running(cls, name: str = None, cookie=None, **overrides):
        """创建 running 状态的执行"""
        return cls.create(
            cookie=cookie, name=name,
            status=cls.STATUS_RUNNING, progress=50, **overrides
        )

    @classmethod
    def create_completed(cls, name: str = None, output_data: dict = None, cookie=None, **overrides):
        """创建已完成的执行"""
        import json as _json
        return cls.create(
            cookie=cookie, name=name,
            status=cls.STATUS_COMPLETED, progress=100,
            output_data=_json.dumps(output_data or {'result': 'ok'}),
            **overrides
        )

    @classmethod
    def create_failed(cls, name: str = None, error: str = None, cookie=None, **overrides):
        """创建失败状态的执行"""
        return cls.create(
            cookie=cookie, name=name,
            status=cls.STATUS_FAILED, error_message=error or 'Test failure', **overrides
        )

    @classmethod
    def create_queued(cls, name: str = None, cookie=None, **overrides):
        """创建排队中的执行"""
        return cls.create(
            cookie=cookie, name=name,
            status=cls.STATUS_QUEUED, **overrides
        )

    @classmethod
    def create_for_task(cls, task_id: int, task_type: str = None, cookie=None, **overrides):
        """创建关联 task_id 的执行"""
        return cls.create(
            cookie=cookie, task_id=task_id,
            task_type=task_type or cls.TYPE_BUSINESS, **overrides
        )