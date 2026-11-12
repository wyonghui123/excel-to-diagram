# -*- coding: utf-8 -*-
"""规则中心 API（FR-014 / FR-015 / FR-017 / FR-018，IF-003 / IF-006 / IF-007 / IF-008）。

端点：
    GET  /api/v2/rules                  规则目录（多来源聚合 + 筛选）
    GET  /api/v2/rules/view-config      规则中心视图元数据
    GET  /api/v2/rules/<rule_key>       规则详情
    POST /api/v2/rules/simulate         规则试算（IF-008，只读）
    GET  /api/v2/rules/config/history   配置发布 / 回滚历史（audit_logs）
    POST /api/v2/rules/config/draft     保存配置草稿
    POST /api/v2/rules/config/publish   校验并发布草稿
    POST /api/v2/rules/config/rollback  按上一发布版本回滚
    POST /api/v2/bo/<object_type>/rules/explain       单场景解释（IF-003）
    GET  /api/v2/bo/<object_type>/<record_id>/rule-trace  单据推导链（IF-007）

试算 / 解释 / 推导只读：不落库、不改变业务数据。
"""

import logging
from typing import Any, Optional

from flask import Blueprint, request

from meta.api._response_contract import error_response, ok
from meta.api.decorators import require_permission
from meta.core.rule_keys import DIMENSION_FIELDS
from meta.core.rule_trace_service import (
    RuleTraceError,
    RuleTraceNotFound,
    get_rule_trace_service,
)
from meta.services.auth_middleware import login_required
from meta.services.rule_catalog_service import (
    RuleCatalogError,
    RuleFilterError,
    get_rule_catalog_service,
)
from meta.services.rule_config_publish_service import (
    RuleConfigError,
    RuleConfigNotFound,
    get_rule_config_publish_service,
)
from meta.services.rule_simulate_service import (
    RuleSimulateError,
    get_rule_simulate_service,
)

logger = logging.getLogger(__name__)

rule_center_bp = Blueprint('rule_center_api', __name__, url_prefix='/api/v2/rules')
rule_trace_bp = Blueprint('rule_trace_api', __name__, url_prefix='/api/v2/bo')


# ----------------------------------------------------------------------
# 视图元数据 & 目录
# ----------------------------------------------------------------------

@rule_center_bp.route('/view-config', methods=['GET'])
@login_required
def get_view_config():
    """规则中心视图元数据（页签 / 列 / 详情分区唯一数据源）。"""
    try:
        return ok(get_rule_catalog_service().get_view_config())
    except RuleCatalogError as e:
        logger.warning('rule_center view-config 不可用: %s', e)
        return error_response('规则中心视图元数据不可用', status=500)
    except Exception as e:  # noqa: BLE001
        logger.exception('Failed to load rule center view config: %s', e)
        return error_response('加载规则中心视图元数据失败', status=500)


@rule_center_bp.route('', methods=['GET'])
@login_required
def list_rules():
    """规则目录：多来源聚合后按来源 / 类型 / 可配置 / 关键字筛选。"""
    args = request.args
    try:
        result = get_rule_catalog_service().list_rules(
            sources=_split_csv(args.get('sources') or args.get('source')),
            rule_type=args.get('rule_type') or None,
            configurable=_as_bool(args.get('configurable')),
            status=args.get('status') or None,
            keyword=args.get('keyword') or args.get('q') or None,
            domain=args.get('domain') or None,
            bo=args.get('bo') or None,
            layer=args.get('layer') or None,
            # 管理面板默认可看到草稿；显式 include_draft=false 时只看生效态
            include_draft=_as_bool(args.get('include_draft')) is not False,
            limit=args.get('limit') or args.get('page_size') or 50,
            offset=_offset(args),
        )
        return ok(result)
    except RuleFilterError as e:
        return error_response(str(e), status=400, error_code='RULE_FILTER_UNKNOWN_VALUE')
    except RuleCatalogError as e:
        return error_response(str(e), status=400)
    except Exception as e:  # noqa: BLE001
        logger.exception('Failed to list rules: %s', e)
        return error_response('查询规则目录失败', status=500)


