# -*- coding: utf-8 -*-
"""
权限包API

提供权限包管理和分配的REST API
"""

from flask import Blueprint, request, jsonify, g
import os

from meta.core.datasource import get_data_source
from meta.services.permission_bundle_service import PermissionBundleService
from meta.services.data_permission_service import DataPermissionService
from meta.services.menu_permission_service import MenuPermissionService
from meta.api.user_api import login_required
from meta.services.auth_middleware import is_admin, get_current_user
from functools import wraps

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or not is_admin(user):
            return jsonify({"success": False, "message": "需要管理员权限"}), 403
        return f(*args, **kwargs)
    return decorated

permission_bundle_bp = Blueprint('permission_bundle', __name__, url_prefix='/api/v1/permission-bundles')

_data_source = None


def _get_data_source():
    global _data_source
    if _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    return _data_source


def _get_bundle_service():
    ds = _get_data_source()
    dps = DataPermissionService(ds)
    mps = MenuPermissionService(ds)
    return PermissionBundleService(ds, dps, mps)


@permission_bundle_bp.route('', methods=['GET'])
@login_required
def get_bundles():
    """获取所有权限包"""
    try:
        service = _get_bundle_service()
        bundles = service.get_all_bundles()
        
        return jsonify({
            'success': True,
            'data': bundles
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@permission_bundle_bp.route('/<bundle_code>', methods=['GET'])
@login_required
def get_bundle(bundle_code):
    """获取指定权限包"""
    try:
        service = _get_bundle_service()
        bundle = service.get_bundle_by_code(bundle_code)
        
        if not bundle:
            return jsonify({
                'success': False,
                'error': f'权限包不存在: {bundle_code}'
            }), 404
        
        return jsonify({
            'success': True,
            'data': bundle
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@permission_bundle_bp.route('/assign', methods=['POST'])
@admin_required
def assign_bundle():
    """将权限包分配给用户"""
    try:
        data = request.get_json()
        # [FIX BUG-005] 原代码 `if not data` 把空 dict {} 也当 falsy, 触发 "请求体不能为空"
        # 改为检查 None: 空 body (Content-Length 0) → 400, 空 dict {} → 走到字段校验
        if data is None:
            return jsonify({
                'success': False,
                'error': '请求体不能为空'
            }), 400

        user_id = data.get('user_id')
        bundle_code = data.get('bundle_code')
        data_resource_ids = data.get('data_resource_ids')
        propagate_to_parents = data.get('propagate_to_parents', True)
        
        if not user_id or not bundle_code:
            return jsonify({
                'success': False,
                'error': '缺少必填字段: user_id, bundle_code'
            }), 400
        
        service = _get_bundle_service()
        result = service.assign_bundle_to_user(
            user_id, bundle_code, data_resource_ids, propagate_to_parents
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'data': result
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('errors', ['分配失败'])
            }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@permission_bundle_bp.route('/user/<int:user_id>', methods=['GET'])
@login_required
def get_user_bundles(user_id):
    """获取用户已分配的权限包"""
    try:
        service = _get_bundle_service()
        bundles = service.get_user_bundles(user_id)
        
        return jsonify({
            'success': True,
            'data': bundles
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@permission_bundle_bp.route('', methods=['POST'])
@admin_required
def create_bundle():
    """创建权限包"""
    try:
        data = request.get_json()
        # [FIX BUG-005] 同上
        if data is None:
            return jsonify({
                'success': False,
                'error': '请求体不能为空'
            }), 400

        required_fields = ['bundle_code', 'bundle_name']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'缺少必填字段: {field}'
                }), 400
        
        service = _get_bundle_service()
        bundle_id = service.create_bundle(data)
        
        if bundle_id:
            return jsonify({
                'success': True,
                'data': {'id': bundle_id}
            })
        else:
            return jsonify({
                'success': False,
                'error': '创建权限包失败'
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@permission_bundle_bp.route('/<bundle_code>', methods=['PUT'])
@admin_required
def update_bundle(bundle_code):
    """更新权限包"""
    try:
        data = request.get_json()
        # [FIX BUG-005] 同上
        if data is None:
            return jsonify({
                'success': False,
                'error': '请求体不能为空'
            }), 400

        service = _get_bundle_service()
        success = service.update_bundle(bundle_code, data)
        
        if success:
            return jsonify({
                'success': True,
                'message': '更新成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '更新失败或权限包不存在/是系统预置'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@permission_bundle_bp.route('/<bundle_code>', methods=['DELETE'])
@admin_required
def delete_bundle(bundle_code):
    """删除权限包"""
    try:
        service = _get_bundle_service()
        success = service.delete_bundle(bundle_code)
        
        if success:
            return jsonify({
                'success': True,
                'message': '删除成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '删除失败或权限包不存在/是系统预置'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
