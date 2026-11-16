# -*- coding: utf-8 -*-
"""金额重算（显式动作 `amount.recalc`）—— 四类单据共用同一入口。

设计（用户诉求「重新计算也应统一」）:
  · 前端不再依赖各单据的隐式重算；由本 Action 显式触发，回溯面板同一按钮；
  · 算术仍只调用既有内核（SO/PO/VI 的 `recompute_line` / `recompute_order`，
    CI 的 `CustomerInvoiceService.recalc`），本文件不出现任何公式；
  · 状态门槛与内核一致：草稿可重算（CI 沿用草稿/已提交）；
    已确认/已过账的金额是快照，拒绝重算，避免破坏 R9 / VI 过账只读。

返回信封沿用 BO Action 约定：{'success', 'data', 'message'}。
"""

import logging
from decimal import Decimal
from typing import Any, Dict

from meta.core.db_path import get_meta_db_path

logger = logging.getLogger(__name__)

RECALC_ALLOWED_STATUS = {
    'sales_order': ('draft',),
    'purchase_order': ('draft',),
    'vendor_invoice': ('draft',),
    'customer_invoice': ('draft', 'submitted'),
}

HEADER_TABLE = {
    'sales_order': 'sales_orders',
    'purchase_order': 'purchase_orders',
    'vendor_invoice': 'vendor_invoices',
    'customer_invoice': 'customer_invoices',
}

LINE_TABLE = {
    'sales_order': ('sales_order_lines', 'order_id'),
    'purchase_order': ('purchase_order_lines', 'order_id'),
    'vendor_invoice': ('vendor_invoice_lines', 'invoice_id'),
}


def _table(entity: str, fallback: str) -> str:
    """表名走元模型 SSOT；未声明时回退字面量。"""
    from meta.core.metadata_resolver import MetadataResolver
    return MetadataResolver.get_table_name(entity) or fallback


class AmountRecalcError(ValueError):
    """重算被拒绝（状态不允许 / 对象不支持 / 单据不存在）。"""

    def __init__(self, message: str, rule: str = ''):
        super().__init__(message)
        self.rule = rule


class AmountRecalcService:
    """按对象类型分发到既有金额内核，只做编排。"""

    def __init__(self, data_source):
        self.ds = data_source

    def recalc(self, object_type: str, record_id: Any) -> Dict[str, Any]:
        if object_type not in HEADER_TABLE:
            raise AmountRecalcError(
                '不支持重算的金额对象: %s' % object_type, rule='AMOUNT_RECALC_UNSUPPORTED')
        if record_id in (None, ''):
            raise AmountRecalcError('缺少单据 id', rule='AMOUNT_RECALC_NO_ID')

        header = self._load_header(object_type, record_id)
        if not header:
            raise AmountRecalcError('单据不存在: %s#%s' % (object_type, record_id),
                                    rule='AMOUNT_RECALC_NOT_FOUND')
        status = str(header.get('status') or '')
        allowed = RECALC_ALLOWED_STATUS.get(object_type, ())
        if status not in allowed:
            raise AmountRecalcError(
                '当前状态 %s 不允许重算（允许: %s）'
                % (status or '未知', ' / '.join(allowed)),
                rule='AMOUNT_RECALC_STATE_INVALID')

        if object_type == 'customer_invoice':
            return self._recalc_customer_invoice(record_id)
        return self._recalc_kernel(object_type, record_id)

    # ------------------------------------------------------------------
    def _load_header(self, object_type: str, record_id: Any) -> Dict[str, Any]:
        rows = self.ds.query(
            'SELECT id, status FROM %s WHERE id = ?'
            % _table(object_type, HEADER_TABLE[object_type]), [record_id])
        return dict(rows[0]) if rows else {}

    def _line_ids(self, object_type: str, record_id: Any):
        table, fk = LINE_TABLE[object_type]
        table = _table(object_type + '_line', table)
        rows = self.ds.query(
            'SELECT id FROM %s WHERE %s = ? ORDER BY id'
            % (table, fk), [record_id])
        return [row['id'] for row in rows]

    def _recalc_kernel(self, object_type: str, record_id: Any):
        if object_type == 'sales_order':
            from meta.services.sales_order_amount_service import (
                SalesOrderAmountService)
            service = SalesOrderAmountService(self.ds)
        elif object_type == 'vendor_invoice':
            from meta.services.vendor_invoice_amount_service import (
                VendorInvoiceAmountService)
            service = VendorInvoiceAmountService(self.ds)
        else:  # purchase_order
            from meta.services.purchase_order_guard_service import (
                PurchaseOrderGuardService)
            service = PurchaseOrderGuardService(self.ds)

        line_ids = self._line_ids(object_type, record_id)
        with self.ds.transaction():
            for line_id in line_ids:
                service.recompute_line(line_id)
            header_values = service.recompute_order(record_id)
        return {
            'object_type': object_type,
            'id': record_id,
            'line_count': len(line_ids),
            'header': {k: (float(v) if isinstance(v, Decimal) else v)
                       for k, v in (header_values or {}).items()},
            'action': 'amount.recalc',
        }

    def _recalc_customer_invoice(self, record_id: Any):
        from meta.services.customer_invoice_service import CustomerInvoiceService
        result = CustomerInvoiceService(self.ds).recalc(record_id)
        return {
            'object_type': 'customer_invoice',
            'id': record_id,
            'result': result,
            'action': 'amount.recalc',
        }


def amount_recalc_handler(params: Dict[str, Any],
                          context: Dict[str, Any]) -> Dict[str, Any]:
    """BO Action：按统一契约重算单据金额（只支持草稿类状态）。"""
    p = params or {}
    object_type = str(p.get('object_type') or '').strip()
    record_id = p.get('id')
    if record_id in (None, ''):
        record_id = p.get('record_id')
    if not object_type or record_id in (None, ''):
        return {'success': False, 'data': None,
                'message': '缺少 object_type / id 参数'}

    try:
        _set_user_context()
        from meta.core.datasource import get_data_source
        ds = get_data_source('sqlite', database=get_meta_db_path())
    except Exception as exc:  # noqa: BLE001
        logger.exception('[amount_recalc] 初始化失败: %s', exc)
        return {'success': False, 'data': None,
                'message': '服务初始化失败: %s' % exc}

    try:
        data = AmountRecalcService(ds).recalc(object_type, record_id)
    except AmountRecalcError as exc:
        return {'success': False, 'data': None, 'message': str(exc),
                'rule': exc.rule}
    except Exception as exc:  # noqa: BLE001
        logger.exception('[amount_recalc] %s#%s 重算失败: %s',
                         object_type, record_id, exc)
        return {'success': False, 'data': None, 'message': str(exc)}

    return {'success': True, 'data': data, 'message': '金额已按当前数据重算'}


def _set_user_context():
    """写入审计日志的用户上下文（无请求上下文时静默跳过）。"""
    from flask import request
    from meta.services.auth_middleware import get_current_user
    from meta.core.bo_framework import bo_framework
    current_user = get_current_user() or {}
    bo_framework.set_user_context(
        user_id=current_user.get('user_id'),
        user_name=current_user.get(
            'display_name', current_user.get('username', 'unknown')),
        ip_address=request.remote_addr,
    )