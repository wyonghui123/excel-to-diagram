# -*- coding: utf-8 -*-
"""采购发票守卫拦截器 —— 抬头状态迁移与行写入的统一入口。

优先级 51（与 shipment / customer_invoice 同批，受管对象不同互不冲突；
必须在 PersistenceInterceptor 95 之前）：
  · before_action 把带跨表副作用的状态迁移委托
    `VendorInvoiceMatchService`（submit / post / cancel）；
  · after_action 把服务结果并回响应体（匹配状态等）。

受管范围：
  vendor_invoice       —— 创建（仅草稿）/ 更新（状态迁移 + posted 只读）/ 删除（仅草稿）
  vendor_invoice_line  —— 创建 / 更新 / 删除（父单必须为草稿）
其余对象与动作零开销短路。

口径：
  · 前端 StateTransitionButtons 走 `PUT /bo/vendor_invoice/{id}` + `{status}`，
    因此状态机必须在拦截器链里接线，否则可直接把 status 改成 posted 而绕过
    匹配 / 查重 / doc_flow 边写入；
  · 红冲（posted → reversed）委托 `VendorInvoiceMatchService.reverse`，
    由 ReversalOrchestrator 生成红字采购贷项凭证并写红字冲减边；
    状态推进失败即整体不生效（不留半成品副作用）；
  · 已知边界：拦截器链只覆盖 bo_api 写路径，manage_api 与 Excel 导入绕过本守卫。
"""

