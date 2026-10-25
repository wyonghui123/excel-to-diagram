# -*- coding: utf-8 -*-
"""销售订单重新取价端点

    POST /api/v1/sales-orders/<order_id>/reprice

语义（§3.7 触发时点 4）:
    无视 `price_source='manual'`，全部开放行重取；成功后单价回写、
    `price_source` 复位为 `rate_table`，并重算行金额与抬头合计。

错误映射:
    404  订单不存在
    409  订单非草稿（W1-R1：取价只在草稿态）
    422  取价链路不可完成（价目表/过程缺失等）—— 由服务返回失败原因码

权限：不新增对象；挂在 `sales_order` 的 update（与行展开端点同一口径）。
"""

import logging
from typing import Optional

from flask import Blueprint

from meta.api._response_contract import error_response, ok
from meta.services.auth_middleware import login_required
from meta.services.sales_order_pricing_service import (
    SalesOrderPricingError,
    SalesOrderPricingService,
)

logger = logging.getLogger(__name__)

sales_order_pricing_bp = Blueprint(
    'sales_order_pricing', __name__, url_prefix='/api/v1/sales-orders')

_NOT_FOUND_RULES = frozenset({'order_not_found'})
_CONFLICT_RULES = frozenset({'order_not_draft'})

_service: Optional[SalesOrderPricingService] = None


def init_service(data_source=None) -> SalesOrderPricingService:
    """测试传内存数据源；生产懒取 meta 库（路径必须走 get_meta_db_path）。"""
    global _service
    if data_source is not None:
        _service = SalesOrderPricingService(data_source)
    elif _service is None:
        from meta.core.datasource import get_data_source
        from meta.core.db_path import get_meta_db_path
        data_source = get_data_source('sqlite', database=get_meta_db_path())
        _service = SalesOrderPricingService(data_source)
    return _service


def _get_service() -> SalesOrderPricingService:
    init_service()
    return _service


def _fail(exc: Exception):
    if isinstance(exc, SalesOrderPricingError):
        if exc.rule in _NOT_FOUND_RULES:
            status = 404
        elif exc.rule in _CONFLICT_RULES:
            status = 409
        else:
            status = 422
        return error_response(str(exc), code=exc.rule or 'REPRICE_FAILED',
                              status=status,
                              details={'rule': exc.rule, 'field': exc.field_name})
    raise exc


@sales_order_pricing_bp.route('/<int:order_id>/reprice', methods=['POST'])
@login_required
def reprice_order(order_id: int):
    """重取整单单价（无视手工价标记）。"""
    try:
        data = _get_service().reprice_order(order_id, force=True, strict=True)
    except Exception as exc:  # noqa: BLE001 - 域内异常统一映射
        return _fail(exc)
    return ok(data)
