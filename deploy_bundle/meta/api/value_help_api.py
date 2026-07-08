from flask import Blueprint, request, jsonify, g
import json
from meta.core.value_help_providers import get_provider
from meta.core.models import ValueHelpSource
from meta.services.auth_middleware import login_required
from meta.services.bo_pick_service import BoPickService

value_help_bp = Blueprint("value_help", __name__)


def _parse_sort(sort_str: str):
    if not sort_str:
        return []
    result = []
    for part in sort_str.split(","):
        parts = part.strip().split(":")
        if len(parts) == 2:
            result.append({"field": parts[0].strip(), "direction": parts[1].strip()})
        elif len(parts) == 1:
            result.append({"field": parts[0].strip(), "direction": "asc"})
    return result


def _get_user_context():
    current_user = getattr(g, "current_user", None) or {}
    roles = current_user.get("roles", [])
    return {
        "user_id": current_user.get("user_id"),
        "roles": roles,
        "is_admin": "admin" in roles if isinstance(roles, list) else False,
    }


@value_help_bp.route("/api/v2/value-help/<source_type>/<source_id>", methods=["GET"])
@login_required
def search_value_help(source_type, source_id):
    source = ValueHelpSource(type=source_type)
    if source_type == "enum":
        source.enum_type_id = source_id
        source.apply_target_permissions = False
    elif source_type == "bo":
        source.target_bo = source_id
        source.value_field = request.args.get("value_field", "id")
        source.display_field = request.args.get("display_field", "name")
        source.code_field = request.args.get("code_field", "code")
        # [V1.2.1 2026-06-16] 从请求参数读取 apply_target_permissions
        # 前端 useValueHelp 会把 YAML 中的 apply_target_permissions 传过来
        # 默认 True (应用权限), 跨域关系创建的级联字段设为 False
        atp = request.args.get("apply_target_permissions", None)
        if atp is not None:
            source.apply_target_permissions = atp.lower() in ("true", "1", "yes")
        value_filter_str = request.args.get("value_filter", "")
        if value_filter_str:
            try:
                source.value_filter = json.loads(value_filter_str)
            except (json.JSONDecodeError, ValueError):
                source.value_filter = {}
        hierarchy_str = request.args.get("hierarchy", "")
        if hierarchy_str:
            try:
                source.hierarchy = json.loads(hierarchy_str)
            except (json.JSONDecodeError, ValueError):
                source.hierarchy = {}
    elif source_type == "custom":
        source.endpoint = source_id
    else:
        return jsonify({"success": False, "error": f"Unknown source type: {source_type}"}), 400

    try:
        provider = get_provider(source)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    search = request.args.get("search", "")
    search_fields = [f.strip() for f in request.args.get("search_fields", "").split(",") if f.strip()]
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("pageSize", request.args.get("page_size", 15)))
    sort = _parse_sort(request.args.get("sort", ""))

    filters = {}
    for key, value in request.args.items():
        if key.startswith("filters["):
            field_name = key[8:-1]
            if value.lower() == "null" or value == "":
                filters[field_name] = None
            else:
                filters[field_name] = value

    user_context = _get_user_context()

    try:
        result = provider.search(
            query=search,
            search_fields=search_fields,
            filters=filters,
            page=page,
            page_size=page_size,
            sort=sort,
            user_context=user_context,
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@value_help_bp.route("/api/v2/value-help/<source_type>/<source_id>/resolve", methods=["GET"])
@login_required
def resolve_value_help(source_type, source_id):
    value = request.args.get("value")
    if not value:
        return jsonify({"success": False, "error": "value parameter is required"}), 400

    source = ValueHelpSource(type=source_type)
    if source_type == "enum":
        source.enum_type_id = source_id
        source.apply_target_permissions = False
    elif source_type == "bo":
        source.target_bo = source_id
        source.value_field = request.args.get("value_field", "id")
        source.display_field = request.args.get("display_field", "name")
        source.code_field = request.args.get("code_field", "code")
        # [V1.2.1 2026-06-16] 从请求参数读取 apply_target_permissions
        atp = request.args.get("apply_target_permissions", None)
        if atp is not None:
            source.apply_target_permissions = atp.lower() in ("true", "1", "yes")
    elif source_type == "custom":
        source.endpoint = source_id
    else:
        return jsonify({"success": False, "error": f"Unknown source type: {source_type}"}), 400

    try:
        provider = get_provider(source)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    user_context = _get_user_context()

    try:
        result = provider.resolve(value, user_context)
        if result is None:
            return jsonify({"success": True, "data": {"value": value, "display": str(value), "code": str(value)}})
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# [V1.2.0 2026-06-15] 跨领域关系 - BO Pick by Code 端点
# Spec: .trae/specs/cross-domain-relationship-permission/spec.md
#
# 设计目的: 解决"前端 ValueHelp List 模式看不到 D2 BO" 的死锁.
#   - List 模式走 read scope 过滤 (现有), U1 看不到 D2 BO
#   - Pick by Code 模式按编码精确选, 不应用 read scope 过滤
#   - 但仍受 WriteScopeInterceptor 写权限校验 (OR-edit, 不绕过)
#
# 安全保证:
#   1. 仍需 dev-login cookie 鉴权 (login_required)
#   2. product_id 必填 (OQ2 决策), 防跨产品误选
#   3. 仅返回非敏感字段 (id, code, name, description, version_id, service_module_id)
#   4. 不返回 owner_id, created_by, updated_by 等敏感字段
# =============================================================================
@value_help_bp.route("/api/v2/bo/business_object/pick_by_code", methods=["GET"])
@login_required
def pick_bo_by_code():
    """[V1.2.0] 按编码精确选取 BO (不应用 read scope 过滤)

    Query:
        code: BO 编码 (必填, 如 BO_B_001)
        product_id: 产品 ID (必填, OQ2 决策, 防跨产品误选)

    Response:
        200: {success: true, data: {id, code, name, description, version_id, service_module_id}}
        400: {success: false, error_code: 'MISSING_CODE' | 'MISSING_PRODUCT_ID' | 'INVALID_PRODUCT_ID'}
        404: {success: false, error_code: 'BO_NOT_FOUND'}
    """
    code = request.args.get("code", "").strip()
    product_id = request.args.get("product_id", "").strip()

    if not code:
        return jsonify({
            "success": False,
            "error_code": "MISSING_CODE",
            "message": "code 参数不能为空",
        }), 400

    if not product_id:
        return jsonify({
            "success": False,
            "error_code": "MISSING_PRODUCT_ID",
            "message": "product_id 参数必填 (OQ2 决策, 防跨产品误选)",
        }), 400

    try:
        product_id_int = int(product_id)
    except ValueError:
        return jsonify({
            "success": False,
            "error_code": "INVALID_PRODUCT_ID",
            "message": f"product_id 必须是整数, 当前: {product_id}",
        }), 400

    # 委派给 BoPickService
    bo = BoPickService.pick_by_code(code=code, product_id=product_id_int)
    if bo is None:
        return jsonify({
            "success": False,
            "error_code": "BO_NOT_FOUND",
            "message": f"BO 编码 {code} 在 product {product_id} 下不存在",
        }), 404

    return jsonify({"success": True, "data": bo})


@value_help_bp.route("/api/v2/bo/business_object/<int:bo_id>", methods=["GET"])
@login_required
def pick_bo_by_id(bo_id: int):
    """[V1.2.0] 按 ID 精确选取 BO

    两个使用场景:
      1. ValueHelp 逃生口 (reason=value_help): 跨域关系创建时选域外 BO, 不应用 read scope 过滤
      2. 默认 (无 reason): 详情页等常规访问, 应用 dim scope 校验

    Path:
        bo_id: BO ID

    Query:
        reason: 可选, "value_help" 表示 ValueHelp 场景, 跳过 dim scope 校验

    Response:
        200: {success: true, data: {id, code, name, ...}}
        404: {success: false, error_code: 'BO_NOT_FOUND'}
    """
    # [FIX v1.2.1 2026-06-16] dim scope 校验
    # 详情页 GET /api/v2/bo/business_object/{id} 命中此路由 (Flask 路由优先级),
    # 绕过了 read_bo 的 _check_single_bo_in_dim_scope, 导致域外 BO 详情可被读取.
    # 修复: 默认应用 dim scope 校验; ValueHelp 场景 (reason=value_help) 跳过,
    # 因为跨域关系创建需要选域外 BO (spec: cross-domain-relationship-permission).
    reason = request.args.get('reason', '')

    # [FIX v1.2.2 2026-06-16] 详情页走完整 bo_framework.read 链路
    # v1.2.0-v1.2.1 一直用 BoPickService.pick_by_id() 取 6 字段 (id/code/name/description/version_id/service_module_id),
    # 该路径不经过 PersistenceInterceptor._do_read + QueryInterceptor._enrich_records + enrich_fk_display_names,
    # 导致业务对象详情的 FK 字段 (domain_id / sub_domain_id / *_display / *_name) 都是空的.
    # list 上能显示是因为 list 走 unified_query_facade, list 路径完整.
    # 修复: 详情页场景 (无 reason) 委托给 bo.read 走完整链路;
    #       ValueHelp 场景保留 BoPickService (跨域选择不需要 read scope 和完整字段).
    if reason != 'value_help':
        from meta.api.bo_api import _check_single_bo_in_dim_scope, _get_bo, _attach_change_history
        _deny = _check_single_bo_in_dim_scope('business_object', bo_id)
        if _deny:
            return jsonify({
                "success": False,
                "error_code": "ACCESS_DENIED",
                "message": "对象不存在或无访问权限",
            }), 404

        # 走完整链路: 物理列 + virtual redundancy + *_name + *_display + display_values
        bo = _get_bo()
        result = bo.read('business_object', bo_id)
        if not result.success:
            return jsonify({
                "success": False,
                "error_code": "BO_NOT_FOUND",
                "message": f"BO ID {bo_id} 不存在",
            }), 404
        _attach_change_history(result.data, 'business_object', bo_id)
        return jsonify({"success": True, "data": result.data})

    # ValueHelp 跨域场景: 走 BoPickService (无 read scope, 只查最小白名单字段)
    bo = BoPickService.pick_by_id(bo_id=bo_id)
    if bo is None:
        return jsonify({
            "success": False,
            "error_code": "BO_NOT_FOUND",
            "message": f"BO ID {bo_id} 不存在",
        }), 404

    return jsonify({"success": True, "data": bo})
