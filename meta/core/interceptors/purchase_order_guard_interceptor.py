# -*- coding: utf-8 -*-
"""采购订单守卫拦截器 —— 抬头 / 订单行 / 计划行 / 需求分配的统一写入入口。

优先级 50（sales_order_guard 49 之后、PersistenceInterceptor 95 之前）：
  · before_action 做写前校验（spec §14.1 R-PO-0 ~ R-PO-18）；
  · after_action 做金额回写与采购取价 —— 拦截器 after 为逆序执行，
    优先级 50 低于 PersistenceInterceptor 的 95，故回写时行已落库、新行 id 已回填。

受管范围：
  purchase_order            —— 创建 / 更新 / 删除
  purchase_order_line       —— 创建 / 更新 / 删除（含取价与金额回写）
  purchase_order_schedule   —— 创建 / 更新 / 删除（R-PO-11，编号自增在守卫内完成）
  demand_allocation         —— 创建 / 更新 / 删除（R-PO-9 / R-PO-17）

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过拦截器链
（与 sales_order_guard 同一限制）。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.services.approval_task_service import ApprovalTaskService
from meta.services.document_approval_service import DocumentApprovalResolver
from meta.services.purchase_order_guard_service import (
    PurchaseOrderGuardError,
    PurchaseOrderGuardService,
)
from meta.services.purchase_pricing_service import (
    PurchasePricingError,
    PurchasePricingService,
)
from meta.services.sales_order_amount_service import SalesOrderAmountError

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

ORDER_OBJECT = 'purchase_order'
LINE_OBJECT = 'purchase_order_line'
SCHEDULE_OBJECT = 'purchase_order_schedule'
ALLOCATION_OBJECT = 'demand_allocation'

_WRITE_ACTIONS = ('crud_create', 'crud_update', 'crud_delete')
_ORDER_ID_KEY = 'po_parent_order_id'
#: 提交审批解析结果（after 侧据此建待办，spec §6.3 / §6.4）
_APPROVAL_FLAG = 'po_approval'
_STATUS_DRAFT = 'draft'
_STATUS_SUBMITTED = 'submitted'
_APPROVAL_NOT_REQUIRED = 'not_required'
_APPROVAL_PENDING = 'pending'
#: 抬头变更触发重取价的维度（spec §4.3 取价触发时点）
_PRICE_HEADER_FIELDS = ('price_date', 'currency_id', 'purchase_org_id',
                        'document_type_id', 'supplier_party_id')
#: 行变更触发重取价的维度
_PRICE_LINE_FIELDS = ('item_id', 'qty', 'uom_id', 'deliver_to_location_id')
_STATUS_CANCELLED = 'cancelled'


class PurchaseOrderGuardInterceptor(Interceptor):
    """采购订单四对象的写前校验 + after 金额 / 取价 / 取消级联。"""

    @property
    def priority(self) -> int:
        return 50

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id not in (ORDER_OBJECT, LINE_OBJECT, SCHEDULE_OBJECT,
                             ALLOCATION_OBJECT):
            return False
        return context.action in _WRITE_ACTIONS

    # ------------------------------------------------------------------
    # before
    # ------------------------------------------------------------------

    def before_action(self, context: 'ActionContext') -> None:
        guard = PurchaseOrderGuardService(context.data_source)
        object_id = getattr(context.meta_object, 'id', None)
        try:
            if object_id == ORDER_OBJECT:
                if context.action == 'crud_delete':
                    guard.validate_order_delete(context.object_id)
                    return
                if context.action == 'crud_update':
                    self._resolve_submit_approval(context)
                data, old_data = self._effective_data(context)
                guard.validate_order_write(
                    data, old_data=old_data,
                    is_create=context.action == 'crud_create')
                # TBD-10：守卫派生的采购法人快照回填到写入口径
                self._sync_params(
                    context, data, old_data, ('purchase_legal_entity_id',))
                return

            if object_id == SCHEDULE_OBJECT:
                if context.action == 'crud_delete':
                    guard.validate_schedule_delete(context.object_id)
                    return
                data, old_data = self._effective_data(context)
                guard.validate_schedule_write(
                    data, old_data=old_data,
                    is_create=context.action == 'crud_create')
                # 计划行序号由守卫自增后回填到写入口径
                self._sync_params(context, data, old_data, ('schedule_no',))
                return

            if object_id == ALLOCATION_OBJECT:
                if context.action == 'crud_delete':
                    guard.validate_allocation_delete(context.object_id)
                    return
                data, old_data = self._effective_data(context)
                guard.validate_allocation_write(
                    data, old_data=old_data,
                    is_create=context.action == 'crud_create')
                self._sync_params(context, data, old_data, ('reversed_at',))
                return

            # 采购订单行
            if context.action == 'crud_delete':
                # 删除后行已不在，after 侧靠这里记下的父单汇总
                context.extra[_ORDER_ID_KEY] = (context.old_data or {}).get('order_id')
                guard.validate_line_delete(context.object_id)
                return
            data, old_data = self._effective_data(context)
            context.extra[_ORDER_ID_KEY] = data.get('order_id')
            guard.validate_line_write(
                data, old_data=old_data,
                is_create=context.action == 'crud_create')
        except PurchaseOrderGuardError as e:
            self._raise_validation(e)

    # ------------------------------------------------------------------
    # after
    # ------------------------------------------------------------------

    def after_action(self, context: 'ActionContext') -> None:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id == SCHEDULE_OBJECT or object_id == ALLOCATION_OBJECT:
            # 计划行 / 分配不参与行金额与取价（取消冲销已在守卫内完成）
            return
        if object_id == ORDER_OBJECT:
            self._after_order_write(context)
            return
        if object_id != LINE_OBJECT:
            return
        self._after_line_write(context)

    def _after_line_write(self, context: 'ActionContext') -> None:
        guard = PurchaseOrderGuardService(context.data_source)
        try:
            line_id = self._line_id(context)
            if context.action != 'crud_delete' and line_id not in (None, ''):
                self._apply_line_pricing(context, line_id)
                values = guard.recompute_line(line_id)
                self._merge_result(context, values)

                # R-PO-10：行取消 → 其 active 分配冲销
                params = dict(context.params or {})
                if str(params.get('status') or '').lower() == _STATUS_CANCELLED \
                        and str((context.old_data or {}).get('status') or '').lower() \
                        != _STATUS_CANCELLED:
                    guard.cascade_cancel_line(line_id)

            order_id = context.extra.get(_ORDER_ID_KEY)
            if order_id in (None, '') and context.old_data:
                order_id = context.old_data.get('order_id')
            if order_id in (None, ''):
                return
            totals = guard.recompute_order(order_id)
            self._merge_result(context, totals)
        except SalesOrderAmountError as e:
            self._raise_validation(e)
        except PurchasePricingError as e:
            self._raise_validation(e)

    def _after_order_write(self, context: 'ActionContext') -> None:
        self._create_approval_task(context)
        if context.action != 'crud_update':
            return
        params = dict(context.params or {})
        pricing = PurchasePricingService(context.data_source)
        if set(params) & set(_PRICE_HEADER_FIELDS):
            try:
                pricing.reprice_order(context.object_id, force=False, strict=False)
            except PurchasePricingError as e:
                self._raise_validation(e)
                return
        guard = PurchaseOrderGuardService(context.data_source)
        totals = guard.recompute_order(context.object_id)
        self._merge_result(context, totals)

    # ------------------------------------------------------------------
    # 取价接线
    # ------------------------------------------------------------------

    def _apply_line_pricing(self, context: 'ActionContext', line_id) -> None:
        """手工改价只打标记；其余按触发维度取价（§4.3）。"""
        params = dict(context.params or {})
        pricing = PurchasePricingService(context.data_source)

        if context.action == 'crud_create':
            manual = params.get('unit_price') not in (None, '')
        else:
            if 'unit_price' in params and params.get('unit_price') is not None:
                pricing.mark_manual(line_id)
                return
            if not (set(params) & set(_PRICE_LINE_FIELDS)):
                return
            manual = False

        if manual:
            pricing.mark_manual(line_id)
            return
        pricing.price_line(line_id)

    # ------------------------------------------------------------------
    # 审批接线（spec §6.3 / §6.4）
    # ------------------------------------------------------------------

    def _resolve_submit_approval(self, context: 'ActionContext') -> None:
        """草稿 → 提交时解析审批策略：命中则 approval_status=pending，after 建任务。"""
        params = dict(context.params or {})
        old = dict(context.old_data or {})
        if str(params.get('status') or '').strip().lower() != _STATUS_SUBMITTED:
            return
        if str(old.get('status') or _STATUS_DRAFT).strip().lower() != _STATUS_DRAFT:
            return
        record_id = context.object_id or params.get('id')
        if record_id in (None, ''):
            return
        try:
            decision = DocumentApprovalResolver(context.data_source).resolve(
                ORDER_OBJECT, record_id)
        except Exception as error:  # noqa: BLE001 - 策略表异常不得静默放行
            self._raise_validation(PurchaseOrderGuardError(
                '审批策略解析失败: {0}'.format(error),
                field_name='approval_status', rule='PO_APPROVAL_RESOLVE_FAILED'))
            return

        if not decision.get('required'):
            # R4：无命中策略 = 免审批；同时清理上一轮驳回留下的 rejected 缓存
            context.params['approval_status'] = _APPROVAL_NOT_REQUIRED
            return

        context.params['approval_status'] = _APPROVAL_PENDING
        extra = getattr(context, 'extra', None)
        if extra is not None:
            extra[_APPROVAL_FLAG] = {
                'record_id': record_id,
                'policy_snapshot': decision.get('snapshot'),
            }
        logger.info('[PurchaseOrder] id=%s 命中审批策略 %s，approval_status=pending',
                    record_id, decision.get('policy_code'))

    def _create_approval_task(self, context: 'ActionContext') -> None:
        """提交已落库后补建审批待办（避免持久化失败留下孤儿任务）。"""
        extra = getattr(context, 'extra', None) or {}
        info = extra.pop(_APPROVAL_FLAG, None)
        if not info:
            return
        result = getattr(context, 'result', None)
        if result is not None and not getattr(result, 'success', True):
            return
        actor = str(getattr(context, 'user_id', '') or
                    getattr(context, 'user_name', '') or '')
        try:
            ApprovalTaskService(context.data_source).create_task(
                ORDER_OBJECT, info['record_id'],
                policy_snapshot=info.get('policy_snapshot'), actor=actor)
        except Exception as error:  # noqa: BLE001 - 建任务失败不阻断已完成的提交
            logger.warning('[PurchaseOrder] 审批任务创建失败: %s', error)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _effective_data(context: 'ActionContext') -> tuple:
        """更新可能是部分字段：与旧行合并还原「更新后的有效行」。"""
        params = dict(context.params or {})
        if context.action != 'crud_update':
            return params, context.old_data
        merged = dict(context.old_data or {})
        merged.update(params)
        return merged, context.old_data

    @staticmethod
    def _sync_params(context: 'ActionContext', data: dict, old_data,
                     fields) -> None:
        """把守卫在 data 上派生出的字段回填到实际写入口径。"""
        params = context.params
        if not isinstance(params, dict):
            return
        old = old_data or {}
        for field in fields:
            if field not in data:
                continue
            if context.action != 'crud_create' and data.get(field) == old.get(field):
                continue
            params[field] = data.get(field)

    @staticmethod
    def _line_id(context: 'ActionContext'):
        line_id = context.object_id
        if line_id in (None, '') and context.result and context.result.data:
            line_id = context.result.data.get('id')
        return line_id

    @staticmethod
    def _merge_result(context: 'ActionContext', values) -> None:
        """把重算结果并回响应体（Decimal → float，便于 JSON 序列化）。"""
        if not values or not context.result or not context.result.data:
            return
        for key, value in values.items():
            context.result.data[key] = (
                None if value is None else float(value))

    @staticmethod
    def _raise_validation(error) -> None:
        from meta.core.exceptions import ValidationFailedError

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
