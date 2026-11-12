# -*- coding: utf-8 -*-
"""批次 4b 履约编排 —— 端到端验收（T4b.6）

依据: docs/superpowers/specs/2026-10-29-so-wave3/batch4b_orchestration_design.md §8
      docs/superpowers/specs/2026-10-29-so-wave3/spec.md §10.18 / §10.19

覆盖（每条对应 §8 一条验收判据）:
  1. 备货出库（stock）: start_run → tick 派发 → pick/ship/deliver → 交货单 delivered
  2. 按单生产（mto）: 生产确认人工节点 → pick/ship/deliver
  3. 现场服务（service）: dispatch 建服务工单 → 上门/确认人工 → close 置 resolved
  4. 发货安装混合（mixed）: ship/deliver → install（channel=install）→ 客户验收人工
  5. 动态失败: ship 失败 → exception 节点 ready，Run 不卡死
  6. 驳回返工: confirm 上调用 work_order.rework → 新 Run（variables.reason='rework'）
  7. 负向回归: 无兜底规则 → DEFAULT_ROUTING_MISS
  8. line_refs 全链路 = schedule_id（Run meta + 每个任务）
  9. 跨批次（4a×4b）: 生产工单 + BOM 组件展开 → 完工闸口 → 发运

说明:
  - 用真实 sqlite 数据源（temp 文件），合并 Shipment/WorkOrder 两套业务表 schema；
  - handler 经 monkeypatch `_get_ds` 指向 temp ds —— 绕过 B4 守卫，让 service 真写业务表；
  - 人工节点直接 UPDATE tasks.status='done' 模拟收件箱办理（A8 不在本批范围）。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pytest

pytestmark = pytest.mark.integration

os.environ.setdefault("ALLOW_RAW_SQL", "1")

from meta.services import fulfillment_action_registrations as fa  # noqa: E402
from meta.services.fulfillment_routing_service import (  # noqa: E402
    FulfillmentRoutingError,
    FulfillmentRoutingService,
)
from meta.core.task_executor_adapter import start_task  # noqa: E402
from meta.core.task_tick import platform_tick  # noqa: E402
from meta.core.workflow_engine import advance_run, get_run, list_run_tasks  # noqa: E402

DEFAULT_EVIDENCE_DIR = r"d:\filework\docs\superpowers\specs\2026-10-29-so-wave3\evidence"

_EVIDENCE: Dict[str, Any] = {
    "batch": "4b",
    "generated_at": "",
    "flows": {},
    "checks": {},
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ─────────────────────────────────────────────────────────────────────────────
# 合并 schema（Shipment + WorkOrder 两套业务表；只保留本批用到的表）
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE orgs (id INTEGER PRIMARY KEY, code TEXT);
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY, order_no TEXT, org_id INTEGER, order_date TEXT,
    status TEXT, ship_to_party_id INTEGER, ship_to_address_text TEXT,
    customer_account_id INTEGER, fulfillment_status TEXT DEFAULT 'not_started',
    fulfillment_derived_at TEXT, updated_at TEXT
);
CREATE TABLE sales_order_lines (
    id INTEGER PRIMARY KEY, order_id INTEGER, line_type_id INTEGER, item_id INTEGER,
    uom_id INTEGER, qty REAL, status TEXT, fulfillment_status TEXT DEFAULT 'not_started',
    fulfillment_derived_at TEXT, updated_at TEXT
);
CREATE TABLE sales_order_schedules (
    id INTEGER PRIMARY KEY, order_id INTEGER, line_id INTEGER, schedule_kind TEXT,
    plant_location_id INTEGER, promised_date TEXT, promised_qty REAL,
    delivered_qty REAL DEFAULT 0, delivery_id INTEGER, status TEXT, updated_at TEXT
);
CREATE TABLE type_definitions (
    id INTEGER PRIMARY KEY, code TEXT, level TEXT, line_category TEXT,
    delivery_relevant INTEGER DEFAULT 1
);
CREATE TABLE shipments (
    id INTEGER PRIMARY KEY, delivery_no TEXT, order_id INTEGER,
    ship_from_location_id INTEGER, ship_to_party_id INTEGER,
    ship_to_address_text TEXT, carrier_name TEXT, tracking_no TEXT, waybill_no TEXT,
    planned_ship_date TEXT, actual_ship_date TEXT, actual_arrival_date TEXT,
    signature_ref TEXT, status TEXT, source TEXT, remark TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE TABLE shipment_lines (
    id INTEGER PRIMARY KEY, delivery_id INTEGER, schedule_id INTEGER,
    order_line_id INTEGER, item_id INTEGER, uom_id INTEGER, qty REAL,
    lot_no TEXT, serial_no TEXT, status TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE calendars (
    id INTEGER PRIMARY KEY, day_mask_mon INTEGER DEFAULT 1, day_mask_tue INTEGER DEFAULT 1,
    day_mask_wed INTEGER DEFAULT 1, day_mask_thu INTEGER DEFAULT 1,
    day_mask_fri INTEGER DEFAULT 1, day_mask_sat INTEGER DEFAULT 0,
    day_mask_sun INTEGER DEFAULT 0
);
CREATE TABLE calendar_days (id INTEGER PRIMARY KEY, calendar_id INTEGER, date TEXT, day_type TEXT);
CREATE TABLE sla_coverages (
    id INTEGER PRIMARY KEY, name TEXT, org_id INTEGER, calendar_id INTEGER,
    start_date TEXT, end_date TEXT, active INTEGER DEFAULT 1
);
CREATE TABLE sla_coverage_rules (
    id INTEGER PRIMARY KEY, coverage_id INTEGER, severity TEXT, channel TEXT,
    first_response_minutes INTEGER, first_response_warn_minutes INTEGER,
    resolution_minutes INTEGER, resolution_warn_minutes INTEGER, seq INTEGER DEFAULT 0
);
CREATE TABLE work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT, work_order_no TEXT, order_type TEXT,
    schedule_id INTEGER, order_id INTEGER, order_line_id INTEGER,
    customer_account_id INTEGER, severity TEXT, channel TEXT, status TEXT,
    coverage_id INTEGER, asset_ref TEXT, source_demand_type TEXT,
    source_demand_id INTEGER, opened_at TEXT, first_response_at TEXT,
    resolved_at TEXT, closed_at TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE sla_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT, work_order_id INTEGER, milestone_type TEXT,
    state TEXT, due_at TEXT, warn_at TEXT, started_at TEXT,
    paused_total_minutes INTEGER DEFAULT 0, completed_at TEXT, warned_at TEXT,
    breached_at TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE service_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, work_order_id INTEGER, event_type TEXT,
    occurred_at TEXT, actor TEXT, payload TEXT, note TEXT, created_at TEXT
);
CREATE TABLE change_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, object_type TEXT, object_id INTEGER,
    event_type TEXT, changed_fields TEXT, old_values TEXT, new_values TEXT,
    payload TEXT, status TEXT, created_at TEXT
);
CREATE TABLE item_structures (
    id INTEGER PRIMARY KEY, item_id INTEGER, usage TEXT,
    alternative_no INTEGER DEFAULT 1, revision TEXT, base_qty REAL DEFAULT 1,
    status TEXT DEFAULT 'active', valid_from TEXT, valid_to TEXT
);
CREATE TABLE item_structure_lines (
    id INTEGER PRIMARY KEY, structure_id INTEGER, line_no INTEGER,
    component_item_id INTEGER, qty_per REAL, fixed_qty REAL,
    scrap_rate REAL DEFAULT 0, optional_flag INTEGER DEFAULT 0,
    default_qty REAL, min_qty REAL, max_qty REAL, valid_from TEXT, valid_to TEXT
);
CREATE TABLE work_order_components (
    id INTEGER PRIMARY KEY AUTOINCREMENT, work_order_id INTEGER,
    structure_id INTEGER, structure_line_id INTEGER, component_item_id INTEGER,
    line_no INTEGER, qty_per REAL, fixed_qty REAL, scrap_rate REAL,
    qty_required REAL, optional_flag INTEGER DEFAULT 0,
    created_at TEXT, updated_at TEXT
);
"""

