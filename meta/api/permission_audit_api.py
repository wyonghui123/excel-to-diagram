# -*- coding: utf-8 -*-
"""
权限审计API

提供权限审计和报告的REST API
"""

from flask import Blueprint, request, jsonify, g
import os

from meta.core.datasource import get_data_source
from meta.services.permission_audit_service import PermissionAuditService
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

permission_audit_bp = Blueprint('permission_audit', __name__, url_prefix='/api/v1/permission-audit')

_data_source = None


def _get_data_source():
    global _data_source
    if _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    return _data_source


def _get_audit_service():
    ds = _get_data_source()
    dps = DataPermissionService(ds)
    mps = MenuPermissionService(ds)
    return PermissionAuditService(ds, dps, mps)


@permission_audit_bp.route('/report', methods=['GET'])
@admin_required
def get_audit_report():
    """获取权限审计报告"""
    try:
        service = _get_audit_service()
        report = service.generate_audit_report()

        return jsonify({
            'success': True,
            'data': report
        })
    except Exception as e:
        # [FIX BUG-004] 打印 traceback 方便生产诊断
        import traceback
        traceback.print_exc()
        logger = __import__('logging').getLogger(__name__)
        logger.exception("[FIX BUG-004] generate_audit_report failed: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@permission_audit_bp.route('/user/<int:user_id>/summary', methods=['GET'])
@login_required
def get_user_summary(user_id):
    """获取用户权限摘要"""
    try:
        # 只能查看自己的权限摘要，或者管理员可以查看所有人
        current_user_id = g.current_user.get('user_id')
        if user_id != current_user_id:
            user = g.current_user
            if not is_admin(user):
                return jsonify({
                    'success': False,
                    'error': '无权查看其他用户的权限'
                }), 403
        
        service = _get_audit_service()
        summary = service.get_user_permission_summary(user_id)
        
        return jsonify({
            'success': True,
            'data': summary
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@permission_audit_bp.route('/stats', methods=['GET'])
@admin_required
def get_usage_stats():
    """获取权限使用统计"""
    try:
        days = request.args.get('days', 30, type=int)
        service = _get_audit_service()
        stats = service.get_permission_usage_stats(days)
        
        return jsonify({
            'success': True,
            'data': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@permission_audit_bp.route('/orphans', methods=['GET'])
@admin_required
def find_orphan_permissions():
    """查找孤立权限"""
    try:
        service = _get_audit_service()
        orphans = service.find_orphan_permissions()
        
        return jsonify({
            'success': True,
            'data': orphans
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@permission_audit_bp.route('/excessive', methods=['GET'])
@admin_required
def find_excessive_permissions():
    """查找过度权限"""
    try:
        service = _get_audit_service()
        excessive = service.find_excessive_permissions()
        
        return jsonify({
            'success': True,
            'data': excessive
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@permission_audit_bp.route('/history', methods=['GET'])
@admin_required
def get_change_history():
    """获取权限变更历史"""
    try:
        user_id = request.args.get('user_id', type=int)
        resource_type = request.args.get('resource_type')
        limit = request.args.get('limit', 100, type=int)
        
        service = _get_audit_service()
        history = service.get_permission_change_history(user_id, resource_type, limit)
        
        return jsonify({
            'success': True,
            'data': history
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
