# -*- coding: utf-8 -*-
"""
QueryAllowList（QE-M6-2026-06-v2）

[M6.1] Query 白名单机制。

设计原则：
- 按 entity_type 注册允许的 filter / sort / 字段集合
- 未注册或使用未授权字段 → 抛 QueryProtocolError
- 与 v3 UnifiedQueryFacade 入口集成（fail-fast）
- 与 v1/v2 路径不冲突（旧路径不强制校验）
- 向后兼容：默认全部放行（必须主动注册才校验）
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class EntityAllowList:
    """单实体白名单配置。"""

    entity_type: str
    # 允许的 filter 字段（含 op 模式）
    filter_fields: Set[str] = field(default_factory=set)
    # 允许的排序字段
    ordering_fields: Set[str] = field(default_factory=set)
    # 允许的 select 字段
    select_fields: Set[str] = field(default_factory=set)
    # 允许的 op 类型（默认 = 所有）
    allowed_ops: Set[str] = field(default_factory=lambda: {
        'eq', 'in', 'not_in', 'like', 'ilike', 'gte', 'lte',
        'gt', 'lt', 'ne', 'between', 'is_null', 'is_not_null',
        'func_year', 'func_month', 'func_day', 'date_diff',
        'regex', 'iregex', 'json',
    })
    # 限制最大 page_size
    max_page_size: int = 500
    # 限制最大结果集（防止 DoS）
    max_total_limit: int = 10000
    # 是否启用校验（默认 True，置 False 绕过）
    enabled: bool = True


class QueryAllowList:
    """全局白名单注册中心。"""

    def __init__(self):
        self._lists: Dict[str, EntityAllowList] = {}
        self.rejected_count = 0
        self.passed_count = 0

    def register(self, allow: EntityAllowList) -> None:
        """注册单个实体的白名单。"""
        self._lists[allow.entity_type] = allow
        logger.info(
            f"[QueryAllowList.M6.1] registered {allow.entity_type}: "
            f"filters={len(allow.filter_fields)}, orderings={len(allow.ordering_fields)}, "
            f"selects={len(allow.select_fields)}"
        )

    def unregister(self, entity_type: str) -> None:
        self._lists.pop(entity_type, None)

    def get(self, entity_type: str) -> Optional[EntityAllowList]:
        return self._lists.get(entity_type)

    def check(
        self,
        entity_type: str,
        filters: Optional[Dict[str, Any]] = None,
        ordering: str = '',
        page_size: int = 0,
        select: Optional[List[str]] = None,
    ) -> None:
        """校验查询是否在白名单内。失败抛 QueryProtocolError。

        注意：如果 entity_type 未注册，默认放行（向后兼容）。
        """
        # 延迟导入（避免循环依赖）
        from meta.core.unified_query_protocol import QueryProtocolError

        allow = self._lists.get(entity_type)
        if allow is None or not allow.enabled:
            self.passed_count += 1
            return

        # 1. filter 字段校验
        if filters:
            for field_name in filters.keys():
                if field_name not in allow.filter_fields and '*' not in allow.filter_fields:
                    self.rejected_count += 1
                    raise QueryProtocolError(
                        code='field_not_in_allowlist',
                        message=(
                            f"field '{field_name}' is not in query allow-list for "
                            f"'{entity_type}'"
                        ),
                        detail={
                            'entity_type': entity_type,
                            'field': field_name,
                            'allowed_sample': list(allow.filter_fields)[:5],
                        },
                    )
                # 校验 op
                fv = filters[field_name]
                op = fv.op if hasattr(fv, 'op') else 'eq'
                if op not in allow.allowed_ops:
                    self.rejected_count += 1
                    raise QueryProtocolError(
                        code='op_not_in_allowlist',
                        message=(
                            f"op '{op}' is not in allow-list for '{entity_type}'"
                        ),
                        detail={
                            'entity_type': entity_type,
                            'op': op,
                            'allowed': sorted(allow.allowed_ops),
                        },
                    )

        # 2. ordering 字段校验
        if ordering and allow.ordering_fields:
            for tok in [t.strip().lstrip('-') for t in ordering.split(',') if t.strip()]:
                if tok not in allow.ordering_fields and '*' not in allow.ordering_fields:
                    self.rejected_count += 1
                    raise QueryProtocolError(
                        code='ordering_not_in_allowlist',
                        message=(
                            f"ordering field '{tok}' is not in allow-list for "
                            f"'{entity_type}'"
                        ),
                        detail={
                            'entity_type': entity_type,
                            'field': tok,
                            'allowed': sorted(allow.ordering_fields),
                        },
                    )

        # 3. page_size 上限
        if page_size and page_size > allow.max_page_size:
            self.rejected_count += 1
            raise QueryProtocolError(
                code='page_size_exceeds_allowlist',
                message=(
                    f"page_size {page_size} exceeds max {allow.max_page_size} "
                    f"for '{entity_type}'"
                ),
                detail={
                    'entity_type': entity_type,
                    'requested': page_size,
                    'max': allow.max_page_size,
                },
            )

        # 4. select 字段校验
        if select and allow.select_fields:
            for field_name in select:
                if field_name not in allow.select_fields and '*' not in allow.select_fields:
                    self.rejected_count += 1
                    raise QueryProtocolError(
                        code='select_not_in_allowlist',
                        message=(
                            f"select field '{field_name}' is not in allow-list "
                            f"for '{entity_type}'"
                        ),
                        detail={
                            'entity_type': entity_type,
                            'field': field_name,
                            'allowed': sorted(allow.select_fields),
                        },
                    )

        self.passed_count += 1

    def stats(self) -> Dict[str, Any]:
        """DRE 上报。"""
        total = self.passed_count + self.rejected_count
        return {
            'registered_entities': len(self._lists),
            'passed': self.passed_count,
            'rejected': self.rejected_count,
            'rejection_rate': f'{(self.rejected_count / total) if total else 0:.2%}',
        }


# 全局默认实例
_default_allow_list: Optional[QueryAllowList] = None


def get_query_allow_list() -> QueryAllowList:
    global _default_allow_list
    if _default_allow_list is None:
        _default_allow_list = QueryAllowList()
    return _default_allow_list
