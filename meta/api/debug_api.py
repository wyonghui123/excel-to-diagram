# -*- coding: utf-8 -*-
"""
调试 API - 检查当前用户状态
"""

from flask import Blueprint, g, jsonify
from meta.services.auth_middleware import login_required

debug_bp = Blueprint('debug', __name__, url_prefix='/api/v1/debug')


@debug_bp.route('/current-user', methods=['GET'])
@login_required
def get_current_user_debug():
    """获取当前用户调试信息"""
    current = g.current_user
    
    return jsonify({
        'success': True,
        'data': {
            'user_id': current.get('user_id'),
            'username': current.get('username'),
            'display_name': current.get('display_name'),
            'token_version': current.get('token_version'),
            'permissions_count': len(current.get('permissions', [])),
            'has_super': '*' in current.get('permissions', []),
        }
    })
