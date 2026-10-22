# -*- coding: utf-8 -*-
"""
[Plan B Task 9] 组织多职能视图 API (对齐 spec 13 §5.1d)

路由:
  GET    /api/v1/orgs/<org_id>/functions       — 列出某 org 的所有职能
  POST   /api/v1/orgs/<org_id>/functions       — 添加新职能
  DELETE /api/v1/orgs/<org_id>/functions/<fn>  — 移除某职能
"""
from flask import Blueprint, request, jsonify
from meta.services.auth_middleware import login_required, is_admin, get_current_user
from meta.services.org_function_service import OrgFunctionService, SUBJECT_FUNCTIONS
from meta.core.platform_modules import is_module_enabled
from meta.core.datasource import get_data_source
from meta.core.db_path import get_meta_db_path

org_function_bp = Blueprint('org_function', __name__, url_prefix='/api/v1/orgs/<int:org_id>/functions')

_data_source = None
_function_service = None


def init_org_function_services(data_source=None):
    """初始化 org_function 服务"""
    global _data_source, _function_service
    if data_source:
        _data_source = data_source
    elif _data_source is None:
        _data_source = get_data_source("sqlite", database=get_meta_db_path())
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
def add_function(org_id):
    """添加新职能"""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Admin required'}), 403
    data = request.get_json() or {}
    function_type = data.get('function_type')
    is_primary = data.get('is_primary', False)

    if not function_type:
        return jsonify({'success': False, 'message': 'function_type required'}), 400

    # [模块门控] party 关闭（BIP 应用架构管理部署）时 org 是应用架构节点，
    #   授予我方主体职能会把架构节点变成「法人/业务单元」（语义污染），且会让
    #   party 轴半可用 —— 直接拒绝，口径与 DISABLED_PLATFORM_MODULES=party 一致。
    if function_type in SUBJECT_FUNCTIONS and not is_module_enabled('party'):
        return jsonify({
            'success': False,
            'message': '当前部署未启用往来关系（party 模块），'
                       '不允许授予我方主体职能（legal_entity / management_unit）',
        }), 409

    svc = _get_function_service()
    new_id = svc.add_function(org_id, function_type, is_primary)

    if new_id:
        return jsonify({'success': True, 'data': {'id': new_id}})
    return jsonify({'success': False, 'message': 'Invalid function_type'}), 400


@org_function_bp.route('/<function_type>', methods=['DELETE'])
@login_required
def remove_function(org_id, function_type):
    """移除某职能"""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Admin required'}), 403
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
