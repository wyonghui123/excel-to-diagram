# -*- coding: utf-8 -*-
"""采购侧付款条件带出链 —— 与销售侧 `CustomerSalesOrgService` 对称。

依据: docs/specs/spec-vendor-invoice-object-model-2026-11-11.md §23.5

带出链（逐级回退；调用方显式给值一律不覆盖）：
  1. PO 锚点：发票行上的 `schedule_id` / `order_line_id` / `receipt_line_id`
     回溯 `purchase_orders.payment_term_id`（首个非空命中即用）
  2. 供应商档案：`vendor_accounts.default_payment_term_id`
  3. 留空：过账按期即期 1 期 100%（R-VI-34 的「空条件」分支）

主数据缺失 / 查询异常一律返回 None，不阻断保存与过账。
"""

import logging
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger(__name__)


def _table_name(entity: str, fallback: str) -> str:
    """表名走元模型 SSOT；未声明时回退字面量。"""
    from meta.core.metadata_resolver import MetadataResolver
    return MetadataResolver.get_table_name(entity) or fallback


def _account_table() -> str:
    return _table_name('vendor_account', 'vendor_accounts')


def _po_table() -> str:
    return _table_name('purchase_order', 'purchase_orders')


def _po_line_table() -> str:
    return _table_name('purchase_order_line', 'purchase_order_lines')


def _po_schedule_table() -> str:
    return _table_name('purchase_order_schedule', 'purchase_order_schedules')


def _receipt_line_table() -> str:
    return _table_name('receipt_line', 'receipt_lines')


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class VendorPaymentTermService:
    """按「PO → 供应商默认 → 留空」解析采购发票付款条件。"""

    def __init__(self, ds):
        self.ds = ds

    # ---------------------------------------------------------------- 解析入口
    def resolve(self, supplier_account_id: Any,
                lines: Optional[Iterable[Dict[str, Any]]] = None,
                explicit: Any = None) -> Optional[int]:
        """返回付款条件 id；显式给值优先，解析不到返回 None（即期）。"""
        if not _blank(explicit):
            return _int(explicit)
        from_po = self.resolve_from_lines(lines)
        if from_po is not None:
            return from_po
        return self.load_account_default(supplier_account_id)

    def resolve_from_lines(
            self, lines: Optional[Iterable[Dict[str, Any]]]) -> Optional[int]:
        """按发票行的 PO 锚点回溯订单付款条件（首个非空命中）。"""
        for line in lines or []:
            if not line:
                continue
            po_id = self._po_id_from_line(line)
            if po_id is None:
                continue
            term_id = self._po_payment_term(po_id)
            if term_id is not None:
                return term_id
        return None

    def load_account_default(self, vendor_account_id: Any) -> Optional[int]:
        account_id = _int(vendor_account_id)
        if account_id is None:
            return None
        rows = self._query(
            'SELECT default_payment_term_id FROM {0} WHERE id = ?'.format(
                _account_table()),
            [account_id], _account_table())
        return _int(rows[0].get('default_payment_term_id')) if rows else None

    # ---------------------------------------------------------------- 内部实现
    def _po_id_from_line(self, line: Dict[str, Any]) -> Optional[int]:
        """行锚点 → 采购订单 id（计划期次 > 订单行 > 收货行）。"""
        for field, table in (
                ('schedule_id', _po_schedule_table()),
                ('order_line_id', _po_line_table()),
                ('receipt_line_id', _receipt_line_table()),
        ):
            row_id = _int(line.get(field))
            if row_id is None:
                continue
            rows = self._query(
                'SELECT order_id FROM {0} WHERE id = ?'.format(table),
                [row_id], table)
            po_id = _int(rows[0].get('order_id')) if rows else None
            if po_id is not None:
                return po_id
        return None

    def _po_payment_term(self, po_id: int) -> Optional[int]:
        rows = self._query(
            'SELECT payment_term_id FROM {0} WHERE id = ?'.format(_po_table()),
            [po_id], _po_table())
        return _int(rows[0].get('payment_term_id')) if rows else None

    def _query(self, sql: str, params: list, table: str) -> list:
        """表不存在或查询失败时降级为空结果（不阻断保存/过账）。"""
        try:
            if not self.ds.table_exists(table):
                return []
            return self.ds.query(sql, params) or []
        except Exception as e:  # pragma: no cover - 依赖注入层异常
            logger.warning('[vendor_payment_term] 查询 %s 失败（忽略）: %s', table, e)
            return []