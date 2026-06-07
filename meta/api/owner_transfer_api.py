# -*- coding: utf-8 -*-
"""
Owner 转移 API

REST API：
- POST /api/v1/admin/owner/transfer - 单记录 Owner 转移
- POST /api/v1/admin/owner/bulk-transfer - 批量转移（人员离职场景）
- GET /api/v1/admin/owner/transfer-history - 转移历史查询
- POST /api/v1/admin/owner/validate - 转移前校验
"""

from flask import Blueprint, request, jsonify, g
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.core.datasource import get_data_source
from meta.services.owner_transfer_service import OwnerTransferService
from meta.services.auth_middleware import is_admin
from functools import wraps


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        from meta.api.user_api import get_current_user
        user = get_current_user()
        if not user or not is_admin(user):
            return jsonify({"success": False, "message": "需要管理员权限"}), 403
        return f(*args, **kwargs)
    return decorated


owner_transfer_bp = Blueprint('owner_transfer', __name__, url_prefix='/api/v1/admin/owner')

_data_source = None


def _get_data_source():
    global _data_source
    if _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    return _data_source


def _get_service():
    ds = _get_data_source()
    return OwnerTransferService(ds)


def _get_admin_user_id():
    try:
        from meta.api.user_api import get_current_user
        user = get_current_user()
        return user['user_id'] if user else None
    except Exception:
        return None


@owner_transfer_bp.route('/validate', methods=['POST'])
@admin_required
def validate_transfer():
    """转移前校验
    
    请求体：
    {
        "resource_type": "product",
        "resource_id": 42,
        "from_user_id": 1,
        "to_user_id": 2
    }
    
    返回：
    {
        "success": true,
        "data": {
            "is_valid": true,
            "errors": [],
            "warnings": []
        }
    }
    """
    try:
        data = request.get_json() or {}
        required = ['resource_type', 'resource_id', 'from_user_id', 'to_user_id']
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({'success': False, 'error': f'缺少参数: {", ".join(missing)}'}), 400

        svc = _get_service()
        result = svc.validate_transfer(
            data['resource_type'],
            int(data['resource_id']),
            int(data['from_user_id']),
            int(data['to_user_id'])
        )

        return jsonify({'success': True, 'data': result})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@owner_transfer_bp.route('/transfer', methods=['POST'])
@admin_required
def transfer_ownership():
    """单记录 Owner 转移
    
    请求体：
    {
        "resource_type": "product",
        "resource_id": 42,
        "from_user_id": 1,
        "to_user_id": 2,
        "keep_original_permissions": true   // 可选
    }
    
    返回：
    {
        "success": true,
        "data": {
            "transfer_id": 1,
            "old_owner": {...},
            "new_owner": {...},
            "permissions_kept": 0
        }
    }
    """
    try:
        data = request.get_json() or {}
        required = ['resource_type', 'resource_id', 'from_user_id', 'to_user_id']
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({'success': False, 'error': f'缺少参数: {", ".join(missing)}'}), 400

        svc = _get_service()
        admin_user_id = _get_admin_user_id()

        result = svc.transfer_ownership(
            resource_type=data['resource_type'],
            resource_id=int(data['resource_id']),
            from_user_id=int(data['from_user_id']),
            to_user_id=int(data['to_user_id']),
            admin_user_id=admin_user_id,
            keep_original_permissions=data.get('keep_original_permissions')
        )

        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error'), 'data': result}), 400

        return jsonify({
            'success': True,
            'data': result,
            'message': result.get('message', '转移成功')
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@owner_transfer_bp.route('/bulk-transfer', methods=['POST'])
@admin_required
def bulk_transfer_ownership():
    """批量转移（人员离职/转岗场景）
    
    请求体：
    {
        "resource_type": "product",
        "from_user_id": 1,
        "to_user_id": 2
    }
    
    返回：
    {
        "success": true,
        "data": {
            "total": 50,
            "transferred": 48,
            "failed": 2,
            "details": {...}
        }
    }
    """
    try:
        data = request.get_json() or {}
        required = ['resource_type', 'from_user_id', 'to_user_id']
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({'success': False, 'error': f'缺少参数: {", ".join(missing)}'}), 400

        svc = _get_service()
        admin_user_id = _get_admin_user_id()

        result = svc.bulk_transfer(
            resource_type=data['resource_type'],
            from_user_id=int(data['from_user_id']),
            to_user_id=int(data['to_user_id']),
            admin_user_id=admin_user_id
        )

        return jsonify({
            'success': True,
            'data': result,
            'message': f"批量转移完成: {result.get('transferred', 0)}/{result.get('total', 0)}"
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@owner_transfer_bp.route('/transfer-history', methods=['GET'])
@admin_required
def get_transfer_history():
    """查询转移历史
    
    可选参数：
    - resource_type: 按 BO 过滤
    - resource_id: 按记录过滤
    - user_id: 按用户过滤
    - limit: 返回数量（默认 50）
    """
    try:
        svc = _get_service()

        result = svc.get_transfer_history(
            resource_type=request.args.get('resource_type'),
            resource_id=int(request.args['resource_id']) if request.args.get('resource_id') else None,
            user_id=int(request.args['user_id']) if request.args.get('user_id') else None,
            limit=int(request.args.get('limit', 50))
        )

        return jsonify({
            'success': True,
            'data': {
                'transfers': result,
                'count': len(result)
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
