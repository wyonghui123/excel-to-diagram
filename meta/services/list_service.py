# -*- coding: utf-8 -*-
"""
ListService（QE-2026-06-v2）

封装 v3 统一查询 Facade 的 list/query 路径服务。

v1 路径：persistence_interceptor._do_list 手写 SQL
v2 路径：ListService → UnifiedQueryFacade → QueryService（v3 SSOT）

M2 阶段：
- 新增本文件（不动 _do_list）
- 任何 _do_list 调用方都可以用 ListService 作为替代路径
- 默认仍走 v1 路径（向后兼容）
- 后续 M3 阶段：把 _do_list 内部切到 ListService

设计原则：
- 零依赖破坏：v1 调用方继续可用
- 复用 SSOT：v2 路径只编排，不重新实现 SQL
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Optional

from meta.core.unified_query_protocol import (
    UnifiedQueryRequest,
    QueryProtocolError,
)
from meta.core.unified_query_facade import UnifiedQueryFacade

logger = logging.getLogger(__name__)


class ListService:
    """List service backed by UnifiedQueryFacade.

    单一入口 `list(object_type, params)` 接收 URL 参数风格的 dict，
    返回 dict 形式的列表结果（items / total / page / page_size）。

    与 _do_list 完全等价的对外接口（除字段名差异），便于替换。
    """

    def __init__(self, facade: Optional[UnifiedQueryFacade] = None):
        self.facade = facade or UnifiedQueryFacade()

    def list(self, object_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行列表查询（v2 路径）。

        Args:
            object_type: BO id（如 'user', 'user_group'）
            params: URL 参数（_order_by / _limit / _offset / page / page_size /
                search / keyword / 任意 filter 字段）

        Returns:
            {
                'items': [...],
                'total': int,
                'page': int,
                'page_size': int,
                'total_pages': int,
                'trace_id': str,
                'elapsed_ms': float,
            }
        """
        try:
            req = UnifiedQueryRequest.from_url_args(object_type, params or {})
        except ValueError as e:
            # 协议层校验失败：抛 400-friendly 异常，由调用方决定如何处理
            raise QueryProtocolError(
                code='invalid_params',
                message=f'invalid query params: {e}',
                detail={'object_type': object_type, 'params_keys': list((params or {}).keys())},
            ) from e

        try:
            resp = self.facade.execute(req)
        except QueryProtocolError:
            raise
        except Exception as e:
            logger.exception(f"[ListService] list error: {e}")
            return {
                'items': [],
                'total': 0,
                'page': req.page,
                'page_size': req.page_size,
                'total_pages': 0,
                'error': str(e),
            }

        return {
            'items': resp.items,
            'total': resp.total,
            'page': resp.page,
            'page_size': resp.page_size,
            'total_pages': resp.total_pages,
            'trace_id': resp.trace_id,
            'elapsed_ms': resp.elapsed_ms,
            'next_cursor': resp.next_cursor,
            'prev_cursor': resp.prev_cursor,
        }


# 全局默认实例（惰性）
_default_list_service: Optional[ListService] = None


def get_list_service() -> ListService:
    """获取全局 ListService 实例（惰性构造）。"""
    global _default_list_service
    if _default_list_service is None:
        _default_list_service = ListService()
    return _default_list_service