import logging
from typing import Any, Dict, TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor
from meta.services.vendor_invoice_match_service import (
    ADJUSTMENT_DIRECTIONS,
    ADJUSTMENT_INCREASE,
    CATEGORY_ADJUSTMENT,
    CATEGORY_INVOICE,
    LINE_TABLE,
    STATUS_CANCELLED,
    STATUS_DRAFT,
    STATUS_POSTED,
    STATUS_REVERSED,
    STATUS_SUBMITTED,
    VendorInvoiceError,
    VendorInvoiceMatchService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

HEADER_OBJECT = 'vendor_invoice'
LINE_OBJECT = 'vendor_invoice_line'
_WRITE_ACTIONS = ('crud_create', 'crud_update', 'crud_delete')
#: 只能由红冲引擎生成的单据类别（手工创建会静默零冲减，必须拒绝）
_MANUAL_FORBIDDEN_CATEGORIES = ('credit_memo', 'debit_memo', 'cancellation')
_RESULT_KEY = 'vendor_invoice_result'
_RESULT_KEYS = ('status', 'match_status', 'match_exception_reason')


def _object_id(context) -> Any:
    """目标记录 ID：优先 ActionContext 属性，退化到入参 id（SimpleNamespace 场景）。"""
    return getattr(context, 'object_id', None) or (context.params or {}).get('id')


def _blank(value: Any) -> bool:
    return value is None or value == ''


class VendorInvoiceGuardInterceptor(Interceptor):
    """采购发票头 / 行的守卫与状态迁移接线。"""

    @property
    def priority(self) -> int:
        return 51

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id not in (HEADER_OBJECT, LINE_OBJECT):
            return False
        return context.action in _WRITE_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        object_id = getattr(context.meta_object, 'id', None)
        try:
            if object_id == HEADER_OBJECT:
                self._guard_header(context)
            elif object_id == LINE_OBJECT:
                self._guard_line(context)
        except VendorInvoiceError as error:
            raise ValidationFailedError(
                message=str(error),
                details=[{
                    'field_name': error.field,
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
            for key in _RESULT_KEYS:
                if key in info and info[key] is not None:
                    context.result.data[key] = info[key]

    # ------------------------------------------------------------------ 抬头

    def _guard_header(self, context: 'ActionContext') -> None:
        params = context.params
        if not isinstance(params, dict):
            return
        service = VendorInvoiceMatchService(context.data_source)
        invoice_id = _object_id(context)

        if context.action == 'crud_delete':
            header = service._require_header(invoice_id)
            if header.get('status') != STATUS_DRAFT:
                raise VendorInvoiceError(
                    '仅草稿采购发票可删除（当前状态：{0}）'.format(header.get('status')),
                    'VI_DELETE_FORBIDDEN', 'status')
            return

        if context.action == 'crud_create':
            target = params.get('status')
            if not _blank(target) and target != STATUS_DRAFT:
                raise VendorInvoiceError(
                    '采购发票创建时状态只能为草稿', 'VI_STATE_INVALID', 'status')
            category = self._resolve_category(service, params)
            if category in _MANUAL_FORBIDDEN_CATEGORIES:
                raise VendorInvoiceError(
                    '贷项 / 借项 / 取消凭证只能由采购发票红冲生成，不支持手工创建',
                    'VI_MANUAL_ADJUSTMENT_FORBIDDEN', 'document_category')
            if category == CATEGORY_ADJUSTMENT:
                self._guard_adjustment_create(service, params)
            return

        old_data = context.old_data or {}
        header = service._require_header(invoice_id)
        current = old_data.get('status') or header.get('status')
        category = str(old_data.get('document_category')
                       or header.get('document_category') or '')
        target = params.get('status')

        # 单据类别由单据类型派生，任何状态下都不允许直接改写
        if not _blank(params.get('document_category')) and \
                params.get('document_category') != old_data.get('document_category'):
            raise VendorInvoiceError(
                '单据类别由单据类型派生，不可修改',
                'VI_POSTED_READONLY', 'document_category')

        if current == STATUS_POSTED:
            if target == STATUS_REVERSED:
                if category == CATEGORY_ADJUSTMENT:
                    raise VendorInvoiceError(
                        '调整单不支持红冲，请新建方向相反的反向调整单',
                        'VI_ADJUSTMENT_NOT_REVERSIBLE', 'status')
                extra = {key for key in params
                         if key not in ('id', 'status', 'reversal_reason')}
                if extra:
                    raise VendorInvoiceError(
                        '已过账采购发票红冲时只接受红冲原因',
                        'VI_POSTED_READONLY', sorted(extra)[0])
                reason = params.get('reversal_reason')
                if _blank(reason):
                    raise VendorInvoiceError(
                        '红冲原因必填', 'VI_REVERSAL_REASON_REQUIRED',
                        'reversal_reason')
                result = service.reverse(invoice_id, reason=reason)
                context.extra[_RESULT_KEY] = result
                params.clear()
                params.update({'id': invoice_id, 'status': STATUS_REVERSED})
                return
            extra = {key for key in params if key not in ('id', 'status')}
            if extra or (not _blank(target) and target != STATUS_POSTED):
                hint = ('已过账调整单只读，仅允许新建反向调整单'
                        if category == CATEGORY_ADJUSTMENT
                        else '已过账采购发票只读，仅允许红冲')
                raise VendorInvoiceError(hint, 'VI_POSTED_READONLY', 'status')
            return

        if current in (STATUS_REVERSED, STATUS_CANCELLED):
            raise VendorInvoiceError(
                '采购发票已处于终态 {0}，禁止任何修改'.format(current),
                'VI_POSTED_READONLY', 'status')

        if current == STATUS_SUBMITTED:
            extra = {key for key in params if key not in ('id', 'status')}
            if extra:
                raise VendorInvoiceError(
                    '已提交采购发票内容已锁定，仅允许状态迁移',
                    'VI_POSTED_READONLY', sorted(extra)[0])

        if _blank(target) or target == current:
            return

        if current == STATUS_DRAFT and target == STATUS_SUBMITTED:
            result = service.submit(invoice_id)
        elif current == STATUS_DRAFT and target == STATUS_CANCELLED:
            result = service.cancel(invoice_id)
        elif current == STATUS_SUBMITTED and target == STATUS_POSTED:
            result = service.post(invoice_id)
        elif current == STATUS_SUBMITTED and target == STATUS_CANCELLED:
            result = service.cancel(invoice_id)
        else:
            raise VendorInvoiceError(
                '不允许的状态迁移：{0} → {1}'.format(current, target),
                'VI_STATE_INVALID', 'status')

        context.extra[_RESULT_KEY] = result
        params.clear()
        params.update({'id': invoice_id, 'status': target})

    @staticmethod
    def _guard_adjustment_create(service: VendorInvoiceMatchService,
                                 params: Dict[str, Any]) -> None:
        """调整单创建前置校验：原票 posted / 方向合法 / 原因必填。"""
        direction = params.get('adjustment_direction')
        direction = '' if direction is None else str(direction).strip()
        if direction not in ADJUSTMENT_DIRECTIONS:
            raise VendorInvoiceError(
                '调整方向必须为 increase / decrease',
                'VI_ADJUSTMENT_DIRECTION_INVALID', 'adjustment_direction')
        reason = params.get('adjustment_reason')
        if reason is None or not str(reason).strip():
            raise VendorInvoiceError(
                '调整单必须填写调整原因', 'VI_ADJUSTMENT_REASON_REQUIRED',
                'adjustment_reason')
        original_id = params.get('adjustment_of_invoice_id')
        if _blank(original_id):
            raise VendorInvoiceError(
                '调整单必须回指原发票', 'VI_ADJUSTMENT_SOURCE_INVALID',
                'adjustment_of_invoice_id')
        header = service._require_header(original_id)
        if str(header.get('document_category') or '') not in (
                CATEGORY_INVOICE, CATEGORY_ADJUSTMENT) or \
                header.get('status') != STATUS_POSTED:
            raise VendorInvoiceError(
                '只有已过账的采购发票 / 调整单可创建调整单',
                'VI_ADJUSTMENT_SOURCE_NOT_POSTED', 'adjustment_of_invoice_id')
        if not _blank(params.get('reversal_of_invoice_id')) or \
                not _blank(params.get('reversal_reason')):
            raise VendorInvoiceError(
                '调整单不允许携带红冲字段',
                'VI_POSTED_READONLY', 'reversal_of_invoice_id')
        if header.get('document_category') == CATEGORY_ADJUSTMENT and \
                direction == ADJUSTMENT_INCREASE:
            # 调整行不落锚点列，increase 过账无法解析锚点（与服务层一致）
            raise VendorInvoiceError(
                '调整单不支持再增加数量，请对原发票行做 increase 调整',
                'VI_ADJUSTMENT_INCREASE_UNSUPPORTED', 'adjustment_direction')

    @staticmethod
    def _resolve_category(service: VendorInvoiceMatchService,
                          params: Dict[str, Any]) -> str:
        """单据类别：优先入参显式值，其次由单据类型派生。"""
        value = params.get('document_category')
        if not _blank(value):
            return str(value)
        type_id = params.get('document_type_id')
        if _blank(type_id):
            return ''
        rows = service.ds.query(
            'SELECT document_category FROM type_definitions WHERE id = ?',
            [type_id])
        return str(rows[0].get('document_category') or '') if rows else ''

    # ------------------------------------------------------------------ 行

    def _guard_line(self, context: 'ActionContext') -> None:
        params = context.params
        if not isinstance(params, dict):
            return
        service = VendorInvoiceMatchService(context.data_source)

        if context.action == 'crud_create':
            invoice_id = params.get('invoice_id')
            parent = self._require_draft_parent(service, invoice_id)
            if str(parent.get('document_category') or '') == CATEGORY_ADJUSTMENT:
                original_line_id = params.get('invoice_line_id')
                if _blank(original_line_id):
                    raise VendorInvoiceError(
                        '调整行必须回指原发票行', 'VI_ADJUSTMENT_ANCHOR_REQUIRED',
                        'invoice_line_id')
                self._require_source_line(service, original_line_id)
            if _blank(params.get('line_no')):
                params['line_no'] = self._next_line_no(service, invoice_id)
            return

        existing = self._require_line(service, _object_id(context))
        self._require_draft_parent(service, existing.get('invoice_id'))

    @staticmethod
    def _next_line_no(service: VendorInvoiceMatchService, invoice_id: Any) -> int:
        rows = service.ds.query(
            'SELECT COALESCE(MAX(line_no), 0) + 1 AS next_no '
            'FROM {0} WHERE invoice_id = ?'.format(LINE_TABLE), [invoice_id])
        return int(rows[0]['next_no'] or 1) if rows else 1

    @staticmethod
    def _require_line(service: VendorInvoiceMatchService,
                      line_id: Any) -> Dict[str, Any]:
        rows = service.ds.query(
            'SELECT * FROM {0} WHERE id = ?'.format(LINE_TABLE), [line_id])
        if not rows:
            raise VendorInvoiceError(
                '采购发票行不存在', 'VI_LINE_NOT_FOUND', 'id')
        return rows[0]

    @staticmethod
    def _require_source_line(service: VendorInvoiceMatchService,
                             line_id: Any) -> None:
        rows = service.ds.query(
            'SELECT id FROM {0} WHERE id = ?'.format(LINE_TABLE), [line_id])
        if not rows:
            raise VendorInvoiceError(
                '调整行回指的原发票行不存在', 'VI_ADJUSTMENT_ANCHOR_REQUIRED',
                'invoice_line_id')

    @staticmethod
    def _require_draft_parent(service: VendorInvoiceMatchService,
                              invoice_id: Any) -> Dict[str, Any]:
        if _blank(invoice_id):
            raise VendorInvoiceError(
                '采购发票行必须指定父发票', 'VI_STATE_INVALID', 'invoice_id')
        header = service._require_header(invoice_id)
        if header.get('status') != STATUS_DRAFT:
            raise VendorInvoiceError(
                '仅草稿采购发票可增删改行（当前状态：{0}）'.format(
                    header.get('status')),
                'VI_POSTED_READONLY', 'invoice_id')
        return header