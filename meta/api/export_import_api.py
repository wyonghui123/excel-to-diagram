# -*- coding: utf-8 -*-
"""
导入导出API端点

提供批量导出和导入功能的REST API接口
"""

import os
import json
import uuid
import logging
import threading
from pathlib import Path
from flask import Blueprint, request, jsonify, send_file, abort, g, copy_current_request_context
from meta.api._response_contract import error_response, normalize_error_code, ok
from werkzeug.utils import secure_filename
from urllib.parse import unquote

from meta.services.import_export_service import (
    ImportExportService,
    ExportResult,
    ImportPreview,
    ImportResult
)
from meta.core.datasource import get_data_source
from meta.services.manage_service import ManageService
from meta.services.query_service import QueryService
from meta.services.auth_middleware import login_required, get_current_user
from meta.services.permission_service import PermissionService
from meta.core.db_path import get_meta_db_path

export_import_bp = Blueprint('export_import', __name__, url_prefix='/api/v1')

logger = logging.getLogger(__name__)

_data_source = None
_import_export_service = None
_manage_service = None
_query_service = None

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
EXPORT_FOLDER = os.path.join(os.getcwd(), 'exports')
ALLOWED_EXTENSIONS = {'xlsx'}


def _api_error(message, error_code='INTERNAL_ERROR', status_code=400, detail=None):
    # [FR-004 2026-11-14] 收敛到统一错误出口
    normalized = normalize_error_code(error_code)
    if normalized == 'internal_error' and status_code == 400:
        status_code = 500
        message = '系统内部错误，请稍后重试'
    details = {'detail': detail} if detail and os.environ.get('FLASK_DEBUG') == '1' else None
    return error_response(message, error_code=normalized, status=status_code, details=details)


def _api_success(data=None, message='Success', **kwargs):
    response = {
        'success': True,
        'message': message
    }
    if data is not None:
        response['data'] = data
    response.update(kwargs)
    return jsonify(response)

_import_tasks = {}
_export_tasks = {}

#: [FR-006/FR-007 2026-11-14] 导入任务接入统一执行账本（`task_runs`）。
#: 开关默认 1（走账本）；置 0 回退到纯内存实现（spec TR-002）。
IMPORT_JOB_CODE = 'import_cascade'
_job_store = None


def _use_job_ledger() -> bool:
    return os.environ.get('IMPORT_USE_JOB_LEDGER', '1').strip().lower() not in (
        '0', 'false', 'no', 'off')


def _get_job_store():
    """复用 server.py 注入的 `JobRunStore`；未初始化时按需构造并缓存。"""
    global _job_store
    if _job_store is not None:
        return _job_store
    try:
        from meta.api.job_admin_api import get_job_store
        _job_store = get_job_store()
    except Exception:
        _job_store = None
    if _job_store is None and _data_source is not None:
        from meta.core.job_run_store import JobRunStore
        _job_store = JobRunStore(_data_source)
    return _job_store


def _run_to_task_status(run) -> dict:
    """把 `task_runs` 行投影为 `/import/status` 的旧响应结构（逐字兼容）。"""
    progress = run.get('progress') or {}
    if not isinstance(progress, dict):
        progress = {}
    try:
        result = json.loads(run['result']) if run.get('result') else None
    except (TypeError, ValueError):
        result = None

    status = run.get('status')
    error = run.get('error')
    if status == 'succeeded':
        legacy_status = 'completed'
        percent = 100
        message = '导入完成'
    elif status in ('failed', 'dead'):
        legacy_status = 'failed'
        percent = progress.get('percent') or 0
        # 失败时以真实错误为准，避免展示过期的"正在导入 X"进度文案
        message = ('导入失败: %s' % error) if error else (
            progress.get('message') or '导入失败')
    elif status == 'cancelled':
        legacy_status = 'failed'
        percent = progress.get('percent') or 0
        error = error or '已取消'
        message = '导入已取消'
    else:
        legacy_status = 'processing'
        percent = progress.get('percent') or 0
        message = progress.get('message') or '准备中...'

    return {
        'status': legacy_status,
        'progress': percent,
        'current_type': progress.get('stage') or '',
        'current_type_name': progress.get('stage_name') or '',
        'total_types': progress.get('total') or 0,
        'current_index': progress.get('current') or 0,
        'message': message,
        'result': result,
        'error': error,
    }


