# -*- coding: utf-8 -*-
"""
[Plan B Task 9] 组织多职能视图 API (对齐 spec 13 §5.1d)

路由:
  GET    /api/v1/orgs/<org_id>/functions       — 列出某 org 的所有职能
  POST   /api/v1/orgs/<org_id>/functions       — 添加新职能
  DELETE /api/v1/orgs/<org_id>/functions/<fn>  — 移除某职能
"""
from flask import Blueprint, request, jsonify
from meta.services.auth_middleware import login_required, is_admin
from meta.services.org_function_service import OrgFunctionService
from meta.core.datasource import get_data_source

org_function_bp = Blueprint('org_function', __name__, url_prefix='/api/v1/orgs/<int:org_id>/functions')

_data_source = None
_function_service = None


def init_org_function_services(data_source=None):
    """初始化 org_function 服务"""
    global _data_source, _function_service
    if data_source:
        _data_source = data_source
    elif _data_source is None:
        _data_source = get_data_source("sqlite", database="meta/architecture.db")
    _function_service = OrgFunctionService(_data_source)


def _get_function_service():
    if _function_service is None:
        init_org_function_services()
    return _function_service


@org_function_bp.route('', methods=['GET'])
@login_required
def list_functions(org_id):
    """获取 org 的所有职能"""
    svc = _get_function_service()
    funcs = svc.get_functions_by_org(org_id)
    return jsonify({'success': True, 'data': funcs})


@org_function_bp.route('', methods=['POST'])
@login_required
@is_admin
def add_function(org_id):
    """添加新职能"""
    data = request.get_json() or {}
    function_type = data.get('function_type')
    is_primary = data.get('is_primary', False)

    if not function_type:
        return jsonify({'success': False, 'message': 'function_type required'}), 400

    svc = _get_function_service()
    new_id = svc.add_function(org_id, function_type, is_primary)

    if new_id:
        return jsonify({'success': True, 'data': {'id': new_id}})
    return jsonify({'success': False, 'message': 'Invalid function_type'}), 400


@org_function_bp.route('/<function_type>', methods=['DELETE'])
@login_required
@is_admin
def remove_function(org_id, function_type):
    """移除某职能"""
    svc = _get_function_service()
    success = svc.remove_function(org_id, function_type)
    return jsonify({'success': success})


@org_function_bp.route('/primary', methods=['GET'])
@login_required
def get_primary_function(org_id):
    """获取 org 的主职能"""
    svc = _get_function_service()
    primary = svc.get_primary_function(org_id)
    return jsonify({'success': True, 'data': primary})
