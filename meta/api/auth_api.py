# -*- coding: utf-8 -*-
"""
认证API

提供登录、登出、获取当前用户信息等接口
"""

from flask import Blueprint, request, jsonify, g, make_response, abort
from meta.services.auth_provider import LocalAuthProvider, _hash_password_pbdkdf2
from meta.services.token_service import TokenService
from meta.services.auth_middleware import login_required, get_current_user, is_admin
from meta.services.rate_limiter import rate_limiter
from meta.services.token_blacklist_service import token_blacklist_service
from meta.core.datasource import get_data_source
import os

auth_bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')


def _is_production():
    """
    [FR-023] 检测当前是否为生产环境。
    多源判断,任一为 True 即视为生产:
    - FLASK_ENV == 'production' (标准 Flask)
    - FLASK_PRODUCTION == 'true' (项目自定义)
    - FLASK_ENV == 'staging' (staging 也视作生产,无 dev-login)

    Returns:
        bool: True 表示生产/staging 环境
    """
    flask_env = os.environ.get('FLASK_ENV', '').lower()
    flask_prod = os.environ.get('FLASK_PRODUCTION', '').lower() == 'true'
    return flask_env in ('production', 'staging') or flask_prod

_data_source = None
_auth_provider = None


def init_auth_services(data_source=None):
    global _data_source, _auth_provider
    if data_source:
        _data_source = data_source
    elif _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    _auth_provider = LocalAuthProvider(_data_source)


def _get_auth_provider():
    if _auth_provider is None:
        init_auth_services()
    return _auth_provider


def _extract_token_from_request():
    token = request.cookies.get('auth_token')
    if token:
        return token
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    return None


@auth_bp.route('/login', methods=['POST'])
def login():
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip is not None and ',' in client_ip:
        client_ip = client_ip.split(',')[0].strip()

    data = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({
            'success': False,
            'message': '用户名和密码不能为空',
        }), 400

    is_locked, lockout_msg = rate_limiter.check_rate_limit(client_ip, username)
    if is_locked:
        return jsonify({
            'success': False,
            'message': lockout_msg,
        }), 429

    provider = _get_auth_provider()
    user_info = provider.authenticate({'username': username, 'password': password})

    if not user_info:
        is_locked, lockout_msg = rate_limiter.record_failed_attempt(client_ip, username)
        if is_locked:
            return jsonify({
                'success': False,
                'message': lockout_msg,
            }), 429
        return jsonify({
            'success': False,
            'message': f'用户名或密码错误 ({lockout_msg})',
        }), 401

    rate_limiter.record_successful_attempt(client_ip, username)

    token, expires_at = TokenService.create_token(user_info)

    cursor = _data_source.execute(
        "SELECT must_change_password FROM users WHERE id = ?",
        [user_info.user_id]
    )
    row = cursor.fetchone()
    must_change_password = bool(row[0]) if row else False

    response = make_response(jsonify({
        'success': True,
        'data': {
            'user': {
                'user_id': user_info.user_id,
                'username': user_info.username,
                'display_name': user_info.display_name,
                'email': user_info.email,
                'roles': user_info.roles,
                'permissions': user_info.permissions,
            },
            'token': token,
            'must_change_password': must_change_password,
        },
        'message': '登录成功',
    }))
    response.set_cookie(
        'auth_token',
        value=token,
        max_age=86400 * 7,
        httponly=True,
        secure=False,
        samesite='Lax',
        path='/',
    )
    return response


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    token = _extract_token_from_request()
    if token:
        payload = TokenService.extract_payload_without_verification(token)
        if payload and 'exp' in payload:
            from datetime import datetime
            expires_at = datetime.utcfromtimestamp(payload['exp'])
            token_blacklist_service.add_to_blacklist(token, expires_at)
    response = make_response(jsonify({
        'success': True,
        'message': '登出成功',
    }))
    response.delete_cookie('auth_token', path='/')
    return response


@auth_bp.route('/me', methods=['GET'])
@login_required
def get_current_user_info():
    user = get_current_user()
    if not user:
        return jsonify({
            'success': False,
            'message': '未登录',
        }), 401

    return jsonify({
        'success': True,
        'data': {
            'user_id': user.get('user_id'),
            'username': user.get('username'),
            'display_name': user.get('display_name'),
            'email': user.get('email'),
            'roles': user.get('roles', []),
            'permissions': user.get('permissions', []),
            'is_admin': is_admin(user),
        },
    })