def _progress_payload(info: dict) -> dict:
    """`import_cascade` 进度回调 → `task_runs.progress` JSON（FR-004）。"""
    return {
        'current': info.get('current_index'),
        'total': info.get('total_types'),
        'percent': info.get('progress'),
        'stage': info.get('current_type'),
        'stage_name': info.get('current_type_name'),
        'message': info.get('message'),
    }


def init_services(data_source=None):
    global _data_source, _import_export_service, _manage_service, _query_service
    if data_source:
        _data_source = data_source
    elif _data_source is None:
        import os
        db_path = get_meta_db_path()
        _data_source = get_data_source("sqlite", database=db_path)
    _manage_service = ManageService(_data_source)
    _query_service = QueryService(_data_source)
    _import_export_service = ImportExportService(
        _data_source, _manage_service, _query_service
    )


def get_import_export_service():
    if _import_export_service is None:
        init_services()
    return _import_export_service


def _set_audit_user():
    """设置审计用户信息（用于导入操作）"""
    service = _manage_service
    if service is None:
        return
    
    current_user = getattr(g, 'current_user', None)
    
    if not current_user:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.replace('Bearer ', '')
            try:
                from meta.services.token_service import TokenService
                current_user = TokenService.verify_token(token)
            except Exception:
                logger.debug('[ExportImport] Bearer token 校验失败，按匿名处理', exc_info=True)
    
    current_user = current_user or {}
    user_id = current_user.get('user_id') or request.headers.get('X-User-Id')
    
    user_name_raw = (current_user.get('display_name')
                     or current_user.get('username')
                     or request.headers.get('X-User-Name', '')
                     or os.environ.get('AUDIT_DEFAULT_USER', ''))
    try:
        user_name = unquote(user_name_raw) if user_name_raw else ''
    except Exception:
        user_name = user_name_raw
    
    if not user_name:
        user_name = 'system'
    
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr) or request.headers.get('X-IP-Address', '')
    user_agent = request.headers.get('User-Agent', '')
    service.set_audit_user(user_id, user_name, ip_address, user_agent)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _check_export_permission(object_type: str, action: str = 'export') -> bool:
    """检查用户是否有导出/导入权限

    Args:
        object_type: 业务对象类型（如 'service_module'）
        action: 动作类型（'export' 或 'import'）

    Returns:
        bool: True if user has permission, False otherwise

    Raises:
        403 Forbidden if user lacks permission
    """
    user = get_current_user()
    if not user:
        abort(403, "未登录")

    # 超级管理员绕过权限检查
    if user.get('username') == 'admin':
        return True

    # 构建权限编码
    permission_code = f"{object_type}:{action}"

    # 检查权限
    service = get_import_export_service()
    perm_service = PermissionService(service.data_source)
    has_permission = perm_service.check_permission_unified(
        user['user_id'],
        object_type,
        action
    )

    if not has_permission:
        abort(403, f"您没有 {object_type}:{action} 权限")

    return True


