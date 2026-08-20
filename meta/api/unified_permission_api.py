# -*- coding: utf-8 -*-
"""
Phase 3 统一权限管理 API

[覆盖] P3.1-P3.7
  - permission_rules_v2 CRUD
  - role_effective_intents CRUD
  - 推导管道触发
  - SQL 预览
  - 完整性检查
  - 角色对比
  - 权限模拟

[认证] 复用 login_required (测试时由 before_request 注入 g.current_user)
[DB] 从 app.config['DB_PATH'] 或环境变量 DB_PATH 获取
"""
import json
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app, g, jsonify, request

logger = logging.getLogger(__name__)

unified_permission_bp = Blueprint('unified_permission', __name__, url_prefix='/api/v2')


def _get_db_path() -> str:
    """获取 DB 路径 (优先 app.config, 其次环境变量)"""
    db_path = current_app.config.get('DB_PATH') if current_app else None
    if not db_path:
        db_path = os.environ.get('DB_PATH')
    if not db_path:
        # fallback: 项目默认路径
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_path = os.path.join(project_root, 'db', 'archdata.db')
    return db_path


def _current_user_id() -> Optional[int]:
    """从 g.current_user 获取 user_id"""
    user = getattr(g, 'current_user', None)
    if not user:
        return None
    return user.get('user_id') or user.get('id')


