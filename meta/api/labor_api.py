# -*- coding: utf-8 -*-
"""工时回聚只读聚合 API（项目侧 G14 · Phase 3-2）

    GET /api/labor/project-tasks?project_id=&task_id=   任务级实际工时
    GET /api/labor/projects?project_id=                 项目级实际工时
    GET /api/labor/resources/utilization?resource_id=&start_date=&end_date=

口径:
  · 只读投影，全部读 `v_project_task_labor` / `v_project_labor` /
    `v_resource_labor_daily`，不落汇总表、不重算金额。
  · 产能利用率复用 `LaborService.resource_utilization()`（D16：不在 SQL 里
    重写日历 / 班次口径）。
  · 权限沿用 `project:time_entry_read`（v182 已落码）。
  · 响应统一走 `_response_contract`，不直接调用 jsonify。
"""

import logging
from datetime import date
from typing import Optional

from flask import Blueprint, request

from meta.api._response_contract import error_response, ok, ok_list
from meta.services.auth_middleware import require_permission
from meta.services.labor_service import LaborError, LaborService

logger = logging.getLogger(__name__)

labor_bp = Blueprint('labor', __name__, url_prefix='/api/v1/labor')

_service: Optional[LaborService] = None


def init_service(data_source=None) -> LaborService:
    """测试传内存 / 临时数据源；生产懒取 meta 库（路径走 get_meta_db_path）。"""
    global _service
    if data_source is not None:
        _service = LaborService(data_source)
    elif _service is None:
        from meta.core.datasource import get_data_source
        from meta.core.db_path import get_meta_db_path
        data_source = get_data_source('sqlite', database=get_meta_db_path())
        _service = LaborService(data_source)
    return _service


def _get_service() -> LaborService:
    init_service()
    return _service


@labor_bp.route('/project-tasks', methods=['GET'])
@require_permission('project:time_entry_read')
def list_project_task_labor():
    project_id = request.args.get('project_id', type=int)
    task_id = request.args.get('task_id', type=int)
    try:
        items = _get_service().project_task_labor(
            project_id=project_id, task_id=task_id)
    except LaborError as e:
        return _labor_error(e)
    except Exception as e:  # noqa: BLE001 - 只读查询失败不放大成 500 细节
        logger.exception('[labor] 任务级工时读取失败: project_id=%s task_id=%s',
                         project_id, task_id)
        return error_response('任务级工时读取失败', code='LABOR_QUERY_ERROR',
                              status=500, details=str(e))
    return ok_list(items, total=len(items), page=1, page_size=len(items) or 1)


@labor_bp.route('/projects', methods=['GET'])
@require_permission('project:time_entry_read')
def list_project_labor():
    project_id = request.args.get('project_id', type=int)
    try:
        items = _get_service().project_labor(project_id=project_id)
    except LaborError as e:
        return _labor_error(e)
    except Exception as e:  # noqa: BLE001
        logger.exception('[labor] 项目级工时读取失败: project_id=%s', project_id)
        return error_response('项目级工时读取失败', code='LABOR_QUERY_ERROR',
                              status=500, details=str(e))
    return ok_list(items, total=len(items), page=1, page_size=len(items) or 1)


@labor_bp.route('/resources/utilization', methods=['GET'])
@require_permission('project:time_entry_read')
def get_resource_utilization():
    resource_id = request.args.get('resource_id', type=int)
    if resource_id is None:
        return error_response('resource_id 必填', code='INVALID_PARAMETER',
                              status=400)

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if start_date is None or end_date is None:
        today = date.today().isoformat()
        start_date = start_date or end_date or today
        end_date = end_date or start_date

    try:
        data = _get_service().resource_utilization(
            resource_id, start_date, end_date)
    except LaborError as e:
        return _labor_error(e)
    except Exception as e:  # noqa: BLE001
        logger.exception('[labor] 资源利用率读取失败: resource_id=%s', resource_id)
        return error_response('资源利用率读取失败', code='LABOR_QUERY_ERROR',
                              status=500, details=str(e))
    return ok(data)


def _labor_error(error: LaborError):
    status = 404 if error.rule == 'RESOURCE_NOT_FOUND' else 400
    return error_response(str(error), code=error.rule or 'INVALID_PARAMETER',
                          status=status,
                          details={'field': error.field_name} if error.field_name
                          else None)
