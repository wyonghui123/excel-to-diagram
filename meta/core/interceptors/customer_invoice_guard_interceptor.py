# -*- coding: utf-8 -*-
"""销售发票守卫拦截器 —— 抬头状态迁移、行写入与期次只读的统一入口。

优先级 51（与 shipment_guard 同批，受管对象不同互不冲突；必须在
PersistenceInterceptor 95 之前）：
  · before_action 做写前校验，并把带跨表副作用的状态迁移委托
    `CustomerInvoiceService`（submit / post / cancel / reverse）；
  · after_action 把服务结果并回响应体（红字单号等）。

受管范围：
  customer_invoice          —— 创建（归一化抬头 + 取号）/ 更新（冻结与状态迁移）/ 删除
  customer_invoice_line     —— 创建 / 更新（服务重算金额与来源校验）/ 删除
  customer_invoice_schedule —— 任意写拒绝（R-INV-22，D27 严格只读）
其余对象与动作零开销短路。

口径：
  · 本拦截器不发跨表 SQL（billed 回写、期次生成、doc_flow、billing_status 派生
    全部由 customer_invoice_service 完成），只在迁移后收紧持久化入参，
    避免同一请求体的旧值覆盖服务已写定的业务字段；
  · `posted` 抬头仅允许 `status=reversed` 一种迁移（委托 reverse）；
    `reversed` / `cancelled` 为终态，任何写入拒绝；
  · 已知边界：拦截器链只覆盖 bo_api 写路径，manage_api 与 Excel 导入绕过本守卫。
"""

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor
from meta.services.customer_invoice_service import (
    LINE_TABLE,
    STATUS_CANCELLED,
    STATUS_DRAFT,
    STATUS_POSTED,
    STATUS_REVERSED,
    STATUS_SUBMITTED,
    SUBMITTED_FROZEN_FIELDS,
    CustomerInvoiceError,
    CustomerInvoiceService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

HEADER_OBJECT = 'customer_invoice'
LINE_OBJECT = 'customer_invoice_line'
SCHEDULE_OBJECT = 'customer_invoice_schedule'
_WRITE_ACTIONS = ('crud_create', 'crud_update', 'crud_delete')
_RESULT_KEY = 'customer_invoice_result'

#: 创建时由服务归一化后回填到写入口径的抬头列
_CREATE_SYNC_KEYS = (
    'invoice_no', 'document_type_id', 'invoice_date', 'status',
    'customer_account_id', 'bill_to_account_id', 'payer_account_id',
    'bill_to_address_text', 'tax_registration_no', 'currency_id',
    'exchange_rate', 'exchange_rate_type', 'exchange_rate_date',
    'payment_term_id', 'incoterm_code', 'net_amount', 'tax_amount',
    'gross_amount', 'org_id', 'sales_org_id', 'project_id',
    'reversal_of_invoice_id', 'reversal_reason', 'remark',
    'created_at', 'updated_at',
)

#: 行服务归一化后回填入参的列（含服务重算的金额与来源快照）
_LINE_NORMALIZED_KEYS = (
    'line_no', 'line_type_id', 'source_doc_type', 'source_doc_id',
    'source_line_id', 'shipment_line_id', 'schedule_id', 'order_line_id',
    'item_id', 'description', 'uom_id', 'qty', 'billing_basis',
    'unit_price', 'net_amount', 'tax_amount', 'gross_amount',
    'tax_code_id', 'tax_rate_percent', 'project_id', 'project_task_id',
    'billing_percent', 'billing_base_amount', 'price_source',
    'order_unit_price', 'price_change_reason', 'price_change_approved_by',
    'original_invoice_line_id',
)

#: 终态抬头：除无迁移外的一切写入都拒绝
_TERMINAL_STATUSES = (STATUS_POSTED, STATUS_REVERSED, STATUS_CANCELLED)


def _object_id(context) -> Any:
    """目标记录 ID：优先 ActionContext 属性，退化到入参 id（SimpleNamespace 场景）。"""
    return getattr(context, 'object_id', None) or (context.params or {}).get('id')


def _blank(value: Any) -> bool:
    return value is None or value == ''


def _to_param(value: Any) -> Any:
    """服务归一化值 → 持久化入参：Decimal/date 转 SQLite 友好类型。"""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date) and not isinstance(value, str):
        return value.strftime('%Y-%m-%d')
    return value


