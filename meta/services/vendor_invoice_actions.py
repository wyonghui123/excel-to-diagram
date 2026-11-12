# -*- coding: utf-8 -*-
"""采购发票 BO Action（Spec §12 页面动作 / §13 W5）。

注册于 `meta/services/bo_action_registrations.py`：

  · `vendor_invoice.match`              —— 重新计算三单匹配（只算不写边）
  · `vendor_invoice.override_match`     —— 行级例外放行
  · `vendor_invoice.override_duplicate` —— 重复发票放行留痕（audit_logs）
  · `vendor_invoice.submit`             —— draft → submitted
  · `vendor_invoice.post`               —— submitted → posted（写 doc_flow 边）
  · `vendor_invoice.cancel`             —— draft / submitted → cancelled
  · `vendor_invoice.reverse`            —— posted → reversed（红冲生成红字贷项凭证）
  · `vendor_invoice.create_adjustment`  —— 基于已过账发票创建正向调整单（increase / decrease）

事务边界由 handler 控制；服务层不自行提交，异常整体回滚（R-VI-18）。
`reverse` 例外：服务内部先在事务外分配红字单号，再由 ReversalOrchestrator
自持事务执行 7 步，故 handler 不包外层事务。
"""

import logging
from typing import Any, Dict, List, Optional

from meta.services.vendor_invoice_match_service import (
    VendorInvoiceError,
    VendorInvoiceMatchService,
)

logger = logging.getLogger(__name__)


def _ok(data: Any, message: str) -> Dict[str, Any]:
    return {'success': True, 'data': data, 'message': message}


def _fail(message: str, code: str) -> Dict[str, Any]:
    return {'success': False, 'data': None, 'message': message, 'code': code}


def _invoice_id(params: Dict[str, Any]) -> Any:
    """目标发票 ID：显式 invoice_id / id 优先，退化为详情页下发的 source_doc_id。

    DetailPage 的业务动作统一以 `source_doc_id` 传入当前记录（见 useBoAction），
    此前只认 invoice_id / id ⇒ match / override_* / reverse 均报「缺少采购发票 ID」。
    """
    return params.get('invoice_id') or params.get('id') or params.get('source_doc_id')


def _current_user_name() -> str:
    try:
        from meta.services.auth_middleware import get_current_user
        user = get_current_user() or {}
        return user.get('display_name') or user.get('username') or 'system'
    except Exception:  # noqa: BLE001 - 无请求上下文时回落 system
        return 'system'


def _set_user_context() -> None:
    """把当前请求用户塞进 BO 框架上下文（审计 / 权限拦截器依赖）。"""
    try:
        from flask import request
        from meta.services.auth_middleware import get_current_user
        from meta.core.bo_framework import bo_framework
        current_user = get_current_user()
        if not current_user:
            return
        bo_framework.set_user_context(
            user_id=current_user.get('user_id'),
            user_name=current_user.get('display_name') or current_user.get(
                'username', 'unknown'),
            ip_address=request.remote_addr,
        )
    except Exception:  # noqa: BLE001
        pass


def _service() -> VendorInvoiceMatchService:
    return VendorInvoiceMatchService()


def _handle(params: Dict[str, Any], action: str,
            runner) -> Dict[str, Any]:
    invoice_id = _invoice_id(params or {})
    if not invoice_id:
        return _fail('缺少采购发票 ID', 'VI_NOT_FOUND')
    _set_user_context()
    service = _service()
    try:
        with service.ds.transaction():
            data = runner(service, invoice_id)
        return _ok(data, '采购发票{0}成功'.format(action))
    except VendorInvoiceError as exc:
        return _fail(exc.message, exc.rule)
    except Exception as exc:  # noqa: BLE001 - 统一转业务失败，避免 500
        logger.exception('[vendor_invoice] action %s failed', action)
        return _fail(str(exc), 'VI_ACTION_FAILED')