@export_import_bp.route('/export', methods=['POST'])
@login_required
def export_data():
    """
    导出数据API
    
    请求体:
    {
        "object_type": "domain",           // 必填：起始对象类型
        "scope": "cascade",                // single | cascade
        "filters": {"version_id": 1},      // 可选：筛选条件
        "options": {
            "include_hierarchy_path": true,
            "include_hierarchy_ids": true,
            "include_metadata_sheet": true
        }
    }
    
    响应:
    {
        "success": true,
        "data": {
            "file_path": "/exports/cascade_domain_20260101.xlsx",
            "download_url": "/api/v1/export/download/cascade_domain_20260101.xlsx",
            "sheets": [...],
            "total_rows": 100
        }
    }
    """
    try:
        # [H15.2 FIX] 添加导出权限检查 (SAP风格 graceful degradation)
        # 如果用户对部分object_type无权限，跳过这些，导出用户有权限的
        data = request.get_json()
        if not data:
            return error_response("请求内容不能为空")

        object_type = data.get('object_type')
        if not object_type:
            return error_response("object_type 参数必填")

        scope = data.get('scope', 'single')
        selected_types = data.get('selected_types', [])
        filters = data.get('filters')
        sort_by = data.get('sort_by')
        sort_order = data.get('sort_order', 'asc')

        page = data.get('page')
        page_size = data.get('page_size')
        # [NEW v3.20 2026-06-19] 菜单编码, arch-data → 文件名"架构数据"前缀
        menu_code = data.get('menu_code')

        options = data.get('options', {
            "include_hierarchy_path": True,
            "include_hierarchy_ids": True,
            "include_metadata_sheet": True,
            "protect_sheet": False,
            "include_child_objects": True
        })

        # [H15.2 SAP风格] 过滤用户无权限的object_types
        user = get_current_user()
        skipped_types = []

        def _has_perm(ot):
            """检查用户对object_type是否有export权限"""
            if not user or user.get('username') == 'admin':
                return True
            service_inner = get_import_export_service()
            perm_service = PermissionService(service_inner.data_source)
            return perm_service.check_permission_unified(
                user['user_id'], ot, 'export'
            )

        # 对所有涉及的object_types做权限过滤
        # 收集所有需要检查的object_types
        all_types_to_check = set()
        if selected_types:
            all_types_to_check.update(selected_types)
        if object_type:
            all_types_to_check.add(object_type)

        # 过滤
        skipped_types = [t for t in all_types_to_check if not _has_perm(t)]
        allowed_types = [t for t in all_types_to_check if t not in skipped_types]

        if selected_types:
            selected_types = [t for t in selected_types if t in allowed_types]
        if object_type and object_type in skipped_types:
            # 起始object_type无权限，从allowed中选一个
            if allowed_types:
                object_type = allowed_types[0]
            else:
                # [H15.2 修复] 错误信息要根据具体跳过的object_type生成
                if len(skipped_types) == 1:
                    msg = f"您对 {skipped_types[0]} 没有export权限"
                else:
                    msg = f"您对所选的所有object_type都没有export权限: {', '.join(skipped_types)}"
                return jsonify({
                    "success": False,
                    "message": msg,
                    "skipped_types": skipped_types
                }), 403

        print(f"[Export API] Received filters: {filters}")
        print(f"[Export API] Object type: {object_type}, Scope: {scope}, Selected types: {selected_types}, Skipped: {skipped_types}, Menu: {menu_code}")
        print(f"[Export API] Sort by: {sort_by}, Order: {sort_order}")
        print(f"[Export API] Pagination: page={page}, page_size={page_size}")

        service = get_import_export_service()

        # [FIX v1.2.50 2026-06-22] 同步导出也设置 thread-local user
        # 原因: import_export_service._query_association_with_hierarchy_filters
        #   会调 _build_permission_filter, 该函数同时支持 thread-local user 和 g.current_user
        #   设置 thread-local 作为额外保险, 避免 g.current_user 在某些边界场景下丢失
        try:
            from meta.services.query_service import set_thread_user
            g_user = getattr(g, 'current_user', None)
            if g_user:
                set_thread_user(g_user)
        except Exception:
            logger.debug('[ExportImport] set_thread_user 失败', exc_info=True)

        if scope == 'template':
            if not selected_types:
                return jsonify({
                    "success": False,
                    "message": "模板导出至少需要一个object_type",
                    "skipped_types": skipped_types
                }), 400
            result = service.export_template(selected_types, options, menu_code=menu_code)
        elif scope == 'cascade':
            result = service.export_cascade(
                object_type, filters, options,
                sort_by=sort_by, sort_order=sort_order,
                page=page, page_size=page_size,
                menu_code=menu_code,
            )
        elif scope == 'selected' and selected_types:
            result = service.export_selected_types(selected_types, filters, options, sort_by=sort_by, sort_order=sort_order, page=page, page_size=page_size)
        elif scope == 'selected' and not selected_types:
            return jsonify({
                "success": False,
                "message": "您对所选的所有object_type都没有export权限",
                "skipped_types": skipped_types
            }), 403
        else:
            result = service.export_selected_types([object_type], filters, options, sort_by=sort_by, sort_order=sort_order, page=page, page_size=page_size)

        if not result.success:
            return jsonify({
                "success": False,
                "message": "导出失败",
                "errors": result.errors
            }), 500

        file_name = os.path.basename(result.file_path)
        download_url = "/api/v1/export/download/{0}".format(file_name)

        return ok({
            "file_path": result.file_path,
            "download_url": download_url,
            "sheets": result.sheets,
            "total_rows": result.total_rows,
            "skipped_types": skipped_types  # [H15.2 SAP风格] 返回被跳过的object_types
        })
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[EXPORT ERROR] {e}")
        print(error_trace)
        return jsonify({
            "success": False,
            "error": type(e).__name__,
            "message": "导出过程中发生错误: {0}".format(str(e)),
            "detail": error_trace
        }), 500


