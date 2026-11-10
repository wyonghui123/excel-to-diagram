# -*- coding: utf-8 -*-
"""销售发票 BO Action（S8 Wave A / B2，spec §13）。

注册于 `meta/services/bo_action_registrations.py`：

  · `customer_invoice.create_from_shipment` —— 由已发运/已签收发货单
    生成草稿销售发票（可按行部分开票）

口径：
  · 事务边界由服务层 `create_from_shipment` 的 `_atomic(self.ds)` 控制，
    本模块不再包事务（避免嵌套）；
  · 取号在事务外，由 `DocumentNumberService.allocate_for` 完成；
  · 错误码透传 `CustomerInvoiceError.rule`，便于前端定位。
"""

import logging
from datetime import date
from typing import Any, Dict

from meta.services.customer_invoice_service import (
    CustomerInvoiceError,
    CustomerInvoiceService,
)

logger = logging.getLogger(__name__)

#: 可透传给 `create_from_shipment` 的抬头字段（其余由服务推导）
HEADER_KEYS = (
    'invoice_date', 'posting_date', 'document_type_id', 'payment_term_id',
    'incoterm_code', 'remark',
)


def _blank(value: Any) -> bool:
    return value is None or value == ''


def _ok(data: Any, message: str) -> Dict[str, Any]:
    return {'success': True, 'data': data, 'message': message}


def _fail(message: str, code: str) -> Dict[str, Any]:
    return {'success': False, 'data': None, 'message': message, 'code': code}


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
    except Exception:  # noqa: BLE001 - 无请求上下文（任务链路）时跳过审计用户
        pass


def _service() -> CustomerInvoiceService:
    from meta.core.datasource import get_data_source
    from meta.core.db_path import get_meta_db_path
    return CustomerInvoiceService(
        get_data_source('sqlite', database=get_meta_db_path()))


def create_from_shipment_handler(params: Dict[str, Any],
                                 context: Any = None) -> Dict[str, Any]:
    """`customer_invoice.create_from_shipment` 的处理器。"""
    _set_user_context()
    params = dict(params or {})

    shipment_id = params.get('shipment_id') or params.get('source_doc_id')
    if _blank(shipment_id):
        return _fail('缺少 shipment_id（发货单 id）', 'INVALID_ARGUMENT')

    payload = {key: params.get(key) for key in HEADER_KEYS
               if not _blank(params.get(key))}
    payload['shipment_id'] = shipment_id
    # 详情页按钮不弹日期：未指定时按当天开票
    payload.setdefault('invoice_date', date.today().strftime('%Y-%m-%d'))
    lines = params.get('lines')
    if isinstance(lines, list) and lines:
        payload['lines'] = lines

    try:
        data = _service().create_from_shipment(payload)
    except CustomerInvoiceError as exc:
        return _fail(str(exc), getattr(exc, 'rule', '') or 'INVOICE_INVALID')

    logger.info('[customer_invoice_action] create_from_shipment shipment=%s '
                'invoice=%s', shipment_id, data.get('invoice_no'))
    return _ok(data, '已生成销售发票 %s（草稿）' % data.get('invoice_no', ''))


def create_from_schedule_handler(params: Dict[str, Any],
                                 context: Any = None) -> Dict[str, Any]:
    """`customer_invoice.create_from_schedule` 的处理器（Wave B）。"""
    _set_user_context()
    params = dict(params or {})

    schedule_ids = params.get('schedule_ids') or []
    if not isinstance(schedule_ids, (list, tuple, set)):
        schedule_ids = [schedule_ids]
    lines = params.get('lines') or []
    source_doc_id = params.get('source_doc_id')
    if not schedule_ids and not lines and _blank(source_doc_id):
        return _fail('缺少 schedule_ids / lines / source_doc_id',
                     'INVALID_ARGUMENT')

    payload = {key: params.get(key) for key in HEADER_KEYS
               if not _blank(params.get(key))}
    payload.setdefault('invoice_date', date.today().strftime('%Y-%m-%d'))
    if schedule_ids:
        payload['schedule_ids'] = schedule_ids
    if isinstance(lines, list) and lines:
        payload['lines'] = lines
    if not _blank(source_doc_id):
        payload['source_doc_id'] = source_doc_id

    try:
        data = _service().create_from_schedule(payload)
    except CustomerInvoiceError as exc:
        return _fail(str(exc), getattr(exc, 'rule', '') or 'INVOICE_INVALID')

    logger.info('[customer_invoice_action] create_from_schedule '
                'schedules=%s invoice=%s', schedule_ids or source_doc_id,
                data.get('invoice_no'))
    return _ok(data, '已生成销售发票 %s（草稿）' % data.get('invoice_no', ''))


