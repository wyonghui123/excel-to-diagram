# -*- coding: utf-8 -*-
"""
UnifiedMutationFacade（QE-M5-2026-06-v2）

写路径 SSOT（Single Source of Truth），统一 create / update / delete / deep_insert。
与 UnifiedQueryFacade 对称，共同构成 v3 引擎的读写双 SSOT。

设计原则：
- 包装而非替换：BOFramework.create/update/delete / DeepInsertEngine.execute 全部复用
- 复用现有事务：bo_framework.transaction() / DataSource.transaction()
- 复用 transaction_id 体系：X-Transaction-Id header + audit_log 共享 transaction_id
- 嵌套识别：DataSource.in_transaction=True 时跳过内层开事务
- 零侵入：旧调用方 bo_framework.create(...) 仍可用
"""
from __future__ import annotations
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class UnifiedMutationRequest(BaseModel):
    """统一写请求。"""
    entity_type: str
    action: str  # 'create' | 'update' | 'delete' | 'deep_insert'
    data: Dict[str, Any] = Field(default_factory=dict)
    options: Dict[str, Any] = Field(default_factory=dict)
    user_context: Dict[str, Any] = Field(default_factory=dict)
    trace_id: str = ''


class UnifiedMutationResponse(BaseModel):
    """统一写响应。"""
    success: bool
    transaction_id: str = ''
    trace_id: str = ''
    affected_ids: List[int] = Field(default_factory=list)
    data: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    rolled_back: bool = False
    failed_at: str = ''
    elapsed_ms: float = 0.0
    # [M5.4] 审计回放链（同一 transaction_id 收集的 audit_log）
    audit_chain: List[Dict[str, Any]] = Field(default_factory=list)


class _MutationError(Exception):
    """内部异常：标记事务失败阶段。"""

    def __init__(self, stage: str, detail: str, errors: Optional[List[str]] = None):
        super().__init__(f'{stage}: {detail}')
        self.stage = stage
        self.detail = detail
        self.errors = errors or [detail]