@auth_bp.route('/dev-login', methods=['GET'])
def dev_login():
    # [FR-023] 生产环境直接 404,隐藏端点存在性
    if _is_production():
        # 不记录日志,避免泄露存在性
        abort(404)

    username = request.args.get('username', 'admin')
    dev_mode = os.environ.get('FLASK_ENV') in ('development', 'dev', None)
    if not dev_mode:
        # 非开发/生产环境(如显式设置其他 FLASK_ENV),返回 403
        return jsonify({'success': False, 'message': '仅开发环境可用'}), 403

    provider = _get_auth_provider()
    cursor = _data_source.execute(
        "SELECT id, username, display_name, email FROM users WHERE username = ?", [username]
    )
    row = cursor.fetchone()
    if not row:
        return jsonify({'success': False, 'message': f'用户 {username} 不存在'}), 404

    cursor2 = _data_source.execute(
        "SELECT r.name, r.code, p.code "
        "FROM roles r "
        "JOIN group_roles gr ON r.id = gr.role_id "
        "JOIN user_group_members ugm ON gr.group_id = ugm.group_id "
        "JOIN users u ON u.id = ugm.user_id "
        "LEFT JOIN role_permissions rp ON r.id = rp.role_id "
        "LEFT JOIN permissions p ON rp.permission_id = p.id "
        "WHERE u.username = ?", [username]
    )
    rows = cursor2.fetchall()
    roles = {}
    permissions = set()
    for r in rows:
        role_key = r[1]
        if role_key not in roles:
            roles[role_key] = {'name': r[0], 'code': r[1]}
        if r[2]:
            permissions.add(r[2])
    roles = list(roles.values())
    permissions = list(permissions)

    from meta.services.auth_provider import UserInfo
    user_info = UserInfo(
        user_id=row[0], username=row[1], display_name=row[2],
        email=row[3], roles=roles, permissions=permissions
    )
    token, _ = TokenService.create_token(user_info)

    response = make_response(jsonify({
        'success': True,
        'data': {'user': {'user_id': row[0], 'username': row[1], 'display_name': row[2]}},
        'message': f'dev-login: {username}',
    }))
    # P2 修复：写 session（兼容 auth_helpers.is_authenticated()）
    from flask import session
    session['user_id'] = row[0]
    session['username'] = row[1]
    session['display_name'] = row[2]
    session['logged_in'] = True
    session.permanent = True
    response.set_cookie(
        'auth_token', value=token,
        max_age=86400 * 7, httponly=True, secure=False,
        samesite='Lax', path='/',
    )
    return response


@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    user = get_current_user()
    user_id = user.get('user_id')
    username = user.get('username', '')

    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip is not None and ',' in client_ip:
        client_ip = client_ip.split(',')[0].strip()

    is_locked, lockout_msg = rate_limiter.check_rate_limit(client_ip, username)
    if is_locked:
        return jsonify({
            'success': False,
            'message': lockout_msg,
        }), 429

    data = request.get_json(silent=True) or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not old_password or not new_password:
        return jsonify({
            'success': False,
            'message': '旧密码和新密码不能为空',
        }), 400

    if len(new_password) < 6:
        return jsonify({
            'success': False,
            'message': '新密码长度不能少于6位',
        }), 400

    provider = _get_auth_provider()
    user_info = provider.authenticate({
        'username': username,
        'password': old_password
    })

    if not user_info:
        is_locked, lockout_msg = rate_limiter.record_failed_attempt(client_ip, username)
        response_data = {
            'success': False,
            'message': '旧密码错误',
        }
        if not is_locked:
            response_data['message'] += f' ({lockout_msg})'
        return jsonify(response_data), 400

    rate_limiter.record_successful_attempt(client_ip, username)

    new_hash = _hash_password_pbdkdf2(new_password)

    with _data_source.transaction():
        _data_source.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
            [new_hash, user_id]
        )

    client_ip_addr = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ',' in client_ip_addr:
        client_ip_addr = client_ip_addr.split(',')[0].strip()

    # [FIX 2026-06-20 P2.3] 改用 AuditLogger (audit-compliance.md §1.3 禁止直接 INSERT)
    # 通过 AuditService.log() 自动获得 transaction_id (P2 v2)
    try:
        from meta.core.action_executor import AuditLogger
        audit_logger = AuditLogger(_data_source)
        audit_logger.log_update(
            object_type='user',
            object_id=user_id,
            old_data={'password_hash': '***'},
            new_data={'password_hash': '***'},
            user_id=user_id,
            user_name=username,
            ip_address=client_ip_addr,
        )
    except Exception as e:
        # 不影响主流程, 仅记录警告
        import logging
        logging.getLogger(__name__).warning(f"[Audit] password change audit failed: {e}")

    return jsonify({
        'success': True,
        'message': '密码修改成功',
    })