def list_due_schedules_handler(params: Dict[str, Any],
                               context: Any = None) -> Dict[str, Any]:
    """`customer_invoice.list_due_schedules` 处理器（只读）。"""
    _set_user_context()
    params = dict(params or {})
    try:
        data = _service().list_due_schedules(
            as_of=params.get('as_of'),
            order_id=params.get('order_id'),
            page=params.get('page') or 1,
            page_size=params.get('page_size') or 50)
    except Exception as exc:  # noqa: BLE001 - 只读查询失败透传
        logger.warning('[customer_invoice_action] list_due_schedules 失败: %s',
                       exc)
        return _fail('查询到期开票计划失败：%s' % exc,
                     'INVOICE_DUE_LIST_FAILED')
    return _ok(data, '共 %s 条到期开票期次' % data.get('total', 0))


def create_credit_from_invoice_handler(params: Dict[str, Any],
                                       context: Any = None) -> Dict[str, Any]:
    """`customer_invoice.create_credit_from_invoice` 的处理器（B5）。"""
    _set_user_context()
    params = dict(params or {})

    source_id = (params.get('source_invoice_id') or params.get('invoice_id')
                 or params.get('source_doc_id'))
    if _blank(source_id):
        return _fail('缺少 source_invoice_id（原发票 id）', 'INVALID_ARGUMENT')

    payload = {key: params.get(key)
               for key in ('invoice_date', 'remark', 'reason', 'line_ids',
                           'lines')
               if not _blank(params.get(key))}
    payload['source_invoice_id'] = source_id
    payload.setdefault('invoice_date', date.today().strftime('%Y-%m-%d'))

    try:
        data = _service().create_credit_from_invoice(payload)
    except CustomerInvoiceError as exc:
        return _fail(str(exc), getattr(exc, 'rule', '') or 'INVOICE_INVALID')

    logger.info('[customer_invoice_action] create_credit source=%s credit=%s',
                source_id, data.get('invoice_no'))
    return _ok(data, '已生成贷项单 %s（草稿）' % data.get('invoice_no', ''))


def create_credit_on_account_handler(params: Dict[str, Any],
                                     context: Any = None) -> Dict[str, Any]:
    """`customer_invoice.create_credit_on_account`（Wave C C4）。"""
    _set_user_context()
    params = dict(params or {})

    lines = list(params.get('lines') or [])
    if not lines:
        return _fail('缺少 lines（on-account 贷项行）', 'INVALID_ARGUMENT')

    payload = {key: params.get(key) for key in (
        'invoice_date', 'remark', 'reason', 'lines', 'customer_id',
        'customer_account_id', 'currency_id', 'exchange_rate', 'org_id',
        'sales_org_id', 'payment_term_id', 'bill_to_account_id',
        'payer_account_id') if not _blank(params.get(key))}
    payload['lines'] = lines
    payload.setdefault('invoice_date', date.today().strftime('%Y-%m-%d'))

    try:
        data = _service().create_credit_on_account(payload)
    except CustomerInvoiceError as exc:
        return _fail(str(exc), getattr(exc, 'rule', '') or 'INVOICE_INVALID')

    logger.info('[customer_invoice_action] on-account credit=%s',
                data.get('invoice_no'))
    return _ok(data, '已生成贷项单 %s（草稿）' % data.get('invoice_no', ''))


def create_credit_from_return_shipment_handler(params: Dict[str, Any],
                                               context: Any = None
                                               ) -> Dict[str, Any]:
    """`customer_invoice.create_credit_from_return_shipment`（Wave C C3）。"""
    _set_user_context()
    params = dict(params or {})

    shipment_id = (params.get('return_shipment_id') or params.get('shipment_id')
                   or params.get('source_doc_id'))
    if _blank(shipment_id):
        return _fail('缺少 shipment_id（退货发货单 id）', 'INVALID_ARGUMENT')

    payload = {key: params.get(key) for key in (
        'invoice_date', 'remark', 'reason', 'return_line_ids',
        'source_invoice_id', 'invoice_line_ids', 'auto_allocate')
        if not _blank(params.get(key))}
    payload['return_shipment_id'] = shipment_id
    payload.setdefault('invoice_date', date.today().strftime('%Y-%m-%d'))

    try:
        data = _service().create_credit_from_return_shipment(payload)
    except CustomerInvoiceError as exc:
        return _fail(str(exc), getattr(exc, 'rule', '') or 'INVOICE_INVALID')

    logger.info('[customer_invoice_action] return credit shipment=%s credit=%s',
                shipment_id, data.get('invoice_no'))
    return _ok(data, '已生成贷项单 %s（草稿）' % data.get('invoice_no', ''))