# ============================================================================
# P3.1 permission_rules_v2 CRUD
# ============================================================================
@unified_permission_bp.route('/unified-permission-rules', methods=['GET'])
def list_unified_rules():
    """GET /api/v2/unified-permission-rules?role_id=X&resource_type=Y"""
    try:
        from meta.core.permission_rule_v2_dao import PermissionRuleV2DAO

        dao = PermissionRuleV2DAO(_get_db_path())
        role_id = request.args.get('role_id', type=int)
        resource_type = request.args.get('resource_type')

        if role_id:
            rules = dao.list_by_role(role_id, resource_type)
        else:
            rules = dao.list_all(resource_type)

        return jsonify({'success': True, 'data': rules})
    except Exception as e:
        logger.error(f'[list_unified_rules] {e}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@unified_permission_bp.route('/unified-permission-rules', methods=['POST'])
def create_unified_rule():
    """POST /api/v2/unified-permission-rules"""
    try:
        from meta.core.permission_rule_v2_dao import PermissionRuleV2DAO

        body = request.get_json(silent=True) or {}

        # 必填校验
        role_id = body.get('role_id')
        resource_type = body.get('resource_type')
        if not role_id or not resource_type:
            return jsonify({
                'success': False,
                'message': 'role_id and resource_type are required',
            }), 400

        dao = PermissionRuleV2DAO(_get_db_path())
        rule_id = dao.create(
            role_id=role_id,
            resource_type=resource_type,
            permission_level=body.get('permission_level', 'read'),
            include_conditions=body.get('include_conditions'),
            exclude_conditions=body.get('exclude_conditions'),
            derivation_mode=body.get('derivation_mode', 'static'),
            source=body.get('source', 'manual'),
        )
        return jsonify({'success': True, 'data': {'id': rule_id}}), 201
    except Exception as e:
        logger.error(f'[create_unified_rule] {e}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@unified_permission_bp.route('/unified-permission-rules/<int:rule_id>', methods=['GET'])
def get_unified_rule(rule_id: int):
    """GET /api/v2/unified-permission-rules/<id>"""
    try:
        from meta.core.permission_rule_v2_dao import PermissionRuleV2DAO

        dao = PermissionRuleV2DAO(_get_db_path())
        rule = dao.get(rule_id)
        if not rule:
            return jsonify({'success': False, 'message': 'Rule not found'}), 404
        return jsonify({'success': True, 'data': rule})
    except Exception as e:
        logger.error(f'[get_unified_rule] {e}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@unified_permission_bp.route('/unified-permission-rules/<int:rule_id>', methods=['PUT'])
def update_unified_rule(rule_id: int):
    """PUT /api/v2/unified-permission-rules/<id>"""
    try:
        from meta.core.permission_rule_v2_dao import PermissionRuleV2DAO

        body = request.get_json(silent=True) or {}
        dao = PermissionRuleV2DAO(_get_db_path())

        # 先检查存在
        if not dao.get(rule_id):
            return jsonify({'success': False, 'message': 'Rule not found'}), 404

        affected = dao.update(
            rule_id,
            permission_level=body.get('permission_level'),
            include_conditions=body.get('include_conditions'),
            exclude_conditions=body.get('exclude_conditions'),
            derivation_mode=body.get('derivation_mode'),
            source=body.get('source'),
        )
        return jsonify({'success': True, 'data': {'affected': affected}})
    except Exception as e:
        logger.error(f'[update_unified_rule] {e}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@unified_permission_bp.route('/unified-permission-rules/<int:rule_id>', methods=['DELETE'])
def delete_unified_rule(rule_id: int):
    """DELETE /api/v2/unified-permission-rules/<id>"""
    try:
        from meta.core.permission_rule_v2_dao import PermissionRuleV2DAO

        dao = PermissionRuleV2DAO(_get_db_path())
        affected = dao.delete(rule_id)
        if affected == 0:
            return jsonify({'success': False, 'message': 'Rule not found'}), 404
        return jsonify({'success': True, 'data': {'affected': affected}})
    except Exception as e:
        logger.error(f'[delete_unified_rule] {e}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# P3.2 role_effective_intents CRUD
# ============================================================================
@unified_permission_bp.route('/roles/<int:role_id>/effective-intents', methods=['GET'])
def list_effective_intents(role_id: int):
    """GET /api/v2/roles/<role_id>/effective-intents?bo_id=X&action_name=Y"""
    try:
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        dao = EffectiveIntentDAO(_get_db_path())
        bo_id = request.args.get('bo_id')
        action_name = request.args.get('action_name')

        if bo_id and action_name:
            intents = dao.get_for_bo_action(role_id, bo_id, action_name)
        else:
            intents = dao.list_for_role(role_id)
            if bo_id:
                intents = [i for i in intents if i.get('bo_id') == bo_id]
            if action_name:
                intents = [i for i in intents if i.get('action_name') == action_name]

        return jsonify({'success': True, 'data': intents})
    except Exception as e:
        logger.error(f'[list_effective_intents] {e}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@unified_permission_bp.route(
    '/roles/<int:role_id>/effective-intents/<int:intent_id>', methods=['PUT']
)
def update_effective_intent(role_id: int, intent_id: int):
    """PUT /api/v2/roles/<role_id>/effective-intents/<id> — 更新 data_scope"""
    try:
        body = request.get_json(silent=True) or {}
        data_scope = body.get('data_scope')
        if data_scope is None:
            return jsonify({'success': False, 'message': 'data_scope is required'}), 400

        db_path = _get_db_path()
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                '''UPDATE role_effective_intents
                   SET data_scope = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND role_id = ?''',
                [json.dumps(data_scope, ensure_ascii=False), intent_id, role_id],
            )
            conn.commit()
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Intent not found'}), 404

        return jsonify({'success': True, 'data': {'affected': cursor.rowcount}})
    except Exception as e:
        logger.error(f'[update_effective_intent] {e}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@unified_permission_bp.route(
    '/roles/<int:role_id>/effective-intents/<int:intent_id>', methods=['DELETE']
)
def delete_effective_intent(role_id: int, intent_id: int):
    """DELETE /api/v2/roles/<role_id>/effective-intents/<id>"""
    try:
        db_path = _get_db_path()
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                'DELETE FROM role_effective_intents WHERE id = ? AND role_id = ?',
                [intent_id, role_id],
            )
            conn.commit()
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Intent not found'}), 404

        return jsonify({'success': True, 'data': {'affected': cursor.rowcount}})
    except Exception as e:
        logger.error(f'[delete_effective_intent] {e}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# P3.3 推导管道触发
# ============================================================================
@unified_permission_bp.route('/roles/<int:role_id>/derive', methods=['POST'])
def trigger_derivation(role_id: int):
    """POST /api/v2/roles/<role_id>/derive — 触发推导管道"""
    try:
        from meta.core.derivation_pipeline import PermissionDerivationPipeline
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        db_path = _get_db_path()
        dao = EffectiveIntentDAO(db_path)
        pipeline = PermissionDerivationPipeline(db_path=db_path, dao=dao)
        result = pipeline.derive(role_id=role_id)

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f'[trigger_derivation] {e}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# P3.4 SQL 预览
# ============================================================================
@unified_permission_bp.route('/roles/<int:role_id>/sql-preview', methods=['GET'])
def sql_preview(role_id: int):
    """GET /api/v2/roles/<role_id>/sql-preview?bo_id=X&action=Y"""
    try:
        from meta.core.intent_scope_adapter import IntentScopeAdapter

        bo_id = request.args.get('bo_id')
        action_name = request.args.get('action', 'read')
        if not bo_id:
            return jsonify({'success': False, 'message': 'bo_id is required'}), 400

        user_id = _current_user_id()
        db_path = _get_db_path()
        adapter = IntentScopeAdapter(db_path)
        result = adapter.get_filter_for_roles(
            role_ids=[role_id],
            bo_id=bo_id,
            action_name=action_name,
            user_id=user_id,
        )

        if result is None:
            # 无 Intent → 默认拒绝
            return jsonify({
                'success': True,
                'data': {
                    'cond_expr': '1=0',
                    'params': [],
                    'sources': ['default_deny'],
                },
            })

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f'[sql_preview] {e}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# P3.5 完整性检查
# ============================================================================
@unified_permission_bp.route('/roles/<int:role_id>/completeness', methods=['GET'])
def completeness_check(role_id: int):
    """GET /api/v2/roles/<role_id>/completeness — 红黄绿灯"""
    try:
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        db_path = _get_db_path()
        dao = EffectiveIntentDAO(db_path)
        intents = dao.list_for_role(role_id)

        intent_count = len(intents)
        stale_count = sum(1 for i in intents if i.get('is_stale'))

        # 状态判定:
        # - red: 无 Intent
        # - yellow: 有 Intent 但存在 stale (需要重推导)
        # - green: 有 Intent 且全部最新
        if intent_count == 0:
            status = 'red'
        elif stale_count > 0:
            status = 'yellow'
        else:
            status = 'green'

        return jsonify({
            'success': True,
            'data': {
                'status': status,
                'intent_count': intent_count,
                'stale_count': stale_count,
            },
        })
    except Exception as e:
        logger.error(f'[completeness_check] {e}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# P3.6 角色对比
# ============================================================================
@unified_permission_bp.route('/roles/diff', methods=['GET'])
def role_diff():
    """GET /api/v2/roles/diff?role_a=X&role_b=Y"""
    try:
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        role_a = request.args.get('role_a', type=int)
        role_b = request.args.get('role_b', type=int)
        if not role_a or not role_b:
            return jsonify({
                'success': False,
                'message': 'role_a and role_b are required',
            }), 400

        db_path = _get_db_path()
        dao = EffectiveIntentDAO(db_path)

        intents_a = dao.list_for_role(role_a)
        intents_b = dao.list_for_role(role_b)

        # 用 (bo_id, action_name) 作为 key
        def _key(i):
            return (i['bo_id'], i['action_name'])

        set_a = {_key(i) for i in intents_a}
        set_b = {_key(i) for i in intents_b}

        only_in_a = [i for i in intents_a if _key(i) not in set_b]
        only_in_b = [i for i in intents_b if _key(i) not in set_a]
        common_keys = set_a & set_b
        common = [i for i in intents_a if _key(i) in common_keys]

        return jsonify({
            'success': True,
            'data': {
                'only_in_a': only_in_a,
                'only_in_b': only_in_b,
                'common': common,
            },
        })
    except Exception as e:
        logger.error(f'[role_diff] {e}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# P3.7 权限模拟
# ============================================================================
@unified_permission_bp.route('/permissions/simulate', methods=['POST'])
def permission_simulate():
    """POST /api/v2/permissions/simulate

    Body:
        {
            "role_ids": [100, 101],
            "bo_id": "product",
            "action_name": "read",
            "record_id": 1,
            "user_id": 999  # 可选, 默认从 g.current_user 获取
        }
    """
    try:
        from meta.core.intent_scope_adapter import IntentScopeAdapter

        body = request.get_json(silent=True) or {}

        role_ids = body.get('role_ids')
        bo_id = body.get('bo_id')
        action_name = body.get('action_name')
        record_id = body.get('record_id')
        user_id = body.get('user_id') or _current_user_id()

        if not role_ids or not bo_id or not action_name or record_id is None:
            return jsonify({
                'success': False,
                'message': 'role_ids, bo_id, action_name, record_id are required',
            }), 400

        db_path = _get_db_path()
        adapter = IntentScopeAdapter(db_path)
        result = adapter.check_record_allowed(
            role_ids=role_ids,
            bo_id=bo_id,
            action_name=action_name,
            record_id=record_id,
            user_id=user_id or 0,
        )

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f'[permission_simulate] {e}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500
