# -*- coding: utf-8 -*-
"""T4b.4 履约节点 handler 注册 + 单测（mock service）

覆盖目标:
  1. `register_fulfillment_actions()` 注册 8 个业务 action + 1 个返工控制动作
  2. shipment.pick / ship / deliver：状态幂等 + service 调用参数
  3. work_order.produce / dispatch / install：按来源去重，命中返回 idempotent
  4. work_order.confirm / close：resolve + new_status（决策回执）
  5. work_order.rework：拒绝 → 新 Run（variables.reason='rework'）
  6. service 抛异常 → 统一信封 `success=False`（任务可归位 failed）
"""

import pytest

from meta.services import fulfillment_action_registrations as reg


pytestmark = pytest.mark.unit


class _Cursor:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [] if self._row is None else [self._row]


class FakeDS:
    """按调用顺序吐预置行的最小 datasource 替身。"""

    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def execute(self, sql, params=()):  # noqa: ARG002
        row = self.rows.pop(0) if self.rows else None
        return _Cursor(row)


class FakeRegistry:
    def __init__(self):
        self.actions = {}

    def register(self, action_id, handler, **kwargs):
        self.actions[action_id] = {"handler": handler, **kwargs}
        return self


@pytest.fixture()
def ds(monkeypatch):
    source = FakeDS()
    monkeypatch.setattr(reg, "_get_ds", lambda: source)
    return source


def _ctx(**extra):
    return {"actor": "u-1", **extra}


# ─────────────────────────────────────────────────────────────────────────────
# 注册
# ─────────────────────────────────────────────────────────────────────────────

def test_register_fulfillment_actions():
    registry = FakeRegistry()
    reg.register_fulfillment_actions(registry)
    assert set(reg.BUSINESS_ACTION_IDS) <= set(registry.actions)
    assert reg.ACTION_REWORK in registry.actions
    for action_id in reg.BUSINESS_ACTION_IDS:
        assert registry.actions[action_id]["category"] == "fulfillment"
        assert registry.actions[action_id]["idempotent"] is True


# ─────────────────────────────────────────────────────────────────────────────
# shipment.*
# ─────────────────────────────────────────────────────────────────────────────

def test_pick_idempotent_when_already_staged(monkeypatch, ds):
    ds.rows = [("staged",)]
    service = type("S", (), {"stage": lambda self, sid: (_ for _ in ()).throw(
        AssertionError("stage 不应被调用"))})()
    monkeypatch.setattr(reg, "_shipment_service", lambda _ds: service)

    result = reg.shipment_pick_handler({"shipment_id": "d-1"}, _ctx())
    assert result["success"] is True
    assert result["data"]["idempotent"] is True
    assert result["data"]["new_status"] == "staged"


def test_pick_released_calls_stage(monkeypatch, ds):
    ds.rows = [("released",)]
    calls = []
    service = type("S", (), {
        "stage": lambda self, sid: calls.append(("stage", sid)) or {"status": "staged"},
    })()
    monkeypatch.setattr(reg, "_shipment_service", lambda _ds: service)

    result = reg.shipment_pick_handler({"shipment_id": "d-1"}, _ctx())
    assert result["success"] is True
    assert calls == [("stage", "d-1")]
    assert result["data"]["new_status"] == "staged"


def test_pick_without_shipment_creates_release_stage(monkeypatch, ds):
    calls = []

    class Service:
        def create_shipment(self, header, lines):
            calls.append(("create", header, lines))
            return {"id": "d-2", "delivery_no": "DN-2"}

        def release(self, sid):
            calls.append(("release", sid))

        def stage(self, sid):
            calls.append(("stage", sid))
            return {"status": "staged"}

    monkeypatch.setattr(reg, "_shipment_service", lambda _ds: Service())
    result = reg.shipment_pick_handler(
        {"order_id": "o-1", "line_refs": "s-1", "qty": 2, "item_id": "i-1"}, _ctx())

    assert result["success"] is True
    assert calls[0][0] == "create"
    assert [c[0] for c in calls] == ["create", "release", "stage"]


def test_ship_calls_ship_confirm(monkeypatch, ds):
    calls = []
    service = type("S", (), {
        "ship_confirm": lambda self, sid, date=None: calls.append((sid, date)) or {
            "status": "shipped"},
    })()
    monkeypatch.setattr(reg, "_shipment_service", lambda _ds: service)

    result = reg.shipment_ship_handler({"shipment_id": "d-1"}, _ctx())
    assert result["success"] is True
    assert calls == [("d-1", None)]
    assert result["data"]["new_status"] == "shipped"


def test_deliver_calls_receive(monkeypatch, ds):
    calls = []
    service = type("S", (), {
        "receive": lambda self, sid, sig=None, date=None: calls.append(
            (sid, sig, date)) or {"status": "delivered", "idempotent": True},
    })()
    monkeypatch.setattr(reg, "_shipment_service", lambda _ds: service)

    result = reg.shipment_deliver_handler(
        {"shipment_id": "d-1", "signature_ref": "SIG-1"}, _ctx())
    assert result["success"] is True
    assert calls == [("d-1", "SIG-1", None)]


