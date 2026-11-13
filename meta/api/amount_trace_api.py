# -*- coding: utf-8 -*-
"""金额回溯 API（只读）
========================

端点：
    GET /api/v2/bo/<object_type>/<record_id>/amount-trace

统一四类单据（销售订单 / 采购订单 / 采购发票 / 销售发票）的金额回溯视图：
  · header：抬头存储值 vs 内核只读重算值（漂移）
  · lines：行存储值 / 重算值 / 公式 / 取价来源 / 定价步骤 / 税额口径
  · adjustments：调整事实（独立调整单 / 抬头折扣与附加费分摊）
  · recalc：是否允许显式重算及原因（状态门槛）

与 `rule-trace` 同构：只读、不落库、不写公式；算术口径由
`SalesOrderAmountService.preview_line / preview_order` 统一提供。
"""

import logging

from flask import Blueprint, request

from meta.api._response_contract import error_response, ok
from meta.api.decorators import require_permission
from meta.services.auth_middleware import login_required

logger = logging.getLogger(__name__)

amount_trace_bp = Blueprint('amount_trace_api', __name__, url_prefix='/api/v2/bo')


@amount_trace_bp.route('/<object_type>/<record_id>/amount-trace', methods=['GET'])
@login_required
@require_permission('amount:trace')
def get_amount_trace(object_type: str, record_id: str):
    """金额计算回溯（统一契约，四类单据共用）。"""
    try:
        record_pk = int(record_id)
    except (TypeError, ValueError):
        return error_response('id 必须是整数', status=400, error_code='INVALID_ID')

    try:
        from meta.api.bo_api import _check_single_bo_in_dim_scope

        if _check_single_bo_in_dim_scope(object_type, record_pk):
            # 不暴露记录存在性（与 bo_api 单条 get 口径一致）
            return error_response('记录不存在', status=404, error_code='NOT_FOUND')

        from meta.core.datasource import get_data_source
        from meta.core.db_path import get_meta_db_path
        from meta.services.amount_trace_service import AmountTraceService

        data = AmountTraceService(
            get_data_source('sqlite', database=get_meta_db_path())
        ).build(object_type, record_pk)
        if data is None:
            return error_response('记录不存在或不支持金额回溯', status=404,
                                  error_code='NOT_FOUND')
        return ok(data)
    except Exception as e:  # noqa: BLE001
        logger.exception('Failed to build amount trace for %s/%s: %s',
                         object_type, record_id, e)
        return error_response('生成金额回溯失败', status=500)


__all__ = ['amount_trace_bp']