def _update_export_task_progress(task_id, info):
    """更新导出任务进度"""
    if task_id in _export_tasks:
        task = _export_tasks[task_id]
        task['progress'] = info.get('progress', task['progress'])
        task['current_type'] = info.get('current_type', task['current_type'])
        task['current_type_name'] = info.get('current_type_name', task['current_type_name'])
        task['total_types'] = info.get('total_types', task['total_types'])
        task['current_index'] = info.get('current_index', task['current_index'])
        task['message'] = info.get('message', task['message'])


@export_import_bp.route('/export/async', methods=['POST'])
@login_required
def export_data_async():
    """
    异步导出数据API（支持进度查询）
    
    返回 task_id，前端可通过 /export/status/<task_id> 查询进度
    """
    try:
        data = request.get_json()
        if not data:
            return error_response("请求内容不能为空")

        object_type = data.get('object_type')
        if not object_type:
            return error_response("object_type 参数必填")

        scope = data.get('scope', 'single')
        selected_types = data.get('selected_types', [])
        filters = data.get('filters')
        sort_by = data.get('sort_by')
        sort_order = data.get('sort_order', 'asc')
        options = data.get('options', {
            "include_hierarchy_path": True,
            "include_hierarchy_ids": True,
            "include_metadata_sheet": True,
            "protect_sheet": False
        })

        # [FIX 2026-06-17] 从 login_required 已写入的 g.current_user 拿 user_id
        # 用于后台线程的权限过滤 (避免子线程中 flask.g 不可用导致权限被绕过)
        export_user_id = None
        try:
            g_user = getattr(g, 'current_user', None)
            if g_user:
                export_user_id = g_user.get('user_id')
        except Exception:
            pass

        task_id = str(uuid.uuid4())
        total_types = len(selected_types) if selected_types else 1
        
        _export_tasks[task_id] = {
            'status': 'processing',
            'progress': 0,
            'current_type': '',
            'current_type_name': '',
            'total_types': total_types,
            'current_index': 0,
            'message': '准备导出...',
            'result': None,
            'error': None
        }

        # [FIX 2026-06-17] 用 thread-local user_id 传递 user 身份到子线程
        # 否则 query_service.search() 调 _apply_data_permission 时 get_current_user() 返回 None
        # 导致权限过滤被跳过 (async 导出包含所有数据的安全漏洞)
        _run_user_id = export_user_id
        # [FIX v1.2.12 2026-06-17] 同时传完整 user dict (含 permissions) 让 is_admin() 能识别 admin
        _run_user = g.current_user  # full dict with permissions
        def _run_export():
            from meta.services.query_service import set_thread_user
            if _run_user:
                set_thread_user(_run_user)
            try:
                service = get_import_export_service()

                if scope == 'template':
                    result = service.export_template(selected_types, options, 
                        progress_callback=lambda info: _update_export_task_progress(task_id, info))
                elif scope == 'cascade':
                    result = service.export_cascade(object_type, filters, options, 
                        sort_by=sort_by, sort_order=sort_order,
                        progress_callback=lambda info: _update_export_task_progress(task_id, info))
                elif scope == 'selected' and selected_types:
                    result = service.export_selected_types(selected_types, filters, options, 
                        sort_by=sort_by, sort_order=sort_order,
                        progress_callback=lambda info: _update_export_task_progress(task_id, info))
                else:
                    result = service.export_selected_types([object_type], filters, options, 
                        sort_by=sort_by, sort_order=sort_order,
                        progress_callback=lambda info: _update_export_task_progress(task_id, info))
                
                if result.success:
                    file_name = os.path.basename(result.file_path)
                    download_url = "/api/v1/export/download/{0}".format(file_name)
                    _export_tasks[task_id]['status'] = 'completed'
                    _export_tasks[task_id]['progress'] = 100
                    _export_tasks[task_id]['message'] = '导出完成'
                    _export_tasks[task_id]['result'] = {
                        'file_path': result.file_path,
                        'download_url': download_url,
                        'sheets': result.sheets,
                        'total_rows': result.total_rows
                    }
                else:
                    _export_tasks[task_id]['status'] = 'failed'
                    _export_tasks[task_id]['error'] = result.errors or '导出失败'
                    
            except Exception as e:
                import traceback
                _export_tasks[task_id]['status'] = 'failed'
                _export_tasks[task_id]['error'] = str(e)
                _export_tasks[task_id]['detail'] = traceback.format_exc()

        threading.Thread(target=_run_export, daemon=True).start()
        
        return ok({"task_id": task_id})
        
    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": type(e).__name__,
            "message": "启动导出任务失败: {0}".format(str(e))
        }), 500


