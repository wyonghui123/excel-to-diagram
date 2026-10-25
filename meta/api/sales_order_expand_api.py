# -*- coding: utf-8 -*-
"""销售订单行结构展开 API（P1）
================================

    POST /api/v1/sales-orders/<order_id>/lines/<line_id>/expand

请求体:
    selections        选填  结构行 id 集合或 {结构行 id: 是否选中}
    quantities        选填  {结构行 id: 显式数量}，仅可选行生效
    attribute_values  选填  {特征编码: 取值}，仅模型结构生效
    pricing_mode      选填  bundle_price / component_price / base_plus_option
    as_of             选填  结构生效基准日，缺省取订单日期
    max_depth         选填  结构解析深度，缺省 20

[分层] 本层只做参数校验与错误映射，展开规则在 `sales_order_expand_service`：
E1 前提 / E2 结构唯一 / E3 求解 / E4 落行 / E5 定价归属 / E6 服务行 /
E7 不可重展开 / E8 单事务。

[错误映射] 域内只有 `SalesOrderExpandError` 一族，按语义分档：

    404  订单 / 订单行不存在
    400  请求参数与行或结构内容矛盾（定价模式非法、行无物料）
    409  状态或幂等冲突（订单非草稿、行已展开、行非开放、子行再展开）
    422  结构 / 配置求解不可满足（无 sales 生效版本、多版本歧义、求解冲突）

权限：不新增对象，展开挂 `sales_order_line` 的 update（v121 已落 10 条双段式码）。
"""

import logging
from typing import Any, Dict, Optional

from flask import Blueprint, request

from meta.api._response_contract import error_response, ok
from meta.services.auth_middleware import login_required
from meta.services.sales_order_expand_service import (
    SalesOrderExpandError,
    SalesOrderExpandService,
)

logger = logging.getLogger(__name__)

sales_order_expand_bp = Blueprint(
    'sales_order_expand', __name__, url_prefix='/api/v1/sales-orders')

_NOT_FOUND_RULES = frozenset({'order_not_found', 'line_not_found'})

_CLIENT_RULES = frozenset({'pricing_mode_invalid', 'line_item_required'})

_CONFLICT_RULES = frozenset({
    'expand_order_not_draft', 'line_already_expanded',
    'line_not_open', 'line_is_component',
})

_service: Optional[SalesOrderExpandService] = None


def init_service(data_source=None) -> SalesOrderExpandService:
    """测试传内存数据源；生产懒取 meta 库（路径必须走 get_meta_db_path）。"""
    global _service
    if data_source is not None:
        _service = SalesOrderExpandService(data_source)
    elif _service is None:
        from meta.core.datasource import get_data_source
        from meta.core.db_path import get_meta_db_path
        data_source = get_data_source('sqlite', database=get_meta_db_path())
        _service = SalesOrderExpandService(data_source)
    return _service


def _get_service() -> SalesOrderExpandService:
    init_service()
    return _service


class _ParamError(Exception):
    """请求本身不合法（400）。"""


def _json_body() -> Dict[str, Any]:
    body = request.get_json(force=True, silent=True)
    return body if isinstance(body, dict) else {}


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _opt_int(body: Dict[str, Any], key: str, default: int) -> int:
    value = body.get(key)
    if _is_blank(value):
        return default
    if isinstance(value, bool):
        raise _ParamError(f'{key} 必须为整数')
    try:
        return int(value)
    except (TypeError, ValueError):
        raise _ParamError(f'{key} 必须为整数')


def _fail(exc: Exception):
    if isinstance(exc, _ParamError):
        return error_response(str(exc), code='INVALID_PARAM', status=400)
    if isinstance(exc, SalesOrderExpandError):
        if exc.rule in _NOT_FOUND_RULES:
            status = 404
        elif exc.rule in _CLIENT_RULES:
            status = 400
        elif exc.rule in _CONFLICT_RULES:
            status = 409
        else:
            status = 422
        return error_response(str(exc), code=exc.rule or 'EXPAND_FAILED',
                              status=status,
                              details={'rule': exc.rule, 'field': exc.field_name})
    raise exc


@sales_order_expand_bp.route('/<int:order_id>/lines/<int:line_id>/expand',
                             methods=['POST'])
@login_required
def expand_line(order_id: int, line_id: int):
    """把一条父订单行按销售用途结构展开成子行。"""
    try:
        body = _json_body()
        data = _get_service().expand(
            order_id,
            line_id,
            selections=body.get('selections') or None,
            quantities=body.get('quantities') or None,
            attribute_values=body.get('attribute_values') or None,
            pricing_mode=body.get('pricing_mode') or None,
            as_of=body.get('as_of') or None,
            max_depth=_opt_int(body, 'max_depth', 20),
        )
    except Exception as exc:  # noqa: BLE001 - 域内异常统一映射
        return _fail(exc)
    return ok(data)