@rule_center_bp.route('/<path:rule_key>', methods=['GET'])
@login_required
def get_rule(rule_key: str):
    """规则详情（含表达式 / 因子 / 来源片段）。"""
    try:
        rule = get_rule_catalog_service().get_rule(rule_key)
    except RuleCatalogError as e:
        return error_response(str(e), status=400)
    except Exception as e:  # noqa: BLE001
        logger.exception('Failed to load rule %s: %s', rule_key, e)
        return error_response('加载规则详情失败', status=500)

    if rule is None:
        return error_response('规则不存在', status=404, error_code='RULE_NOT_FOUND')
    return ok(rule)


# ----------------------------------------------------------------------
# 规则试算 / 配置发布流
# ----------------------------------------------------------------------

@rule_center_bp.route('/simulate', methods=['POST'])
@login_required
@require_permission('rule_center:read')
def simulate_rule():
    """规则试算（IF-008）：只读，不落库。"""
    payload = request.get_json(force=True, silent=True) or {}
    try:
        result = get_rule_simulate_service().simulate(
            payload.get('scenario'),
            factors=payload.get('factors'),
            record_id=payload.get('record_id'),
            codes=payload.get('codes'),
            config_mode=payload.get('config_mode') or 'baseline',
            object_type=payload.get('object_type'),
            data=payload.get('data'),
        )
        return ok(result)
    except RuleSimulateError as e:
        return error_response(str(e), status=400)
    except RuleTraceNotFound as e:
        return error_response(str(e), status=404, error_code='NOT_FOUND')
    except Exception as e:  # noqa: BLE001
        logger.exception('Failed to simulate rule: %s', e)
        return error_response('规则试算失败', status=500)


@rule_center_bp.route('/config/history', methods=['GET'])
@login_required
@require_permission('rule_center:read')
def get_config_history():
    """配置发布 / 回滚历史（来自 audit_logs，biz_type=rule_config）。"""
    args = request.args
    try:
        result = get_rule_config_publish_service().history(
            target=args.get('target') or None,
            rule_key=args.get('rule_key') or None,
            limit=args.get('limit', 20, type=int) or 20,
        )
        return ok(result)
    except RuleConfigError as e:
        return error_response(str(e), status=400)
    except Exception as e:  # noqa: BLE001
        logger.exception('Failed to load rule config history: %s', e)
        return error_response('读取配置变更历史失败', status=500)


@rule_center_bp.route('/config/draft', methods=['POST'])
@login_required
@require_permission('rule_center:write')
def save_config_draft():
    """保存配置草稿（只写 status=draft，生产解析不受影响）。"""
    payload = request.get_json(force=True, silent=True) or {}
    user = _current_user()
    try:
        result = get_rule_config_publish_service().save_draft(
            payload.get('target'), payload.get('payload') or payload,
            user_id=user.get('user_id'), user_name=user.get('username'))
        return ok(result)
    except RuleConfigError as e:
        return error_response(str(e), status=400, error_code='RULE_CONFIG_INVALID')
    except Exception as e:  # noqa: BLE001
        logger.exception('Failed to save rule config draft: %s', e)
        return error_response('保存配置草稿失败', status=500)


@rule_center_bp.route('/config/publish', methods=['POST'])
@login_required
@require_permission('rule_center:write')
def publish_config():
    """校验并发布草稿：draft → active，同键旧版本置 inactive。"""
    payload = request.get_json(force=True, silent=True) or {}
    user = _current_user()
    try:
        result = get_rule_config_publish_service().publish(
            payload.get('target'),
            payload=payload.get('payload') or payload,
            draft_id=payload.get('draft_id'),
            user_id=user.get('user_id'), user_name=user.get('username'))
        # 发布后目录需立即反映新态（spec §13 F-13-13）
        get_rule_catalog_service().invalidate()
        return ok(result)
    except RuleConfigNotFound as e:
        return error_response(str(e), status=404, error_code='NOT_FOUND')
    except RuleConfigError as e:
        return error_response(str(e), status=400, error_code='RULE_CONFIG_INVALID')
    except Exception as e:  # noqa: BLE001
        logger.exception('Failed to publish rule config: %s', e)
        return error_response('发布配置失败', status=500)