@export_import_bp.route('/export/status/<task_id>', methods=['GET'])
@login_required
def export_status(task_id):
    """查询异步导出任务状态"""
    task = _export_tasks.get(task_id)
    if not task:
        return error_response("任务不存在", status=404)

    return ok({
        "status": task['status'],
        "progress": task['progress'],
        "current_type": task['current_type'],
        "current_type_name": task['current_type_name'],
        "total_types": task['total_types'],
        "current_index": task['current_index'],
        "message": task['message'],
        "result": task.get('result'),
        "error": task.get('error')
    })


@export_import_bp.route('/export/download/<path:filename>', methods=['GET'])
def download_export(filename):
    """下载导出文件"""
    try:
        import traceback
        print(f"[DOWNLOAD_DEBUG] Raw filename from Flask: {repr(filename)}")
        
        if not filename or '..' in filename or filename.startswith('/'):
            return error_response("无效的文件名")
        
        export_path = Path(EXPORT_FOLDER).resolve()
        file_path = (export_path / filename).resolve()
        
        print(f"[DOWNLOAD_DEBUG] Export folder: {export_path}")
        print(f"[DOWNLOAD_DEBUG] File path: {file_path}")
        print(f"[DOWNLOAD_DEBUG] Starts with check: {str(file_path).startswith(str(export_path))}")
        print(f"[DOWNLOAD_DEBUG] File exists: {file_path.exists()}")
        
        if not str(file_path).startswith(str(export_path)):
            abort(403)
        
        if not file_path.exists():
            return error_response("文件不存在", status=404)
        
        return send_file(
            str(file_path),
            as_attachment=True,
            download_name=file_path.name
        )
    except Exception as e:
        print(f"[DOWNLOAD_DEBUG] Error: {e}")
        traceback.print_exc()
        return error_response("下载失败: {0}".format(str(e)), status=500)