# --------------------------------------------------------- 单据动作（Wave C）

def _invoice_id(params: Dict[str, Any]) -> Any:
    for key in ('invoice_id', 'source_doc_id', 'source_id'):
        value = params.get(key)
        if not _blank(value):
            return value
    return None


def _summary(header: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    data = {
        'id': int(header['id']),
        'invoice_no': header.get('invoice_no'),
        'status': header.get('status'),
    }
    data.update(extra)
    return data


def submit_handler(params: Dict[str, Any],
                   context: Any = None) -> Dict[str, Any]:
    """`customer_invoice.submit`：draft → submitted（幂等）。"""
    _set_user_context()
    params = dict(params or {})
    invoice_id = _invoice_id(params)
    if invoice_id is None:
        return _fail('缺少 invoice_id（发票 id）', 'INVALID_ARGUMENT')

    service = _service()
    try:
        header = service.load(invoice_id)['header']
        if header['status'] in ('submitted', 'posted'):
            return _ok(_summary(header), '发票已提交（当前状态 %s）'
                       % header['status'])
        data = service.submit(invoice_id)
        header = service.load(invoice_id)['header']
    except CustomerInvoiceError as exc:
        return _fail(str(exc), getattr(exc, 'rule', '') or 'INVOICE_INVALID')

    logger.info('[customer_invoice_action] submit id=%s status=%s',
                invoice_id, data.get('status'))
    return _ok(_summary(header), '发票 %s 已提交'
               % header.get('invoice_no', ''))


def post_handler(params: Dict[str, Any],
                 context: Any = None) -> Dict[str, Any]:
    """`customer_invoice.post`：submitted → posted（幂等）。"""
    _set_user_context()
    params = dict(params or {})
    invoice_id = _invoice_id(params)
    if invoice_id is None:
        return _fail('缺少 invoice_id（发票 id）', 'INVALID_ARGUMENT')

    service = _service()
    try:
        header = service.load(invoice_id)['header']
        if header['status'] == 'posted':
            return _ok(_summary(header), '发票已过账')
        data = service.post(invoice_id, posting_date=params.get('posting_date'))
        header = service.load(invoice_id)['header']
    except CustomerInvoiceError as exc:
        return _fail(str(exc), getattr(exc, 'rule', '') or 'INVOICE_INVALID')

    logger.info('[customer_invoice_action] post id=%s posting_date=%s',
                invoice_id, data.get('posting_date'))
    return _ok(_summary(header, posting_date=data.get('posting_date')),
               '发票 %s 已过账' % header.get('invoice_no', ''))


def reverse_handler(params: Dict[str, Any],
                    context: Any = None) -> Dict[str, Any]:
    """`customer_invoice.reverse`：posted → 红字 posted（幂等）。"""
    _set_user_context()
    params = dict(params or {})
    invoice_id = _invoice_id(params)
    if invoice_id is None:
        return _fail('缺少 invoice_id（发票 id）', 'INVALID_ARGUMENT')
    reason = params.get('reason') or params.get('reversal_reason')
    if _blank(reason):
        return _fail('红冲原因必填', 'INVOICE_REVERSE_INVALID')

    service = _service()
    try:
        header = service.load(invoice_id)['header']
        existing = service.find_reversal(invoice_id)
        if existing:
            return _ok(_summary(
                header, original_invoice_id=int(header['id']),
                red_invoice_id=existing['id'],
                red_invoice_no=existing.get('invoice_no')),
                '该发票已红冲（红字发票 %s）' % existing.get('invoice_no', ''))
        data = service.reverse(
            invoice_id, reason,
            invoice_date=params.get('reversal_date')
            or params.get('invoice_date'))
        header = service.load(invoice_id)['header']
    except CustomerInvoiceError as exc:
        return _fail(str(exc), getattr(exc, 'rule', '') or 'INVOICE_INVALID')

    logger.info('[customer_invoice_action] reverse id=%s red=%s',
                invoice_id, data.get('red_invoice_id'))
    return _ok(_summary(
        header, original_invoice_id=int(header['id']),
        red_invoice_id=data.get('red_invoice_id'),
        red_invoice_no=data.get('red_invoice_no')),
        '发票 %s 已红冲，红字发票 %s'
        % (header.get('invoice_no', ''), data.get('red_invoice_no', '')))
