from flask import Blueprint, request, jsonify, g
import json
from meta.core.value_help_providers import get_provider
from meta.core.models import ValueHelpSource
from meta.services.auth_middleware import login_required

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