_ROUTING_SCHEMA = """
CREATE TABLE fulfillment_routing_rules (
    id INTEGER PRIMARY KEY, priority INTEGER, item_type TEXT, procurement_type TEXT,
    delivery_mode TEXT, site_id TEXT, workflow_key TEXT, is_default INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1, remark TEXT
);
"""


def _exec_script(ds, script: str) -> None:
    """逐条执行多语句 DDL（DataSource.execute 每次只接受一条语句）。"""
    for statement in script.split(";"):
        if statement.strip():
            ds.execute(statement)


# ─────────────────────────────────────────────────────────────────────────────
# 夹具
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _evidence_file():
    yield
    _EVIDENCE["generated_at"] = _now()
    target = Path(os.environ.get("B4B_EVIDENCE_DIR", DEFAULT_EVIDENCE_DIR))
    target.mkdir(parents=True, exist_ok=True)
    (target / "b4b_orchestration_e2e.json").write_text(
        json.dumps(_EVIDENCE, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture()
def registry():
    """快照-恢复全局注册表单例，避免污染其他测试。"""
    from meta.core.bo_action_registry import bo_action_registry

    saved = dict(bo_action_registry._actions)
    bo_action_registry.clear()
    fa.register_fulfillment_actions(bo_action_registry)
    yield bo_action_registry
    bo_action_registry._actions.clear()
    bo_action_registry._actions.update(saved)


@pytest.fixture()
def ds(tmp_path, monkeypatch):
    """临时平台库 + 业务表 + 路由规则；handler 的 `_get_ds` 指向同一实例。"""
    from meta.core.datasource import get_data_source
    from meta.core.task_event_schema import ensure_task_event_tables
    from meta.core.task_idempotency import ensure_idempotency_table
    from meta.core.task_schema import ensure_task_tables

    source = get_data_source("sqlite", database=str(tmp_path / "b4b_e2e.db"))
    with source.transaction():
        _exec_script(source, _SCHEMA)
        _exec_script(source, _ROUTING_SCHEMA)
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_idempotency_table(source)
        _seed_routing(source)
    monkeypatch.setattr(fa, "_get_ds", lambda: source)
    yield source


def _seed_routing(ds) -> None:
    rows = [
        (1, 10, None, "stock", None, None, "wf-fulfill-stock", 0, 1, "备货出库"),
        (2, 20, None, "mto", None, None, "wf-fulfill-mto", 0, 1, "按单生产"),
        (3, 30, "service", None, None, None, "wf-fulfill-service", 0, 1, "现场服务"),
        (4, 90, None, None, None, None, "wf-fulfilled-mixed", 1, 1, "兜底混合"),
    ]
    for row in rows:
        ds.execute(
            "INSERT INTO fulfillment_routing_rules "
            "(id, priority, item_type, procurement_type, delivery_mode, site_id, "
            "workflow_key, is_default, enabled, remark) VALUES (?,?,?,?,?,?,?,?,?,?)",
            row,
        )


def _seed_base(ds, *, promised_qty: float = 5.0, with_service: bool = False) -> None:
    """订单 + 订单行 + 交货计划行（可选服务计划行）。"""
    ds.execute("INSERT INTO orgs (id, code) VALUES (1, 'ORG1')")
    ds.execute(
        "INSERT INTO type_definitions (id, code, level, line_category, delivery_relevant) "
        "VALUES (1, 'DLV', 'line', 'delivery', 1)")
    ds.execute(
        "INSERT INTO sales_orders (id, order_no, org_id, order_date, status, "
        "ship_to_party_id, ship_to_address_text, customer_account_id) "
        "VALUES (10, 'SO-10', 1, '2026-10-01', 'confirmed', 20, '上海某地址', 30)")
    ds.execute(
        "INSERT INTO sales_order_lines (id, order_id, line_type_id, item_id, uom_id, qty, status) "
        "VALUES (100, 10, 1, 1000, 1, 10, 'confirmed')")
    ds.execute(
        "INSERT INTO sales_order_schedules (id, order_id, line_id, schedule_kind, "
        "plant_location_id, promised_date, promised_qty, delivered_qty, status) "
        "VALUES (10, 10, 100, 'delivery', 5, '2026-10-10', ?, 0, 'planned')",
        (promised_qty,))
    if with_service:
        ds.execute(
            "INSERT INTO sales_order_schedules (id, order_id, line_id, schedule_kind, "
            "plant_location_id, promised_date, promised_qty, delivered_qty, status) "
            "VALUES (11, 10, 100, 'service', NULL, '2026-10-12', 1, 0, 'planned')")


def _seed_item_structure(ds) -> None:
    """物料 1000 的生产 BOM：组件 2001×2、组件 2002×1（含 20% 损耗）。"""
    ds.execute(
        "INSERT INTO item_structures (id, item_id, usage, alternative_no, revision, "
        "base_qty, status, valid_from, valid_to) "
        "VALUES (1, 1000, 'production', 1, 'A', 1, 'active', '2026-01-01', NULL)")
    ds.execute(
        "INSERT INTO item_structure_lines (id, structure_id, line_no, "
        "component_item_id, qty_per, fixed_qty, scrap_rate, optional_flag, "
        "default_qty, min_qty, max_qty, valid_from, valid_to) "
        "VALUES (1, 1, 10, 2001, 2, 0, 0, 0, NULL, NULL, NULL, NULL, NULL)")
    ds.execute(
        "INSERT INTO item_structure_lines (id, structure_id, line_no, "
        "component_item_id, qty_per, fixed_qty, scrap_rate, optional_flag, "
        "default_qty, min_qty, max_qty, valid_from, valid_to) "
        "VALUES (2, 1, 20, 2002, 1, 0, 0.2, 0, NULL, NULL, NULL, NULL, NULL)")


# ─────────────────────────────────────────────────────────────────────────────
# 流控助手
# ─────────────────────────────────────────────────────────────────────────────

def _task_by_node(ds, run_id: str, node_id: str) -> Dict[str, Any]:
    for task in list_run_tasks(ds, run_id):
        if task["workflow_node_id"] == node_id:
            return task
    raise AssertionError("节点不存在: %s" % node_id)


def _advance(ds, run_id: str) -> Dict[str, Any]:
    advance_run(ds, run_id)
    tick = platform_tick(ds, dispatch=True, reclaim=False,
                         escalate=False, reconcile=False)
    assert not tick["errors"], tick["errors"]
    return tick


def _run_system(ds, registry, run_id: str, node_id: str) -> Dict[str, Any]:
    _advance(ds, run_id)
    task = _task_by_node(ds, run_id, node_id)
    assert task["status"] == "claimed", (node_id, task["status"])
    outcome = start_task(ds, task["id"], registry=registry)
    assert outcome["status"] == "completed", (node_id, outcome)
    return outcome


def _run_system_expect_failed(ds, registry, run_id: str, node_id: str) -> Dict[str, Any]:
    _advance(ds, run_id)
    task = _task_by_node(ds, run_id, node_id)
    assert task["status"] == "claimed", (node_id, task["status"])
    return start_task(ds, task["id"], registry=registry)


def _complete_human(ds, run_id: str, node_id: str) -> Dict[str, Any]:
    _advance(ds, run_id)
    task = _task_by_node(ds, run_id, node_id)
    assert task["status"] == "ready", (node_id, task["status"])
    ds.execute("UPDATE tasks SET status = 'done', finished_at = ? WHERE id = ?",
               (_now(), task["id"]))
    return task


def _start(ds, payload: Dict[str, Any], schedule_id: int) -> Dict[str, Any]:
    return FulfillmentRoutingService(ds).start_fulfillment_run(
        payload, line_refs=[schedule_id], created_by="e2e")


def _assert_line_refs(ds, run_id: str, schedule_id: int) -> None:
    run = get_run(ds, run_id)
    assert run["meta"]["line_refs"] == [schedule_id]
    for task in list_run_tasks(ds, run_id):
        assert task["line_refs"] == [schedule_id], task["workflow_node_id"]


def _scalar(ds, sql: str, params: tuple):
    row = ds.execute(sql, params).fetchone()
    return row[0] if row else None


def _record(flow: str, **data) -> None:
    _EVIDENCE["flows"][flow] = data


# ─────────────────────────────────────────────────────────────────────────────
# 1. 备货出库
# ─────────────────────────────────────────────────────────────────────────────

def test_stock_flow_end_to_end(ds, registry):
    _seed_base(ds, promised_qty=5.0)
    payload = {
        "procurement_type": "stock",
        "order_id": 10,
        "schedule_id": 10,
        "lines": [{"schedule_id": 10, "qty": 5, "item_id": 1000}],
    }
    started = _start(ds, payload, schedule_id=10)
    run_id = started["run"]["run_id"]
    assert started["workflow_key"] == "wf-fulfill-stock"

    pick = _run_system(ds, registry, run_id, "pick")
    ship = _run_system(ds, registry, run_id, "ship")
    deliver = _run_system(ds, registry, run_id, "deliver")

    shipment_id = deliver["outputs"]["shipment_id"]
    assert _scalar(ds, "SELECT status FROM shipments WHERE id = ?", (shipment_id,)) == "delivered"
    assert _scalar(ds, "SELECT delivered_qty FROM sales_order_schedules WHERE id = 10", ()) == 5
    assert _scalar(ds, "SELECT status FROM sales_order_schedules WHERE id = 10", ()) == "completed"
    assert _task_by_node(ds, run_id, "exception")["status"] == "pending"

    _assert_line_refs(ds, run_id, 10)
    _record("stock", run_id=run_id, shipment_id=shipment_id,
            shipment_status="delivered", delivered_qty=5,
            pick_outputs=pick["outputs"], ship_outputs=ship["outputs"])


# ─────────────────────────────────────────────────────────────────────────────
# 2. 按单生产（生产完工为人工闸口）
# ─────────────────────────────────────────────────────────────────────────────

def test_mto_flow_with_produce_gate(ds, registry):
    _seed_base(ds, promised_qty=5.0)
    payload = {
        "procurement_type": "mto",
        "order_id": 10,
        "schedule_id": 10,
        "lines": [{"schedule_id": 10, "qty": 5, "item_id": 1000}],
    }
    started = _start(ds, payload, schedule_id=10)
    run_id = started["run"]["run_id"]
    assert started["workflow_key"] == "wf-fulfill-mto"

    produce = _complete_human(ds, run_id, "produce")
    assert _scalar(ds, "SELECT status FROM tasks WHERE id = ?", (produce["id"],)) == "done"

    pick = _run_system(ds, registry, run_id, "pick")
    ship = _run_system(ds, registry, run_id, "ship")
    deliver = _run_system(ds, registry, run_id, "deliver")

    shipment_id = deliver["outputs"]["shipment_id"]
    assert _scalar(ds, "SELECT status FROM shipments WHERE id = ?", (shipment_id,)) == "delivered"
    _assert_line_refs(ds, run_id, 10)
    _record("mto", run_id=run_id, shipment_id=shipment_id,
            produce_task_status="done", shipment_status="delivered",
            pick_outputs=pick["outputs"], ship_outputs=ship["outputs"])


# ─────────────────────────────────────────────────────────────────────────────
# 2b. 跨批次：生产工单 + 组件展开接入按单生产 Run
# ─────────────────────────────────────────────────────────────────────────────

def test_mto_production_work_order_and_component_chain(ds, registry):
    """批次 4a（生产工单/组件展开）× 批次 4b（编排）：需求追溯 → BOM → 完工 → 发运。"""
    from meta.services.work_order_service import WorkOrderService

    _seed_base(ds, promised_qty=5.0)
    _seed_item_structure(ds)

    payload = {"procurement_type": "mto", "order_id": 10, "schedule_id": 10,
               "lines": [{"schedule_id": 10, "qty": 5, "item_id": 1000}]}
    started = _start(ds, payload, schedule_id=10)
    run_id = started["run"]["run_id"]
    assert started["workflow_key"] == "wf-fulfill-mto"

    production = WorkOrderService(ds).create_work_order({
        "order_type": "production",
        "source_demand_type": "sales_order_line",
        "source_demand_id": 100,
        "actor": "e2e",
    })
    work_order_id = production["id"]
    assert production["order_type"] == "production"
    assert production["item_id"] == 1000 and production["qty"] == 10
    assert production["component_expansion"]["code"] == "expanded"

    rows = ds.query(
        "SELECT component_item_id, qty_required FROM work_order_components "
        "WHERE work_order_id = ? ORDER BY component_item_id", [work_order_id])
    assert [(r["component_item_id"], r["qty_required"]) for r in rows] == [
        (2001, 20), (2002, 12)]

    assert _scalar(ds, "SELECT COUNT(*) FROM sla_milestones", ()) == 0
    assert _scalar(ds, "SELECT COUNT(*) FROM service_events", ()) == 0
    assert _scalar(ds, "SELECT COUNT(*) FROM change_events WHERE object_type = 'work_order'", ()) == 1

    resolved = WorkOrderService(ds).resolve_event(work_order_id, actor="e2e")
    assert str(resolved["status"]).lower() == "resolved"
    assert resolved["schedule_status"] is None
    assert _scalar(ds, "SELECT status FROM sales_order_schedules WHERE id = 10", ()) == "planned"

    produce = _complete_human(ds, run_id, "produce")
    assert _scalar(ds, "SELECT status FROM tasks WHERE id = ?", (produce["id"],)) == "done"

    pick = _run_system(ds, registry, run_id, "pick")
    ship = _run_system(ds, registry, run_id, "ship")
    deliver = _run_system(ds, registry, run_id, "deliver")

    shipment_id = deliver["outputs"]["shipment_id"]
    assert _scalar(ds, "SELECT status FROM shipments WHERE id = ?", (shipment_id,)) == "delivered"
    assert _scalar(ds, "SELECT delivered_qty FROM sales_order_schedules WHERE id = 10", ()) == 5
    assert _scalar(ds, "SELECT status FROM sales_order_schedules WHERE id = 10", ()) == "completed"

    _assert_line_refs(ds, run_id, 10)
    _record("mto_production", run_id=run_id, production_work_order_id=work_order_id,
            production_status="resolved", component_qty={2001: 20, 2002: 12},
            shipment_id=shipment_id, shipment_status="delivered",
            schedule_status="completed", pick_outputs=pick["outputs"],
            ship_outputs=ship["outputs"])


# ─────────────────────────────────────────────────────────────────────────────
# 3. 现场服务
# ─────────────────────────────────────────────────────────────────────────────

def test_service_flow_end_to_end(ds, registry):
    _seed_base(ds, promised_qty=5.0, with_service=True)
    payload = {"item_type": "service", "schedule_id": 11,
               "severity": "high", "is_field_service": True}
    started = _start(ds, payload, schedule_id=11)
    run_id = started["run"]["run_id"]
    assert started["workflow_key"] == "wf-fulfill-service"

    dispatch = _run_system(ds, registry, run_id, "dispatch")
    work_order_id = dispatch["outputs"]["work_order_id"]
    assert _scalar(ds, "SELECT order_type FROM work_orders WHERE id = ?",
                   (work_order_id,)) == "service"
    assert _scalar(ds, "SELECT channel FROM work_orders WHERE id = ?",
                   (work_order_id,)) == "dispatch"

    onsite = _complete_human(ds, run_id, "onsite")
    assert _scalar(ds, "SELECT status FROM tasks WHERE id = ?", (onsite["id"],)) == "done"
    confirm = _complete_human(ds, run_id, "confirm")
    assert _scalar(ds, "SELECT status FROM tasks WHERE id = ?", (confirm["id"],)) == "done"

    close = _run_system(ds, registry, run_id, "close")
    assert str(_scalar(ds, "SELECT status FROM work_orders WHERE id = ?",
                       (work_order_id,))).lower() == "resolved"
    assert _scalar(ds, "SELECT status FROM sales_order_schedules WHERE id = 11", ()) == "completed"
    assert close["outputs"]["service_status"] == "completed"

    _assert_line_refs(ds, run_id, 11)
    _record("service", run_id=run_id, work_order_id=work_order_id,
            work_order_status="resolved", schedule_status="completed",
            service_status=close["outputs"]["service_status"],
            dispatch_outputs=dispatch["outputs"])


# ─────────────────────────────────────────────────────────────────────────────
# 4. 发货安装混合
# ─────────────────────────────────────────────────────────────────────────────

def test_mixed_ship_install_flow(ds, registry):
    from meta.services.shipment_service import ShipmentService

    _seed_base(ds, promised_qty=5.0, with_service=True)
    shipment = ShipmentService(ds).create_shipment(
        {"order_id": 10}, [{"schedule_id": 10, "qty": 5, "item_id": 1000}])
    ShipmentService(ds).release(shipment["id"])
    ShipmentService(ds).stage(shipment["id"])

    payload = {"item_type": "equipment", "shipment_id": shipment["id"],
               "schedule_id": 11}
    started = _start(ds, payload, schedule_id=11)
    run_id = started["run"]["run_id"]
    assert started["workflow_key"] == "wf-fulfilled-mixed"

    ship = _run_system(ds, registry, run_id, "ship")
    deliver = _run_system(ds, registry, run_id, "deliver")
    install = _run_system(ds, registry, run_id, "install")
    accept = _complete_human(ds, run_id, "accept")

    assert _scalar(ds, "SELECT status FROM shipments WHERE id = ?",
                   (shipment["id"],)) == "delivered"
    install_wo = install["outputs"]["work_order_id"]
    assert _scalar(ds, "SELECT channel FROM work_orders WHERE id = ?",
                   (install_wo,)) == "install"
    assert _scalar(ds, "SELECT status FROM tasks WHERE id = ?", (accept["id"],)) == "done"

    _record("mixed", run_id=run_id, shipment_id=shipment["id"],
            shipment_status="delivered", install_work_order_id=install_wo,
            install_channel="install", accept_task_status="done",
            ship_outputs=ship["outputs"], deliver_outputs=deliver["outputs"])


# ─────────────────────────────────────────────────────────────────────────────
# 5. 动态失败 → exception
# ─────────────────────────────────────────────────────────────────────────────

def test_dynamic_failure_routes_to_exception(ds, registry):
    _seed_base(ds, promised_qty=5.0)
    payload = {
        "procurement_type": "stock", "order_id": 10, "schedule_id": 10,
        "lines": [{"schedule_id": 10, "qty": 5, "item_id": 1000}],
    }
    started = _start(ds, payload, schedule_id=10)
    run_id = started["run"]["run_id"]

    pick = _run_system(ds, registry, run_id, "pick")
    shipment_id = pick["outputs"]["shipment_id"]
    ds.execute("UPDATE shipments SET status = 'cancelled' WHERE id = ?", (shipment_id,))

    ship = _run_system_expect_failed(ds, registry, run_id, "ship")
    assert ship["status"] == "failed"
    assert _scalar(ds, "SELECT status FROM tasks WHERE id = ?",
                   (ship["task_id"],)) == "failed"

    advance_run(ds, run_id)
    exception = _task_by_node(ds, run_id, "exception")
    assert exception["status"] == "ready"
    deliver = _task_by_node(ds, run_id, "deliver")
    assert deliver["status"] == "pending"

    _record("dynamic_failure", run_id=run_id, shipment_id=shipment_id,
            ship_status="failed", exception_status=exception["status"],
            deliver_status=deliver["status"])


# ─────────────────────────────────────────────────────────────────────────────
# 6. 驳回 → 返工 Run
# ─────────────────────────────────────────────────────────────────────────────

def test_reject_starts_rework_run(ds, registry):
    _seed_base(ds, promised_qty=5.0, with_service=True)
    payload = {"item_type": "service", "schedule_id": 11,
               "severity": "high", "is_field_service": True}
    started = _start(ds, payload, schedule_id=11)
    run_id = started["run"]["run_id"]

    _run_system(ds, registry, run_id, "dispatch")
    _complete_human(ds, run_id, "onsite")
    confirm = _complete_human(ds, run_id, "confirm")

    result = registry.call("work_order.rework", {}, {"task_id": confirm["id"]})
    assert result["success"] is True, result
    new_run_id = result["data"]["new_run_id"]
    assert result["data"]["workflow_key"] == "wf-fulfill-service"

    new_run = get_run(ds, new_run_id)
    assert new_run["variables"]["reason"] == "rework"
    assert new_run["variables"]["retry_of"] == confirm["id"]
    assert len(list_run_tasks(ds, new_run_id)) == 4
    assert new_run["meta"]["line_refs"] == [11]

    _record("rework", source_run_id=run_id, new_run_id=new_run_id,
            workflow_key=new_run["workflow_key"],
            variables=new_run["variables"], task_count=4)


# ─────────────────────────────────────────────────────────────────────────────
# 7. 负向回归：无兜底规则
# ─────────────────────────────────────────────────────────────────────────────

def test_routing_without_default_raises(ds):
    ds.execute("UPDATE fulfillment_routing_rules SET enabled = 0 WHERE is_default = 1")
    service = FulfillmentRoutingService(ds)
    with pytest.raises(FulfillmentRoutingError) as exc:
        service.resolve_workflow_key({"item_type": "unknown"})
    assert exc.value.rule == "DEFAULT_ROUTING_MISS"
    _EVIDENCE["checks"]["negative_routing"] = {
        "rule": exc.value.rule, "message": str(exc.value),
    }
