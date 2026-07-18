"""
AiAsyncTaskFactory (Phase 5 新建)
==================================

AI 异步任务工厂: 用于 AI 查询/分析/嵌入等异步任务测试

yaml: meta/schemas/ai_async_task.yaml
required 字段 (排除审计自动生成):
- task_type (enum: query/analyze/action/embedding/agent/rag)
- request (json)
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class AiAsyncTaskFactory(BaseFactory):
    """AI 异步任务工厂"""

    _OBJECT_TYPE = 'ai_async_task'

    # 标准 task_type 值 (来自 schema enum_values)
    TYPE_QUERY = 'query'
    TYPE_ANALYZE = 'analyze'
    TYPE_ACTION = 'action'
    TYPE_EMBEDDING = 'embedding'
    TYPE_AGENT = 'agent'
    TYPE_RAG = 'rag'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        suffix = unique_str(4)
        return {
            # [FIX 2026-07-17 P1] 覆盖 yaml 必填字段
            'task_type': cls.TYPE_QUERY,
            'request': {
                'prompt': f'Test AI query #{n}',
                'context': {'test': True},
            },
            # 业务字段 (使用 yaml default 值)
            'session_id': f'sess_{n}_{suffix}',
            'agent_id': None,
            'parent_task_id': None,
            'context': {'test': True, 'auto_generated': True},
            'priority': 50,
            'queue': 'ai_normal',
            'status': 'pending',
            'worker_id': None,
        }

    @classmethod
    def create_query(cls, prompt: str, cookie=None, **overrides) -> Dict[str, Any]:
        """创建 AI 查询任务"""
        return cls.create(
            cookie=cookie,
            task_type=cls.TYPE_QUERY,
            request={'prompt': prompt},
            **overrides
        )

    @classmethod
    def create_analyze(cls, data: Dict, cookie=None, **overrides) -> Dict[str, Any]:
        """创建 AI 分析任务"""
        return cls.create(
            cookie=cookie,
            task_type=cls.TYPE_ANALYZE,
            request={'data': data},
            **overrides
        )

    @classmethod
    def create_embedding(cls, text: str, cookie=None, **overrides) -> Dict[str, Any]:
        """创建嵌入计算任务"""
        return cls.create(
            cookie=cookie,
            task_type=cls.TYPE_EMBEDDING,
            request={'text': text},
            **overrides
        )

    @classmethod
    def create_agent_task(
        cls, agent_id: str, instruction: str, cookie=None, **overrides
    ) -> Dict[str, Any]:
        """创建 Agent 任务"""
        return cls.create(
            cookie=cookie,
            task_type=cls.TYPE_AGENT,
            agent_id=agent_id,
            request={'instruction': instruction},
            **overrides
        )

    @classmethod
    def create_rag_query(
        cls, query: str, knowledge_base: str, cookie=None, **overrides
    ) -> Dict[str, Any]:
        """创建 RAG 检索任务"""
        return cls.create(
            cookie=cookie,
            task_type=cls.TYPE_RAG,
            request={'query': query, 'knowledge_base': knowledge_base},
            **overrides
        )