# -*- coding: utf-8 -*-
r"""
Intent API — FR-017 BO 统一模型 Intent API 端点

【背景 2026-06-04】
Spec v1.4 FR-017: BO 统一模型 Intent API
提供 7 个端点：
- POST /api/v1/permissions/check_intent  - 5 步权限检查
- GET  /api/v1/bos                       - 列出所有 BO
- GET  /api/v1/bos/<bo_id>/actions       - 列出 BO 的 actions
- GET  /api/v1/bos/<bo_id>/actions/<action_name> - 获取单个 action 详情
- GET  /api/v1/roles/<id>/intents        - 列出角色的 Intent 权限
- PUT  /api/v1/roles/<id>/intents/<bo>/<action>  - 授予/拒绝 Intent
- DELETE /api/v1/roles/<id>/intents/<bo>/<action> - 撤销 Intent
"""
import logging
import os

from flask import Blueprint, request, jsonify

from meta.core.intent_resolver import (
    get_intent_permission_checker,
    get_role_intent_dao,
)
from meta.core.bo_schema_loader import get_bo_schema_loader

logger = logging.getLogger(__name__)

intent_bp = Blueprint("intent_api", __name__)


# ============================================================
# Intent 权限检查
# ============================================================

def check_intent_permission():
    """FR-017 5 步 Intent 权限检查

    Request Body:
        {
            "user_id": 1,
            "bo_id": "business_object",
            "action_name": "read",
            "parameters": {},   # 可选
            "context": {}       # 可选
        }

    Response:
        {
            "success": true,
            "data": {
                "granted": bool,
                "bo_id": "...",
                "action_name": "...",
                "user_id": 1,
                "steps": [...5 个 step...],
                "reason": "..."
            }
        }
    """
    try:
        payload = request.get_json(force=True, silent=True) or {}
        user_id = payload.get("user_id")
        bo_id = payload.get("bo_id")
        action_name = payload.get("action_name", "read")
        parameters = payload.get("parameters") or {}
        context = payload.get("context") or {}

        if user_id is None or bo_id is None:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "user_id and bo_id are required",
                    }
                ),
                400,
            )

        checker = get_intent_permission_checker()
        result = checker.check(
            user_id=int(user_id),
            bo_id=bo_id,
            action_name=action_name,
            parameters=parameters,
            context=context,
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to check intent permission: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# BO 列表 & Action 查询
# ============================================================

def list_bos():
    """列出所有 BO（FR-017 AC-1）

    Query Params:
        type: 可选，按 BO 类型过滤（entity / service）

    Response:
        {
            "success": true,
            "data": [
                {"bo_id": "business_object", "type": "entity", "name": "..."},
                ...
            ]
        }
    """
    try:
        schema_loader = get_bo_schema_loader()
        schema_dir = schema_loader._schema_dir
        filter_type = request.args.get("type")

        bos = []
        if os.path.isdir(schema_dir):
            for fname in os.listdir(schema_dir):
                if not fname.endswith(".yaml") or fname.startswith("_"):
                    continue
                bo_id = fname[:-5]  # 去掉 .yaml 后缀
                schema = schema_loader.get_bo_schema(bo_id)
                if not schema:
                    continue
                bo_type = schema.get("type", "entity")
                if filter_type and bo_type != filter_type:
                    continue
                bos.append({
                    "bo_id": bo_id,
                    "type": bo_type,
                    "name": schema.get("name", bo_id),
                })

        return jsonify({"success": True, "data": bos})
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to list BOs: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


def list_bo_actions(bo_id):
    """列出 BO 的 actions（FR-017 AC-2）

    Response:
        {
            "success": true,
            "data": [
                {"id": "business_object_read", "name": "...", "action_type": "read"},
                ...
            ]
        }
    """
    try:
        schema_loader = get_bo_schema_loader()
        actions = schema_loader.get_bo_actions(bo_id)
        return jsonify({"success": True, "data": actions})
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to list BO actions: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


def get_bo_action(bo_id, action_name):
    """获取 BO 的单个 action 详情（FR-017 AC-2）

    Response:
        {
            "success": true,
            "data": {"id": "...", "name": "...", "action_type": "read", ...}
        }
    """
    try:
        schema_loader = get_bo_schema_loader()
        action = schema_loader.get_bo_action(bo_id, action_name)
        if action is None:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Action '{action_name}' not found in BO '{bo_id}'",
                    }
                ),
                404,
            )
        return jsonify({"success": True, "data": action})
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to get BO action: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# Role Intent CRUD
# ============================================================

def list_role_intents(role_id):
    """列出角色的 Intent 权限（FR-017 AC-4）

    Response:
        {
            "success": true,
            "data": [
                {"id": 1, "role_id": 1, "bo_id": "...", "action_name": "...",
                 "granted": true, "source": "manual", ...},
                ...
            ]
        }
    """
    try:
        dao = get_role_intent_dao()
        intents = dao.list_for_role(int(role_id))
        return jsonify({"success": True, "data": intents})
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to list role intents: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


def grant_or_deny_intent(role_id, bo_id, action_name):
    """授予或拒绝 Intent 权限（FR-017 AC-4）

    Request Body:
        {
            "granted": true,       # true=授予, false=拒绝
            "parameters": {},      # 可选
            "source": "manual"     # 可选
        }

    Response:
        {
            "success": true,
            "data": {"granted": true, "bo_id": "...", "action_name": "..."}
        }
    """
    try:
        payload = request.get_json(force=True, silent=True) or {}
        granted = payload.get("granted", True)
        parameters = payload.get("parameters")
        source = payload.get("source", "manual")

        dao = get_role_intent_dao()
        if granted:
            dao.grant(
                role_id=int(role_id),
                bo_id=bo_id,
                action_name=action_name,
                parameters=parameters,
                source=source,
            )
        else:
            dao.deny(
                role_id=int(role_id),
                bo_id=bo_id,
                action_name=action_name,
                parameters=parameters,
            )

        return jsonify({
            "success": True,
            "data": {
                "granted": granted,
                "bo_id": bo_id,
                "action_name": action_name,
            },
        })
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to grant/deny intent: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


def revoke_intent(role_id, bo_id, action_name):
    """撤销 Intent 权限（FR-017 AC-4）

    Response:
        {
            "success": true,
            "data": {"revoked": true, "bo_id": "...", "action_name": "..."}
        }
    """
    try:
        dao = get_role_intent_dao()
        dao.revoke(
            role_id=int(role_id),
            bo_id=bo_id,
            action_name=action_name,
        )
        return jsonify({
            "success": True,
            "data": {
                "revoked": True,
                "bo_id": bo_id,
                "action_name": action_name,
            },
        })
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to revoke intent: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


# v1.4 修复：v2 别名路由，用 helper 统一注册
from meta.api._dual_route import add_dual_routes
add_dual_routes(intent_bp, '/permissions/check_intent', check_intent_permission, ['POST'])
add_dual_routes(intent_bp, '/bos', list_bos, ['GET'])
add_dual_routes(intent_bp, '/bos/<bo_id>/actions', list_bo_actions, ['GET'])
add_dual_routes(intent_bp, '/bos/<bo_id>/actions/<action_name>', get_bo_action, ['GET'])
add_dual_routes(intent_bp, '/roles/<role_id>/intents', list_role_intents, ['GET'])
add_dual_routes(intent_bp, '/roles/<role_id>/intents/<bo_id>/<action_name>', grant_or_deny_intent, ['PUT'])
add_dual_routes(intent_bp, '/roles/<role_id>/intents/<bo_id>/<action_name>', revoke_intent, ['DELETE'])
