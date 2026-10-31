# -*- coding: utf-8 -*-
"""统一功能权限判定入口（FR-005）。

所有功能权限判定（API 装饰器、BO 拦截器、管理端校验）都经由此模块，
避免"装饰器查一次 JWT、拦截器再查一次"的两套解析。

职责边界：
- 本模块只做功能权限（resource:action / 声明的权限码）判定；
- 数据范围（行级/维度）判定仍由 DataPermissionInterceptor 等负责。
"""

from dataclasses import dataclass
import logging
from typing import Any, Dict, Iterable, Optional

from meta.core.platform_flags import SHADOW, STRICT, permission_gate_mode

logger = logging.getLogger(__name__)

ADMIN_PERMISSION = '*'

# crud_* 标准动作 → 权限后缀映射（唯一真源）
# list/query 复用 read，避免缺 product:list 时 403
ACTION_PERMISSION_SUFFIX = {
    'crud_create': 'create',
    'crud_read': 'read',
    'crud_update': 'update',
    'crud_delete': 'delete',
    'crud_list': 'read',
    'crud_query': 'read',
}


@dataclass(frozen=True)
class PermissionDecision:
    """一次功能权限判定结果。"""

    allowed: bool
    required: str
    source: str  # declared / canonical / none


def _normalize_permissions(permissions: Any) -> Iterable[str]:
    if not permissions:
        return ()
    if isinstance(permissions, (set, list, tuple, frozenset)):
        return permissions
    try:
        return set(permissions)
    except TypeError:
        return ()


def is_admin_user(user_info: Optional[Dict[str, Any]]) -> bool:
    """拥有 '*' 通配权限即视为管理员。"""
    if not user_info:
        return False
    return ADMIN_PERMISSION in _normalize_permissions(user_info.get('permissions', []))


def user_has_permission(permissions: Any, required: str) -> bool:
    """permissions 集合是否包含 required（支持 '*' 通配）。"""
    if not permissions:
        return False
    return ADMIN_PERMISSION in permissions or required in permissions


def permission_suffix(action: str) -> str:
    """crud_* → 权限后缀；非 CRUD 动作返回空串。"""
    return ACTION_PERMISSION_SUFFIX.get(action, '')


def resolve_declared_permission(object_type: str, action: str) -> Optional[str]:
    """读取元对象声明的权限码（authorization.permissions[action]）。"""
    try:
        from meta.core.models import registry
        meta_obj = registry.get(object_type)
    except Exception:
        return None
    if meta_obj is None:
        return None
    auth = getattr(meta_obj, 'authorization', None)
    if not isinstance(auth, dict) or auth.get('check') is not True:
        return None
    declared = (auth.get('permissions') or {}).get(action)
    return declared or None


def resolve_required_permission(object_type: str, action: str) -> tuple:
    """返回 (required_code, source)；无权限要求时为 ('', 'none')。

    声明式权限优先；未声明时回退到规范的 object_type:suffix。
    """
    declared = resolve_declared_permission(object_type, action)
    if declared:
        return declared, 'declared'
    suffix = permission_suffix(action)
    if not suffix:
        return '', 'none'
    return f'{object_type}:{suffix}', 'canonical'


def _apply_gate_mode(allowed: bool, required: str, source: str) -> bool:
    """按 `PLATFORM_PERMISSION_GATE` 模式收敛判定结果（NFR-005）。

    - strict（默认）：保持强制，拒绝即拒绝
    - shadow：本应拒绝时放行并记 warning（影子观察）
    - off：放行（显式关闭，故障时快速恢复的 fail-open 路径）
    """
    if allowed:
        return True
    mode = permission_gate_mode()
    if mode == STRICT:
        return False
    if mode == SHADOW:
        logger.warning(
            "[permission-gate] shadow: 本应拒绝 %s（来源: %s），按开关放行",
            required, source,
        )
    return True


def evaluate_code(user_info: Optional[Dict[str, Any]], permission_code: str) -> bool:
    """固定权限码判定（供 require_permission 装饰器使用）。"""
    if not permission_code:
        return True
    if is_admin_user(user_info):
        return True
    return _apply_gate_mode(
        user_has_permission((user_info or {}).get('permissions', []), permission_code),
        permission_code,
        'code',
    )


def _decision_cache() -> Optional[Dict[tuple, PermissionDecision]]:
    try:
        from flask import g
        cache = getattr(g, '_permission_decisions', None)
        if cache is None:
            cache = {}
            g._permission_decisions = cache
        return cache
    except Exception:
        return None


def evaluate(user_info: Optional[Dict[str, Any]], object_type: str, action: str) -> PermissionDecision:
    """判定 user 对 object_type 执行 action 的功能权限，并在请求内复用结果。"""
    cache = _decision_cache()
    key = ((user_info or {}).get('user_id') or (user_info or {}).get('id'), object_type, action)
    if cache is not None and key in cache:
        return cache[key]

    required, source = resolve_required_permission(object_type, action)
    if not required:
        decision = PermissionDecision(True, '', 'none')
    else:
        decision = PermissionDecision(
            _apply_gate_mode(
                user_has_permission((user_info or {}).get('permissions', []), required),
                required,
                source,
            ),
            required,
            source,
        )

    if cache is not None:
        cache[key] = decision
    return decision


def declare_permission(action: str):
    """在 API 端点上声明该端点对应的对象权限动作（元数据，由拦截器统一判定）。

    Usage:
        @bo_bp.route('/<object_type>', methods=['POST'])
        @login_required
        @declare_permission('crud_create')
        def create_bo(object_type):
            ...
    """
    def decorator(f):
        f.__permission_action__ = action
        return f
    return decorator
