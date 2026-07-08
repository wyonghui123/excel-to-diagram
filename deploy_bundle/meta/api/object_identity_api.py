# -*- coding: utf-8 -*-
"""
对象标识 API

提供对象标识查询的 RESTful API 接口
"""

from flask import Blueprint, request, jsonify
import logging
import os

from meta.core.datasource import get_data_source
from meta.services.object_identity_service import ObjectIdentityService

logger = logging.getLogger(__name__)

identity_bp = Blueprint('identity', __name__, url_prefix='/api/v1/identity')

_identity_service = None
_data_source = None


def init_services(data_source=None):
    """初始化对象标识服务
    
    Args:
        data_source: 数据源实例。如果为 None，则创建新的 sqlite 数据源。
    """
    global _identity_service, _data_source
    if data_source:
        _data_source = data_source
    elif _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    _identity_service = ObjectIdentityService(_data_source)


def get_identity_service():
    """获取对象标识服务实例"""
    global _identity_service
    if _identity_service is None:
        init_services()
    return _identity_service


@identity_bp.route('', methods=['GET'])
def get_single_identity():
    """
    获取单个对象的完整身份标识
    
    Query Parameters:
        object_type: 对象类型（如 'domain', 'sub_domain' 等）
        object_id: 对象 ID
        format: 输出格式（'full', 'short', 'minimal', 'technical', 'detailed'）
        include_technical: 是否包含技术信息（true/false）
    
    Returns:
        {
            "success": true,
            "data": {
                "formatted": "ERP产品 → V5 → 供应链云 [SUPPLY_CHAIN]",
                "technical": {...},
                "semantic": {...},
                "display": {...},
                "hierarchical": {...}
            }
        }
    """
    try:
        object_type = request.args.get('object_type')
        object_id = request.args.get('object_id')
        format = request.args.get('format', 'full')
        include_technical = request.args.get('include_technical', 'false').lower() == 'true'
        
        if not object_type or not object_id:
            return jsonify({
                'success': False,
                'message': '缺少必需参数：object_type 和 object_id'
            }), 400
        
        try:
            object_id = int(object_id)
        except ValueError:
            return jsonify({
                'success': False,
                'message': 'object_id 必须是整数'
            }), 400
        
        service = get_identity_service()
        result = service.get_identity(object_type, object_id, format, include_technical)
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        logger.error(f"Failed to get identity: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@identity_bp.route('/batch', methods=['POST'])
def get_batch_identities():
    """
    批量获取对象标识
    
    Request Body:
        {
            "requests": [
                {"object_type": "domain", "object_id": 1},
                {"object_type": "domain", "object_id": 2}
            ],
            "format": "short",
            "include_technical": false
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "(domain, 1)": {...},
                "(domain, 2)": {...}
            }
        }
    """
    try:
        data = request.get_json()
        
        if not data or 'requests' not in data:
            return jsonify({
                'success': False,
                'message': '缺少必需参数：requests'
            }), 400
        
        requests = data.get('requests', [])
        format = data.get('format', 'full')
        include_technical = data.get('include_technical', False)
        
        if not isinstance(requests, list):
            return jsonify({
                'success': False,
                'message': 'requests 必须是数组'
            }), 400
        
        request_tuples = []
        for req in requests:
            if not isinstance(req, dict):
                continue
            
            object_type = req.get('object_type')
            object_id = req.get('object_id')
            
            if not object_type or not object_id:
                continue
            
            try:
                object_id = int(object_id)
                request_tuples.append((object_type, object_id))
            except ValueError:
                continue
        
        if not request_tuples:
            return jsonify({
                'success': False,
                'message': '没有有效的请求项'
            }), 400
        
        service = get_identity_service()
        results = service.batch_get_identities(request_tuples, format, include_technical)
        
        serializable_results = {}
        for key, value in results.items():
            str_key = f"({key[0]}, {key[1]})"
            serializable_results[str_key] = value
        
        return jsonify({
            'success': True,
            'data': serializable_results
        })
        
    except Exception as e:
        logger.error(f"Failed to get batch identities: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@identity_bp.route('/formatted', methods=['GET'])
def get_formatted_identity():
    """
    获取格式化的对象标识字符串
    
    Query Parameters:
        object_type: 对象类型
        object_id: 对象 ID
        format: 输出格式
    
    Returns:
        {
            "success": true,
            "data": {
                "formatted": "供应链云 [SUPPLY_CHAIN]"
            }
        }
    """
    try:
        object_type = request.args.get('object_type')
        object_id = request.args.get('object_id')
        format = request.args.get('format', 'short')
        
        if not object_type or not object_id:
            return jsonify({
                'success': False,
                'message': '缺少必需参数：object_type 和 object_id'
            }), 400
        
        try:
            object_id = int(object_id)
        except ValueError:
            return jsonify({
                'success': False,
                'message': 'object_id 必须是整数'
            }), 400
        
        service = get_identity_service()
        formatted = service.get_formatted_identity(object_type, object_id, format)
        
        return jsonify({
            'success': True,
            'data': {
                'formatted': formatted
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get formatted identity: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@identity_bp.route('/cache/clear', methods=['POST'])
def clear_cache():
    """
    清空对象标识服务缓存
    
    Returns:
        {
            "success": true,
            "message": "缓存已清空"
        }
    """
    try:
        service = get_identity_service()
        service.clear_cache()
        
        return jsonify({
            'success': True,
            'message': '缓存已清空'
        })
        
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
