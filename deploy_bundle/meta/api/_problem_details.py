# -*- coding: utf-8 -*-
"""
_problem_details.py — RFC 7807 错误响应工厂 (FR-001)

对齐 Stripe / RFC 7807 业界实践:
- 必有字段: type / title / status / detail / instance / code / trace_id / timestamp
- 可选字段: recovery (FR-002 用户可恢复)
"""
from __future__ import annotations
from flask import jsonify, g
from typing import Optional, Dict, Any, List
from datetime import datetime
import urllib.parse
import sys


def _trace_id() -> str:
    """从 flask g 取 trace_id"""
    try:
        return getattr(g, 'trace_id', '') or ''
    except Exception:
        return ''


def _instance() -> str:
    """当前请求路径 (URL-encoded)"""
    try:
        from flask import request
        if request and request.path:
            return urllib.parse.quote(request.path, safe='/')
        return ''
    except Exception:
        return ''


def build(
    *,
    status: int,
    title: str,
    detail: str,
    code: str,
    type_slug: str = None,
    recovery: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
):
    """构造 RFC 7807 ProblemDetails 响应

    Args:
        status: HTTP status code (400/404/422/500 etc.)
        title: 简短标题 (e.g. "Delete Blocked")
        detail: 详细描述
        code: 错误码 (e.g. "DELETE_BLOCKED_HAS_MEMBERS")
        type_slug: 错误类型 slug, 默认 /problems/<code>
        recovery: 用户可恢复提示 (FR-002)
        extra: 附加信息
    Returns:
        (flask Response, status_code) tuple

    Example:
        from meta.api._problem_details import problem
        return problem.delete_blocked(
            object_type='user_group',
            object_id=567,
            reason='HAS_MEMBERS',
            count=12,
        )
    """
    if not type_slug:
        type_slug = f"/problems/{code.lower()}"

    body: Dict[str, Any] = {
        "type": type_slug,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": _instance(),
        "code": code,
        "trace_id": _trace_id(),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    if recovery:
        body["recovery"] = recovery
    if extra:
        body["extra"] = extra
    return jsonify(body), status


# ============ 别名（兼容旧代码） ============
# 保留 problem 作为 build 的别名，兼容旧代码导入
problem = build


# ============ 常见错误工厂 ============

def not_found(resource: str, resource_id: Any = None):
    return build(
        status=404,
        title="Resource Not Found",
        detail=f"{resource} 不存在" + (f" (id={resource_id})" if resource_id else ""),
        code="NOT_FOUND",
        extra={"resource": resource, "resource_id": str(resource_id) if resource_id else None},
    )


def validation_error(field: str, message: str):
    return build(
        status=422,
        title="Validation Failed",
        detail=f"字段 {field} 校验失败: {message}",
        code="VALIDATION_ERROR",
        extra={"field": field, "message": message},
    )


def unauthorized(reason: str = "未登录"):
    return build(
        status=401,
        title="请先登录后再操作",
        detail=reason,
        code="UNAUTHORIZED",
        recovery={
            "type": "redirect",
            "title": "请重新登录",
            "ui_path": "/login",
            "auto_resolvable": False,
        },
    )


def forbidden(reason: str = "权限不足", required_role: str = None):
    return build(
        status=403,
        title="您没有执行此操作的权限",
        detail=reason,
        code="FORBIDDEN",
        extra={"required_role": required_role} if required_role else None,
        recovery={
            "type": "request_access",
            "title": "申请权限",
            "ui_path": "/admin/permissions/request",
            "auto_resolvable": False,
        },
    )


def conflict(reason: str):
    return build(
        status=409,
        title="Conflict",
        detail=reason,
        code="CONFLICT",
    )


def internal_error(reason: str = "服务器内部错误"):
    return build(
        status=500,
        title="Internal Server Error",
        detail=reason,
        code="INTERNAL_ERROR",
        recovery={
            "type": "retry",
            "title": "请重试或联系管理员",
            "auto_resolvable": True,
            "estimated_seconds": 5,
        },
    )


def bad_gateway(reason: str = "上游服务不可用"):
    return build(
        status=502,
        title="Bad Gateway",
        detail=reason,
        code="BAD_GATEWAY",
        recovery={
            "type": "retry",
            "title": "请稍后重试",
            "auto_resolvable": True,
            "estimated_seconds": 30,
        },
    )


def service_unavailable(reason: str = "服务暂不可用"):
    return build(
        status=503,
        title="Service Unavailable",
        detail=reason,
        code="SERVICE_UNAVAILABLE",
        recovery={
            "type": "retry",
            "title": "请稍后重试",
            "auto_resolvable": True,
            "estimated_seconds": 60,
        },
    )


# ============ FR-002: DELETE_BLOCKED recovery ============

_DELETE_BLOCKED_REASONS = {
    "HAS_CHILDREN": {
        "type": "remove_children",
        "title": "请先删除子项",
        "ui_path": "/admin/{object_type}/{object_id}/children",
        "endpoint": "/api/v2/bo/{object_type}/{object_id}/list_children",
        "auto_resolvable": False,
    },
    "HAS_MEMBERS": {
        "type": "remove_members",
        "title": "请先移除成员",
        "ui_path": "/admin/{object_type}/{object_id}/members",
        "endpoint": "/api/v2/bo/{object_type}/{object_id}/members",
        "auto_resolvable": True,
        "batch_endpoint": "/api/v2/bo/{object_type}/{object_id}/batch_unassign",
    },
    "IS_REFERENCED": {
        "type": "remove_references",
        "title": "请先移除外部引用",
        "ui_path": "/admin/{object_type}/{object_id}/references",
        "auto_resolvable": False,
    },
    "IS_SYSTEM": {
        "type": "system_protected",
        "title": "系统级对象, 不可删除",
        "ui_path": None,
        "auto_resolvable": False,
    },
    "HAS_TRANSACTIONS": {
        "type": "archive",
        "title": "存在交易记录, 建议归档而非删除",
        "ui_path": "/admin/{object_type}/{object_id}/archive",
        "auto_resolvable": False,
    },
    "HAS_AUDIT_TRAIL": {
        "type": "archive",
        "title": "存在审计历史, 建议归档",
        "ui_path": "/admin/audit/query?object_type={object_type}&object_id={object_id}",
        "auto_resolvable": False,
    },
    "VERSION_LOCKED": {
        "type": "unlock_version",
        "title": "版本被锁定, 请先解锁",
        "ui_path": "/admin/{object_type}/{object_id}/versions",
        "auto_resolvable": True,
        "endpoint": "/api/v2/bo/{object_type}/{object_id}/versions/unlock",
    },
}


def delete_blocked(
    object_type: str,
    object_id: Any,
    reason: str,
    count: int = None,
    extra_recovery: Dict[str, Any] = None,
):
    """构造 DELETE_BLOCKED 的 RFC 7807 响应 (FR-002)"""
    template = _DELETE_BLOCKED_REASONS.get(
        reason,
        {
            "type": "manual",
            "title": f"删除被阻止 ({reason})",
            "auto_resolvable": False,
        },
    )
    # 模板字符串替换
    recovery: Dict[str, Any] = {}
    for k, v in template.items():
        if isinstance(v, str) and "{" in v:
            try:
                recovery[k] = v.format(object_type=object_type, object_id=object_id)
            except KeyError:
                recovery[k] = v
        else:
            recovery[k] = v
    if count is not None:
        recovery["count"] = count
    if extra_recovery:
        recovery.update(extra_recovery)

    detail_parts = [f"{object_type}#{object_id} 删除被阻止"]
    if reason:
        detail_parts.append(f"原因: {reason}")
    if count is not None:
        detail_parts.append(f"关联 {count} 条")

    return build(
        status=422,
        title="Delete Blocked",
        detail=", ".join(detail_parts),
        code=f"DELETE_BLOCKED_{reason}" if reason else "DELETE_BLOCKED",
        recovery=recovery,
        extra={
            "object_type": object_type,
            "object_id": str(object_id),
            "reason": reason,
            "count": count,
        },
    )


# ============ 自测 ============

if __name__ == "__main__":
    # 不在 flask context, 测 build 工厂
    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context("/api/v2/bo/user_group/567?x=1", headers={"X-Trace-Id": "t123"}):
        resp, status = not_found("user_group", 567)
        print(f"  not_found status={status}")
        print(f"  body: {resp.get_json()}")

    print("\n[OK] ProblemDetails 自测")


# [FIX] 将模块本身导出为 problem，以兼容 from meta.api._problem_details import problem
problem = sys.modules[__name__]
