# -*- coding: utf-8 -*-
r"""
Permission API — FR-012 Match Preview API 端点

【背景 2026-06-04】
Spec v1.4 FR-012: Match Preview API（SAP SU53 Trace 启发）
提供 2 个端点：
- POST /api/v1/permissions/explain  - 解释权限决策（5 步 + SQL 预览）
- POST /api/v1/permissions/check   - 快速权限检查（true/false）
"""
import logging
from flask import Blueprint, request, jsonify

from meta.core.permission_explainer import get_permission_explainer

logger = logging.getLogger(__name__)

permission_bp = Blueprint("permission_api", __name__)


def explain_permission():
    """FR-012 权限决策解释（5 步 + SQL 预览）

    Request Body:
        {
            "user_id": 1,
            "bo_id": "business_object",
            "action_id": "read",   # 可选，默认 'read'
            "parameters": {...},   # 可选
            "context": {...}        # 可选
        }

    Response:
        {
            "success": true,
            "data": {
                "granted": bool,
                "bo_id": "...",
                "action_id": "...",
                "user_id": 1,
                "steps": [...5 个 step...],
                "sql_preview": "SELECT * FROM business_objects WHERE ...",
                "final_condition": "..."
            }
        }
    """
    try:
        payload = request.get_json(force=True, silent=True) or {}
        user_id = payload.get("user_id")
        bo_id = payload.get("bo_id")
        action_id = payload.get("action_id", "read")
        parameters = payload.get("parameters") or {}
        context = payload.get("context") or {}

        if user_id is None or bo_id is None:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "用户 ID 和业务对象 ID 不能为空",
                    }
                ),
                400,
            )

        explainer = get_permission_explainer()
        result = explainer.explain(
            user_id=int(user_id),
            bo_id=bo_id,
            action_id=action_id,
            parameters=parameters,
            context=context,
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to explain permission: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


def check_permission():
    """快速权限检查（true/false）

    Request Body:
        {
            "user_id": 1,
            "bo_id": "business_object",
            "action_id": "read"
        }

    Response:
        {
            "success": true,
            "data": {"granted": true}
        }
    """
    try:
        payload = request.get_json(force=True, silent=True) or {}
        user_id = payload.get("user_id")
        bo_id = payload.get("bo_id")
        action_id = payload.get("action_id", "read")
        if user_id is None or bo_id is None:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "用户 ID 和业务对象 ID 不能为空",
                    }
                ),
                400,
            )
        explainer = get_permission_explainer()
        result = explainer.explain(
            user_id=int(user_id),
            bo_id=bo_id,
            action_id=action_id,
        )
        return jsonify({"success": True, "data": {"granted": result["granted"]}})
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to check permission: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


# v1.4 修复：用 helper 注册 v2 别名（v1 保留作过渡）
from meta.api._dual_route import add_dual_routes
add_dual_routes(permission_bp, "/permissions/explain", explain_permission, ["POST"])
add_dual_routes(permission_bp, "/permissions/check", check_permission, ["POST"])