@export_import_bp.route('/import', methods=['POST'])
@login_required
def import_data():
    """
    导入数据API
    
    请求: multipart/form-data
    - file: Excel文件
    - mode: preview | execute
    - conflict_strategy: upsert | skip | replace
    - version_id: 可选，导入时自动填充版本ID
    - product_id: 可选，导入时自动填充产品线ID
    
    响应 (preview模式):
    {
        "success": true,
        "data": {
            "sheets": [...],
            "validation": {...},
            "import_order": [...]
        }
    }
    
    响应 (execute模式):
    {
        "success": true,
        "data": {
            "results": {...},
            "errors": [...]
        }
    }
    """
    try:
        if 'file' not in request.files:
            return error_response("未上传文件")
        
        file = request.files['file']
        if file.filename == '':
            return error_response("未选择文件")
        
        if not allowed_file(file.filename):
            return error_response("只支持 .xlsx 格式的文件")
        
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        mode = request.form.get('mode', 'preview')
        conflict_strategy = request.form.get('conflict_strategy', 'upsert')
        # [FIX 2026-06-24] force_override_explicit_mode 默认 True:
        #   UI 的 conflict_strategy 永远比 Excel "操作模式"列优先级高
        #   老脚本要保留 v1.2.18l 行为 (Excel 列优先) 可显式传 'false'
        force_override_explicit_mode = request.form.get('force_override_explicit_mode', 'true').lower() == 'true'

        _set_audit_user()

        import logging
        logger = logging.getLogger(__name__)

        context = {}
        version_id = request.form.get('version_id')
        product_id = request.form.get('product_id')

        logger.info(f"[API] 接收到的Form Data:")
        logger.info(f"[API]   version_id = {version_id} (type: {type(version_id)})")
        logger.info(f"[API]   product_id = {product_id} (type: {type(product_id)})")
        logger.info(f"[API]   mode = {mode}")
        logger.info(f"[API]   conflict_strategy = {conflict_strategy}")
        logger.info(f"[API]   force_override_explicit_mode = {force_override_explicit_mode}")

        if version_id:
            context['version_id'] = int(version_id)
            logger.info(f"[API] context['version_id'] = {context['version_id']}")
        if product_id:
            context['product_id'] = int(product_id)
            logger.info(f"[API] context['product_id'] = {context['product_id']}")

        logger.info(f"[API] 最终传递给service的context: {context}")

        service = get_import_export_service()
        result = service.import_cascade(file_path, mode, conflict_strategy, context,
                                        force_override_explicit_mode=force_override_explicit_mode)
        
        if mode == 'preview':
            return ok({
                "sheets": result.sheets,
                "validation": result.validation,
                "import_order": result.import_order
            })
        else:
            return jsonify({
                "success": result.success,
                "data": {
                    "results": result.results,
                    "errors": result.errors
                }
            })
    
    except Exception as e:
        return error_response("导入过程中发生错误: {0}".format(str(e)), status=500)