def _same_value(left: Any, right: Any) -> bool:
    """冻结字段比较：数值按 Decimal 归一，其余按字符串归一。"""
    if left == right:
        return True
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, TypeError, ValueError):
        return str(left) == str(right)


class CustomerInvoiceGuardInterceptor(Interceptor):
    """销售发票头 / 行 / 期次的守卫与状态迁移接线。"""

    @property
    def priority(self) -> int:
        return 51

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id not in (HEADER_OBJECT, LINE_OBJECT, SCHEDULE_OBJECT):
            return False
        return context.action in _WRITE_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        object_id = getattr(context.meta_object, 'id', None)
        try:
            if object_id == HEADER_OBJECT:
                self._guard_header(context)
            elif object_id == LINE_OBJECT:
                self._guard_line(context)
            elif object_id == SCHEDULE_OBJECT:
                raise CustomerInvoiceError(
                    '发票期次为派生只读数据，禁止手工增删改（R-INV-22）',
                    field_name='', rule='INVOICE_SCHEDULE_IMMUTABLE')
        except CustomerInvoiceError as error:
            raise ValidationFailedError(
                message=str(error),
                details=[{
                    'field_name': error.field_name,
                    'rule': error.rule,
                    'message': str(error),
                    'i18n_key': '',
                    'params': {},
                }],
            )

    def after_action(self, context: 'ActionContext') -> None:
        info = (context.extra or {}).get(_RESULT_KEY)
        if not info:
            return
        if context.result is not None and isinstance(context.result.data, dict):
            for key in ('red_invoice_id', 'red_invoice_no', 'posting_date'):
                if key in info:
                    context.result.data[key] = info[key]

    # ------------------------------------------------------------------ 抬头

    def _guard_header(self, context: 'ActionContext') -> None:
        params = context.params
        service = CustomerInvoiceService(context.data_source)
        invoice_id = _object_id(context)

        if context.action == 'crud_delete':
            header = service._require_header(invoice_id)
            if header.get('status') != STATUS_DRAFT:
                raise CustomerInvoiceError(
                    '仅草稿发票可删除（当前状态：%s）' % header.get('status'),
                    field_name='status', rule='INVOICE_DELETE_FORBIDDEN')
            return

        if context.action == 'crud_create':
            if not isinstance(params, dict):
                return
            header = service.prepare_header(params)
            self._sync_params(params, header, _CREATE_SYNC_KEYS)
            return

        if not isinstance(params, dict):
            return
        old_data = context.old_data or {}
        current = old_data.get('status') or service._require_header(
            invoice_id).get('status')
        target = params.get('status')

        if current == STATUS_POSTED:
            self._guard_posted_update(context, service, invoice_id,
                                      params, target)
            return
        if current in (STATUS_REVERSED, STATUS_CANCELLED):
            raise CustomerInvoiceError(
                '发票已处于终态 %s，禁止任何修改' % current,
                field_name='status', rule='INVOICE_POSTED_READONLY')
        if current == STATUS_SUBMITTED:
            self._assert_not_frozen(params, old_data)

        if _blank(target) or target == current:
            return

        if current == STATUS_DRAFT and target == STATUS_SUBMITTED:
            result = service.submit(invoice_id)
        elif current == STATUS_DRAFT and target == STATUS_CANCELLED:
            result = service.cancel(invoice_id)
        elif current == STATUS_SUBMITTED and target == STATUS_POSTED:
            result = service.post(
                invoice_id, posting_date=params.get('posting_date'))
        elif current == STATUS_SUBMITTED and target == STATUS_CANCELLED:
            result = service.cancel(invoice_id)
        else:
            raise CustomerInvoiceError(
                '不允许的状态迁移：%s → %s' % (current, target),
                field_name='status', rule='INVOICE_STATE_INVALID')

        context.extra[_RESULT_KEY] = result
        self._tighten_transition_params(params, invoice_id, target)

    def _guard_posted_update(self, context: 'ActionContext',
                             service: CustomerInvoiceService, invoice_id: Any,
                             params: Dict[str, Any], target: Any) -> None:
        """posted：只允许 status=reversed 的迁移，其余字段一律拒绝。"""
        if target == STATUS_REVERSED:
            extra = {k: v for k, v in params.items()
                     if k not in ('id', 'status', 'reversal_reason')}
            if extra:
                raise CustomerInvoiceError(
                    '已过账发票红冲时只接受红冲原因',
                    field_name=sorted(extra)[0],
                    rule='INVOICE_POSTED_READONLY')
            reason = params.get('reversal_reason')
            if _blank(reason):
                raise CustomerInvoiceError(
                    '红冲原因必填', field_name='reversal_reason',
                    rule='INVOICE_REVERSE_INVALID')
            result = service.reverse(invoice_id, reason)
            context.extra[_RESULT_KEY] = result
            self._tighten_transition_params(params, invoice_id, target)
            return

        extra = {k for k in params if k not in ('id', 'status')}
        if extra or (not _blank(target) and target != STATUS_POSTED):
            raise CustomerInvoiceError(
                '已过账发票只读，仅允许红冲', field_name='status',
                rule='INVOICE_POSTED_READONLY')

    @staticmethod
    def _assert_not_frozen(params: Dict[str, Any],
                           old_data: Dict[str, Any]) -> None:
        """submitted：冻结源字段，值变化即拒绝；同值回传放行。"""
        for field in SUBMITTED_FROZEN_FIELDS:
            if field not in params:
                continue
            if not _same_value(params.get(field), old_data.get(field)):
                raise CustomerInvoiceError(
                    '发票已提交，字段 %s 不可修改' % field,
                    field_name=field, rule='INVOICE_POSTED_READONLY')

    @staticmethod
    def _tighten_transition_params(params: Dict[str, Any], invoice_id: Any,
                                   target: str) -> None:
        """迁移副作用已由服务写定，持久化只回写状态本身。"""
        params.clear()
        params.update({'id': invoice_id, 'status': target})

    @staticmethod
    def _sync_params(params: Dict[str, Any], values: Dict[str, Any],
                     keys) -> None:
        for key in keys:
            if key in values and not _blank(values[key]):
                params[key] = _to_param(values[key])

    # ------------------------------------------------------------------ 行

    def _guard_line(self, context: 'ActionContext') -> None:
        params = context.params
        if not isinstance(params, dict):
            return
        service = CustomerInvoiceService(context.data_source)

        if context.action == 'crud_create':
            invoice_id = params.get('invoice_id')
            header = self._require_draft_parent(service, invoice_id)
            if _blank(params.get('line_no')):
                params['line_no'] = self._next_line_no(service, invoice_id)
            values = service.validate_line_write(params, invoice=header)
            self._sync_params(params, values, _LINE_NORMALIZED_KEYS)
            return

        existing = self._require_line(service, _object_id(context))
        header = self._require_draft_parent(service, existing.get('invoice_id'))
        if context.action == 'crud_delete':
            return
        values = service.validate_line_write(
            params, existing=existing, invoice=header)
        self._sync_params(params, values, _LINE_NORMALIZED_KEYS)

    @staticmethod
    def _next_line_no(service: CustomerInvoiceService, invoice_id: Any) -> int:
        rows = service.ds.query(
            'SELECT COALESCE(MAX(line_no), 0) + 1 AS next_no '
            'FROM %s WHERE invoice_id = ?' % LINE_TABLE, [invoice_id])
        return int(rows[0]['next_no'] or 1) if rows else 1

    @staticmethod
    def _require_line(service: CustomerInvoiceService,
                      line_id: Any) -> Dict[str, Any]:
        rows = service.ds.query(
            'SELECT * FROM %s WHERE id = ?' % LINE_TABLE, [line_id])
        if not rows:
            raise CustomerInvoiceError('发票行不存在', field_name='id',
                                       rule='INVOICE_SOURCE_INVALID')
        return rows[0]

    @staticmethod
    def _require_draft_parent(service: CustomerInvoiceService,
                              invoice_id: Any) -> Dict[str, Any]:
        if _blank(invoice_id):
            raise CustomerInvoiceError('发票行必须指定父发票',
                                       field_name='invoice_id',
                                       rule='INVOICE_STATE_INVALID')
        header = service._require_header(invoice_id)
        if header.get('status') != STATUS_DRAFT:
            raise CustomerInvoiceError(
                '仅草稿发票可增删改行（当前状态：%s）' % header.get('status'),
                field_name='invoice_id', rule='INVOICE_POSTED_READONLY')
        return header
