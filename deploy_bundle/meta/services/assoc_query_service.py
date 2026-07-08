# -*- coding: utf-8 -*-
"""
AssocQueryService（QE-2026-06-v2）

关联查询的统一入口（v2 路径）。

v1 路径：association_engine._query_m2m / _query_reverse_m2m / _query_reference /
         _query_composition 各自手写 SQL
v2 路径：AssocQueryService → UnifiedQueryFacade → QueryService（v3 SSOT）

M2 阶段：
- 新增本文件（不动 association_engine._query_*）
- 提供 list_associated() / list_reverse_associated() / list_referenced() 三个方法
- 内部统一走 UnifiedQueryFacade
- 默认仍走 v1 路径（向后兼容）

设计原则：
- 对外接口与 _query_* 完全等价（返回 items + total）
- 不引入新的 SQL 模板（全部复用 v3 QueryBuilder 能力）
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from meta.core.unified_query_facade import UnifiedQueryFacade
from meta.core.unified_query_protocol import (
    UnifiedQueryRequest,
    QueryProtocolError,
)

logger = logging.getLogger(__name__)


class AssocQueryService:
    """Association query service backed by UnifiedQueryFacade.

    接收与 association_engine 完全等价的参数（src_id / association metadata），
    返回标准 dict 格式（items + total）。
    """

    def __init__(self, facade: Optional[UnifiedQueryFacade] = None):
        self.facade = facade or UnifiedQueryFacade()

    def list_associated(
        self,
        object_type: str,
        target_entity: str,
        src_id: Any,
        through: str,
        source_key: str,
        target_key: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """查询目标实体的关联记录（many_to_many）。

        [M3 2026-06-05] 走 v2 路径：对 target_entity 执行 list 查询，
        通过 EXISTS 子查询过滤出与 src_id 通过 through 表关联的记录。
        SQL 形态: target.id IN (SELECT target_key FROM through WHERE source_key = src_id)
        """
        try:
            req = UnifiedQueryRequest.from_url_args(target_entity, params or {})
        except ValueError as e:
            raise QueryProtocolError(
                code='invalid_params',
                message=f'invalid assoc query params: {e}',
                detail={'object_type': target_entity},
            ) from e

        # [M3] 注入关联 EXISTS 子查询
        # 关键: 子查询必须与主查询关联（correlated subquery），
        # 否则 EXISTS 对每行都返回 TRUE（参数只检查一次，过滤失效）。
        # SQL 形态: WHERE EXISTS (SELECT 1 FROM through WHERE source_key = ? AND target_key = bo.id)
        if (
            src_id is not None
            and through
            and source_key
            and target_key
        ):
            from meta.core.unified_query_protocol import is_safe_field
            if is_safe_field(target_key) and is_safe_field(through):
                assoc_subquery = (
                    f"SELECT 1 FROM {through} "
                    f"WHERE {source_key} = ? AND {target_key} = bo.id"
                )
                req.assoc_subqueries.append({
                    'field': 'id',
                    'subquery_sql': assoc_subquery,
                    'subquery_params': [src_id],
                })
                logger.info(
                    f"[AssocQueryService.M3] list_associated: src={object_type}#{src_id} "
                    f"target={target_entity} through={through} ({source_key}->{target_key})"
                )

        try:
            resp = self.facade.execute(req)
        except Exception as e:
            logger.exception(f"[AssocQueryService.list_associated] error: {e}")
            return {'items': [], 'total': 0, 'error': str(e)}

        return {
            'items': resp.items,
            'total': resp.total,
            'page': resp.page,
            'page_size': resp.page_size,
            'trace_id': resp.trace_id,
        }

    def list_reverse_associated(
        self,
        object_type: str,
        target_entity: str,
        src_id: Any,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """查询反向关联记录（reverse_many_to_many，one_to_many）。

        M3 阶段：直接复用 list_associated（v2 路径无 reverse 区分）。
        """
        return self.list_associated(
            object_type=object_type,
            target_entity=target_entity,
            src_id=src_id,
            through='', source_key='', target_key='',
            params=params,
        )

    def list_referenced(
        self,
        object_type: str,
        target_entity: str,
        src_id: Any,
        source_key: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """查询引用关联记录（one_to_one / many_to_one）。

        M3 阶段：复用 list_associated。
        """
        return self.list_associated(
            object_type=object_type,
            target_entity=target_entity,
            src_id=src_id,
            through='', source_key=source_key, target_key='id',
            params=params,
        )


_default_assoc_service: Optional[AssocQueryService] = None


def get_assoc_query_service() -> AssocQueryService:
    """获取全局 AssocQueryService 实例（惰性构造）。"""
    global _default_assoc_service
    if _default_assoc_service is None:
        _default_assoc_service = AssocQueryService()
    return _default_assoc_service
