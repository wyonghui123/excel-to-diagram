# -*- coding: utf-8 -*-
"""逆向原语注册表（Reversal Platform 阶段 D1）。

所有原语统一签名 ``(ds, args, ctx) -> Dict[str, Any]``：

- ``ds``   ：应用数据源（事务由编排器持有，原语不自行开事务）
- ``args`` ：已解析占位符的声明参数（见规格 §7.2）
- ``ctx``  ：:class:`ReversalContext`（schema_id / doc_id / ref / now / reason / row）

纪律（规格 §8.1 / §15 R6）：
- **只转调既有服务实现**，不复制业务逻辑；
- 按事实键定位，重复调用必须幂等（既有服务已保证）；
- 返回值中的 ``txn_ids`` 供后续写面引用（``{<face_id>.txn_ids}``）。

对应方案: docs/specs/spec-reversal-platform-2026-11-06.md §8.1
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReversalContext:
    """一次逆向执行的上下文（原语只读）。"""

    ds: Any
    schema_id: str
    doc_id: Any
    ref: str = ""
    now: str = ""
    reason: str = ""
    row: Dict[str, Any] = field(default_factory=dict)
    executed: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    user_info: Optional[Dict[str, Any]] = None
    # 调用方透传参数（如预分配的红字单号 / 业务日期），只读
    params: Dict[str, Any] = field(default_factory=dict)


def _txn_ids(result: Dict[str, Any]) -> List[Any]:
    return [txn.get("id") for txn in (result.get("transactions") or [])
            if isinstance(txn, dict) and txn.get("id") is not None]


# ─────────────────────────────────────────────────────────────────────────────
# 库存
# ─────────────────────────────────────────────────────────────────────────────

def inventory_reverse_by_event(ds, args, ctx) -> Dict[str, Any]:
    """按正向过账事件键生成 REVERSAL 分录（方向自动翻转）。

    返回的 ``source_txn_ids`` 是**被冲销的原分录** id，供序列号/HU 面引用；
    ``txn_ids`` 是新建的反向分录 id（供后续面追溯）。
    """
    from meta.services.inventory_posting_service import InventoryPostingService

    event_key = str(args.get("event_key") or "")
    if not event_key:
        return {"created": 0, "txn_ids": [], "source_txn_ids": []}
    source_txn_ids: List[Any] = []
    try:
        rows = ds.query(
            "SELECT id FROM inventory_transactions WHERE source_event_key = ?",
            [event_key])
        source_txn_ids = [row.get("id") for row in rows
                          if row.get("id") is not None]
    except Exception as exc:  # noqa: BLE001 - 库存表未建时视为无分录
        logger.warning("[reversal] 原分录查询跳过: %s", exc)

    new_key = str(args.get("new_event_key") or (event_key + ":reverse"))
    transaction_date = args.get("transaction_date") or ctx.now
    source = {
        "source_doc_type": ctx.schema_id,
        "source_doc_id": args.get("source_doc_id", ctx.doc_id),
        "source_doc_no": args.get("source_doc_no"),
        "source_event_key": new_key,
        "transaction_date": transaction_date,
        "created_by": args.get("created_by") or
                      (ctx.user_info or {}).get("user_id"),
        "remark": args.get("remark") or "逆向冲销 %s" % ctx.schema_id,
    }
    service = InventoryPostingService(ds)
    if source_txn_ids and bool(args.get("allow_blocked_batch")):
        result = service.reverse(source_txn_ids, source,
                                 transaction_date=transaction_date,
                                 allow_blocked_batch=True)
    else:
        result = service.reverse_by_source(event_key, source,
                                           transaction_date=transaction_date)
    return {"created": int(result.get("created") or 0),
            "existing": len(result.get("existing") or []),
            "txn_ids": _txn_ids(result),
            "source_txn_ids": source_txn_ids}


def inventory_reverse_by_txn(ds, args, ctx) -> Dict[str, Any]:
    """按库存分录 id 列表生成 REVERSAL 分录（已冲销的幂等跳过）。"""
    from meta.services.inventory_posting_service import InventoryPostingService

    txn_ids = [raw for raw in (args.get("txn_ids") or []) if raw not in (None, "")]
    if not txn_ids:
        return {"created": 0, "txn_ids": []}
    event_key = str(args.get("new_event_key") or
                    "reverse:%s:%s" % (ctx.schema_id, ctx.doc_id))
    result = InventoryPostingService(ds).reverse(
        txn_ids,
        {"source_doc_type": ctx.schema_id,
         "source_doc_id": ctx.doc_id,
         "source_event_key": event_key,
         "transaction_date": ctx.now,
         "created_by": (ctx.user_info or {}).get("user_id")},
        transaction_date=ctx.now,
    )
    return {"created": int(result.get("created") or 0),
            "existing": len(result.get("existing") or []),
            "txn_ids": _txn_ids(result)}


# ─────────────────────────────────────────────────────────────────────────────
# 序列号 / 容器
# ─────────────────────────────────────────────────────────────────────────────

def serial_reverse_by_txn(ds, args, ctx) -> Dict[str, Any]:
    """按库存事务回退序列号使用状态；未启用序列号台账时为空操作。"""
    from meta.services.serial_number_service import (
        SerialNumberService, serial_schema_ready,
    )

    if not serial_schema_ready(ds):
        return {"count": 0, "errors": []}
    service = SerialNumberService(ds)
    count = 0
    errors: List[str] = []
    for txn_id in (args.get("txn_ids") or []):
        try:
            count += int(service.reverse_serial_event(txn_id).get("reversed") or 0)
        except Exception as exc:  # noqa: BLE001 - 单事务失败不阻断其余写面（对齐既有实现）
            logger.warning("[reversal] 序列号回退跳过 tx=%s: %s", txn_id, exc)
            errors.append(str(exc))
    return {"count": count, "errors": errors}


def serial_reverse_completion(ds, args, ctx) -> Dict[str, Any]:
    """按工单 + 完工收货单回退完工序列号状态（未启用序列号时为空操作）。"""
    from meta.services.serial_number_service import (
        SerialNumberService, serial_schema_ready,
    )

    if not serial_schema_ready(ds):
        return {"reversed": 0}
    work_order_id = args.get("work_order_id")
    receipt_id = args.get("receipt_id", ctx.doc_id)
    if work_order_id in (None, ""):
        return {"reversed": 0}
    SerialNumberService(ds).reverse_completion(work_order_id, receipt_id)
    return {"reversed": 1}


def hu_reverse_document(ds, args, ctx) -> Dict[str, Any]:
    """按来源单据整体倒序反冲 HU 事件（未启用 HU 时为空操作）。

    与 ``hu_rewind_by_txn`` 的区别：不依赖库存事务桥接，直接按
    ``(doc_type, doc_id)`` 回退该单据产生的装箱 / 发运 / 移库事件，
    对齐收货服务既有 ``reverse_document('receipt', id)`` 口径。
    """
    from meta.services.handling_unit_service import (
        HandlingUnitService, hu_schema_ready,
    )

    if not hu_schema_ready(ds):
        return {"count": 0}
    doc_type = str(args.get("doc_type") or ctx.schema_id)
    doc_id = args.get("doc_id", ctx.doc_id)
    if doc_id in (None, ""):
        return {"count": 0}
    HandlingUnitService(ds).reverse_document(doc_type, doc_id)
    return {"count": 1}


def hu_rewind_by_txn(ds, args, ctx) -> Dict[str, Any]:
    """按库存事务回溯其来源行上的 HU 事件并倒序反冲（未启用 HU 时为空操作）。

    HU 事件表无库存事务外键，故经 ``inventory_transactions.source_line_id``
    桥接（与发货服务按单据反冲同源）。
    """
    from meta.services.handling_unit_service import (
        HandlingUnitService, TXN_PACK, TXN_SHIP, hu_schema_ready,
    )

    if not hu_schema_ready(ds):
        return {"count": 0}
    txn_ids = [raw for raw in (args.get("txn_ids") or []) if raw not in (None, "")]
    if not txn_ids:
        return {"count": 0}
    placeholders = ", ".join("?" for _ in txn_ids)
    try:
        rows = ds.query(
            "SELECT DISTINCT source_line_id FROM inventory_transactions "
            "WHERE id IN (%s)" % placeholders, list(txn_ids))
    except Exception as exc:  # noqa: BLE001 - 未迁移库存表时视为无 HU 事实
        logger.warning("[reversal] HU 桥接查询跳过: %s", exc)
        return {"count": 0}

    service = HandlingUnitService(ds)
    count = 0
    for row in rows:
        line_id = row.get("source_line_id") if isinstance(row, dict) else None
        if line_id in (None, ""):
            continue
        txns = ds.query(
            "SELECT id FROM hu_transactions WHERE line_id = ? "
            "AND txn_type IN (?, ?) ORDER BY id DESC",
            [line_id, TXN_SHIP, TXN_PACK])
        for txn in txns:
            try:
                service.reverse_hu_transaction(txn.get("id"))
                count += 1
            except Exception as exc:  # noqa: BLE001 - 与发货服务同口径：不阻断红冲
                logger.warning("[reversal] HU 反冲跳过 txn=%s: %s",
                               txn.get("id"), exc)
    return {"count": count}


# ─────────────────────────────────────────────────────────────────────────────
# 预留
# ─────────────────────────────────────────────────────────────────────────────

def reservation_release_by_demand(ds, args, ctx) -> Dict[str, Any]:
    """按需求节点反向核销预留（未给 qty 时按已核销量回退）。"""
    from meta.services.inventory_reservation_service import (
        RESERVATION_TABLE, STATUS_FULFILLED, STATUS_PARTIALLY_FULFILLED,
        InventoryReservationService,
    )

    demand_type = str(args.get("demand_type") or ctx.schema_id)
    demand_id = args.get("demand_id", args.get("doc_id", ctx.doc_id))
    qty = args.get("qty")
    if qty in (None, ""):
        try:
            rows = ds.query(
                "SELECT qty_fulfilled FROM %s WHERE demand_object_type = ? "
                "AND demand_object_id = ? AND status IN (?, ?)" % RESERVATION_TABLE,
                [demand_type, demand_id, STATUS_PARTIALLY_FULFILLED,
                 STATUS_FULFILLED])
        except Exception as exc:  # noqa: BLE001 - 预留表缺失时视为无事实
            logger.warning("[reversal] 预留回退查询跳过: %s", exc)
            return {"count": 0, "unfulfilled": 0.0}
        qty = sum(float(row.get("qty_fulfilled") or 0) for row in rows)
    qty = float(qty or 0)
    if qty <= 0:
        return {"count": 0, "unfulfilled": 0.0}
    result = InventoryReservationService(ds).unfulfill_by_demand(
        demand_type, demand_id, qty, reason=ctx.reason)
    return {"count": len(result.get("reservations") or []),
            "unfulfilled": float(result.get("unfulfilled") or 0)}


# ─────────────────────────────────────────────────────────────────────────────
# 单据流边
# ─────────────────────────────────────────────────────────────────────────────

def edge_compensate_by_source(ds, args, ctx) -> Dict[str, Any]:
    """按源行追加 DOC_FLOW 补偿边（原边与红字历史全部保留）。

    ``source_ids`` 缺省时依次读 ``ctx.row['line_ids']`` 与 ``ctx.params['line_ids']``；
    皆空视为无事实。``derived_by`` 缺省 ``reversal``。
    """
    from meta.core.doc_flow_attach import reverse_edges_by_source

    source_bo = str(args.get("source_bo") or "")
    rule_ids = list(args.get("rule_ids") or [])
    ref = args.get("ref") or ctx.ref
    derived_by = str(args.get("derived_by") or "reversal")
    source_ids = (args.get("source_ids")
                  or ctx.row.get("line_ids")
                  or (ctx.params or {}).get("line_ids") or [])
    if not source_bo or not rule_ids or not ref or not source_ids:
        return {"created": 0, "reason": "SOURCE_IDS_REQUIRED"}

    created = 0
    for rule_id in rule_ids:
        for source_id in source_ids:
            created += reverse_edges_by_source(
                ds, str(rule_id), source_bo, source_id,
                ref_id=ref, derived_by=derived_by)
    return {"created": created}


# ─────────────────────────────────────────────────────────────────────────────
# 投影（纯重算，幂等）
# ─────────────────────────────────────────────────────────────────────────────

def recompute_schedule_delivered(ds, args, ctx) -> Dict[str, Any]:
    """按交货行事实重算计划行交付量（单一权威：禁止增量算术）。"""
    from meta.services.shipment_service import ShipmentService

    schedule_ids = [raw for raw in (args.get("schedule_ids") or []) if raw]
    if not schedule_ids and args.get("schedule_id"):
        schedule_ids = [args["schedule_id"]]
    if not schedule_ids:
        try:
            rows = ds.query(
                "SELECT DISTINCT schedule_id FROM shipment_lines "
                "WHERE delivery_id = ?", [ctx.doc_id])
            schedule_ids = [row.get("schedule_id") for row in rows
                            if row.get("schedule_id")]
        except Exception as exc:  # noqa: BLE001 - 无交货行表时视为无投影
            logger.warning("[reversal] 计划行投影跳过: %s", exc)
            return {"updated": 0}
    if not schedule_ids:
        return {"updated": 0}
    ShipmentService(ds)._refresh_schedule_delivery(schedule_ids)
    return {"updated": len(schedule_ids)}


def recompute_fulfillment(ds, args, ctx) -> Dict[str, Any]:
    """重算订单履约状态（无订单时跳过）。"""
    from meta.services.sales_order_fulfillment_service import (
        SalesOrderFulfillmentService,
    )

    order_id = args.get("order_id", ctx.row.get("order_id"))
    if order_id in (None, ""):
        return {"updated": 0}
    SalesOrderFulfillmentService(ds).recompute_order(order_id)
    return {"updated": 1}


def recompute_transfer_fulfillment(ds, args, ctx) -> Dict[str, Any]:
    """重算调拨单履约状态（纯派生，幂等）。"""
    from meta.services.transfer_order_service import TransferOrderService

    order_id = args.get("doc_id", ctx.doc_id)
    if order_id in (None, ""):
        return {"updated": 0}
    derived = TransferOrderService(ds).recompute_fulfillment(order_id)
    return {"updated": 1, "fulfillment_status": derived}


def recompute_purchase_fulfillment(ds, args, ctx) -> Dict[str, Any]:
    """重算采购订单履约状态（无订单时跳过）。"""
    from meta.services.purchase_order_fulfillment_service import (
        PurchaseOrderFulfillmentService,
    )

    order_ids = [raw for raw in (args.get("order_ids") or [])
                 if raw not in (None, "")]
    if not order_ids and args.get("order_id") not in (None, ""):
        order_ids = [args["order_id"]]
    if not order_ids:
        return {"updated": 0}
    service = PurchaseOrderFulfillmentService(ds)
    for order_id in order_ids:
        service.recompute_order(order_id)
    return {"updated": len(order_ids)}


def reverse_schedule_received(ds, args, ctx) -> Dict[str, Any]:
    """按红字单净收量回退 PO 计划行已收量（R-RC-10：只回退收货置位的完成）。"""
    from meta.services.receipt_service import ReceiptService

    items = [item for item in (args.get("items") or [])
             if isinstance(item, dict) and item.get("schedule_id") not in (None, "")]
    if not items:
        return {"updated": 0}
    service = ReceiptService(ds)
    for item in items:
        service.apply_schedule_reversal(item.get("schedule_id"), item.get("net"))
    return {"updated": len(items)}


def recompute_schedule_returned(ds, args, ctx) -> Dict[str, Any]:
    """按已过账退货行重算计划行 returned_qty（D6，幂等）。"""
    from meta.services.receipt_service import ReceiptService

    items = [item for item in (args.get("items") or [])
             if isinstance(item, dict) and item.get("schedule_id") not in (None, "")]
    if not items:
        return {"updated": 0}
    service = ReceiptService(ds)
    for item in items:
        service.recompute_schedule_returned(item.get("schedule_id"))
    return {"updated": len(items)}


def reservation_unfulfill_by_shipment(ds, args, ctx) -> Dict[str, Any]:
    """按交货行汇总反向核销销售订单行预留（恢复可用量）。"""
    from meta.services.inventory_reservation_service import (
        InventoryReservationService,
    )

    delivery_id = args.get("doc_id", ctx.doc_id)
    demand_type = str(args.get("demand_type") or "sales_order_line")
    excluded = str(args.get("exclude_status") or "cancelled")
    try:
        rows = ds.query(
            "SELECT order_line_id, qty, status FROM shipment_lines "
            "WHERE delivery_id = ?", [delivery_id])
    except Exception as exc:  # noqa: BLE001 - 无交货行表时视为无事实
        logger.warning("[reversal] 预留回退查询跳过: %s", exc)
        return {"count": 0, "unfulfilled": 0.0}

    grouped: Dict[Any, float] = {}
    for row in rows:
        if str(row.get("status") or "") == excluded:
            continue
        order_line_id = row.get("order_line_id")
        if order_line_id in (None, ""):
            continue
        grouped[order_line_id] = grouped.get(order_line_id, 0.0) + \
            float(row.get("qty") or 0)

    service = InventoryReservationService(ds)
    count = 0
    unfulfilled = 0.0
    for order_line_id, qty in grouped.items():
        if qty <= 0:
            continue
        result = service.unfulfill_by_demand(
            demand_type, order_line_id, qty, reason=ctx.reason)
        count += len(result.get("reservations") or [])
        unfulfilled += float(result.get("unfulfilled") or 0)
    return {"count": count, "unfulfilled": unfulfilled}


def shipment_reverse_lines(ds, args, ctx) -> Dict[str, Any]:
    """把交货行置 reversed（不改 cancelled 行），供计划行投影重算。"""
    from meta.services.shipment_service import STATUS_CANCELLED, STATUS_REVERSED

    delivery_id = args.get("doc_id", ctx.doc_id)
    now = args.get("now") or ctx.now
    cursor = ds.execute(
        "UPDATE shipment_lines SET status = ?, updated_at = ? "
        "WHERE delivery_id = ? AND status <> ?",
        [STATUS_REVERSED, now, delivery_id, STATUS_CANCELLED])
    return {"count": int(getattr(cursor, "rowcount", 0) or 0)}


def inventory_reverse_by_source(ds, args, ctx) -> Dict[str, Any]:
    """按来源单据枚举全部正向过账事件键并逐一镜像（已红冲的幂等跳过）。

    调拨单发货事件键形如 ``transfer_order:{id}:ship:{seq}``，同一单据可能存在
    多次发货；本原语按 ``(source_doc_type, source_doc_id)`` 全量反冲，
    镜像键为 ``{原键}:reverse``。返回的 ``source_txn_ids`` 供序列号面引用。
    """
    from meta.services.inventory_posting_service import InventoryPostingService

    doc_type = str(args.get("source_doc_type") or ctx.schema_id)
    doc_id = args.get("source_doc_id", ctx.doc_id)
    if doc_id in (None, ""):
        return {"created": 0, "existing": 0, "txn_ids": [],
                "source_txn_ids": [], "event_keys": []}
    try:
        rows = ds.query(
            "SELECT id, source_event_key FROM inventory_transactions "
            "WHERE source_doc_type = ? AND source_doc_id = ? "
            "AND source_event_key IS NOT NULL "
            "AND reversal_of_transaction_id IS NULL "
            "ORDER BY id", [doc_type, doc_id])
    except Exception as exc:  # noqa: BLE001 - 库存表未建时视为无分录
        logger.warning("[reversal] 来源单据分录查询跳过: %s", exc)
        return {"created": 0, "existing": 0, "txn_ids": [],
                "source_txn_ids": [], "event_keys": []}

    event_keys: List[str] = []
    source_txn_ids: List[Any] = []
    for row in rows:
        key = str(row.get("source_event_key") or "")
        if not key:
            continue
        if key not in event_keys:
            event_keys.append(key)
        if row.get("id") is not None:
            source_txn_ids.append(row.get("id"))

    if not event_keys:
        return {"created": 0, "existing": 0, "txn_ids": [],
                "source_txn_ids": [], "event_keys": []}

    transaction_date = args.get("transaction_date") or ctx.now
    service = InventoryPostingService(ds)
    created = 0
    existing = 0
    txn_ids: List[Any] = []
    for event_key in event_keys:
        source = {
            "source_doc_type": doc_type,
            "source_doc_id": doc_id,
            "source_doc_no": args.get("source_doc_no"),
            "source_event_key": event_key + ":reverse",
            "transaction_date": transaction_date,
            "created_by": args.get("created_by") or
                          (ctx.user_info or {}).get("user_id"),
            "remark": args.get("remark") or "逆向冲销 %s" % doc_type,
        }
        result = service.reverse_by_source(
            event_key, source, transaction_date=transaction_date)
        created += int(result.get("created") or 0)
        existing += len(result.get("existing") or [])
        txn_ids.extend(_txn_ids(result))
    return {"created": created, "existing": existing,
            "txn_ids": txn_ids, "source_txn_ids": source_txn_ids,
            "event_keys": event_keys}


def transfer_reverse_lines(ds, args, ctx) -> Dict[str, Any]:
    """把调拨行发货事实归零（不改 cancelled 行），供履约投影重算。"""
    from meta.services.transfer_order_service import LINE_STATUS_CANCELLED

    order_id = args.get("doc_id", ctx.doc_id)
    now = args.get("now") or ctx.now
    cursor = ds.execute(
        "UPDATE transfer_order_lines SET qty_shipped = 0, qty_received = 0, "
        "updated_at = ? WHERE transfer_order_id = ? AND status <> ?",
        [now, order_id, LINE_STATUS_CANCELLED])
    return {"count": int(getattr(cursor, "rowcount", 0) or 0)}


# ─────────────────────────────────────────────────────────────────────────────
# 销售发票（S8 Wave D）
# ─────────────────────────────────────────────────────────────────────────────

def invoice_billed_release(ds, args, ctx) -> Dict[str, Any]:
    """按红字发票行冲减开票进度（发货行 / 订单行 / 计划期次累计）。"""
    from meta.services.customer_invoice_service import CustomerInvoiceService

    invoice_id = args.get("doc_id", ctx.doc_id)
    sign = int(args.get("sign") or -1)
    return CustomerInvoiceService(ds).release_billed_for_invoice(
        invoice_id, sign=sign)


def invoice_schedule_cancel(ds, args, ctx) -> Dict[str, Any]:
    """取消原发票的应收期次（红冲后不再计划收款）。"""
    from meta.services.customer_invoice_service import CustomerInvoiceService

    invoice_id = args.get("doc_id", ctx.doc_id)
    return CustomerInvoiceService(ds).cancel_schedules_for_invoice(invoice_id)


def invoice_doc_flow_red_edge(ds, args, ctx) -> Dict[str, Any]:
    """写红字行 → 原发票行的反向事实边（B7，幂等）。"""
    from meta.services.customer_invoice_service import CustomerInvoiceService

    invoice_id = args.get("doc_id", ctx.doc_id)
    return CustomerInvoiceService(ds).write_doc_flow_for_invoice(invoice_id)


def recompute_customer_billing_status(ds, args, ctx) -> Dict[str, Any]:
    """按发票行重算关联销售订单的派生开票状态（投影，幂等）。"""
    from meta.services.customer_invoice_service import CustomerInvoiceService

    invoice_id = args.get("doc_id", ctx.doc_id)
    return CustomerInvoiceService(ds).recompute_billing_for_invoice(invoice_id)


# ─────────────────────────────────────────────────────────────────────────────
# 注册表
# ─────────────────────────────────────────────────────────────────────────────

Primitive = Callable[[Any, Dict[str, Any], ReversalContext], Dict[str, Any]]

PRIMITIVES: Dict[str, Primitive] = {
    "inventory_reverse_by_event": inventory_reverse_by_event,
    "inventory_reverse_by_txn": inventory_reverse_by_txn,
    "inventory_reverse_by_source": inventory_reverse_by_source,
    "serial_reverse_by_txn": serial_reverse_by_txn,
    "serial_reverse_completion": serial_reverse_completion,
    "hu_rewind_by_txn": hu_rewind_by_txn,
    "hu_reverse_document": hu_reverse_document,
    "reservation_release_by_demand": reservation_release_by_demand,
    "reservation_unfulfill_by_shipment": reservation_unfulfill_by_shipment,
    "edge_compensate_by_source": edge_compensate_by_source,
    "recompute_schedule_delivered": recompute_schedule_delivered,
    "recompute_fulfillment": recompute_fulfillment,
    "recompute_purchase_fulfillment": recompute_purchase_fulfillment,
    "recompute_transfer_fulfillment": recompute_transfer_fulfillment,
    "reverse_schedule_received": reverse_schedule_received,
    "recompute_schedule_returned": recompute_schedule_returned,
    "shipment_reverse_lines": shipment_reverse_lines,
    "transfer_reverse_lines": transfer_reverse_lines,
    "invoice_billed_release": invoice_billed_release,
    "invoice_schedule_cancel": invoice_schedule_cancel,
    "invoice_doc_flow_red_edge": invoice_doc_flow_red_edge,
    "recompute_customer_billing_status": recompute_customer_billing_status,
}


def get_primitive(primitive_id: str) -> Optional[Primitive]:
    """按 id 取原语；未注册返回 None（由编排器转 REVERSAL_PRIMITIVE_UNKNOWN）。"""
    return PRIMITIVES.get(str(primitive_id or ""))


# ─────────────────────────────────────────────────────────────────────────────
# 红字单创建器（`reversal.create_document.primitive` 引用）
# ─────────────────────────────────────────────────────────────────────────────

def inventory_adjustment_red_letter(ds, ctx) -> Dict[str, Any]:
    """库存调整：创建红字镜像单据（保留既有用户可见行为，幂等）。"""
    from meta.services.inventory_adjustment_service import (
        InventoryAdjustmentService,
    )

    return InventoryAdjustmentService(ds).create_reversal_document(
        ctx.doc_id, user_info=ctx.user_info)


def receipt_red_letter(ds, ctx) -> Dict[str, Any]:
    """收货：创建红字收货单（PO / TO / WO 三分支，保留既有用户可见行为）。"""
    from meta.services.receipt_service import ReceiptService

    params = ctx.params or {}
    return ReceiptService(ds).create_reversal_document(
        ctx.doc_id,
        receipt_date=params.get("receipt_date"),
        receipt_no=params.get("receipt_no"),
        remark=params.get("remark"))


def customer_invoice_red_letter(ds, ctx) -> Dict[str, Any]:
    """销售发票：创建红字发票（单号 / 业务日期由调用方事务外预分配后透传）。"""
    from meta.services.customer_invoice_service import CustomerInvoiceService

    params = ctx.params or {}
    return CustomerInvoiceService(ds).create_red_document(
        ctx.doc_id,
        invoice_no=params.get("invoice_no"),
        invoice_date=params.get("invoice_date") or ctx.now[:10],
        reason=ctx.reason)


DocCreator = Callable[[Any, ReversalContext], Dict[str, Any]]

DOC_CREATORS: Dict[str, DocCreator] = {
    "inventory_adjustment_red_letter": inventory_adjustment_red_letter,
    "receipt_red_letter": receipt_red_letter,
    "customer_invoice_red_letter": customer_invoice_red_letter,
}


def get_doc_creator(creator_id: str) -> Optional[DocCreator]:
    return DOC_CREATORS.get(str(creator_id or ""))
