# -*- coding: utf-8 -*-
"""
UnitOfWork（QE-M5-2026-06-v2）

[M5.5 2026-06-05] 业务层事务单元。

复用 bo_framework.transaction() 现有 context + UnifiedMutationFacade。
允许业务方聚合多个写操作（create/update/delete/deep_insert），
提交时一次性开事务 + 全部成功才 commit / 任一失败整体 rollback。

设计原则：
- 包装而非替换：复用 UnifiedMutationFacade
- 复用现有事务：bo_framework.transaction() / DataSource.transaction()
- 链式 API：uow.add(...).add(...).commit()
- 占位符支持：data 中用 '@uow.last_id' 表示上一次操作返回的主 id
- 部分失败自动回滚：raise → with 块 exit 触发 rollback
"""
from __future__ import annotations
import logging
import re
from typing import Any, Dict, List, Optional

from meta.core.unified_mutation_facade import (
    UnifiedMutationRequest,
    UnifiedMutationResponse,
    UnifiedMutationFacade,
    get_mutation_facade,
)

logger = logging.getLogger(__name__)

# 占位符匹配：@uow.last_id / @uow.last_<entity>_id
_PLACEHOLDER_RE = re.compile(r'@uow\.(last_id|last_(\w+)_id)')


class _UnitOfWorkError(Exception):
    """UoW 部分失败。"""

    def __init__(self, stage: str, detail: str, partial_results: Optional[List[UnifiedMutationResponse]] = None):
        super().__init__(f'{stage}: {detail}')
        self.stage = stage
        self.detail = detail
        self.partial_results = partial_results or []


class UnitOfWork:
    """业务层事务单元。

    Usage:
        with UnitOfWork() as uow:
            uow.add(UnifiedMutationRequest(
                entity_type='user', action='create',
                data={'name': 'zhangsan'},
            ))
            uow.add(UnifiedMutationRequest(
                entity_type='user_group_membership', action='create',
                data={'user_id': '@uow.last_id', 'group_id': 1},
            ))
            result = uow.commit()
    """

    def __init__(self, user_context: Optional[Dict[str, Any]] = None):
        from meta.core.bo_framework import bo_framework
        self.bo_framework = bo_framework
        self.user_context = user_context or {}
        self._operations: List[UnifiedMutationRequest] = []
        self._facade: Optional[UnifiedMutationFacade] = None
        self._results: List[UnifiedMutationResponse] = []
        self._txn_started = False
        self._last_id: Optional[int] = None
        self._last_ids: Dict[str, int] = {}  # entity_type -> id

    def add(self, request: UnifiedMutationRequest) -> 'UnitOfWork':
        """添加一个写操作到 UoW（不立即执行）。"""
        if self._txn_started:
            raise RuntimeError("UnitOfWork: cannot add operations after commit()")
        self._operations.append(request)
        return self

    def commit(self) -> Dict[str, Any]:
        """提交整个 UoW。"""
        if not self._operations:
            return {
                'success': True,
                'transaction_id': '',
                'affected_ids': [],
                'operations': [],
                'commit_count': 0,
            }
        if self._facade is None:
            self._facade = get_mutation_facade()

        all_affected_ids: List[int] = []
        all_audit_chain: List[Dict[str, Any]] = []
        all_errors: List[str] = []
        transaction_id = ''

        try:
            with self.bo_framework.transaction() as txn_ctx:
                self._txn_started = True
                transaction_id = txn_ctx.transaction_id
                for i, op in enumerate(self._operations):
                    # 解析占位符
                    resolved_data = self._resolve_placeholders(op.data)
                    resolved_req = UnifiedMutationRequest(
                        entity_type=op.entity_type,
                        action=op.action,
                        data=resolved_data,
                        options=op.options,
                        user_context=op.user_context,
                        trace_id=op.trace_id,
                    )
                    resp = self._facade.execute(resolved_req)
                    if not resp.success:
                        raise _UnitOfWorkError(
                            stage=f'operation_{i}.{op.action}',
                            detail=resp.errors[0] if resp.errors else 'unknown',
                            partial_results=list(self._results),
                        )
                    self._results.append(resp)
                    all_affected_ids.extend(resp.affected_ids)
                    all_audit_chain.extend(resp.audit_chain)
                    # 记 last_id
                    if resp.affected_ids:
                        self._last_id = resp.affected_ids[0]
                        self._last_ids[op.entity_type] = resp.affected_ids[0]
            # with 正常退出 → commit
            return {
                'success': True,
                'transaction_id': transaction_id,
                'affected_ids': all_affected_ids,
                'operations': [r.data for r in self._results],
                'audit_chain': all_audit_chain,
                'commit_count': len(self._results),
            }
        except _UnitOfWorkError as e:
            logger.warning(
                f"[UnitOfWork.M5.5] rolled back at {e.stage}: {e.detail}"
            )
            return {
                'success': False,
                'transaction_id': transaction_id,
                'rolled_back': True,
                'failed_at': e.stage,
                'reason': e.detail,
                'affected_ids': [],
                'operations': [r.data for r in e.partial_results],  # 已回滚
                'audit_chain': [],
                'commit_count': len(e.partial_results),
            }
        except Exception as e:
            logger.error(f"[UnitOfWork.M5.5] unexpected error: {e}", exc_info=True)
            return {
                'success': False,
                'transaction_id': transaction_id,
                'rolled_back': True,
                'failed_at': 'unexpected',
                'reason': str(e),
                'affected_ids': [],
                'operations': [r.data for r in self._results],
                'audit_chain': [],
                'commit_count': 0,
            }

    def _resolve_placeholders(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """解析 '@uow.last_id' / '@uow.last_<entity>_id' 占位符。"""
        if not data:
            return data
        result: Dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, str):
                m = _PLACEHOLDER_RE.search(v)
                if m:
                    placeholder = m.group(1)
                    if placeholder == 'last_id':
                        actual = self._last_id
                    else:
                        entity_type = m.group(2)
                        actual = self._last_ids.get(entity_type)
                    if actual is None:
                        logger.warning(
                            f"[UnitOfWork.M5.5] placeholder @{placeholder} not resolved "
                            f"(no previous operation returned id)"
                        )
                        result[k] = v
                    else:
                        # 整个字段值就是占位符 → 替换；否则拼接
                        if v == f'@uow.{placeholder}':
                            result[k] = actual
                        else:
                            result[k] = v.replace(f'@uow.{placeholder}', str(actual))
                else:
                    result[k] = v
            else:
                result[k] = v
        return result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False
        if self._operations and not self._txn_started:
            raise RuntimeError(
                "UnitOfWork: must call commit() before exiting 'with' block"
            )
        return False