def match_handler(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """重新计算匹配结果（不写 doc_flow 边）。"""
    user_name = _current_user_name()
    return _handle(params, '匹配', lambda svc, invoice_id: svc.match(invoice_id, user_name=user_name))


def override_match_handler(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """例外放行：必须给 override_reason；可选 line_ids 只放行指定行。"""
    params = params or {}
    reason = params.get('override_reason') or params.get('reason') or ''
    if not reason:
        return _fail('例外放行必须填写 override_reason', 'VI_OVERRIDE_REASON_REQUIRED')
    line_ids: Optional[List[Any]] = params.get('line_ids')
    user_name = _current_user_name()
    return _handle(
        params, '例外放行',
        lambda svc, invoice_id: svc.override_match(
            invoice_id, reason=reason, user_name=user_name, line_ids=line_ids),
    )


def override_duplicate_handler(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """重复发票放行：必须给 duplicate_override_reason（落 audit_logs）。"""
    params = params or {}
    reason = (params.get('duplicate_override_reason') or params.get('override_reason')
              or params.get('reason') or '')
    if not reason:
        return _fail('重复发票放行必须填写 duplicate_override_reason', 'VI_OVERRIDE_REASON_REQUIRED')
    user_name = _current_user_name()
    return _handle(
        params, '重复放行',
        lambda svc, invoice_id: svc.override_duplicate(
            invoice_id, reason=reason, user_name=user_name),
    )


def submit_handler(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    user_name = _current_user_name()
    return _handle(params, '提交', lambda svc, invoice_id: svc.submit(invoice_id, user_name=user_name))


def post_handler(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    user_name = _current_user_name()
    return _handle(params, '过账', lambda svc, invoice_id: svc.post(invoice_id, user_name=user_name))


def cancel_handler(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    user_name = _current_user_name()
    return _handle(params, '取消', lambda svc, invoice_id: svc.cancel(invoice_id, user_name=user_name))


def reverse_handler(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """红冲已过账采购发票（生成红字采购贷项凭证）。

    不包外层事务：``VendorInvoiceMatchService.reverse`` 在事务外预取单号，
    随后由 ``ReversalOrchestrator.execute`` 自持事务完成 faces / state。
    """
    params = params or {}
    reason = params.get('reversal_reason') or params.get('reason') or ''
    invoice_id = _invoice_id(params)
    if not invoice_id:
        return _fail('缺少采购发票 ID', 'VI_NOT_FOUND')
    if not reason:
        return _fail('红冲必须填写原因', 'VI_REVERSAL_REASON_REQUIRED')
    _set_user_context()
    service = _service()
    try:
        data = service.reverse(
            invoice_id, reason=reason,
            invoice_date=params.get('invoice_date'),
            user_name=_current_user_name(),
        )
        return _ok(data, '采购发票红冲成功')
    except VendorInvoiceError as exc:
        return _fail(exc.message, exc.rule)
    except Exception as exc:  # noqa: BLE001 - 统一转业务失败，避免 500
        logger.exception('[vendor_invoice] reverse failed')
        return _fail(str(exc), 'VI_ACTION_FAILED')


def create_adjustment_handler(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """基于已过账发票创建正向调整单（draft）。

    不包外层事务：``create_adjustment`` 在事务外取号，再单事务插入头 + 行。
    """
    params = params or {}
    invoice_id = _invoice_id(params)
    if not invoice_id:
        return _fail('缺少采购发票 ID', 'VI_NOT_FOUND')
    direction = params.get('direction') or params.get('adjustment_direction') or ''
    reason = params.get('reason') or params.get('adjustment_reason') or ''
    if not reason:
        return _fail('调整单必须填写调整原因', 'VI_ADJUSTMENT_REASON_REQUIRED')
    _set_user_context()
    service = _service()
    try:
        data = service.create_adjustment(
            invoice_id,
            direction=direction,
            reason=reason,
            invoice_date=params.get('invoice_date'),
            lines=params.get('lines'),
            user_name=_current_user_name(),
        )
        return _ok(data, '采购发票调整单创建成功')
    except VendorInvoiceError as exc:
        return _fail(exc.message, exc.rule)
    except Exception as exc:  # noqa: BLE001 - 统一转业务失败，避免 500
        logger.exception('[vendor_invoice] create_adjustment failed')
        return _fail(str(exc), 'VI_ACTION_FAILED')