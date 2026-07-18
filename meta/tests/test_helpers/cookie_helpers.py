"""
cookie_helpers - 简化 cookie/header 生成 (Phase 7 重构)

替代各测试文件中重复的:
- 创建 UserInfo + TokenService.create_token() + 拼 headers
"""
from typing import Optional, List, Dict, Any


def make_test_user(user_id: str = '1',
                   username: str = 'test_user',
                   roles: Optional[List[str]] = None,
                   permissions: Optional[List[str]] = None) -> Any:
    """
    构造测试用 UserInfo (避免重复的 UserInfo 构造代码)

    Args:
        user_id: 用户 ID
        username: 用户名
        roles: 角色列表 (默认 ['user'])
        permissions: 权限列表 (默认 ['read'])

    Returns:
        UserInfo 实例
    """
    from meta.services.auth_provider import UserInfo

    return UserInfo(
        user_id=user_id,
        username=username,
        display_name=username.replace('_', ' ').title(),
        email=f'{username}@test.com',
        roles=roles or ['user'],
        permissions=permissions or ['read'],
    )


def _build_headers(user_info) -> Dict[str, str]:
    """从 UserInfo 生成 HTTP headers"""
    from meta.services.token_service import TokenService

    token, _ = TokenService.create_token(user_info)
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': str(user_info.user_id),
        'X-User-Name': user_info.username,
    }


def admin_cookie(user_id: str = '1', username: str = 'admin') -> Dict[str, str]:
    """
    生成管理员认证头 (cookie 替代名 - 因为本质是 header)

    Returns:
        {'Content-Type': ..., 'Authorization': 'Bearer xxx', 'X-User-Id': '1', 'X-User-Name': 'admin'}
    """
    user = make_test_user(
        user_id=user_id,
        username=username,
        roles=['admin'],
        permissions=['*'],
    )
    return _build_headers(user)


def user_cookie(user_id: str = '2',
                username: str = 'test_user',
                roles: Optional[List[str]] = None,
                permissions: Optional[List[str]] = None) -> Dict[str, str]:
    """
    生成普通用户认证头

    Returns:
        标准 HTTP headers
    """
    user = make_test_user(
        user_id=user_id,
        username=username,
        roles=roles,
        permissions=permissions,
    )
    return _build_headers(user)