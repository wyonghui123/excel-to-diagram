# -*- coding: utf-8 -*-
"""工单执行入口 API（项目侧 G13）

    POST /api/v1/work-orders/<id>/start   开始作业

口径:
  · New → In Progress；`source_demand_type='project_task'` 的工单在同一事务内
    调用 `create_operation_tasks` 生成执行 tasks（幂等），其它来源不生成。
  · 桥接失败整体回滚，不出现「工单已开工但无任务」的半成品。
  · 权限沿用 `work_order:update`（与通用 BO 更新同一动作码）。
"""

import logging
from typing import Optional

from flask import Blueprint, request

from meta.api._response_contract import error_response, ok
from meta.services.auth_middleware import get_current_user, require_permission
from meta.services.work_order_execution_service import BridgeError
from meta.services.work_order_service import WorkOrderError, WorkOrderService

logger = logging.getLogger(__name__)

work_order_bp = Blueprint(
    'work_order_execution', __name__, url_prefix='/api/v1/work-orders')

_service: Optional[WorkOrderService] = None


def init_service(data_source=None) -> WorkOrderService:
    """测试传内存 / 临时数据源；生产懒取 meta 库（路径走 get_meta_db_path）。"""
    global _service
    if data_source is not None:
        _service = WorkOrderService(data_source)
    elif _service is None:
        from meta.core.datasource import get_data_source
        from meta.core.db_path import get_meta_db_path
        data_source = get_data_source('sqlite', database=get_meta_db_path())
        _service = WorkOrderService(data_source)
    return _service


def _get_service() -> WorkOrderService:
    init_service()
    return _service


def _actor() -> str:
    user = get_current_user() or {}
    return (user.get('username') or user.get('display_name')
            or str(user.get('user_id') or ''))


@work_order_bp.route('/<int:work_order_id>/start', methods=['POST'])
@require_permission('work_order:update')
def start_work_order(work_order_id):
    payload = request.get_json(silent=True) or {}
    service = _get_service()
    try:
        with service.ds.transaction():
            result = service.start_work_order(
                work_order_id,
                actor=_actor(),
                created_by=_actor(),
                executor_type=payload.get('executor_type') or 'human',
            )
    except BridgeError as e:
        return error_response(str(e), code=e.rule or 'BRIDGE_ERROR', status=400,
                              details=e.details or None)
    except WorkOrderError as e:
        status = 404 if e.rule == 'ST_NOT_FOUND' else 400
        return error_response(str(e), code=e.rule or 'INVALID_PARAMETER',
                              status=status,
                              details={'field': e.field_name} if e.field_name
                              else None)
    except Exception as e:  # noqa: BLE001
        logger.exception('[work_order] 开始作业失败: id=%s', work_order_id)
        return error_response('开始作业失败', code='WORK_ORDER_START_ERROR',
                              status=500, details=str(e))
    return ok(result)
