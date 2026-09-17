# -*- coding: utf-8 -*-
"""
v1 API 废弃状态统一标记装饰器

解决 v1 端点废弃状态三态不一致问题：
- 有的返回 410 Gone
- 有的返回 200 + _deprecated: true
- 有的正常工作（未标记）

统一为 4 种状态：
- ACTIVE    : 正常使用（200，无标记）
- DEPRECATED: 可用但警告（200 + _deprecated: true + sunset_at）
- SUNSET    : 已迁移（410 Gone + migrated_to）
- REMOVED   : 已删除（404 Not Found）

使用示例：

    from meta.api._deprecation import v1_deprecated, v1_sunset, v1_removed

    # 1. 标记为 DEPRECATED（仍可用，但前端应迁移）
    @role_v1_bp.route('/<int:role_id>/logs')
    @v1_deprecated(migrated_to='/api/v2/bo/role/<int:role_id>/logs')
    def get_role_logs(role_id):
        ...

    # 2. 标记为 SUNSET（返回 410，前端不能再调用）
    @role_v1_bp.route('/permissions')
    @v1_sunset(migrated_to='/api/v2/bo/permission')
    def list_permissions():
        ...

    # 3. 标记为 REMOVED（返回 404）
    @role_v1_bp.route('/old-endpoint')
    @v1_removed()
    def old_endpoint():
        ...

响应头（所有废弃状态都会添加）：
- X-API-Version: v1
- X-API-Status: DEPRECATED | SUNSET | REMOVED
- X-API-Sunset-At: 2026-09-01（仅 DEPRECATED）
- X-API-Migrated-To: /api/v2/...（DEPRECATED + SUNSET）

注意：
- ACTIVE 状态不需要装饰器（默认就是 ACTIVE）
- 装饰器只用于 v1 端点，v2 端点不需要
"""
from functools import wraps
from typing import Optional

from flask import jsonify, request, g


# 废弃状态枚举
DEPRECATION_ACTIVE = 'ACTIVE'
DEPRECATION_DEPRECATED = 'DEPRECATED'
DEPRECATION_SUNSET = 'SUNSET'
DEPRECATION_REMOVED = 'REMOVED'

# 默认 sunset 日期（DEPRECATED 状态的默认过渡期）
DEFAULT_SUNSET_DATE = '2026-12-31'


def _add_deprecation_headers(response, status, migrated_to=None, sunset_at=None):
    """添加废弃状态相关的响应头"""
    response.headers['X-API-Version'] = 'v1'
    response.headers['X-API-Status'] = status
    if migrated_to:
        response.headers['X-API-Migrated-To'] = migrated_to
    if sunset_at:
        response.headers['X-API-Sunset-At'] = sunset_at
    return response


def v1_deprecated(migrated_to: str, sunset_at: str = DEFAULT_SUNSET_DATE):
    """
    标记 v1 端点为 DEPRECATED 状态

    行为：
    - 正常执行原函数
    - 在响应中注入 _deprecated: true 标记
    - 添加 X-API-Status: DEPRECATED 响应头
    - 前端可继续使用，但应尽快迁移

    参数：
    - migrated_to: v2 对应端点路径（如 '/api/v2/bo/role'）
    - sunset_at: 计划完全下线的日期（默认 2026-12-31）
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            result = f(*args, **kwargs)

            # 处理 (response, status_code) 元组返回值
            if isinstance(result, tuple):
                response, status_code = result[0], result[1]
            else:
                response, status_code = result, None

            # 注入废弃标记到 JSON 响应
            if hasattr(response, 'get_json') and response.get_json() is not None:
                data = response.get_json()
                if isinstance(data, dict):
                    data['_deprecated'] = True
                    data['_migrated_to'] = migrated_to
                    data['_sunset_at'] = sunset_at
                    response = jsonify(data)

            response = _add_deprecation_headers(
                response, DEPRECATION_DEPRECATED, migrated_to, sunset_at
            )

            # 保留原始返回格式（元组或 Response）
            if status_code is not None:
                return (response, status_code)
            return response

        # 标记元信息（供 audit_v1_endpoints.py 扫描）
        wrapper._v1_status = DEPRECATION_DEPRECATED
        wrapper._v1_migrated_to = migrated_to
        wrapper._v1_sunset_at = sunset_at
        return wrapper
    return decorator


def v1_sunset(migrated_to: str):
    """
    标记 v1 端点为 SUNSET 状态

    行为：
    - 不执行原函数
    - 直接返回 410 Gone
    - 响应体包含迁移指引
    - 前端不应再调用此端点

    参数：
    - migrated_to: v2 对应端点路径
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            response = jsonify({
                'success': False,
                'code': 'API_GONE',
                'message': f'{request.path} 已下线，请使用 {migrated_to}',
                'migrated_to': migrated_to,
            })
            response.status_code = 410
            response = _add_deprecation_headers(
                response, DEPRECATION_SUNSET, migrated_to
            )
            return response

        wrapper._v1_status = DEPRECATION_SUNSET
        wrapper._v1_migrated_to = migrated_to
        return wrapper
    return decorator


def v1_removed():
    """
    标记 v1 端点为 REMOVED 状态

    行为：
    - 不执行原函数
    - 直接返回 404 Not Found
    - 端点已完全删除，无迁移路径

    使用场景：端点已物理删除但路由仍保留（防止前端报 500）
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            response = jsonify({
                'success': False,
                'code': 'API_REMOVED',
                'message': f'{request.path} 已删除',
            })
            response.status_code = 404
            response = _add_deprecation_headers(response, DEPRECATION_REMOVED)
            return response

        wrapper._v1_status = DEPRECATION_REMOVED
        return wrapper
    return decorator


def get_endpoint_status(view_func) -> str:
    """
    获取端点的废弃状态（供扫描脚本使用）

    返回值：ACTIVE | DEPRECATED | SUNSET | REMOVED
    """
    return getattr(view_func, '_v1_status', DEPRECATION_ACTIVE)


def get_endpoint_migrated_to(view_func) -> Optional[str]:
    """获取端点的迁移目标路径（供扫描脚本使用）"""
    return getattr(view_func, '_v1_migrated_to', None)


def get_endpoint_sunset_at(view_func) -> Optional[str]:
    """获取端点的计划下线日期（供扫描脚本使用）"""
    return getattr(view_func, '_v1_sunset_at', None)
