# -*- coding: utf-8 -*-
"""
BO 业务 Action 统一 API
========================

提供所有业务 Action 的统一 HTTP 端点。
前端只需记住一个端点：/api/v2/action/{action_id}

示例:
  POST /api/v2/action/user.authenticate
  POST /api/v2/action/condition.evaluate
  POST /api/v2/action/user.batch_save

v3.1 增强 (2026-06-05):
- 新增 ActionResult dataclass 支持文件流返回 (audit.export 用)
- 鉴权改为基于 registry 的 requires_admin 字段
- 新增 _schemas 端点输出 OpenAPI-style schema
"""
import logging
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from flask import Blueprint, request, jsonify, g, Response, current_app

from meta.api._messages import MSG_ADMIN_REQUIRED, MSG_SESSION_EXPIRED, MSG_TOKEN_INVALID, MSG_AUTH_SERVICE_ERROR
from meta.core.bo_action_registry import bo_action_registry
from meta.services.auth_middleware import login_required, get_current_user

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    """
    Action 处理器返回值 (扩展)
    - 基础: success / data / message (兼容 dict)
    - [DECORATIVE] v3.1: file_data / file_mimetype / file_filename (文件流支持)
    """
    success: bool
    data: Any = None
    message: str = ''
    file_data: Optional[bytes] = None
    file_mimetype: Optional[str] = None
    file_filename: Optional[str] = None

bo_action_bp = Blueprint(
    'bo_action',
    __name__,
    url_prefix='/api/v2/action',
)


# [DECORATIVE] v3.18 M.1: trace_id before_request 注入 (全 bo_action 路由)
@bo_action_bp.before_request
def _inject_trace_id():
    """每个 bo_action 请求:
    1. 优先用 header X-Trace-Id (Agent 端到端追踪)
    2. 否则生成 UUID 32 char
    3. 存到 Flask g + thread local
    """
    from flask import request, g
    from meta.core.trace_id import TraceId
    tid = request.headers.get('X-Trace-Id') or TraceId.generate()
    TraceId.set(tid)
    g.trace_id = tid


@bo_action_bp.after_request
def _attach_trace_id_header(response):
    """响应 header 加 X-Trace-Id (Agent 可获取)"""
    from meta.core.trace_id import TraceId
    tid = TraceId.get()
    if tid and not response.headers.get('X-Trace-Id'):
        response.headers['X-Trace-Id'] = tid
    return response


def _build_user_context() -> Dict[str, Any]:
    """从 Flask g 构建用户上下文"""
    user = get_current_user() if hasattr(g, 'current_user') else None
    return {
        'user_id': (user or {}).get('user_id') if user else None,
        'user_name': (user or {}).get('username') if user else None,
        'ip_address': request.headers.get(
            'X-Forwarded-For', request.remote_addr
        ),
        'permissions': (user or {}).get('permissions', []) if user else [],
    }


