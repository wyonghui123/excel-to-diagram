"""
TaskQueueFactory (Phase 5 新建)
================================

任务队列配置工厂: 用于任务调度相关测试

yaml: meta/schemas/task_queue.yaml
required 字段 (排除审计自动生成):
- name (unique, max_length=50)
- priority (default=50)
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class TaskQueueFactory(BaseFactory):
    """任务队列配置工厂"""

    _OBJECT_TYPE = 'task_queue'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        suffix = unique_str(4)
        return {
            # [FIX 2026-07-17 P1] 覆盖 yaml 必填字段
            # name: unique + max_length=50
            'name': f'test_queue_{n}_{suffix}'[:50],
            'priority': 50,
            # 业务字段 (使用 yaml default 值)
            'description': f'Test task queue {n}',
            'max_workers': 5,
            'timeout': 300,
            'enabled': True,
            'current_workers': 0,
        }

    @classmethod
    def create_high_priority(cls, cookie=None, **overrides) -> Dict[str, Any]:
        """创建高优先级队列"""
        return cls.create(cookie=cookie, priority=10, **overrides)

    @classmethod
    def create_disabled(cls, cookie=None, **overrides) -> Dict[str, Any]:
        """创建禁用队列"""
        return cls.create(cookie=cookie, enabled=False, **overrides)