class UnifiedMutationFacade:
    """写路径 SSOT 入口。"""

    SUPPORTED_ACTIONS = ('create', 'update', 'delete', 'deep_insert')

    def __init__(self, bo_framework=None, deep_insert_engine=None):
        # 延迟导入避免循环依赖
        from meta.core.bo_framework import bo_framework as default_bf
        from meta.core.deep_insert_engine import DeepInsertEngine
        self.bo_framework = bo_framework or default_bf
        self.deep_insert_engine = deep_insert_engine or DeepInsertEngine()

    def execute(self, req: UnifiedMutationRequest) -> UnifiedMutationResponse:
        """统一写操作入口。"""
        t0 = time.perf_counter()
        trace_id = req.trace_id or f"qe-{uuid.uuid4().hex[:16]}"
        outer_transaction_id = f"mu-{uuid.uuid4().hex[:16]}"
        errors: List[str] = []
        affected_ids: List[int] = []
        result_data: Dict[str, Any] = {}
        rolled_back = False
        failed_at = ''
        transaction_id = ''
        audit_chain: List[Dict[str, Any]] = []

        if req.action not in self.SUPPORTED_ACTIONS:
            return UnifiedMutationResponse(
                success=False,
                transaction_id=outer_transaction_id,
                trace_id=trace_id,
                errors=[f'unsupported action: {req.action}'],
                failed_at='pre_check',
                elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            )

        try:
            # 复用 bo_framework.transaction() 现有 context（生成 transaction_id）
            with self.bo_framework.transaction() as txn_ctx:
                transaction_id = txn_ctx.transaction_id

                if req.action == 'deep_insert':
                    action_result = self.deep_insert_engine.execute(
                        req.entity_type, req.data, self.bo_framework._data_source
                    )
                elif req.action == 'create':
                    action_result = self.bo_framework.create(req.entity_type, req.data)
                elif req.action == 'update':
                    obj_id = req.data.get('id')
                    if obj_id is None:
                        raise _MutationError(
                            stage='pre_check',
                            detail='update requires id in data',
                        )
                    action_result = self.bo_framework.update(
                        req.entity_type, obj_id, req.data
                    )
                elif req.action == 'delete':
                    obj_id = req.data.get('id')
                    if obj_id is None:
                        raise _MutationError(
                            stage='pre_check',
                            detail='delete requires id in data',
                        )
                    action_result = self.bo_framework.delete(
                        req.entity_type, obj_id
                    )
                else:
                    raise _MutationError(
                        stage='pre_check',
                        detail=f'unsupported action: {req.action}',
                    )

                if not action_result.success:
                    raise _MutationError(
                        stage=req.action,
                        detail=action_result.message or 'unknown failure',
                        errors=getattr(action_result, 'errors', []) or None,
                    )

                result_data = action_result.data or {}
                affected_ids = self._extract_ids(result_data)
                # [M5.4] 收集 audit_chain（事务提交前一刻收集）
                audit_chain = self._collect_audit_logs(transaction_id)

        except _MutationError as e:
            rolled_back = True
            failed_at = e.stage
            errors = e.errors or [e.detail]
            logger.warning(
                f"[UnifiedMutationFacade.M5] action={req.action} entity={req.entity_type} "
                f"rolled back at stage={e.stage}: {e.detail}"
            )
        except Exception as e:
            # 未知错误也回滚
            rolled_back = True
            failed_at = 'unexpected'
            errors = [str(e)]
            logger.error(
                f"[UnifiedMutationFacade.M5] unexpected error: {e}",
                exc_info=True,
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return UnifiedMutationResponse(
            success=not rolled_back and not errors,
            transaction_id=transaction_id or outer_transaction_id,
            trace_id=trace_id,
            affected_ids=affected_ids,
            data=result_data,
            errors=errors,
            rolled_back=rolled_back,
            failed_at=failed_at,
            elapsed_ms=elapsed_ms,
            audit_chain=audit_chain,
        )

    def _extract_ids(self, data: Dict[str, Any]) -> List[int]:
        """从 result.data 提取所有 id（主对象 + 嵌套子对象）。"""
        if not data:
            return []
        ids: List[int] = []
        if 'id' in data and isinstance(data['id'], int):
            ids.append(data['id'])
        # deep_insert 嵌套子对象
        for k, v in data.items():
            if isinstance(v, list) and v:
                for item in v:
                    if isinstance(item, dict) and 'id' in item and isinstance(item['id'], int):
                        ids.append(item['id'])
        return ids

    def _collect_audit_logs(self, transaction_id: str) -> List[Dict[str, Any]]:
        """[M5.4] 收集事务内所有 audit_log。

        Returns:
            List[Dict]: 形如 [
                {log_id, user_id, action, object_type, object_id, created_at, ...},
                ...
            ]
        """
        if not transaction_id:
            return []
        try:
            # 尝试从 audit_log 表查询（如果存在）
            from meta.core.bo_framework import bo_framework
            ds = bo_framework._data_source
            if hasattr(ds, '_connection') and ds._connection:
                cursor = ds._connection.cursor()
                try:
                    cursor.execute(
                        "SELECT id, user_id, action, object_type, object_id, created_at, trace_id, transaction_id "
                        "FROM audit_log WHERE transaction_id = ? ORDER BY id",
                        (transaction_id,),
                    )
                    rows = cursor.fetchall()
                    return [
                        {
                            'log_id': row[0],
                            'user_id': row[1],
                            'action': row[2],
                            'object_type': row[3],
                            'object_id': row[4],
                            'created_at': str(row[5]) if row[5] else None,
                            'trace_id': row[6],
                            'transaction_id': row[7],
                        }
                        for row in rows
                    ]
                except Exception:
                    # audit_log 表可能不存在（不强依赖）
                    return []
        except Exception as e:
            logger.debug(f"[UnifiedMutationFacade.M5] audit_log collection skipped: {e}")
        return []


# 全局默认实例
_default_facade: Optional[UnifiedMutationFacade] = None


def get_mutation_facade() -> UnifiedMutationFacade:
    """获取全局 UnifiedMutationFacade（单例）。"""
    global _default_facade
    if _default_facade is None:
        _default_facade = UnifiedMutationFacade()
    return _default_facade
