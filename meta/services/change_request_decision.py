# -*- coding: utf-8 -*-
"""BO 业务 Action: change_request.approve / change_request.reject / change_request.apply（M3 T5）

依据 docs/superpowers/specs/2026-10-29-m3-change-request/spec.md §5.3 / §6.3：

- approve / reject 由 `decision_effect`（决策-生效协议）经任务 `executor_config.decision_actions`
  调用，因此 `data.new_status` 必须严格为 `'approved'` / `'rejected'`（默认回执键）。
- apply 由 `POST /bo/change_request/{id}/actions/change_request.apply` 调用，
  生效编排在 `revision_service.apply`（目标表只经 `ActionExecutor` 漏斗写，D5）。

信封沿用 `sales_order_header_discount_apply`：`{'success','data','message'}`，
失败附 `code` / `status_code`（`bo_action_api` 已支持）。
"""
import logging
from typing import Any, Dict

from meta.core.db_path import get_meta_db_path

logger = logging.getLogger(__name__)

CR_TABLE = 'change_requests'


def _set_user_context():
    """写入审计日志的用户上下文 (无请求上下文时静默跳过)。"""
    from flask import request
    from meta.services.auth_middleware import get_current_user
    from meta.core.bo_framework import bo_framework
    current_user = get_current_user()
    bo_framework.set_user_context(
        user_id=current_user.get('user_id'),
        user_name=current_user.get(
            'display_name', current_user.get('username', 'unknown')
        ),
        ip_address=request.remote_addr,
    )


def _get_ds():
    from meta.core.datasource import get_data_source
    return get_data_source('sqlite', database=get_meta_db_path())


def _cr_id(params: Dict[str, Any]):
    p = params or {}
    cr_id = p.get('change_request_id')
    if cr_id in (None, ''):
        cr_id = p.get('id')
    return cr_id


def _actor(context: Dict[str, Any]) -> str:
    ctx = context or {}
    return ctx.get('actor') or ctx.get('user_id') or ''


def _envelope_error(message: str, code: str = None, status_code: int = None) -> Dict[str, Any]:
    payload = {'success': False, 'data': None, 'message': message}
    if code:
        payload['code'] = code
    if status_code is not None:
        payload['status_code'] = status_code
    return payload


def _decide(params: Dict[str, Any], context: Dict[str, Any], *,
            target_status: str, message: str) -> Dict[str, Any]:
    """approve / reject 的共用实现：submitted → target_status（幂等 no-op）。"""
    from meta.services.change_request_service import (
        ChangeRequestError,
        _ensure_tables,
        transition,
    )

    p = params or {}
    cr_id = _cr_id(p)
    if cr_id in (None, ''):
        return _envelope_error('缺少 change_request_id')

    try:
        _set_user_context()
    except Exception:  # noqa: BLE001 - 无请求上下文时跳过审计用户
        pass

    try:
        ds = _get_ds()
    except Exception as e:  # noqa: BLE001
        logger.exception(f'[change_request] 数据源初始化失败: {e}')
        return _envelope_error(f'数据源未初始化: {e}')
    if not ds:
        return _envelope_error('数据源未初始化')

    try:
        _ensure_tables(ds)
        cr_row = ds.find_by_id(CR_TABLE, cr_id)
        if not cr_row:
            raise ChangeRequestError(
                'CHANGE_REQUEST_NOT_FOUND', '变更申请不存在: %s' % cr_id, 404)

        # 幂等：已是目标状态 → 同值 no-op success（重复决策不报错、不重复推进）
        if cr_row.get('status') == target_status:
            return {
                'success': True,
                'data': {'new_status': target_status, 'change_request_id': cr_id},
                'message': message,
            }

        extra: Dict[str, Any] = {}
        if target_status == 'rejected':
            comment = (p.get('comment') or '').strip()
            if comment:
                extra['fail_reason'] = comment[:200]
        transition(ds, cr_row, target_status, _actor(context), extra or None)
    except ChangeRequestError as e:
        return _envelope_error(str(e), e.code, e.status_code)
    except Exception as e:  # noqa: BLE001
        logger.exception(f'[change_request] 审批决策失败: {e}')
        return _envelope_error(f'审批决策失败: {e}')

    return {
        'success': True,
        'data': {'new_status': target_status, 'change_request_id': cr_id},
        'message': message,
    }


def change_request_approve_handler(params: Dict[str, Any],
                                   context: Dict[str, Any]) -> Dict[str, Any]:
    """审批通过：submitted → approved（写 approved_by / approved_at）。

    回执 `data.new_status` 必须为 `'approved'`（决策-生效协议的任务归位依据）。
    """
    return _decide(params, context, target_status='approved', message='审批通过')


def change_request_reject_handler(params: Dict[str, Any],
                                  context: Dict[str, Any]) -> Dict[str, Any]:
    """审批驳回：submitted → rejected（可带 comment 落 fail_reason）。

    回执 `data.new_status` 必须为 `'rejected'`。
    """
    return _decide(params, context, target_status='rejected', message='已驳回')


def change_request_apply_handler(params: Dict[str, Any],
                                 context: Dict[str, Any]) -> Dict[str, Any]:
    """生效：approved → applied（编排走 revision_service.apply）。"""
    from meta.services.change_request_service import ChangeRequestError, _ensure_tables
    from meta.services.revision_service import apply as apply_change_request

    cr_id = _cr_id(params)
    if cr_id in (None, ''):
        return _envelope_error('缺少 change_request_id')

    try:
        _set_user_context()
    except Exception:  # noqa: BLE001 - 无请求上下文时跳过审计用户
        pass

    try:
        ds = _get_ds()
    except Exception as e:  # noqa: BLE001
        logger.exception(f'[change_request] 数据源初始化失败: {e}')
        return _envelope_error(f'数据源未初始化: {e}')
    if not ds:
        return _envelope_error('数据源未初始化')

    try:
        _ensure_tables(ds)
        cr_row = ds.find_by_id(CR_TABLE, cr_id)
        if not cr_row:
            raise ChangeRequestError(
                'CHANGE_REQUEST_NOT_FOUND', '变更申请不存在: %s' % cr_id, 404)
        data = apply_change_request(ds, cr_row, actor=_actor(context))
    except ChangeRequestError as e:
        return _envelope_error(str(e), e.code, e.status_code)
    except Exception as e:  # noqa: BLE001
        logger.exception(f'[change_request] 生效失败: {e}')
        return _envelope_error(f'变更生效失败: {e}')

    return {'success': True, 'data': data, 'message': '变更申请生效成功'}
