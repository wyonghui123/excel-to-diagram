# -*- coding: utf-8 -*-
"""
权限同步管理 API

提供权限同步和一致性校验的 REST API：
- POST /api/v1/admin/permissions/sync - 手动触发权限同步
- GET /api/v1/admin/permissions/validate - 一致性校验
- GET /api/v1/admin/permissions/report - 权限报告
"""

from flask import Blueprint, request, jsonify, g
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.core.datasource import get_data_source
from meta.services.permission_sync_service import get_permission_sync_service
from meta.services.auth_middleware import is_admin, login_required
from functools import wraps


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        from meta.api.user_api import get_current_user
        user = get_current_user()
        if not user or not is_admin(user):
            return jsonify({"success": False, "message": "您没有执行此操作的权限，需要管理员权限"}), 403
        return f(*args, **kwargs)
    return decorated


permission_sync_bp = Blueprint('permission_sync', __name__, url_prefix='/api/v1/admin/permissions')

_data_source = None


def _get_data_source():
    global _data_source
    if _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    return _data_source


def _get_sync_service():
    ds = _get_data_source()
    return get_permission_sync_service(ds)


@permission_sync_bp.route('/sync', methods=['POST'])
@admin_required
def sync_permissions():
    """手动触发权限同步
    
    请求体：
    {
        "scope": "all" | "object",
        "object_id": "product"  // 仅当 scope="object" 时需要
    }
    
    返回：
    {
        "success": true,
        "data": {
            "created": ["product:create", ...],
            "updated": [...],
            "existing": [...],
            "orphaned": [...],
            "summary": {...}
        }
    }
    """
    try:
        data = request.get_json() or {}
        scope = data.get('scope', 'all')
        
        svc = _get_sync_service()
        
        if scope == 'object':
            object_id = data.get('object_id')
            if not object_id:
                return jsonify({
                    'success': False,
                    'message': '缺少 object_id 参数'
                }), 400
            
            result = svc.sync_for_object(object_id)
            return jsonify({
                'success': True,
                'data': result,
                'message': f"已同步 {result.get('total', 0)} 项权限，新建 {len(result.get('created', []))} 项"
            })
        else:
            result = svc.sync_all()
            return jsonify({
                'success': True,
                'data': result,
                'message': f"同步完成：新建 {result['summary']['created_count']} 项，更新 {result['summary']['updated_count']} 项"
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@permission_sync_bp.route('/validate', methods=['GET'])
@admin_required
def validate_permissions():
    """一致性校验：检查 YAML actions 与 permissions 表的一致性
    
    返回：
    {
        "success": true,
        "data": {
            "is_consistent": true,
            "missing_permissions": [],
            "extra_permissions": [],
            "expected_count": 100,
            "existing_count": 100,
            "missing_count": 0,
            "extra_count": 0,
            "details": {...}
        }
    }
    """
    try:
        svc = _get_sync_service()
        result = svc.validate_consistency()
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@permission_sync_bp.route('/report', methods=['GET'])
@admin_required
def get_permission_report():
    """获取权限报告：汇总所有 BO 的权限定义情况
    
    返回：
    {
        "success": true,
        "data": {
            "objects": [...],
            "total_objects": 20,
            "total_actions": 100,
            "total_permissions": 100
        }
    }
    """
    try:
        svc = _get_sync_service()
        result = svc.get_permission_report()
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@permission_sync_bp.route('/orphans', methods=['GET'])
@admin_required
def get_orphan_permissions():
    """获取孤儿权限列表（在 DB 中但不在 YAML 中定义的权限）
    
    返回：
    {
        "success": true,
        "data": {
            "orphans": ["old_feature:read", ...],
            "count": 5
        }
    }
    """
    try:
        svc = _get_sync_service()
        validation = svc.validate_consistency()
        
        orphans = validation.get('extra_permissions', [])
        
        return jsonify({
            'success': True,
            'data': {
                'orphans': orphans,
                'count': len(orphans),
                'grouped_by_object': validation.get('details', {}).get('extra_by_object', {})
            }
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@permission_sync_bp.route('/orphans', methods=['DELETE'])
@admin_required
def cleanup_orphan_permissions():
    """清理孤儿权限
    
    请求体：
    {
        "codes": ["old_feature:read", ...]  // 可选，不传则清理所有孤儿权限
    }
    
    返回：
    {
        "success": true,
        "data": {
            "deleted": ["old_feature:read", ...],
            "deleted_count": 5
        }
    }
    """
    try:
        data = request.get_json() or {}
        codes_to_delete = data.get('codes')
        
        svc = _get_sync_service()
        validation = svc.validate_consistency()
        orphans = validation.get('extra_permissions', [])
        
        if codes_to_delete:
            codes_to_delete = [c for c in codes_to_delete if c in orphans]
        else:
            codes_to_delete = orphans
        
        ds = _get_data_source()
        deleted = []
        
        for code in codes_to_delete:
            try:
                ds.execute("DELETE FROM permissions WHERE code = ?", [code])
                deleted.append(code)
            except Exception as e:
                print(f"Failed to delete permission {code}: {e}")
        
        return jsonify({
            'success': True,
            'data': {
                'deleted': deleted,
                'deleted_count': len(deleted)
            },
            'message': f"已删除 {len(deleted)} 项孤儿权限"
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
