# -*- coding: utf-8 -*-
"""库存库龄只读 API（P8 §5.4 读模型的薄路由）。

    GET /api/v1/inventory-aging/report   库龄分布（按余额行分桶）
    GET /api/v1/inventory-aging/detail   单键逐层重放（精确钻取）

口径:
  · 不新增 View BO：余额行明细复用既有 /api/v1/inventory_balances
    （first_received_date 已自动生成 date_range 过滤器）；本蓝图只承载
    SQL 视图表达不了的运行时参数（as_of / bucket_edges / summary / 逐层重放）。
  · 权限复用 inventory_balance:read，不新增权限码。
  · 只读：无写路由；口径与 InventoryAgingService 单一实现，不在 SQL 里重写。
"""

import logging
from typing import Any, List, Optional

from flask import Blueprint, request

from meta.api._response_contract import error_response, ok
from meta.services.auth_middleware import require_permission
from meta.services.inventory_aging_service import ERROR_DATE_INVALID, InventoryAgingService
from meta.services.inventory_guard_service import InventoryError

logger = logging.getLogger(__name__)

inventory_aging_bp = Blueprint(
    'inventory_aging', __name__, url_prefix='/api/v1/inventory-aging')

READ_PERMISSION = 'inventory_balance:read'

_service: Optional[InventoryAgingService] = None


def init_service(data_source=None) -> InventoryAgingService:
    """测试传内存 / 临时数据源；生产懒取 meta 库（路径走 get_meta_db_path）。"""
    global _service
    if data_source is not None:
        _service = InventoryAgingService(data_source)
    elif _service is None:
        from meta.core.datasource import get_data_source
        from meta.core.db_path import get_meta_db_path
        data_source = get_data_source('sqlite', database=get_meta_db_path())
        _service = InventoryAgingService(data_source)
    return _service


def _get_service() -> InventoryAgingService:
    init_service()
    return _service


def _arg_int(name: str) -> Optional[int]:
    value = request.args.get(name)
    if value is None or str(value).strip() == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise InventoryError(
            'INV_AGING_PARAM_INVALID', '查询参数必须为整数',
            {'field': name, 'value': value})


def _arg_bool(name: str) -> bool:
    return str(request.args.get(name, '')).strip().lower() in (
        '1', 'true', 'yes', 'y')


def _arg_edges() -> Optional[List[int]]:
    raw = request.args.get('bucket_edges')
    if raw is None or not str(raw).strip():
        return None
    parts = []
    for piece in str(raw).split(','):
        piece = piece.strip()
        if not piece:
            continue
        if not piece.isdigit():
            raise InventoryError(
                ERROR_DATE_INVALID, 'bucket_edges 只能包含正整数',
                {'bucket_edges': raw})
        parts.append(int(piece))
    return parts


def _aging_error(error: InventoryError):
    """参数类错误统一 400（组织缺失 / 日期非法 / 参数类型非法）。"""
    return error_response(error.message, code=error.code, status=400,
                          details=error.details or None)


@inventory_aging_bp.route('/report', methods=['GET'])
@require_permission(READ_PERMISSION)
def inventory_aging_report():
    try:
        data = _get_service().report(
            org_id=_arg_int('org_id'),
            as_of=request.args.get('as_of'),
            location_id=_arg_int('location_id'),
            item_id=_arg_int('item_id'),
            batch_id=_arg_int('batch_id'),
            stock_status=request.args.get('stock_status'),
            group_by=request.args.get('group_by', 'balance'),
            bucket_edges=_arg_edges(),
            include_zero=_arg_bool('include_zero'))
    except InventoryError as error:
        return _aging_error(error)
    except Exception as error:  # noqa: BLE001 - 只读聚合失败不放大成 500 细节
        logger.exception('[inventory-aging] 库龄报表失败: args=%s',
                         dict(request.args))
        return error_response('库龄报表读取失败', code='INV_AGING_QUERY_ERROR',
                              status=500, details=str(error))
    return ok(data)


@inventory_aging_bp.route('/detail', methods=['GET'])
@require_permission(READ_PERMISSION)
def inventory_aging_detail():
    try:
        data = _get_service().detail(
            org_id=_arg_int('org_id'),
            location_id=_arg_int('location_id'),
            item_id=_arg_int('item_id'),
            batch_id=_arg_int('batch_id'),
            stock_status=request.args.get('stock_status') or 'unrestricted',
            stock_segment_type=(request.args.get('stock_segment_type')
                                or 'owned'),
            project_id=_arg_int('project_id'),
            project_task_id=_arg_int('project_task_id'),
            sales_order_line_id=_arg_int('sales_order_line_id'),
            owner_party_id=_arg_int('owner_party_id'),
            as_of=request.args.get('as_of'))
    except InventoryError as error:
        return _aging_error(error)
    except Exception as error:  # noqa: BLE001
        logger.exception('[inventory-aging] 库龄明细失败: args=%s',
                         dict(request.args))
        return error_response('库龄明细读取失败', code='INV_AGING_QUERY_ERROR',
                              status=500, details=str(error))
    return ok(data)
