# -*- coding: utf-8 -*-
"""项目 360 只读聚合 API（项目侧 P1 · AC-03）

    GET /api/v1/projects/<project_id>/overview?limit=20

返回:
    {
      success: true,
      data: {
        project: {...},
        sales_orders: {items: [...], total: n},
        sales_order_lines: {items: [...], total: n},
        sales_order_schedules: {items: [...], total: n},
        readonly: true
      }
    }

口径:
  · 只读投影，金额只从 sales_order / line / schedule 读，不复制、不重算（I1）
  · 权限复用 `project:project_read`（v171 已落双段式码）
"""

import logging
from typing import Optional

from flask import Blueprint, request

from meta.api._response_contract import error_response, ok
from meta.services.auth_middleware import login_required
from meta.services.project_overview_service import (
    ProjectNotFound,
    ProjectOverviewService,
)

logger = logging.getLogger(__name__)

project_overview_bp = Blueprint(
    'project_overview', __name__, url_prefix='/api/v1/projects')

_service: Optional[ProjectOverviewService] = None


def init_service(data_source=None) -> ProjectOverviewService:
    """测试传内存 / 临时数据源；生产懒取 meta 库（路径必须走 get_meta_db_path）。"""
    global _service
    if data_source is not None:
        _service = ProjectOverviewService(data_source)
    elif _service is None:
        from meta.core.datasource import get_data_source
        from meta.core.db_path import get_meta_db_path
        data_source = get_data_source('sqlite', database=get_meta_db_path())
        _service = ProjectOverviewService(data_source)
    return _service


def _get_service() -> ProjectOverviewService:
    init_service()
    return _service


@project_overview_bp.route('/<int:project_id>/overview', methods=['GET'])
@login_required
def get_project_overview(project_id: int):
    limit = request.args.get('limit', 20, type=int)
    try:
        data = _get_service().overview(project_id, limit=limit or 20)
    except ProjectNotFound:
        return error_response('项目不存在', code='PROJECT_NOT_FOUND', status=404)
    except Exception as e:  # noqa: BLE001 - 只读投影失败不放大成 500 细节
        logger.exception('[project-overview] 聚合失败: project_id=%s', project_id)
        return error_response('项目聚合读取失败', code='PROJECT_OVERVIEW_ERROR',
                              status=500, details=str(e))
    return ok(data)