@export_import_bp.route('/import/async', methods=['POST'])
@login_required
def import_data_async():
    """
    异步导入数据API（支持进度查询）

    请求: multipart/form-data
    - file: Excel文件
    - conflict_strategy: upsert | skip | replace
    - version_id: 可选
    - product_id: 可选

    响应:
    {
        "success": true,
        "data": { "task_id": "uuid" }
    }
    """
    try:
        if 'file' not in request.files:
            return error_response("未上传文件")

        file = request.files['file']
        if file.filename == '':
            return error_response("未选择文件")

        if not allowed_file(file.filename):
            return error_response("只支持 .xlsx 格式的文件")

        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)

        conflict_strategy = request.form.get('conflict_strategy', 'upsert')
        # [FIX 2026-06-24] force_override_explicit_mode 默认 True (UI 选择优先)
        force_override_explicit_mode = request.form.get('force_override_explicit_mode', 'true').lower() == 'true'

        context = {}
        version_id = request.form.get('version_id')
        product_id = request.form.get('product_id')

        if version_id:
            context['version_id'] = int(version_id)
        if product_id:
            context['product_id'] = int(product_id)

        current_user = getattr(g, 'current_user', None)
        if not current_user:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header.replace('Bearer ', '')
                try:
                    from meta.services.token_service import TokenService
                    current_user = TokenService.verify_token(token)
                except Exception:
                    pass
        current_user = current_user or {}
        audit_user_id = current_user.get('user_id') or request.headers.get('X-User-Id')
        audit_user_name_raw = (current_user.get('display_name')
                               or current_user.get('username')
                               or request.headers.get('X-User-Name', '')
                               or os.environ.get('AUDIT_DEFAULT_USER', ''))
        try:
            audit_user_name = unquote(audit_user_name_raw) if audit_user_name_raw else ''
        except Exception:
            audit_user_name = audit_user_name_raw
        if not audit_user_name:
            audit_user_name = 'system'
        audit_ip = request.headers.get('X-Forwarded-For', request.remote_addr) or request.headers.get('X-IP-Address', '')
        audit_ua = request.headers.get('User-Agent', '')

        task_id = str(uuid.uuid4())

        _import_tasks[task_id] = {
            'status': 'processing',
            'progress': 0,
            'current_type': '',
            'current_type_name': '',
            'total_types': 0,
            'current_index': 0,
            'message': '准备中...',
            'result': None,
            'error': None
        }

        # [FR-006 2026-11-14] 双写：内存字典保留（回退路径），同时落 task_runs。
        run_id = None
        store = _get_job_store() if _use_job_ledger() else None
        if store is not None:
            try:
                run_id = store.create_run(
                    IMPORT_JOB_CODE,
                    params={
                        'file_path': file_path,
                        'conflict_strategy': conflict_strategy,
                        'context': context,
                        'force_override_explicit_mode': force_override_explicit_mode,
                        'audit': {
                            'user_id': audit_user_id,
                            'user_name': audit_user_name,
                            'ip': audit_ip,
                            'user_agent': audit_ua,
                            'user': g.current_user if isinstance(g.current_user, dict) else None,
                        },
                    },
                    run_key='import:%s' % task_id,
                    max_attempts=1)
            except Exception as exc:  # 账本不可用不阻断导入，仅降级为内存模式
                logger.warning('[import] run 创建失败，降级内存模式: %s', exc)
                run_id = None
        if run_id is None and _use_job_ledger():
            logger.warning('[import] 未能创建 task_runs（作业定义缺失或账本未初始化），task=%s',
                           task_id)

        # [FIX 2026-06-17] 用 thread-local user_id 传递 user 身份到子线程
        # 修复 async 导入也存在的权限上下文丢失问题
        _run_import_user_id = audit_user_id
        # [FIX v1.2.12 2026-06-17] 同时传完整 user dict (含 permissions) 让 is_admin() 正确识别
        _run_import_user = g.current_user

        def _on_progress(info):
            _update_task_progress(task_id, info)
            if run_id is not None:
                try:
                    store.update_progress(run_id, _progress_payload(info))
                except Exception as exc:  # 进度写失败不影响导入
                    logger.debug('[import] run=%s 进度写入失败: %s', run_id, exc)

        def _run_import():
            from meta.services.query_service import set_thread_user, clear_thread_user_id
            if _run_import_user:
                try:
                    set_thread_user(_run_import_user)
                except Exception:
                    pass
            worker_id = None
            if run_id is not None:
                from meta.core.job_run_store import current_worker_id
                worker_id = current_worker_id()
                try:
                    claimed = store.claim(run_id, worker_id)
                    if claimed:
                        store.start(run_id, worker_id)
                    else:
                        # 账本已被其他执行者持有（如 dispatcher）→ 本线程退出，避免重复导入
                        logger.info('[import] run=%s 已被其他 worker 持有，跳过本次执行', run_id)
                        return
                except Exception as exc:
                    logger.warning('[import] run=%s claim/start 失败: %s', run_id, exc)
                    try:
                        store.mark_dead(run_id, error='账本占用失败: %s' % exc)
                    except Exception:
                        pass
                    task = _import_tasks.get(task_id)
                    if task:
                        task['status'] = 'failed'
                        task['error'] = str(exc)
                        task['message'] = '导入失败: {0}'.format(str(exc))
                    return
            try:
                if _manage_service:
                    _manage_service.set_audit_user(audit_user_id, audit_user_name, audit_ip, audit_ua)
                service = get_import_export_service()
                result = service.import_cascade(
                    file_path, 'execute', conflict_strategy, context,
                    progress_callback=_on_progress,
                    force_override_explicit_mode=force_override_explicit_mode
                )
                task = _import_tasks.get(task_id)
                result_payload = {
                    'success': result.success,
                    'results': result.results,
                    'errors': result.errors,
                    'errors_truncated': bool(getattr(result, 'errors_truncated', False)),
                }
                if task:
                    task['status'] = 'completed'
                    task['progress'] = 100
                    task['message'] = '导入完成'
                    task['result'] = result_payload
                if run_id is not None and worker_id is not None:
                    store.finish(run_id, worker_id, True, result=result_payload)
            except Exception as e:
                import traceback
                if run_id is not None and worker_id is not None:
                    try:
                        store.finish(run_id, worker_id, False, error=str(e))
                    except Exception as finish_exc:
                        logger.warning('[import] run=%s finish 失败: %s', run_id, finish_exc)
                task = _import_tasks.get(task_id)
                if task:
                    task['status'] = 'failed'
                    task['error'] = str(e)
                    task['message'] = '导入失败: {0}'.format(str(e))
            finally:
                try:
                    clear_thread_user_id()
                except Exception:
                    pass

        threading.Thread(target=_run_import, daemon=True).start()

        return ok({"task_id": task_id, "run_id": run_id})

    except Exception as e:
        return error_response("启动异步导入失败: {0}".format(str(e)), status=500)


