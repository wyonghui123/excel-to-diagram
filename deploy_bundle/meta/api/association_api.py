# -*- coding: utf-8 -*-
"""
通用关联操作与删除 API

提供元模型驱动的标准化接口：
- POST /api/v1/associations/<source_type>/<source_id>/<assoc>/<target_type>/<target_id> - 分配关联
- DELETE /api/v1/associations/<source_type>/<source_id>/<assoc>/<target_type>/<target_id> - 取消关联
- GET /api/v1/associations/<source_type>/<source_id>/<assoc> - 查询成员列表
- DELETE /api/v1/associations/<entity_type>/<entity_id> - 通用删除

对齐 OData 标准：$links 导航属性管理
"""

from flask import Blueprint, request, jsonify, g
from datetime import datetime
import os

from meta.core.datasource import get_data_source
from meta.core.yaml_loader import registry
from meta.services.deletion_service import DeletionService
from meta.services.association_service import AssociationService
from meta.services.auth_middleware import login_required

association_bp = Blueprint('association', __name__, url_prefix='/api/v1/associations')

_data_source = None


def init_association_services(data_source=None):
    """初始化关联服务"""
    global _data_source
    if data_source:
        _data_source = data_source
    elif _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)


def _get_data_source():
    """获取数据源"""
    if _data_source is None:
        init_association_services()
    return _data_source


def _get_current_user():
    """获取当前登录用户信息"""
    user = getattr(g, 'current_user', None)
    if not user:
        return {'user_id': 0, 'username': 'system'}
    return {
        'user_id': user.get('user_id', 0),
        'username': user.get('username', 'system'),
    }


@association_bp.route('/<source_type>/<int:source_id>/<association_name>/<target_type>/<int:target_id>',
                       methods=['POST'])
@login_required
def assign_association(source_type, source_id, association_name, target_type, target_id):
    """
    分配关联 - ASSIGN
    
    对应 OData: POST /Entity(id)/$links/NavigationProperty
    
    Args:
        source_type: 源实体类型 (如 role, user)
        source_id: 源实体 ID
        association_name: 关联名称 (如 users, roles)
        target_type: 目标实体类型
        target_id: 目标实体 ID
        
    Returns:
        201 Created 或 400 Bad Request
    """
    try:
        ds = _get_data_source()
        current_user = _get_current_user()
        
        service = AssociationService(ds, registry)
        result = service.assign(
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            operator_id=current_user['user_id'],
            operator_name=current_user['username'],
            association_name=association_name,
        )
        
        status_code = 201 if result.get('success') else 400
        return jsonify(result), status_code
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'分配失败: {str(e)}'
        }), 500


@association_bp.route('/<source_type>/<int:source_id>/<association_name>/<target_type>/<int:target_id>',
                       methods=['DELETE'])
@login_required
def unassign_association(source_type, source_id, association_name, target_type, target_id):
    """
    取消关联 - REVOKE
    
    对应 OData: DELETE /Entity(id)/$links/NavigationProperty
    
    Returns:
        200 OK 或 400 Bad Request
    """
    try:
        ds = _get_data_source()
        current_user = _get_current_user()
        
        service = AssociationService(ds, registry)
        result = service.unassign(
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            operator_id=current_user['user_id'],
            operator_name=current_user['username'],
            association_name=association_name,
        )
        
        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'取消分配失败: {str(e)}'
        }), 500


@association_bp.route('/<source_type>/<int:source_id>/<association_name>', methods=['GET'])
@login_required
def list_association_members(source_type, source_id, association_name):
    """
    查询关联成员列表 - LIST
    
    对应 OData: GET /Entity(id)/$expand=NavigationProperty
    
    Query Params:
        page: 页码 (默认 1)
        page_size: 每页数量 (默认 20)
        
    Returns:
        200 OK with members list
    """
    try:
        ds = _get_data_source()
        
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        
        service = AssociationService(ds, registry)
        result = service.list_members(
            source_type=source_type,
            source_id=source_id,
            association_name=association_name,
            page=page,
            page_size=page_size,
        )
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'查询失败: {str(e)}',
            'data': [],
            'total': 0,
        }), 500


@association_bp.route('/<entity_type>/<int:entity_id>', methods=['DELETE'])
@login_required
def delete_entity(entity_type, entity_id):
    """
    通用删除接口 - 基于元模型删除策略
    
    自动根据 YAML Schema 中定义的 deletion_policy 执行：
    - RESTRICT 检查：存在强依赖时拒绝删除并返回详情
    - CASCADE 清理：自动清理关联表记录
    - SOFT_DELETE：如果配置了软删除则标记删除
    
    Args:
        entity_type: 实体类型 (如 user, role, product)
        entity_id: 要删除的记录 ID
        
    Returns:
        200 OK 或 400 Bad Request (RESTRICT 违规) 或 404 Not Found
    """
    try:
        ds = _get_data_source()
        current_user = _get_current_user()
        
        service = DeletionService(ds, registry)
        result = service.delete(
            entity_type=entity_type,
            entity_id=entity_id,
            operator_id=current_user['user_id'],
            operator_name=current_user['username'],
        )
        
        if '记录不存在' in result.get('message', ''):
            return jsonify(result), 404
        elif '删除被拒绝' in result.get('message', ''):
            return jsonify(result), 400
        elif result.get('success'):
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'删除失败: {str(e)}'
        }), 500


@association_bp.route('/<entity_type>/deletion-policy', methods=['GET'])
@login_required
def get_deletion_policy(entity_type):
    """
    获取实体的删除策略配置
    
    用于前端展示删除确认对话框中的提示信息。
    
    Returns:
        200 OK with policy configuration
    """
    try:
        obj = None
        if hasattr(registry, 'get'):
            try:
                obj = registry.get(entity_type)
            except Exception:
                pass
        
        if not obj or not hasattr(obj, '_deletion_policy') or obj._deletion_policy is None:
            return jsonify({
                'success': True,
                'has_policy': False,
                'policy': None,
                'message': f'{entity_type} 未配置删除策略，将直接物理删除',
            }), 200
        
        policy = obj._deletion_policy
        policy_dict = {
            'restrict_on': [
                {'table': r.table, 'foreign_key': r.foreign_key, 'message': r.message}
                for r in (policy.restrict_on or [])
            ],
            'cascade_delete': policy.cascade_delete or [],
            'soft_delete': {
                'enabled': policy.soft_delete.enabled if policy.soft_delete else False,
                'field': policy.soft_delete.soft_delete_field if policy.soft_delete else 'deleted_at',
            } if policy.soft_delete else None,
        }
        
        return jsonify({
            'success': True,
            'has_policy': True,
            'policy': policy_dict,
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取策略失败: {str(e)}',
        }), 500