@bo_action_bp.route('/<path:action_id>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def execute_action(action_id: str):
    """
    统一 Action 端点

    支持所有方法: GET/POST/PUT/DELETE
    参数来源:
      - GET:  query string
      - POST/PUT/DELETE:  JSON body

    Auth: 根据 registry 的 requires_auth / requires_admin 字段决定
    v3.1: 兼容 ActionResult 文件流返回
    """
    # [DECORATIVE] v3.1: 从 registry 读 requires_auth
    meta = bo_action_registry.get(action_id)
    if not meta:
        return jsonify({'success': False, 'data': None, 'message': f'Unknown action: {action_id}'}), 404

    # 1. 鉴权
    if meta.requires_auth:
        from meta.services.auth_middleware import _extract_token
        from meta.services.token_service import TokenService
        from meta.services.token_blacklist_service import token_blacklist_service
        token = _extract_token()
        if not token:
            return jsonify({'success': False, 'data': None, 'message': '未登录'}), 401
        try:
            if token_blacklist_service.is_blacklisted(token):
                return jsonify({'success': False, 'data': None, 'message': '登录状态已失效，请重新登录'}), 401
        except Exception:
            return jsonify({'success': False, 'data': None, 'message': '认证服务异常，请稍后重试'}), 401
        user_info = TokenService.verify_token(token)
        if not user_info:
            return jsonify({'success': False, 'data': None, 'message': '会话已过期，请重新登录'}), 401
        g.current_user = user_info

        # [DECORATIVE] v3.1: admin 鉴权
        if meta.requires_admin:
            from meta.api.auth_api import is_admin
            if not is_admin():
                return jsonify({'success': False, 'data': None, 'message': '您没有执行此操作的权限，需要管理员权限'}), 403

    # 2. 提取参数
    if request.method == 'GET':
        params: Dict[str, Any] = dict(request.args)
    else:
        if hasattr(g, 'cached_body') and g.cached_body is not None:
            params = g.cached_body
        else:
            params = request.get_json(force=True, silent=True)
            if params is None:
                import json as _json
                try:
                    raw = request.get_data(cache=False, as_text=True)
                    params = _json.loads(raw) if raw else {}
                except Exception as e:
                    logger.warning(f"[BOAction/parse] fallback failed: {e}")
                    params = {}
    logger.info(
        f"[BOAction/parse] {action_id} method={request.method} "
        f"content_type={request.content_type} "
        f"content_length={request.content_length} "
        f"params={params}"
    )

    context = _build_user_context()

    # 3. 调用
    start = time.time()
    result = bo_action_registry.call(action_id, params, context)
    duration_ms = (time.time() - start) * 1000

    # [DECORATIVE] v3.1: ActionResult 文件流支持 (audit.export 用)
    if isinstance(result, ActionResult) and result.file_data is not None:
        # v3.1: 文件流 - base64 包装 (避免 Flask send_file 在某些环境下崩)
        import base64
        try:
            file_b64 = base64.b64encode(result.file_data).decode('ascii')
            return jsonify({
                'success': result.success,
                'data': {
                    **result.data,
                    'file_data_base64': file_b64,
                    'file_size': len(result.file_data),
                },
                'message': result.message,
                '_file_response': True,  # 标记: 前端应识别并触发下载
                '_mimetype': result.file_mimetype,
                '_filename': result.file_filename,
            }), 200 if result.success else 400
        except Exception as e:
            logger.exception(f"[BOAction] file_response failed: {e}")
            return jsonify({
                'success': result.success,
                'data': result.data,
                'message': f'文件返回失败: {e}',
            }), 500

    # 兼容老路径: dict 结果
    if isinstance(result, ActionResult):
        # 转为 dict
        result = {
            'success': result.success,
            'data': result.data,
            'message': result.message,
        }

    # 特殊: login 成功后 set_cookie (兼容现有 auth_api.py 行为)
    from flask import make_response
    if action_id == 'user.authenticate' and result.get('success'):
        token = (result.get('data') or {}).get('token')
        if token:
            resp = make_response(jsonify(result))
            resp.set_cookie(
                'auth_token',
                value=token,
                max_age=86400 * 7,
                httponly=True,
                secure=False,
                samesite='Lax',
                path='/',
            )
            logger.info(
                f"[BOAction] {action_id} "
                f"success={result.get('success')} "
                f"duration={duration_ms:.1f}ms "
                f"user={context.get('user_name')}"
            )
            return resp, 200

    logger.info(
        f"[BOAction] {action_id} "
        f"success={result.get('success')} "
        f"duration={duration_ms:.1f}ms "
        f"user={context.get('user_name')}"
    )

    status_code = 200
    if not result.get('success'):
        msg = result.get('message', '')
        if 'Permission denied' in msg:
            status_code = 403
        elif 'Unknown action' in msg:
            status_code = 404

    return jsonify(result), status_code


@bo_action_bp.route('/_schemas', methods=['GET'])
def list_action_schemas():
    """
    列出所有 Action 的 OpenAPI-style schema (v3.1 新增)

    用于:
    - 客户端代码生成 (TypeScript types)
    - OpenAPI 3.0 spec 导出
    - 文档生成
    """
    schemas = bo_action_registry.list_schemas()
    return jsonify({
        'success': True,
        'data': {
            'count': len(schemas),
            'actions': schemas,
        },
        'message': f'Returned {len(schemas)} action schemas',
    })


@bo_action_bp.route('/_chain', methods=['POST'])
def execute_subflow_endpoint():
    """
    [DECORATIVE] v3.2: Subflow / Chain Action 端点

    串联多个 BO Action 一次执行。
    详情见 meta.services.subflow_engine.execute_subflow()
    """
    # 鉴权 (登录即可, 每个 step 的 admin 鉴权由各 Action 自己处理)
    from meta.services.auth_middleware import _extract_token
    from meta.services.token_service import TokenService
    from meta.services.token_blacklist_service import token_blacklist_service

    token = _extract_token()
    if not token:
        return jsonify({'success': False, 'data': None, 'message': '未登录'}), 401
    try:
        if token_blacklist_service.is_blacklisted(token):
            return jsonify({'success': False, 'data': None, 'message': '登录状态已失效，请重新登录'}), 401
    except Exception:
        return jsonify({'success': False, 'data': None, 'message': '认证服务异常，请稍后重试'}), 401
    user_info = TokenService.verify_token(token)
    if not user_info:
        return jsonify({'success': False, 'data': None, 'message': '会话已过期，请重新登录'}), 401
    g.current_user = user_info
    user_info['ip_address'] = _extract_token.__module__ and g.get('_remote_addr')

    from flask import request
    if hasattr(g, 'cached_body') and g.cached_body is not None:
        body = g.cached_body
    else:
        body = request.get_json(force=True, silent=True) or {}

    name = body.get('name', 'unnamed_subflow')
    steps = body.get('steps', [])
    atomic = bool(body.get('atomic', False))
    context = body.get('context', {})
    templates = body.get('templates', {})  # [DECORATIVE] v3.6 C-3: 嵌套 subflow 模板
    dry_run = bool(body.get('dry_run', False))  # [DECORATIVE] v3.7
    template_name = body.get('template')  # [DECORATIVE] v3.7: 引用 server-side 模板
    template_params = body.get('params', {})  # 模板渲染参数

    # 注入 IP
    from flask import request as _req
    user_info['ip_address'] = _req.remote_addr

    # [DECORATIVE] v3.7: 模板引用
    if template_name:
        from meta.services.subflow_template_store import SubflowTemplateStore
        rendered = SubflowTemplateStore.render_template(template_name, template_params)
        if not rendered:
            return jsonify({
                'success': False,
                'data': None,
                'message': f'模板 {template_name} 不存在',
                'code': 'subflow_template_not_found',
            }), 200
        steps = rendered

    from meta.services.subflow_engine import execute_subflow
    result = execute_subflow(
        registry=bo_action_registry,
        name=name,
        steps=steps,
        atomic=atomic,
        context=context,
        user_info=user_info,
        templates=templates,
        dry_run=dry_run,  # [DECORATIVE] v3.7
    )

    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [DECORATIVE] v3.7: Subflow SSE 进度流
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@bo_action_bp.route('/_chain_stream', methods=['POST'])
def execute_subflow_stream_endpoint():
    """
    SSE 实时推送 subflow 执行进度
    Content-Type: text/event-stream

    事件: start / step_start / step_complete / parallel_group_start / complete
    """
    from meta.core.error_codes import ErrorCode
    from meta.services.auth_middleware import _extract_token
    from meta.services.token_service import TokenService
    from meta.services.token_blacklist_service import token_blacklist_service

    token = _extract_token()
    if not token:
        return jsonify({'success': False, 'data': None, 'message': '未登录', 'code': ErrorCode.UNAUTHORIZED.value}), 401
    try:
        if token_blacklist_service.is_blacklisted(token):
            return jsonify({'success': False, 'data': None, 'message': '登录状态已失效，请重新登录', 'code': ErrorCode.TOKEN_BLACKLISTED.value}), 401
    except Exception:
        return jsonify({'success': False, 'data': None, 'message': '认证服务异常，请稍后重试', 'code': ErrorCode.AUTH_SERVICE_ERROR.value}), 401
    user_info = TokenService.verify_token(token)
    if not user_info:
        return jsonify({'success': False, 'data': None, 'message': '会话已过期，请重新登录', 'code': ErrorCode.TOKEN_EXPIRED.value}), 401

    from flask import request
    if hasattr(g, 'cached_body') and g.cached_body is not None:
        body = g.cached_body
    else:
        body = request.get_json(force=True, silent=True) or {}

    name = body.get('name', 'unnamed_subflow')
    steps = body.get('steps', [])
    atomic = bool(body.get('atomic', False))
    user_info['ip_address'] = request.remote_addr

    from meta.services.subflow_engine import execute_subflow

    # [DECORATIVE] v3.9: 真流式 SSE - gevent WSGIServer 每 yield 立即 flush
    # 不再需要 push app_context, 不再需要一次性 yield 全部
    # 业务收益: 前端能实时看到 step 1 → step 2 → ... 进度

    def generate():
        # [DECORATIVE] v3.9: 关键 - 在 generate 内部使用 gevent 协程 yield
        # gevent 在遇到 IO (registry.call) 时自动切协程
        progress_events = []

        def on_progress(event, data):
            progress_events.append((event, data))

        try:
            # 立即 yield start (客户端立即收)
            yield f'event: start\ndata: {json.dumps({"name": name, "total_steps": len(steps)}, ensure_ascii=False)}\n\n'

            # 真正执行 subflow
            result = execute_subflow(
                registry=bo_action_registry,
                name=name,
                steps=steps,
                atomic=atomic,
                user_info=user_info,
                progress_callback=on_progress,
            )

            # 逐事件 yield - gevent WSGIServer 立即 flush 到客户端
            for event, data in progress_events:
                yield f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n'

            # 最后 final
            yield f'event: final\ndata: {json.dumps(result, ensure_ascii=False, default=str)}\n\n'
        except Exception as e:
            logger.exception(f"[SSE] generate failed: {e}")
            yield f'event: error\ndata: {json.dumps({"error": str(e)}, ensure_ascii=False)}\n\n'

    from flask import Response
    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [DECORATIVE] v3.7: Subflow 模板 CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@bo_action_bp.route('/_subflow_template', methods=['GET'])
def list_subflow_templates():
    """列出所有 server-side subflow 模板"""
    from meta.services.auth_middleware import _extract_token
    from meta.services.token_service import TokenService
    token = _extract_token()
    if not token:
        return jsonify({'success': False, 'data': None, 'message': '未登录'}), 401
    user_info = TokenService.verify_token(token)
    if not user_info:
        return jsonify({'success': False, 'data': None, 'message': '会话已过期，请重新登录'}), 401

    from meta.services.subflow_template_store import SubflowTemplateStore
    templates = SubflowTemplateStore.list_templates()
    return jsonify({
        'success': True,
        'data': {'count': len(templates), 'templates': templates},
        'message': f'Returned {len(templates)} templates',
    })


@bo_action_bp.route('/_subflow_template/<name>', methods=['PUT'])
def upsert_subflow_template(name):
    """创建/更新 server-side subflow 模板"""
    from meta.services.auth_middleware import _extract_token
    from meta.services.token_service import TokenService
    token = _extract_token()
    if not token:
        return jsonify({'success': False, 'data': None, 'message': '未登录'}), 401
    user_info = TokenService.verify_token(token)
    if not user_info:
        return jsonify({'success': False, 'data': None, 'message': '会话已过期，请重新登录'}), 401

    from flask import request
    body = request.get_json(force=True, silent=True) or {}
    description = body.get('description', '')
    steps = body.get('steps', [])

    if not steps:
        return jsonify({'success': False, 'data': None, 'message': '执行步骤不能为空'}), 400

    from meta.services.subflow_template_store import SubflowTemplateStore
    result = SubflowTemplateStore.set(
        name=name,
        steps=steps,
        description=description,
        created_by=user_info.get('user_id'),
    )
    return jsonify(result)


@bo_action_bp.route('/_subflow_template/<name>', methods=['DELETE'])
def delete_subflow_template(name):
    """删除 server-side subflow 模板"""
    from meta.services.auth_middleware import _extract_token
    from meta.services.token_service import TokenService
    token = _extract_token()
    if not token:
        return jsonify({'success': False, 'data': None, 'message': '未登录'}), 401
    user_info = TokenService.verify_token(token)
    if not user_info:
        return jsonify({'success': False, 'data': None, 'message': '会话已过期，请重新登录'}), 401

    from meta.services.subflow_template_store import SubflowTemplateStore
    result = SubflowTemplateStore.delete(name)
    return jsonify(result)


@bo_action_bp.route('/_subflow_template/<name>', methods=['GET'])
def get_subflow_template(name):
    """获取单个模板详情"""
    from meta.services.auth_middleware import _extract_token
    from meta.services.token_service import TokenService
    token = _extract_token()
    if not token:
        return jsonify({'success': False, 'data': None, 'message': '未登录'}), 401
    user_info = TokenService.verify_token(token)
    if not user_info:
        return jsonify({'success': False, 'data': None, 'message': '会话已过期，请重新登录'}), 401

    from meta.services.subflow_template_store import SubflowTemplateStore
    steps = SubflowTemplateStore.get(name)
    if not steps:
        return jsonify({'success': False, 'data': None, 'message': f'模板 {name} 不存在'}), 404
    return jsonify({
        'success': True,
        'data': {'name': name, 'steps': steps, 'step_count': len(steps)},
        'message': 'OK',
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [DECORATIVE] v3.7: Subflow 性能指标
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@bo_action_bp.route('/_subflow_metrics', methods=['GET'])
def subflow_metrics():
    """返回 subflow 执行性能指标"""
    from meta.services.auth_middleware import _extract_token
    from meta.services.token_service import TokenService
    token = _extract_token()
    if not token:
        return jsonify({'success': False, 'data': None, 'message': '未登录'}), 401
    user_info = TokenService.verify_token(token)
    if not user_info:
        return jsonify({'success': False, 'data': None, 'message': '会话已过期，请重新登录'}), 401

    from meta.services.subflow_metrics import SubflowMetrics
    return jsonify({
        'success': True,
        'data': {
            'summary': SubflowMetrics.get_summary(),
            'by_action': SubflowMetrics.get_by_action(),
            'recent': SubflowMetrics.get_recent(20),
        },
        'message': 'OK',
    })


# [DECORATIVE] [NEW] v1.2 / FR-2.1: 提取为独立函数（可被 FR-2.4 全量 OpenAPI 端点复用）
def _generate_action_openapi(base_url: str = 'http://localhost:3010') -> dict:
    """
    生成 Action OpenAPI 3.0 规范（独立函数）

    Returns:
        OpenAPI 3.0 spec dict
    """
    paths = {}
    components_schemas = {}
    tags_set = set()

    for meta in bo_action_registry.list_all():
        path = f'/api/v2/action/{meta.action_id}'
        # OpenAPI path key 不支持 . 替换为 _
        safe_id = meta.action_id.replace('.', '_')
        input_ref = f'#/components/schemas/{safe_id}_input'
        output_ref = f'#/components/schemas/{safe_id}_output'

        # v3.4: 按 operation_type 决定 HTTP method
        if meta.operation_type == 'function':
            method = 'get'
        else:
            method = 'post'

        # v3.6: tag 分组 (function/x vs action/x)
        tag = f'{meta.category or "business"}/{meta.operation_type}'
        tags_set.add(tag)

        operation = {
            'operationId': meta.action_id,
            'summary': meta.description or meta.action_id,
            'tags': [tag],
            'requestBody': {
                'content': {
                    'application/json': {
                        'schema': {'$ref': input_ref}
                    }
                }
            } if method == 'post' else None,
            'parameters': [
                {'name': k, 'in': 'query', 'schema': {'type': 'string'},
                 'required': meta.input_schema.get('required', []).__contains__(k) if meta.input_schema else False}
                for k in (meta.input_schema.get('properties', {}).keys() if meta.input_schema else [])
            ] if method == 'get' and meta.input_schema else None,
            'responses': {
                '200': {
                    'description': 'Success',
                    'content': {
                        'application/json': {
                            'schema': {'$ref': output_ref}
                        }
                    }
                },
                '401': {'description': '未登录'},
                '403': {'description': '权限不足'},
                '404': {'description': 'Action 不存在'},
            }
        }
        if meta.requires_admin:
            operation['description'] = (operation.get('description') or '') + ' (admin only)'

        op_type_label = f'[{meta.operation_type.upper()}]' if meta.operation_type != 'action' else ''
        if op_type_label:
            operation['summary'] = f'{op_type_label} {operation["summary"]}'

        # 移除 None
        operation = {k: v for k, v in operation.items() if v is not None}

        if path not in paths:
            paths[path] = {}
        paths[path][method] = operation

        # Components schemas
        if meta.input_schema:
            components_schemas[f'{safe_id}_input'] = meta.input_schema
        else:
            components_schemas[f'{safe_id}_input'] = {'type': 'object', 'additionalProperties': True}
        if meta.output_schema:
            components_schemas[f'{safe_id}_output'] = meta.output_schema
        else:
            components_schemas[f'{safe_id}_output'] = {
                'type': 'object',
                'properties': {
                    'success': {'type': 'boolean'},
                    'data': {},
                    'message': {'type': 'string'},
                }
            }

    # v3.6 D-2: 完整字段
    return {
        'openapi': '3.0.0',
        'info': {
            'title': 'BO Action API',
            'version': 'v3.6',
            'description': '业务行为 API 统一端点 (Salesforce @AuraEnabled / ServiceNow Flow Designer / Power Platform Custom Connector / SAP CAP / Palantir Foundry 模式)',
            'contact': {
                'name': 'BO Action Team',
                'url': 'https://github.com/excel-to-diagram/bo-action',
            },
            'license': {
                'name': 'MIT',
                'url': 'https://opensource.org/licenses/MIT',
            },
        },
        'servers': [
            {'url': base_url, 'description': '当前服务'},
            {'url': 'http://localhost:3010', 'description': '本地开发'},
        ],
        'tags': [
            {'name': tag, 'description': f'{tag.split("/")[1]} 类型 Action ({tag.split("/")[0]} 域)'}
            for tag in sorted(tags_set)
        ],
        'paths': paths,
        'components': {
            'securitySchemes': {
                'cookieAuth': {
                    'type': 'apiKey',
                    'in': 'cookie',
                    'name': 'auth_token',
                    'description': 'HttpOnly cookie 自动携带 (登录后 set_cookie)',
                }
            },
            'schemas': components_schemas,
        },
        'security': [{'cookieAuth': []}],
    }


@bo_action_bp.route('/_openapi.json', methods=['GET'])
def openapi_spec():
    """
    [DECORATIVE] v3.6 + [NEW] v1.2: Action OpenAPI 3.0 规范输出（重构自内联实现）

    用于:
    - Swagger UI 集成 (/_docs 端点)
    - 客户端代码生成 (openapi-generator)
    - 导入 Postman/Apifox 调试
    """
    from flask import request as _req
    base_url = _req.host_url.rstrip('/')
    return jsonify(_generate_action_openapi(base_url))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [DECORATIVE] v3.6 D-1: Swagger UI 集成
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@bo_action_bp.route('/_docs', methods=['GET'])
def swagger_ui():
    """
    Swagger UI 文档站 (D-1)
    浏览器内浏览所有 Action, 试调
    """
    from flask import Response
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>BO Action API - Swagger UI</title>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui.css">
<style>
  body { margin: 0; padding: 0; }
  .topbar { background: #1f2937; color: #fff; padding: 12px 24px; font-family: sans-serif; }
  .topbar h1 { margin: 0; font-size: 20px; }
  .topbar .meta { color: #9ca3af; font-size: 12px; margin-top: 4px; }
</style>
</head>
<body>
<div class="topbar">
  <h1>BO Action API v3.6</h1>
  <div class="meta">Salesforce @AuraEnabled / ServiceNow Flow Designer / Power Platform / SAP CAP / Palantir 模式</div>
</div>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
<script>
window.onload = () => {
  SwaggerUIBundle({
    url: '/api/v2/action/_openapi.json',
    dom_id: '#swagger-ui',
    deepLinking: true,
    presets: [
      SwaggerUIBundle.presets.apis
    ],
    layout: 'BaseLayout',
    defaultModelsExpandDepth: 2,
    defaultModelExpandDepth: 2,
    tryItOutEnabled: true,
    filter: true,
    requestInterceptor: (req) => {
      // 自动添加 Cookie 认证信息 (浏览器自动带, 这里仅提示)
      console.log('BO Action Swagger UI: ' + req.url);
      return req;
    }
  });
};
</script>
</body>
</html>"""
    return Response(html, mimetype='text/html')


@bo_action_bp.route('/', methods=['GET'])
def list_actions():
    """
    列出所有已注册的业务 Action (调试用)
    """
    items = []
    for m in bo_action_registry.list_all():
        items.append({
            'action_id': m.action_id,
            'description': m.description,
            'object_type': m.object_type,
            'permission_required': m.permission_required,
            'async_supported': m.async_supported,
            'category': m.category,
        })
    return jsonify({
        'success': True,
        'data': {
            'count': len(items),
            'actions': items,
        },
    })


@bo_action_bp.route('/_health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({
        'success': True,
        'data': {
            'registered': len(bo_action_registry.list_ids()),
            'action_ids': bo_action_registry.list_ids(),
        },
        'message': 'bo_action_api healthy',
    })