@rule_center_bp.route('/config/rollback', methods=['POST'])
@login_required
@require_permission('rule_center:write')
def rollback_config():
    """按上一发布版本回滚；写入 ROLLBACK 审计。"""
    payload = request.get_json(force=True, silent=True) or {}
    user = _current_user()
    try:
        result = get_rule_config_publish_service().rollback(
            payload.get('target'), payload.get('payload') or payload,
            user_id=user.get('user_id'), user_name=user.get('username'))
        # 回滚后目录需立即反映新态（spec §13 F-13-13）
        get_rule_catalog_service().invalidate()
        return ok(result)
    except RuleConfigNotFound as e:
        return error_response(str(e), status=404, error_code='NOT_FOUND')
    except RuleConfigError as e:
        return error_response(str(e), status=400, error_code='RULE_CONFIG_INVALID')
    except Exception as e:  # noqa: BLE001
        logger.exception('Failed to rollback rule config: %s', e)
        return error_response('回滚配置失败', status=500)


# ----------------------------------------------------------------------
# 解释 / 推导
# ----------------------------------------------------------------------

@rule_trace_bp.route('/<object_type>/rules/explain', methods=['POST'])
@login_required
def explain_rule(object_type: str):
    """单场景解释（IF-003）：default / permission / state_transition / approval。"""
    payload = request.get_json(force=True, silent=True) or {}
    scenario = payload.get('scenario')
    if not scenario:
        return error_response('scenario 不能为空', status=400)

    try:
        from meta.core.rule_explainer import explain

        result = explain(
            object_type, scenario,
            data=payload.get('data'),
            user_id=payload.get('user_id'),
            action_id=payload.get('action_id') or 'read',
            record_id=payload.get('record_id'),
            state_field=payload.get('state_field') or 'status',
            from_state=payload.get('from_state'),
            to_state=payload.get('to_state'),
        )
        return ok(result)
    except ValueError as e:
        return error_response(str(e), status=400)
    except Exception as e:  # noqa: BLE001
        logger.exception('Failed to explain rule for %s: %s', object_type, e)
        return error_response('规则解释失败', status=500)


@rule_trace_bp.route('/<object_type>/<record_id>/rule-trace', methods=['GET'])
@login_required
@require_permission('rule_center:trace')
def get_rule_trace(object_type: str, record_id: str):
    """单据推导链（IF-007）：返回各场景统一信封。"""
    args = request.args
    try:
        record_pk = _as_int(record_id)

        from meta.api.bo_api import _check_single_bo_in_dim_scope

        if _check_single_bo_in_dim_scope(object_type, record_pk):
            # 不暴露记录存在性（与 bo_api 单条 get 口径一致）
            return error_response('记录不存在', status=404, error_code='NOT_FOUND')

        result = get_rule_trace_service().build(
            object_type,
            record_id=record_pk,
            scenarios=_split_csv(args.get('scenarios')),
            dims=_dims(args),
            codes=_split_csv(args.get('codes')),
            from_state=args.get('from_state') or None,
            to_state=args.get('to_state') or None,
        )
        return ok(result)
    except RuleTraceNotFound as e:
        return error_response(str(e), status=404, error_code='NOT_FOUND')
    except RuleTraceError as e:
        return error_response(str(e), status=400)
    except Exception as e:  # noqa: BLE001
        logger.exception('Failed to build rule trace for %s/%s: %s',
                         object_type, record_id, e)
        return error_response('生成规则推导链失败', status=500)


# ----------------------------------------------------------------------
# 参数解析（仅供本模块）
# ----------------------------------------------------------------------

def _current_user() -> dict:
    """当前登录用户（由 login_required 写入 g.current_user）。"""
    from flask import g

    return g.get('current_user') or {}


def _split_csv(value: Optional[str]):
    if not value:
        return None
    items = [item.strip() for item in str(value).split(',') if item.strip()]
    return items or None


def _as_bool(value: Optional[str]) -> Optional[bool]:
    if value is None or value == '':
        return None
    return str(value).lower() in ('1', 'true', 'yes', 'y')


def _as_int(value: Any):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _offset(args) -> int:
    if args.get('offset') is not None:
        return args.get('offset', 0, type=int) or 0
    page = args.get('page', 1, type=int) or 1
    page_size = args.get('page_size', 50, type=int) or 50
    return max(page - 1, 0) * page_size


def _dims(args) -> dict:
    dims = {}
    for field in DIMENSION_FIELDS:
        value = args.get(field, type=int)
        if value is not None:
            dims[field] = value
    return dims