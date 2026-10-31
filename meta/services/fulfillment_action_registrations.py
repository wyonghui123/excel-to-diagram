# -*- coding: utf-8 -*-
"""履约编排节点 handler 注册 —— 批次 4b

依据: docs/superpowers/specs/2026-10-29-so-wave3/batch4b_orchestration_design.md §4
      docs/superpowers/specs/2026-10-29-so-wave3/spec.md §10.18.2（编排不创建对象，handler 调 service）

纪律:
  · handler **不直接 INSERT 业务表**，一律走 `ShipmentService` / `WorkOrderService`
    （B4 写权守卫会在任务尝试期拦截）。
  · 返回统一信封 `{'success', 'data', 'message'}`；决策动作额外返回
    `data.new_status`（`decision_effect` 默认回执键）。
  · 8 个业务 action 之外额外注册 `work_order.rework`（控制类动作：拒绝 → 新 Run），
    它不写业务表，只调 `start_run`。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from meta.core.db_path import get_meta_db_path

logger = logging.getLogger(__name__)

ACTION_PICK = "shipment.pick"
ACTION_SHIP = "shipment.ship"
ACTION_DELIVER = "shipment.deliver"
ACTION_PRODUCE = "work_order.produce"
ACTION_DISPATCH = "work_order.dispatch"
ACTION_INSTALL = "work_order.install"
ACTION_CONFIRM = "work_order.confirm"
ACTION_CLOSE = "work_order.close"
ACTION_REWORK = "work_order.rework"

BUSINESS_ACTION_IDS = (
    ACTION_PICK, ACTION_SHIP, ACTION_DELIVER,
    ACTION_PRODUCE, ACTION_DISPATCH, ACTION_INSTALL,
    ACTION_CONFIRM, ACTION_CLOSE,
)

#: 已拣货 / 已发运 / 已签收 —— 无需重复推进
_SHIPMENT_STABLE = ("staged", "shipped", "delivered")


# ─────────────────────────────────────────────────────────────────────────────
# 基础设施（测试可 monkeypatch）
# ─────────────────────────────────────────────────────────────────────────────

def _get_ds():
    from meta.core.datasource import get_data_source
    return get_data_source("sqlite", database=get_meta_db_path())


def _shipment_service(ds):
    from meta.services.shipment_service import ShipmentService
    return ShipmentService(ds)


def _work_order_service(ds):
    from meta.services.work_order_service import WorkOrderService
    return WorkOrderService(ds)


def _ok(data: Dict[str, Any], message: str = "") -> Dict[str, Any]:
    return {"success": True, "data": data, "message": message}


def _err(message: str) -> Dict[str, Any]:
    return {"success": False, "data": None, "message": message}


def _actor(context: Dict[str, Any]) -> str:
    return (context or {}).get("actor") or (context or {}).get("run_as") or "system"


def _load_row(ds, sql: str, params: tuple):
    try:
        row = ds.execute(sql, params).fetchone()
    except Exception:  # noqa: BLE001 - 表未就绪 / 测试替身
        return None
    return row


def _task_row(ds, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    task_id = (context or {}).get("task_id")
    if not task_id:
        return None
    row = _load_row(
        ds,
        "SELECT id, workflow_run_id, doc_ref, line_refs, inputs FROM tasks WHERE id = ?",
        (task_id,),
    )
    if row is None:
        return None
    return {"id": row[0], "workflow_run_id": row[1], "doc_ref": row[2],
            "line_refs": row[3], "inputs": _loads(row[4])}


def _run_inputs(ds, run_id: Any) -> Dict[str, Any]:
    if not run_id:
        return {}
    row = _load_row(ds, "SELECT inputs FROM workflow_runs WHERE id = ?", (run_id,))
    if row is None:
        return {}
    return _loads(row[0])


def _loads(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _payload(params: Dict[str, Any], context: Dict[str, Any], ds) -> Dict[str, Any]:
    """参数优先级：params > 任务 inputs > Run inputs；并注入 doc_ref / line_refs。"""
    data: Dict[str, Any] = {}
    task = _task_row(ds, context)
    if task:
        data.update(_run_inputs(ds, task.get("workflow_run_id")))
        data.update(task.get("inputs") or {})
        data.setdefault("doc_ref", task.get("doc_ref"))
        data.setdefault("line_refs", task.get("line_refs"))
        data.setdefault("task_id", task.get("id"))
        data.setdefault("workflow_run_id", task.get("workflow_run_id"))
    data.update(params or {})
    return data


def _first(data: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _schedule_id(data: Dict[str, Any]) -> Any:
    """计划行 id：优先显式字段，其次 `line_refs`（可能是 list / JSON 文本）。"""
    value = _first(data, "schedule_id")
    if value not in (None, ""):
        return value
    refs = data.get("line_refs")
    if isinstance(refs, (list, tuple)) and refs:
        return refs[0]
    if isinstance(refs, str) and refs.strip():
        text = refs.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except ValueError:
                return text
            return parsed[0] if parsed else None
        return text
    return None


def _shipment_id(data: Dict[str, Any], ds) -> Any:
    explicit = _first(data, "shipment_id", "delivery_id", "doc_ref")
    if explicit not in (None, ""):
        return explicit
    schedule_id = _schedule_id(data)
    if schedule_id in (None, ""):
        return None
    row = _load_row(
        ds,
        "SELECT sh.id FROM shipments sh JOIN shipment_lines l "
        "ON l.delivery_id = sh.id WHERE l.schedule_id = ? "
        "AND sh.status <> 'cancelled' ORDER BY sh.id DESC LIMIT 1",
        (schedule_id,),
    )
    return row[0] if row else None


def _work_order_id(data: Dict[str, Any], ds) -> Any:
    explicit = _first(data, "work_order_id", "doc_ref")
    if explicit not in (None, ""):
        return explicit
    schedule_id = _schedule_id(data)
    if schedule_id in (None, ""):
        return None
    row = _load_row(
        ds,
        "SELECT id FROM work_orders WHERE schedule_id = ? "
        "AND status <> 'cancelled' ORDER BY id DESC LIMIT 1",
        (schedule_id,),
    )
    return row[0] if row else None


def _shipment_status(ds, shipment_id: Any) -> Optional[str]:
    row = _load_row(ds, "SELECT status FROM shipments WHERE id = ?", (shipment_id,))
    return str(row[0]) if row else None


# ─────────────────────────────────────────────────────────────────────────────
# shipment.*
# ─────────────────────────────────────────────────────────────────────────────

def shipment_pick_handler(params: Dict[str, Any],
                          context: Dict[str, Any]) -> Dict[str, Any]:
    """拣货：有单 → release + stage；无单 → create + release + stage。"""
    ds = _get_ds()
    data = _payload(params, context, ds)
    service = _shipment_service(ds)
    shipment_id = _shipment_id(data, ds)

    try:
        if shipment_id:
            status = _shipment_status(ds, shipment_id)
            if status in _SHIPMENT_STABLE:
                return _ok({"shipment_id": shipment_id, "new_status": status,
                            "idempotent": True})
            if status == "draft":
                service.release(shipment_id)
            result = service.stage(shipment_id)
            return _ok({"shipment_id": shipment_id,
                        "new_status": result.get("status", "staged")})

        order_id = _first(data, "order_id")
        if not order_id:
            return _err("拣货缺少 shipment_id，且无法建单（缺少 order_id）")
        lines = data.get("lines") or [{
            "schedule_id": _first(data, "line_refs", "schedule_id"),
            "qty": data.get("qty"),
            "item_id": data.get("item_id"),
        }]
        created = service.create_shipment({"order_id": order_id}, lines)
        service.release(created["id"])
        result = service.stage(created["id"])
        return _ok({"shipment_id": created.get("id"),
                    "new_status": result.get("status", "staged"),
                    "delivery_no": created.get("delivery_no")})
    except Exception as e:  # noqa: BLE001 - 业务异常 → 任务 failed（可重试）
        logger.exception("[fulfillment] shipment.pick 失败")
        return _err(str(e))


def shipment_ship_handler(params: Dict[str, Any],
                          context: Dict[str, Any]) -> Dict[str, Any]:
    """发货确认（回写计划行 delivered_qty；已 shipped 幂等返回）。"""
    ds = _get_ds()
    data = _payload(params, context, ds)
    shipment_id = _shipment_id(data, ds)
    if not shipment_id:
        return _err("发货缺少 shipment_id / doc_ref")
    try:
        result = _shipment_service(ds).ship_confirm(
            shipment_id, data.get("actual_ship_date"))
        return _ok({"shipment_id": shipment_id,
                    "new_status": result.get("status", "shipped"),
                    "idempotent": bool(result.get("idempotent"))})
    except Exception as e:  # noqa: BLE001
        logger.exception("[fulfillment] shipment.ship 失败")
        return _err(str(e))


def shipment_deliver_handler(params: Dict[str, Any],
                             context: Dict[str, Any]) -> Dict[str, Any]:
    """签收（shipped → delivered；已 delivered 幂等返回）。"""
    ds = _get_ds()
    data = _payload(params, context, ds)
    shipment_id = _shipment_id(data, ds)
    if not shipment_id:
        return _err("签收缺少 shipment_id / doc_ref")
    try:
        result = _shipment_service(ds).receive(
            shipment_id, data.get("signature_ref"), data.get("actual_arrival_date"))
        return _ok({"shipment_id": shipment_id,
                    "new_status": result.get("status", "delivered"),
                    "idempotent": bool(result.get("idempotent"))})
    except Exception as e:  # noqa: BLE001
        logger.exception("[fulfillment] shipment.deliver 失败")
        return _err(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# work_order.*
# ─────────────────────────────────────────────────────────────────────────────

def _find_work_order(ds, where: str, params: tuple):
    return _load_row(
        ds,
        "SELECT id, status, order_id FROM work_orders WHERE %s "
        "AND status <> 'cancelled' ORDER BY id DESC LIMIT 1" % where,
        params,
    )


def work_order_produce_handler(params: Dict[str, Any],
                               context: Dict[str, Any]) -> Dict[str, Any]:
    """生产工单：按需求来源去重建单（建单时自动展开组件）。"""
    ds = _get_ds()
    data = _payload(params, context, ds)
    demand_type = _first(data, "source_demand_type") or "sales_order_schedule"
    demand_id = _first(data, "source_demand_id", "line_refs", "schedule_id")
    if not demand_id:
        return _err("生产工单缺少需求来源（source_demand_id / line_refs）")

    existing = _find_work_order(
        ds, "source_demand_type = ? AND source_demand_id = ?",
        (demand_type, str(demand_id)))
    if existing:
        return _ok({"work_order_id": existing[0], "new_status": existing[1],
                    "idempotent": True})

    payload = {
        "order_type": "production",
        "source_demand_type": demand_type,
        "source_demand_id": demand_id,
        "item_id": data.get("item_id"),
        "qty": data.get("qty"),
        "severity": data.get("severity"),
        "channel": data.get("channel"),
        "actor": _actor(context),
    }
    try:
        created = _work_order_service(ds).create_work_order(payload)
        return _ok({"work_order_id": created.get("id"),
                    "new_status": created.get("status"),
                    "work_order_no": created.get("work_order_no"),
                    "component_expansion": created.get("component_expansion")})
    except Exception as e:  # noqa: BLE001
        logger.exception("[fulfillment] work_order.produce 失败")
        return _err(str(e))


def _service_work_order(data: Dict[str, Any], channel: str) -> Dict[str, Any]:
    schedule_id = _first(data, "schedule_id", "line_refs")
    if not schedule_id:
        return {"error": "缺少服务计划行（schedule_id / line_refs）"}
    return {
        "order_type": "service",
        "schedule_id": schedule_id,
        "severity": data.get("severity") or "medium",
        "channel": data.get("channel") or channel,
        "customer_account_id": data.get("customer_account_id"),
        "asset_ref": data.get("asset_ref"),
    }


def _create_service_work_order(params, context, *, channel: str) -> Dict[str, Any]:
    ds = _get_ds()
    data = _payload(params, context, ds)
    payload = _service_work_order(data, channel)
    if payload.get("error"):
        return _err(payload["error"])

    existing = _find_work_order(
        ds, "schedule_id = ? AND order_type = 'service' AND channel = ?",
        (payload["schedule_id"], payload["channel"]))
    if existing:
        return _ok({"work_order_id": existing[0], "new_status": existing[1],
                    "idempotent": True})

    payload["actor"] = _actor(context)
    try:
        created = _work_order_service(ds).create_work_order(payload)
        return _ok({"work_order_id": created.get("id"),
                    "new_status": created.get("status"),
                    "work_order_no": created.get("work_order_no")})
    except Exception as e:  # noqa: BLE001
        logger.exception("[fulfillment] work_order.%s 失败", channel)
        return _err(str(e))


def work_order_dispatch_handler(params: Dict[str, Any],
                                context: Dict[str, Any]) -> Dict[str, Any]:
    """服务派工：按计划行去重建服务工单。"""
    return _create_service_work_order(params, context, channel="dispatch")


def work_order_install_handler(params: Dict[str, Any],
                               context: Dict[str, Any]) -> Dict[str, Any]:
    """上门安装：服务工单 + channel=install（工单类型枚举 install 尚未启用）。"""
    return _create_service_work_order(params, context, channel="install")


def work_order_confirm_handler(params: Dict[str, Any],
                               context: Dict[str, Any]) -> Dict[str, Any]:
    """服务确认：结算工单（qty_good 走任务 outputs，确认表属后续批次）。"""
    ds = _get_ds()
    data = _payload(params, context, ds)
    work_order_id = _work_order_id(data, ds)
    if not work_order_id:
        return _err("服务确认缺少 work_order_id / doc_ref")
    try:
        result = _work_order_service(ds).resolve_event(
            work_order_id, actor=_actor(context), note=data.get("note"))
        return _ok({"work_order_id": work_order_id,
                    "new_status": result.get("status"),
                    "qty_good": data.get("qty_good"),
                    "already_resolved": bool(result.get("already_resolved"))})
    except Exception as e:  # noqa: BLE001
        logger.exception("[fulfillment] work_order.confirm 失败")
        return _err(str(e))


def work_order_close_handler(params: Dict[str, Any],
                             context: Dict[str, Any]) -> Dict[str, Any]:
    """工单关闭：resolve + 派生订单行 service_status。"""
    ds = _get_ds()
    data = _payload(params, context, ds)
    work_order_id = _work_order_id(data, ds)
    if not work_order_id:
        return _err("工单关闭缺少 work_order_id / doc_ref")
    try:
        service = _work_order_service(ds)
        result = service.resolve_event(work_order_id, actor=_actor(context),
                                       note=data.get("note"))
        row = _load_row(ds, "SELECT order_id FROM work_orders WHERE id = ?",
                        (work_order_id,))
        order_id = row[0] if row else data.get("order_id")
        service_status = service.derive_service_status(order_id) if order_id else None
        return _ok({"work_order_id": work_order_id,
                    "new_status": result.get("status"),
                    "service_status": service_status,
                    "already_resolved": bool(result.get("already_resolved"))})
    except Exception as e:  # noqa: BLE001
        logger.exception("[fulfillment] work_order.close 失败")
        return _err(str(e))


def work_order_rework_handler(params: Dict[str, Any],
                              context: Dict[str, Any]) -> Dict[str, Any]:
    """拒绝 → 起返工 Run（L3 扩链纪律：返工一律新 Run）。"""
    from meta.core.workflow_engine import get_run, start_run

    ds = _get_ds()
    task = _task_row(ds, context)
    if not task or not task.get("workflow_run_id"):
        return _err("返工缺少来源 Run（task_id）")
    run = get_run(ds, task["workflow_run_id"])
    if not run:
        return _err("返工来源 Run 不存在: %s" % task["workflow_run_id"])

    line_refs = task.get("line_refs")
    if isinstance(line_refs, str):
        text = line_refs.strip()
        try:
            line_refs = json.loads(text)
        except ValueError:
            line_refs = text

    try:
        created = start_run(
            ds,
            workflow_key=run["workflow_key"],
            inputs=run.get("inputs"),
            variables={"reason": "rework", "retry_of": task["id"]},
            trigger_kind="api",
            doc_ref=task.get("doc_ref") or "",
            line_refs=line_refs,
            created_by=_actor(context),
        )
        return _ok({"new_status": "rework", "new_run_id": created["run_id"],
                    "workflow_key": created["workflow_key"]})
    except Exception as e:  # noqa: BLE001
        logger.exception("[fulfillment] work_order.rework 失败")
        return _err(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# 注册
# ─────────────────────────────────────────────────────────────────────────────

_HANDLERS = (
    (ACTION_PICK, shipment_pick_handler, "履约-拣货（交货单 release → staged）", "shipment"),
    (ACTION_SHIP, shipment_ship_handler, "履约-发货确认（staged → shipped）", "shipment"),
    (ACTION_DELIVER, shipment_deliver_handler, "履约-签收（shipped → delivered）", "shipment"),
    (ACTION_PRODUCE, work_order_produce_handler, "履约-生产工单（需求追溯 + 组件展开）", "work_order"),
    (ACTION_DISPATCH, work_order_dispatch_handler, "履约-服务派工（建服务工单）", "work_order"),
    (ACTION_INSTALL, work_order_install_handler, "履约-上门安装（服务工单 channel=install）", "work_order"),
    (ACTION_CONFIRM, work_order_confirm_handler, "履约-服务确认（resolve 工单）", "work_order"),
    (ACTION_CLOSE, work_order_close_handler, "履约-工单关闭（resolve + service_status）", "work_order"),
    (ACTION_REWORK, work_order_rework_handler, "履约-返工（拒绝 → 新 Run）", "workflow_run"),
)


def register_fulfillment_actions(registry=None):
    """注册履约节点 handler（幂等：重复调用覆盖同 action_id）。"""
    if registry is None:
        from meta.core.bo_action_registry import bo_action_registry
        registry = bo_action_registry

    for action_id, handler, description, object_type in _HANDLERS:
        registry.register(
            action_id,
            handler,
            description=description,
            object_type=object_type,
            category="fulfillment",
            requires_auth=False,
            idempotent=True,
        )
    return registry
