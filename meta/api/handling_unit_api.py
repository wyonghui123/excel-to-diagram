# -*- coding: utf-8 -*-
"""包装容器作业 API（P6a-2 / v218）

    GET  /api/v1/handling-units                       待封列表
    GET  /api/v1/handling-units/scan                  扫码预检
    GET  /api/v1/handling-units/<hu_id>/contents      容器内容
    POST /api/v1/handling-units/<hu_id>/seal          封箱
    POST /api/v1/handling-units/<hu_id>/unseal        解封
    POST /api/v1/handling-units/batch-seal            批量封箱

口径:
  · 预检与真封共用 HandlingUnitService.seal_check，规则不复制到前端。
  · 批量封箱逐箱独立事务：单箱失败不回滚已成功的箱子。
  · 读接口沿用 handling_unit:handling_unit_read；封箱 / 解封各自独立权限。
  · 三张 HU 表未就绪时列表返回空、扫码 404（不阻断页面渲染）。
"""

import logging
from typing import Any, Dict, List, Optional

from flask import Blueprint, request

from meta.api._response_contract import error_response, ok
from meta.services.auth_middleware import require_permission
from meta.services.handling_unit_service import (
    HandlingUnitError,
    HandlingUnitService,
    hu_schema_ready,
)

logger = logging.getLogger(__name__)

handling_unit_bp = Blueprint(
    'handling_unit_ops', __name__, url_prefix='/api/v1/handling-units')

_service: Optional[HandlingUnitService] = None

_RULE_STATUS = {
    'HU_NOT_FOUND': 404,
    'HU_STATUS_INVALID': 409,
    'HU_CONTENT_EMPTY': 409,
    'HU_CHILD_STATUS_INVALID': 409,
    'HU_CONTENT_LOCATION_MISMATCH': 409,
    'HU_LOCATION_MISSING': 409,
    'HU_ORG_MISMATCH': 409,
}


def init_handling_unit_service(data_source=None) -> HandlingUnitService:
    """测试传临时数据源；生产懒取 meta 库。"""
    global _service
    if data_source is not None:
        _service = HandlingUnitService(data_source)
    elif _service is None:
        from meta.core.datasource import get_data_source
        from meta.core.db_path import get_meta_db_path
        data_source = get_data_source('sqlite', database=get_meta_db_path())
        _service = HandlingUnitService(data_source)
    return _service


def _get_service() -> HandlingUnitService:
    init_handling_unit_service()
    return _service


def _handling_error(e: HandlingUnitError):
    status = _RULE_STATUS.get(e.rule or '', 400)
    details = {'field': e.field_name} if e.field_name else None
    return error_response(str(e), code=e.rule or 'HU_INVALID',
                          status=status, details=details)


def _int_arg(name: str, default: Optional[int] = None) -> Optional[int]:
    raw = request.args.get(name)
    if raw in (None, ''):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _hu_row(service: HandlingUnitService, hu_id: int) -> Optional[Dict[str, Any]]:
    rows = service.ds.query(
        'SELECT * FROM handling_units WHERE id = ?', [hu_id])
    return rows[0] if rows else None


# ----------------------------------------------------------------------
# 列表
# ----------------------------------------------------------------------
@handling_unit_bp.route('', methods=['GET'])
@require_permission('handling_unit:handling_unit_read')
def list_handling_units():
    service = _get_service()
    if not hu_schema_ready(service.ds):
        return ok({'items': [], 'total': 0, 'page': 1, 'page_size': 50})

    status = request.args.get('status', 'open') or 'open'
    org_id = _int_arg('org_id')
    location_id = _int_arg('location_id')
    hu_no = (request.args.get('hu_no') or '').strip()
    page = max(1, _int_arg('page', 1) or 1)
    page_size = min(200, max(1, _int_arg('page_size', 50) or 50))

    where = ['status = ?']
    params: List[Any] = [status]
    if org_id is not None:
        where.append('org_id = ?')
        params.append(org_id)
    if location_id is not None:
        where.append('location_id = ?')
        params.append(location_id)
    if hu_no:
        where.append('hu_no LIKE ?')
        params.append('%' + hu_no + '%')

    clause = ' AND '.join(where)
    total_rows = service.ds.query(
        'SELECT COUNT(*) AS n FROM handling_units WHERE ' + clause, params)
    total = int(total_rows[0]['n']) if total_rows else 0
    items = service.ds.query(
        'SELECT * FROM handling_units WHERE %s ORDER BY hu_no, id '
        'LIMIT ? OFFSET ?' % clause,
        params + [page_size, (page - 1) * page_size])
    return ok({'items': items, 'total': total,
               'page': page, 'page_size': page_size})