def test_shipment_handler_returns_error_envelope(monkeypatch, ds):
    def boom(self, sid, date=None):
        raise RuntimeError("交货单状态非法")

    service = type("S", (), {"ship_confirm": boom})()
    monkeypatch.setattr(reg, "_shipment_service", lambda _ds: service)

    result = reg.shipment_ship_handler({"shipment_id": "d-1"}, _ctx())
    assert result["success"] is False
    assert "状态非法" in result["message"]


# ─────────────────────────────────────────────────────────────────────────────
# work_order.*
# ─────────────────────────────────────────────────────────────────────────────

def test_produce_idempotent_by_source(monkeypatch, ds):
    ds.rows = [(7, "new", "o-1")]
    service = type("S", (), {"create_work_order": lambda self, payload: (_ for _ in ()).throw(
        AssertionError("已存在时不应建单"))})()
    monkeypatch.setattr(reg, "_work_order_service", lambda _ds: service)

    result = reg.work_order_produce_handler({"line_refs": "s-1"}, _ctx())
    assert result["success"] is True
    assert result["data"]["idempotent"] is True
    assert result["data"]["work_order_id"] == 7


def test_produce_creates_production_work_order(monkeypatch, ds):
    payloads = []
    service = type("S", (), {
        "create_work_order": lambda self, payload: payloads.append(payload) or {
            "id": 8, "status": "new", "work_order_no": "WO-8"},
    })()
    monkeypatch.setattr(reg, "_work_order_service", lambda _ds: service)

    result = reg.work_order_produce_handler(
        {"line_refs": "s-1", "item_id": "i-1", "qty": 3}, _ctx())
    assert result["success"] is True
    assert payloads[0]["order_type"] == "production"
    assert payloads[0]["source_demand_type"] == "sales_order_schedule"
    assert payloads[0]["source_demand_id"] == "s-1"


def test_dispatch_builds_service_work_order(monkeypatch, ds):
    payloads = []
    service = type("S", (), {
        "create_work_order": lambda self, payload: payloads.append(payload) or {
            "id": 9, "status": "new", "work_order_no": "WO-9"},
    })()
    monkeypatch.setattr(reg, "_work_order_service", lambda _ds: service)

    result = reg.work_order_dispatch_handler({"schedule_id": "s-1"}, _ctx())
    assert result["success"] is True
    assert payloads[0]["order_type"] == "service"
    assert payloads[0]["severity"] == "medium"
    assert payloads[0]["channel"] == "dispatch"


def test_install_uses_install_channel(monkeypatch, ds):
    payloads = []
    service = type("S", (), {
        "create_work_order": lambda self, payload: payloads.append(payload) or {
            "id": 10, "status": "new", "work_order_no": "WO-10"},
    })()
    monkeypatch.setattr(reg, "_work_order_service", lambda _ds: service)

    result = reg.work_order_install_handler({"schedule_id": "s-1"}, _ctx())
    assert result["success"] is True
    assert payloads[0]["channel"] == "install"


def test_confirm_returns_new_status(monkeypatch, ds):
    calls = []
    service = type("S", (), {
        "resolve_event": lambda self, wid, actor=None, note=None: calls.append(
            (wid, actor, note)) or {"status": "resolved", "already_resolved": False},
    })()
    monkeypatch.setattr(reg, "_work_order_service", lambda _ds: service)

    result = reg.work_order_confirm_handler(
        {"work_order_id": 11, "qty_good": 2}, _ctx())
    assert result["success"] is True
    assert result["data"]["new_status"] == "resolved"
    assert result["data"]["qty_good"] == 2
    assert calls == [(11, "u-1", None)]


def test_close_resolves_and_derives_service_status(monkeypatch, ds):
    ds.rows = [("o-1",)]
    service = type("S", (), {
        "resolve_event": lambda self, wid, actor=None, note=None: {"status": "resolved"},
        "derive_service_status": lambda self, order_id: "completed",
    })()
    monkeypatch.setattr(reg, "_work_order_service", lambda _ds: service)

    result = reg.work_order_close_handler({"work_order_id": 11}, _ctx())
    assert result["success"] is True
    assert result["data"]["new_status"] == "resolved"
    assert result["data"]["service_status"] == "completed"


# ─────────────────────────────────────────────────────────────────────────────
# rework
# ─────────────────────────────────────────────────────────────────────────────

def test_rework_starts_new_run(monkeypatch):
    ds = FakeDS([("t-1", "r-1", "d-1", '["s-1"]', None)])
    monkeypatch.setattr(reg, "_get_ds", lambda: ds)

    monkeypatch.setattr(
        "meta.core.workflow_engine.get_run",
        lambda _ds, run_id: {"workflow_key": "wf-fulfill-stock", "inputs": {"order_id": "o-1"}},
    )
    captured = {}

    def fake_start_run(_ds, **kwargs):
        captured.update(kwargs)
        return {"run_id": "r-2", "workflow_key": kwargs["workflow_key"]}

    monkeypatch.setattr("meta.core.workflow_engine.start_run", fake_start_run)

    result = reg.work_order_rework_handler({}, _ctx(task_id="t-1"))
    assert result["success"] is True
    assert result["data"]["new_run_id"] == "r-2"
    assert captured["variables"] == {"reason": "rework", "retry_of": "t-1"}
    assert captured["line_refs"] == ["s-1"]
