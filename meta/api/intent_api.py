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
from meta.core.bo_framework import bo_framework
from meta.api._deprecation import v1_deprecated

logger = logging.getLogger(__name__)

intent_bp = Blueprint("intent_api", __name__)


def _get_db_path(ds=None):
    """[P1-B4 修复 2026-07-26] 获取 architecture.db 文件路径

    问题: get_data_source('sqlite') 不带 database 参数时, 会创建 :memory: 连接池
         导致 derivation_pipeline 报错 "v3.13+ :memory: 数据库已不支持"
    修复: 直接返回文件路径, 不依赖 datasource (与 EffectiveIntentDAO 一致)
    """
    # 优先: 环境变量 (允许覆盖)
    env_path = os.environ.get('SQLITE_DB_PATH') or os.environ.get('ARCH_DB_PATH')
    if env_path and env_path != ':memory:' and os.path.exists(env_path):
        return env_path
    # 默认: meta/architecture.db (与 _get_db_path in intent_resolver.py 一致)
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db'
    )


# ============================================================
# Intent 权限检查
# ============================================================

@v1_deprecated(migrated_to='/api/v2/permissions/check_intent')
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
                        "error": "用户 ID 和业务对象 ID 不能为空",
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

@v1_deprecated(migrated_to='/api/v2/bos')
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


@v1_deprecated(migrated_to='/api/v2/bos/<bo_id>/actions')
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


@v1_deprecated(migrated_to='/api/v2/bos/<bo_id>/actions/<action_name>')
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

@v1_deprecated(migrated_to='/api/v2/roles/<permission_set_id>/intents')
def list_permission_set_intents(permission_set_id):
    """列出角色的 Intent 权限（FR-017 AC-4）

    Response:
        {
            "success": true,
            "data": [
                {"id": 1, "permission_set_id": 1, "bo_id": "...", "action_name": "...",
                 "granted": true, "source": "manual", ...},
                ...
            ]
        }
    """
    try:
        dao = get_role_intent_dao()
        intents = dao.list_for_role(int(permission_set_id))
        return jsonify({"success": True, "data": intents})
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to list role intents: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


@v1_deprecated(migrated_to='/api/v2/roles/<permission_set_id>/intents/<bo_id>/<action_name>')
def grant_or_deny_intent(permission_set_id, bo_id, action_name):
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

    [P1-B4 补充 2026-07-26] manual intent 变更后触发 derivation_pipeline 重推导
      - FR-013: manual intent 优先级最高, 覆盖 derived/template
      - 调用 derivation_pipeline.derive(permission_set_id) 重新生成 permission_set_effective_intents
      - 失败不阻塞主操作, 仅记录警告
    """
    try:
        payload = request.get_json(force=True, silent=True) or {}
        granted = payload.get("granted", True)
        parameters = payload.get("parameters")
        source = payload.get("source", "manual")

        dao = get_role_intent_dao()
        # [P1-B4 修复 2026-07-26] 移除 bo_framework.transaction() 包装
        # 背景: DAO 已改用 sqlite3.connect() 直连 + conn.commit() (与 EffectiveIntentDAO 一致)
        #       bo_framework.transaction() 不会在新 sqlite3 连接上设置 tx_state,
        #       反而导致 safe_connect_for_write 探测失败 (已移除)
        # 修复: 检查 DAO 返回值, 失败时返回 500 (避免静默 success)
        if granted:
            ok = dao.grant(
                permission_set_id=int(permission_set_id),
                bo_id=bo_id,
                action_name=action_name,
                parameters=parameters,
                source=source,
            )
        else:
            ok = dao.deny(
                permission_set_id=int(permission_set_id),
                bo_id=bo_id,
                action_name=action_name,
                parameters=parameters,
            )

        if not ok:
            return jsonify({
                "success": False,
                "error": f"DAO {'grant' if granted else 'deny'} failed (see server logs)",
            }), 500

        # [P1-B4 补充 2026-07-26] manual intent 变更后触发 derivation 重推导
        # FR-013: manual intent 优先级最高, derive 后会合并到 permission_set_effective_intents
        try:
            from meta.core.permission_flags import is_enabled
            if is_enabled('effective_intents_enabled'):
                from meta.core.derivation_pipeline import PermissionDerivationPipeline
                from meta.core.effective_intent_dao import EffectiveIntentDAO
                # [P1-B4 修复] 不调用 get_data_source('sqlite') (会创建 :memory: 连接池)
                # 直接获取文件路径
                db_path = _get_db_path()
                if db_path:
                    eff_dao = EffectiveIntentDAO(db_path)
                    pipeline = PermissionDerivationPipeline(db_path=db_path, dao=eff_dao)
                    pipeline.derive(permission_set_id=int(permission_set_id))
                    logger.info(
                        f'[P1-B4] derivation_pipeline.derive(permission_set_id={permission_set_id}) '
                        f'completed after manual intent grant/deny '
                        f'(bo={bo_id}, action={action_name}, granted={granted})'
                    )
        except Exception as derive_err:
            logger.warning(
                f'[P1-B4] derivation_pipeline.derive(permission_set_id={permission_set_id}) '
                f'failed (non-fatal): {derive_err}'
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


@v1_deprecated(migrated_to='/api/v2/roles/<permission_set_id>/intents/<bo_id>/<action_name>')
def revoke_intent(permission_set_id, bo_id, action_name):
    """撤销 Intent 权限（FR-017 AC-4）

    [P1-B4 修复 2026-07-26] 移除 bo_framework.transaction() 包装, 检查 DAO 返回值

    [P1-B4 补充 2026-07-26] revoke 后触发 derivation 重推导 (同 grant/deny)

    Response:
        {
            "success": true,
            "data": {"revoked": true, "bo_id": "...", "action_name": "..."}
        }
    """
    try:
        dao = get_role_intent_dao()
        ok = dao.revoke(
            permission_set_id=int(permission_set_id),
            bo_id=bo_id,
            action_name=action_name,
        )

        if not ok:
            return jsonify({
                "success": False,
                "error": "DAO revoke failed (see server logs)",
            }), 500

        # [P1-B4 补充 2026-07-26] revoke 后触发 derivation 重推导
        try:
            from meta.core.permission_flags import is_enabled
            if is_enabled('effective_intents_enabled'):
                from meta.core.derivation_pipeline import PermissionDerivationPipeline
                from meta.core.effective_intent_dao import EffectiveIntentDAO
                # [P1-B4 修复] 不调用 get_data_source('sqlite') (会创建 :memory: 连接池)
                db_path = _get_db_path()
                if db_path:
                    eff_dao = EffectiveIntentDAO(db_path)
                    pipeline = PermissionDerivationPipeline(db_path=db_path, dao=eff_dao)
                    pipeline.derive(permission_set_id=int(permission_set_id))
                    logger.info(
                        f'[P1-B4] derivation_pipeline.derive(permission_set_id={permission_set_id}) '
                        f'completed after manual intent revoke '
                        f'(bo={bo_id}, action={action_name})'
                    )
        except Exception as derive_err:
            logger.warning(
                f'[P1-B4] derivation_pipeline.derive(permission_set_id={permission_set_id}) '
                f'failed (non-fatal): {derive_err}'
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
add_dual_routes(intent_bp, '/roles/<permission_set_id>/intents', list_permission_set_intents, ['GET'])
add_dual_routes(intent_bp, '/roles/<permission_set_id>/intents/<bo_id>/<action_name>', grant_or_deny_intent, ['PUT'])
add_dual_routes(intent_bp, '/roles/<permission_set_id>/intents/<bo_id>/<action_name>', revoke_intent, ['DELETE'])