# ----------------------------------------------------------------------
# 扫码预检
# ----------------------------------------------------------------------
@handling_unit_bp.route('/scan', methods=['GET'])
@require_permission('handling_unit:handling_unit_read')
def scan_handling_unit():
    service = _get_service()
    if not hu_schema_ready(service.ds):
        return error_response('包装容器表未就绪', code='HU_NOT_FOUND',
                              status=404)
    hu_no = (request.args.get('hu_no') or '').strip()
    if not hu_no:
        return error_response('hu_no 不能为空', code='HU_INVALID_PARAM',
                              status=400)
    org_id = _int_arg('org_id')
    try:
        data = service.hu_contents(hu_no, org_id, mode='direct')
    except HandlingUnitError as e:
        return _handling_error(e)

    hu = data.get('hu') or {}
    items = data.get('items') or []
    child_ids = [row.get('child_hu_id') for row in items
                 if row.get('content_type') == 'hu' and row.get('child_hu_id')]
    children: List[Dict[str, Any]] = []
    if child_ids:
        placeholders = ', '.join('?' for _ in child_ids)
        children = service.ds.query(
            'SELECT id, hu_no, hu_type, status FROM handling_units '
            'WHERE id IN (%s) ORDER BY id' % placeholders, child_ids)

    check = service.seal_check(hu['id'])
    return ok({
        'hu': hu,
        'contents': items,
        'children': children,
        'checks': {'can_seal': not check['blockers'],
                   'blockers': check['blockers']},
    })


# ----------------------------------------------------------------------
# 容器内容
# ----------------------------------------------------------------------
@handling_unit_bp.route('/<int:hu_id>/contents', methods=['GET'])
@require_permission('handling_unit:handling_unit_read')
def get_hu_contents(hu_id: int):
    service = _get_service()
    mode = request.args.get('mode', 'direct') or 'direct'
    if mode not in ('direct', 'exploded'):
        return error_response('mode 只能是 direct / exploded',
                              code='HU_INVALID_PARAM', status=400)
    row = _hu_row(service, hu_id)
    if row is None:
        return error_response('包装容器不存在：%s' % hu_id,
                              code='HU_NOT_FOUND', status=404)
    try:
        data = service.hu_contents(row['hu_no'], row.get('org_id'), mode=mode)
    except HandlingUnitError as e:
        return _handling_error(e)
    return ok(data)


# ----------------------------------------------------------------------
# 封箱 / 解封
# ----------------------------------------------------------------------
@handling_unit_bp.route('/<int:hu_id>/seal', methods=['POST'])
@require_permission('handling_unit:handling_unit_seal')
def seal_handling_unit(hu_id: int):
    service = _get_service()
    try:
        result = service.seal(hu_id)
    except HandlingUnitError as e:
        return _handling_error(e)
    except Exception:  # noqa: BLE001
        logger.exception('[handling_unit] 封箱失败: id=%s', hu_id)
        return error_response('封箱失败', code='HU_INTERNAL_ERROR', status=500)
    return ok(result)


@handling_unit_bp.route('/<int:hu_id>/unseal', methods=['POST'])
@require_permission('handling_unit:handling_unit_unseal')
def unseal_handling_unit(hu_id: int):
    service = _get_service()
    try:
        result = service.unseal(hu_id)
    except HandlingUnitError as e:
        return _handling_error(e)
    except Exception:  # noqa: BLE001
        logger.exception('[handling_unit] 解封失败: id=%s', hu_id)
        return error_response('解封失败', code='HU_INTERNAL_ERROR', status=500)
    return ok(result)


# ----------------------------------------------------------------------
# 批量封箱
# ----------------------------------------------------------------------
@handling_unit_bp.route('/batch-seal', methods=['POST'])
@require_permission('handling_unit:handling_unit_seal')
def batch_seal_handling_units():
    service = _get_service()
    payload = request.get_json(silent=True) or {}
    raw = payload.get('hu_ids')
    if not isinstance(raw, list) or not raw:
        return error_response('hu_ids 必须是非空数组',
                              code='HU_INVALID_PARAM', status=400)
    if len(raw) > 50:
        return error_response('单次最多 50 箱', code='HU_INVALID_PARAM',
                              status=400)
    hu_ids: List[int] = []
    for value in raw:
        try:
            hu_ids.append(int(value))
        except (TypeError, ValueError):
            return error_response('hu_ids 只能包含整数',
                                  code='HU_INVALID_PARAM', status=400)

    results: List[Dict[str, Any]] = []
    for hu_id in hu_ids:
        try:
            service.seal(hu_id)
            results.append({'hu_id': hu_id, 'ok': True})
        except HandlingUnitError as e:
            results.append({'hu_id': hu_id, 'ok': False,
                            'rule': e.rule or 'HU_INVALID',
                            'message': str(e)})
        except Exception as e:  # noqa: BLE001
            logger.exception('[handling_unit] 批量封箱失败: id=%s', hu_id)
            results.append({'hu_id': hu_id, 'ok': False,
                            'rule': 'HU_INTERNAL_ERROR', 'message': str(e)})

    sealed = sum(1 for row in results if row['ok'])
    return ok({'total': len(results), 'sealed': sealed,
               'failed': len(results) - sealed, 'items': results})