def _update_task_progress(task_id, info):
    task = _import_tasks.get(task_id)
    if task:
        task.update(info)


@export_import_bp.route('/import/status/<task_id>', methods=['GET'])
@login_required
def import_status(task_id):
    """查询异步导入任务状态

    [FR-007 2026-11-14] `IMPORT_USE_JOB_LEDGER=1` 时优先读 `task_runs`，
    响应结构保持与内存实现逐字一致；账本查不到时回退内存（双写容错）。
    """
    if _use_job_ledger():
        store = _get_job_store()
        if store is not None:
            try:
                run = store.find_run_by_key('import:%s' % task_id)
            except Exception as exc:
                logger.warning('[import] 账本查询失败，回退内存: %s', exc)
                run = None
            if run:
                return ok(_run_to_task_status(run))

    task = _import_tasks.get(task_id)
    if not task:
        return error_response("任务不存在", status=404)

    return ok({
        "status": task['status'],
        "progress": task['progress'],
        "current_type": task['current_type'],
        "current_type_name": task['current_type_name'],
        "total_types": task['total_types'],
        "current_index": task['current_index'],
        "message": task['message'],
        "result": task.get('result'),
        "error": task.get('error')
    })


@export_import_bp.route('/import/template/<object_type>', methods=['GET'])
@login_required
def download_template(object_type):
    """
    下载导入模板API

    生成指定对象类型的导入模板Excel文件

    [NEW v3.20 2026-06-19] 支持 query 参数 menu_code:
    - arch-data → 文件名前缀走"架构数据" (全局级联模板)
    - 其他 → 走起始对象 objectname
    """
    try:
        from meta.core.models import registry

        meta_obj = registry.get(object_type)
        if not meta_obj:
            return error_response("对象类型不存在", status=404)

        # [NEW v3.20 2026-06-19] menu_code query param
        menu_code = request.args.get('menu_code')

        service = get_import_export_service()
        result = service.export_template(
            [object_type],
            {
                "include_operation_mode": True,
                "include_hierarchy_path": True,
                "include_hierarchy_ids": True,
            },
            menu_code=menu_code,
        )

        if not result.success:
            return jsonify({
                "success": False,
                "message": "生成模板失败",
                "errors": result.errors
            }), 500

        file_path = result.file_path
        file_name = os.path.basename(file_path)

        return send_file(
            file_path,
            as_attachment=True,
            download_name=file_name
        )

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[TEMPLATE ERROR] {e}")
        print(error_trace)
        return jsonify({
            "success": False,
            "message": "生成模板失败: {0}".format(str(e)),
            "detail": error_trace
        }), 500


@export_import_bp.route('/import-export/config/<object_type>', methods=['GET'])
@login_required
def get_import_export_config(object_type):
    """
    获取对象的导入导出配置
    """
    try:
        from meta.core.models import registry
        
        meta_obj = registry.get(object_type)
        if not meta_obj:
            return error_response("对象类型不存在", status=404)
        
        config = meta_obj.import_export
        
        return ok({
            "object_type": object_type,
            "object_name": meta_obj.name,
            "import_enabled": config.import_enabled,
            "export_enabled": config.export_enabled,
            "cascade_export": config.cascade_export,
            "cascade_import": config.cascade_import,
            "conflict_strategy": config.conflict_strategy,
            "conflict_key": config.conflict_key,
            "description_for_agent": config.description_for_agent,
            "fields": [
                {
                    "id": f.id,
                    "name": f.name,
                    "data_category": f.semantics.data_category,
                    "business_key": getattr(f.semantics, 'business_key', False),
                    "import_visible": f.semantics.import_visible,
                    "export_visible": f.semantics.export_visible,
                    "import_order": f.semantics.import_order
                }
                for f in sorted(
                    meta_obj.fields,
                    key=lambda f: f.semantics.import_order
                )
            ]
        })
    
    except Exception as e:
        return error_response("获取配置失败: {0}".format(str(e)), status=500)
