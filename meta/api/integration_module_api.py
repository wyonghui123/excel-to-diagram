# -*- coding: utf-8 -*-
"""集成模块 API（M2）：连接管理 + 投递运行面。

依据: docs/specs/spec-integration-module-2026-11-15.md
  §6 FR-1（连接 CRUD）/ FR-2（连通性测试）/ FR-7（in/out messages 运行面）
  §8 UI 三视图（配置面 / 运行面 / 交付面）
  §10 AC-1（secret 不回显）/ AC-7（删除被引用连接 → 409）

边界:
  · 只读投递事实（`notification_deliveries`），不新建第二套投递表 / 收件箱；
  · 手动重试复用 `notification_api` 的归属校验与 5 秒去抖，不复制第二份实现；
  · 连接配置与订阅解绑由调用方完成，删除前置检查只返回 409。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, List, Optional

from flask import Blueprint, request, send_file
from werkzeug.utils import secure_filename

from meta.api._response_contract import error_response, ok, ok_list
from meta.api.notification_api import (
    RETRY_DEBOUNCE_SECONDS,
    _can_retry_all,
    _current_user_id,
    _retry_debounce,
    _same_user,
)
from meta.services.auth_middleware import get_current_user, is_admin, login_required
from meta.services.import_staging_service import ImportStagingService
from meta.services.integration_connection_service import (
    IntegrationConnectionConflict,
    IntegrationConnectionError,
    IntegrationConnectionService,
)

logger = logging.getLogger(__name__)

integration_module_bp = Blueprint('integration_module', __name__)

ds = None

DELIVERY_TABLE = 'notification_deliveries'

#: 可手动重试的投递状态（delivered/sending 不动）
RETRYABLE_STATUSES = ('failed', 'skipped')

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 20


def init_integration_module_api(datasource) -> None:
    global ds
    ds = datasource


def _service() -> IntegrationConnectionService:
    return IntegrationConnectionService(ds)


def _require_service():
    if not ds:
        return error_response('Service not initialized', status=500)
    return None


def _require_admin():
    if not is_admin(get_current_user()):
        return error_response('您没有执行此操作的权限', status=403)
    return None


def _int_arg(name: str, default: Optional[int] = None,
             minimum: Optional[int] = None,
             maximum: Optional[int] = None) -> Optional[int]:
    raw = request.args.get(name)
    if raw is None or raw == '':
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if minimum is not None:
        value = max(value, minimum)
    if maximum is not None:
        value = min(value, maximum)
    return value


def _bool_arg(name: str) -> Optional[bool]:
    raw = request.args.get(name)
    if raw is None or raw == '':
        return None
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


# ------------------------------------------------------------------ 连接配置
@integration_module_bp.route('/api/v2/integrations/connections', methods=['GET'])
@login_required
def list_connections():
    """连接列表（配置面）。"""
    denied = _require_service() or _require_admin()
    if denied:
        return denied
    try:
        rows = _service().list_connections(
            enabled=_bool_arg('enabled'),
            channel_type=request.args.get('channel_type') or None,
            keyword=request.args.get('keyword') or None,
        )
    except IntegrationConnectionError as exc:
        return error_response(str(exc), status=400)
    return ok_list(rows)


@integration_module_bp.route('/api/v2/integrations/connections', methods=['POST'])
@login_required
def create_connection():
    """新建连接。secret_ref 只接受引用，不接受明文。"""
    denied = _require_service() or _require_admin()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    try:
        row = _service().create(payload, _current_user_id())
    except IntegrationConnectionConflict as exc:
        return error_response(str(exc), status=409,
                             details={'refs': exc.refs})
    except IntegrationConnectionError as exc:
        return error_response(str(exc), status=400)
    return ok(row), 201


@integration_module_bp.route(
    '/api/v2/integrations/connections/<string:code>', methods=['PUT'])
@login_required
def update_connection(code):
    """更新连接（只改传入字段）。"""
    denied = _require_service() or _require_admin()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    try:
        row = _service().update(code, payload)
    except IntegrationConnectionConflict as exc:
        return error_response(str(exc), status=409,
                             details={'refs': exc.refs})
    except IntegrationConnectionError as exc:
        return error_response(str(exc), status=400)
    if not row:
        return error_response('连接不存在: %s' % code, status=404)
    return ok(row)


@integration_module_bp.route(
    '/api/v2/integrations/connections/<string:code>', methods=['DELETE'])
@login_required
def delete_connection(code):
    """删除连接；仍被订阅或投递引用时返回 409。"""
    denied = _require_service() or _require_admin()
    if denied:
        return denied
    try:
        result = _service().delete(code)
    except IntegrationConnectionConflict as exc:
        return error_response(str(exc), status=409,
                             details={'refs': exc.refs})
    if not result:
        return error_response('连接不存在: %s' % code, status=404)
    return ok(result)


@integration_module_bp.route(
    '/api/v2/integrations/connections/<string:code>/test', methods=['POST'])
@login_required
def test_connection(code):
    """连通性测试：webhook 空探测 / rest HEAD / file 目录检查。"""
    denied = _require_service() or _require_admin()
    if denied:
        return denied
    try:
        result = _service().test_connection(code)
    except IntegrationConnectionError as exc:
        return error_response(str(exc), status=400)
    if not result:
        return error_response('连接不存在: %s' % code, status=404)
    return ok(result)


# ------------------------------------------------------------------ 投递运行面
@integration_module_bp.route('/api/v2/integrations/deliveries', methods=['GET'])
@login_required
def list_deliveries():
    """in/out messages：投递事实列表（按连接 / 事件 / 状态 / 时间过滤）。"""
    denied = _require_service() or _require_admin()
    if denied:
        return denied

    service = _service()
    if not service.has_delivery_facts():
        return error_response(
            '投递事实列未就绪，请先执行 v279 迁移', status=503)

    page = _int_arg('page', 1, 1)
    page_size = _int_arg('page_size', DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)

    where: List[str] = []
    params: List[Any] = []

    def _eq(column: str, value: Any) -> None:
        if value is None or value == '':
            return
        where.append('d.%s = ?' % column)
        params.append(value)

    _eq('event_id', _int_arg('event_id'))
    _eq('subscription_id', _int_arg('subscription_id'))
    _eq('connection_id', _int_arg('connection_id'))
    _eq('status', request.args.get('status') or None)
    _eq('target_type', request.args.get('target_type') or None)
    _eq('direction', request.args.get('direction') or None)

    since = request.args.get('since')
    if since:
        where.append('d.created_at >= ?')
        params.append(since)
    until = request.args.get('until')
    if until:
        where.append('d.created_at <= ?')
        params.append(until)

    clause = (' WHERE ' + ' AND '.join(where)) if where else ''

    total_row = ds.execute(
        'SELECT COUNT(*) FROM %s d%s' % (DELIVERY_TABLE, clause),
        tuple(params)).fetchone()
    total = int(total_row[0]) if total_row else 0

    cursor = ds.execute(
        'SELECT d.id, d.event_id, d.subscription_id, d.user_id, d.channel, '
        'd.target, d.status, d.attempts, d.last_error, d.next_retry_at, '
        'd.delivered_at, d.created_at, d.connection_id, d.target_type, '
        'd.direction, e.object_type, e.object_id, e.event_type, '
        'c.code AS connection_code '
        'FROM %s d '
        'LEFT JOIN change_events e ON e.id = d.event_id '
        'LEFT JOIN integration_connection c ON c.id = d.connection_id'
        '%s ORDER BY d.id DESC LIMIT ? OFFSET ?'
        % (DELIVERY_TABLE, clause),
        tuple(params) + (page_size, (page - 1) * page_size))
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

    items = [dict(zip(columns, row)) for row in rows]
    return ok_list(items, total=total, page=page, page_size=page_size)


@integration_module_bp.route(
    '/api/v2/integrations/deliveries/<int:delivery_id>/retry',
    methods=['POST'])
@login_required
def retry_delivery(delivery_id):
    """单条投递重试：复用事件归属校验 + 5 秒去抖，只重置本条。

    与 `notification_api.retry_event` 的差别：后者按事件重置全部失败投递，
    这里只重置指定投递（其余行的 attempts / status 不变）。
    """
    denied = _require_service()
    if denied:
        return denied

    user = get_current_user() or {}
    user_id = user.get('user_id')

    delivery = ds.find_by_id(DELIVERY_TABLE, delivery_id)
    if not delivery:
        return error_response('投递记录不存在: %s' % delivery_id, status=404)

    if not (_same_user(delivery.get('user_id'), user_id)
            or _can_retry_all(user)):
        return error_response('您没有执行此操作的权限', status=403)

    status = delivery.get('status')
    if status not in RETRYABLE_STATUSES:
        return ok({
            'delivery_id': delivery_id,
            'event_id': delivery.get('event_id'),
            'status': status,
            'reset': 0,
            'attempted': 0,
            'debounced': False,
            'message': '当前状态不可重试',
        })

    event_id = delivery.get('event_id')
    debounce_key = (event_id, user_id)
    now_monotonic = time.monotonic()
    last = _retry_debounce.get(debounce_key)
    if last is not None and now_monotonic - last < RETRY_DEBOUNCE_SECONDS:
        return ok({
            'delivery_id': delivery_id,
            'event_id': event_id,
            'reset': 0,
            'attempted': 0,
            'debounced': True,
        })
    _retry_debounce[debounce_key] = now_monotonic

    event = ds.find_by_id('change_events', event_id) if event_id else None
    if not event:
        return error_response('关联事件不存在: %s' % event_id, status=404)

    try:
        from meta.services.change_event_dispatcher import ChangeEventDispatcher

        ds.update(DELIVERY_TABLE, delivery_id, {
            'status': 'pending',
            'next_retry_at': None,
        })
        dispatcher = ChangeEventDispatcher(ds)
        stats = dispatcher.redeliver_pending(event_id, event, force=True)
    except Exception as exc:
        logger.error('Failed to retry delivery %s: %s', delivery_id, exc)
        return error_response(str(exc), status=500)

    return ok({
        'delivery_id': delivery_id,
        'event_id': event_id,
        'reset': 1,
        'debounced': False,
        **stats,
    })


# ---------------------------------------------------------------- 导入 staging
def _staging() -> ImportStagingService:
    return ImportStagingService(ds)


def _batch_not_found(batch_no: str):
    return error_response('导入批次不存在: %s' % batch_no, status=404)


@integration_module_bp.route('/api/v2/integrations/imports', methods=['POST'])
@login_required
def submit_import_batch():
    """三段式导入入口（FR-4：mode=preview|execute）。

    staging → 校验 → 提交由 `import_export_service.import_cascade` 内嵌执行，
    本入口只做文件落盘与参数编排（薄封装，不复制第二套导入实现）。
    """
    denied = _require_service()
    if denied:
        return denied

    upload = request.files.get('file')
    if upload is None or not (upload.filename or '').strip():
        return error_response('未上传文件', status=400)

    from meta.api.export_import_api import (
        UPLOAD_FOLDER, allowed_file, get_import_export_service,
    )

    if not allowed_file(upload.filename):
        return error_response('只支持 Excel 文件（.xlsx/.xls）', status=400)

    mode = (request.form.get('mode') or 'preview').strip().lower()
    if mode not in ('preview', 'execute'):
        return error_response('mode 只支持 preview|execute', status=400)

    context: dict = {}
    for key in ('version_id', 'product_id'):
        raw = request.form.get(key)
        if raw in (None, ''):
            continue
        try:
            context[key] = int(raw)
        except (TypeError, ValueError):
            return error_response('%s 必须为整数' % key, status=400)

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    file_path = os.path.join(UPLOAD_FOLDER, secure_filename(upload.filename))
    upload.save(file_path)

    try:
        result = get_import_export_service().import_cascade(
            file_path,
            mode,
            request.form.get('conflict_strategy') or 'upsert',
            context,
            force_override_explicit_mode=(
                request.form.get('force_override_explicit_mode') or 'true'
            ).strip().lower() == 'true',
        )
    except Exception as exc:  # fail-open：导入失败不落半套数据，直接返回原因
        logger.exception('[integration] 导入失败: %s', exc)
        return error_response('导入失败: %s' % exc, status=500)

    payload = {
        'mode': mode,
        'batch_no': result.batch_no,
        'staging_rows': getattr(result, 'staging_rows', None),
    }
    if mode == 'preview':
        payload['validation'] = getattr(result, 'validation', None)
        payload['import_order'] = getattr(result, 'import_order', None)
    else:
        payload.update({
            'success': getattr(result, 'success', False),
            'results': getattr(result, 'results', None),
            'errors': getattr(result, 'errors', None),
            'error_report_path': getattr(result, 'error_report_path', None),
        })
    return ok(payload)


@integration_module_bp.route('/api/v2/integrations/imports', methods=['GET'])
@login_required
def list_import_batches():
    """批次列表（运行面入口）：按批次聚合，最新在前。"""
    denied = _require_service() or _require_admin()
    if denied:
        return denied

    page = _int_arg('page', 1, 1)
    page_size = _int_arg('page_size', DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
    items, total = _staging().list_batches(
        object_type=request.args.get('object_type') or None,
        page=page,
        page_size=page_size,
    )
    return ok_list(items, total=total, page=page, page_size=page_size)


@integration_module_bp.route(
    '/api/v2/integrations/imports/<string:batch_no>', methods=['GET'])
@login_required
def get_import_batch(batch_no):
    """批次汇总（行数按 status 聚合 + TTL）。"""
    denied = _require_service() or _require_admin()
    if denied:
        return denied
    service = _staging()
    if not service.batch_info(batch_no):
        return _batch_not_found(batch_no)
    return ok(service.summary(batch_no))


@integration_module_bp.route(
    '/api/v2/integrations/imports/<string:batch_no>/rows', methods=['GET'])
@login_required
def list_import_rows(batch_no):
    """staging 行（可按状态 / 错误码 / 对象过滤）。"""
    denied = _require_service() or _require_admin()
    if denied:
        return denied
    service = _staging()
    if not service.batch_info(batch_no):
        return _batch_not_found(batch_no)

    page = _int_arg('page', 1, 1)
    page_size = _int_arg('page_size', 50, 1, MAX_PAGE_SIZE)
    items, total = service.list_rows(
        batch_no,
        status=request.args.get('status') or None,
        error_code=request.args.get('error_code') or None,
        object_type=request.args.get('object_type') or None,
        page=page,
        page_size=page_size,
    )
    return ok_list(items, total=total, page=page, page_size=page_size)


@integration_module_bp.route(
    '/api/v2/integrations/imports/<string:batch_no>/rows/<string:object_type>/'
    '<int:row_no>', methods=['GET'])
@login_required
def get_import_row(batch_no, object_type, row_no):
    """单行详情（含原始行 payload，超 64KB 时只有截断摘要）。"""
    denied = _require_service() or _require_admin()
    if denied:
        return denied
    row = _staging().get_row(batch_no, object_type, row_no)
    if not row:
        return error_response('staging 行不存在: %s#%s' % (object_type, row_no),
                             status=404)
    return ok(row)


@integration_module_bp.route(
    '/api/v2/integrations/imports/<string:batch_no>/error-report',
    methods=['GET'])
@login_required
def download_import_error_report(batch_no):
    """错误报告下载（CSV）；批次过期后返回 410。"""
    denied = _require_service() or _require_admin()
    if denied:
        return denied
    service = _staging()
    info = service.batch_info(batch_no)
    if not info:
        return _batch_not_found(batch_no)
    if info.get('expired'):
        return error_response('导入批次已过期（保留 %s 天）' % info.get('ttl_days'),
                             status=410)

    path = service.error_report(batch_no)
    if not path or not os.path.exists(path):
        return error_response('该批次没有失败行', status=404)
    return send_file(path, mimetype='text/csv', as_attachment=True,
                     download_name=os.path.basename(path))