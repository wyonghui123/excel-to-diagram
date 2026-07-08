# -*- coding: utf-8 -*-
"""
集中式用户可见消息常量 + i18n key 引用 (P4 2026-06-19)

目的：
- 消除后端 354+ 处 hardcoded 重复消息
- 统一"管理员权限"/"用户不存在"等高频消息
- 支持后续 i18n 扩展

设计原则：
- 单一来源：所有用户可见消息都集中在此
- 兼容现有调用：保留 helper 函数 t(key) 用于 .format(**params)
- 错误码：每个 message 对应一个 code (RFC 7807 兼容)

用法：
    from meta.api._messages import t, MSG_ADMIN_REQUIRED
    return jsonify({'success': False, 'message': t('auth.admin_required')}), 403
    # 或直接用常量
    return jsonify({'success': False, 'message': MSG_ADMIN_REQUIRED}), 403
"""
from typing import Any, Dict, Optional

# ========== 高频消息常量（直接复用，避免重复字符串） ==========

# 权限类
MSG_ADMIN_REQUIRED = "您没有执行此操作的权限，需要管理员权限"  # 业务化（用户友好）
MSG_PERMISSION_DENIED = "您没有执行此操作的权限"  # 通用
MSG_UNAUTHORIZED = "请先登录后再操作"  # 业务化
MSG_FORBIDDEN = "您没有执行此操作的权限"

# 认证类
MSG_SESSION_EXPIRED = "会话已过期，请重新登录"
MSG_TOKEN_INVALID = "登录状态已失效，请重新登录"
MSG_AUTH_SERVICE_ERROR = "认证服务异常，请稍后重试"

# 资源不存在
MSG_USER_NOT_FOUND = "用户不存在"
MSG_ROLE_NOT_FOUND = "角色不存在"
MSG_RECORD_NOT_FOUND = "记录不存在"
MSG_ANNOTATION_NOT_FOUND = "标注不存在"
MSG_SUBSCRIPTION_NOT_FOUND = "订阅不存在"

# 请求校验
MSG_BODY_REQUIRED = "请求内容不能为空"
MSG_INVALID_ID = "ID 无效"
MSG_INVALID_PARAMS = "请求参数有误"
MSG_TARGET_ID_REQUIRED = "目标 ID 不能为空"
MSG_TARGET_TYPE_REQUIRED = "目标类型不能为空"

# 系统角色
MSG_SYSTEM_ROLE_IMMUTABLE = "系统内置角色不能修改或删除"

# 操作成功（业务化，已存在 - 由 useMessage 处理）
MSG_LOGIN_SUCCESS = "登录成功"
MSG_LOGOUT_SUCCESS = "已安全退出"
MSG_PASSWORD_CHANGED = "密码修改成功"
MSG_USER_UPDATED = "用户信息已更新"
MSG_USER_CREATED = "用户已创建"
MSG_USER_DELETED = "用户已删除"
MSG_PROFILE_UPDATED = "个人信息已更新"

# 验证
MSG_USERNAME_REQUIRED = "用户名不能为空"
MSG_USERNAME_TOO_SHORT = "用户名长度不能少于3位"
MSG_PASSWORD_TOO_SHORT = "密码长度不能少于6位"
MSG_PASSWORD_REQUIRED = "密码不能为空"
MSG_OLD_PASSWORD_WRONG = "当前密码不正确"
MSG_USERNAME_EXISTS = "用户名已存在"
MSG_PASSWORD_MISMATCH = "两次输入的密码不一致"

# ========== i18n key 表（用于前端 i18n + 后端 future expansion） ==========

_I18N_KEYS: Dict[str, str] = {
    # auth
    "auth.session_expired": MSG_SESSION_EXPIRED,
    "auth.token_invalid": MSG_TOKEN_INVALID,
    "auth.unauthorized": MSG_UNAUTHORIZED,
    "auth.login_success": MSG_LOGIN_SUCCESS,
    "auth.logout_success": MSG_LOGOUT_SUCCESS,
    "auth.password_changed": MSG_PASSWORD_CHANGED,
    "auth.password_too_short": MSG_PASSWORD_TOO_SHORT,
    "auth.password_required": MSG_PASSWORD_REQUIRED,
    "auth.old_password_wrong": MSG_OLD_PASSWORD_WRONG,
    "auth.username_required": MSG_USERNAME_REQUIRED,
    "auth.username_too_short": MSG_USERNAME_TOO_SHORT,
    "auth.username_exists": MSG_USERNAME_EXISTS,
    "auth.password_mismatch": MSG_PASSWORD_MISMATCH,
    # permission
    "permission.admin_required": MSG_ADMIN_REQUIRED,
    "permission.forbidden": MSG_FORBIDDEN,
    "permission.denied": MSG_PERMISSION_DENIED,
    "permission.system_role_immutable": MSG_SYSTEM_ROLE_IMMUTABLE,
    # user
    "user.not_found": MSG_USER_NOT_FOUND,
    "user.updated": MSG_USER_UPDATED,
    "user.created": MSG_USER_CREATED,
    "user.deleted": MSG_USER_DELETED,
    "user.profile_updated": MSG_PROFILE_UPDATED,
    # role
    "role.not_found": MSG_ROLE_NOT_FOUND,
    # common
    "common.not_found": MSG_RECORD_NOT_FOUND,
    "common.body_required": MSG_BODY_REQUIRED,
    "common.invalid_id": MSG_INVALID_ID,
    "common.invalid_params": MSG_INVALID_PARAMS,
    "common.annotation_not_found": MSG_ANNOTATION_NOT_FOUND,
    "common.subscription_not_found": MSG_SUBSCRIPTION_NOT_FOUND,
    "common.target_id_required": MSG_TARGET_ID_REQUIRED,
    "common.target_type_required": MSG_TARGET_TYPE_REQUIRED,
    "common.auth_service_error": MSG_AUTH_SERVICE_ERROR,
}


def t(key: str, default: Optional[str] = None, **params) -> str:
    """
    翻译辅助函数 - 从 i18n key 查找消息
    未来支持多语言时，只需扩展 _I18N_KEYS 表

    Args:
        key: i18n key
        default: 如果 key 不存在时的默认消息
        **params: 格式化参数

    Usage:
        t('auth.session_expired')  # '会话已过期，请重新登录'
        t('user.not_found', user='admin')  # '用户 admin 不存在'
    """
    msg = _I18N_KEYS.get(key, default or key)
    if params:
        try:
            return msg.format(**params)
        except (KeyError, IndexError):
            return msg
    return msg
