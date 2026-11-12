# -*- coding: utf-8 -*-
"""T4b.5 路由 → 模板发布 → start_run 接线（冒烟）

覆盖目标:
  1. stock / service / 兜底 mixed 三类输入命中对应 `workflow_key`
  2. `start_run(line_refs=schedule_id)`：每个克隆任务 `line_refs` 一致，
     `workflow_runs.meta.line_refs` 可读
  3. `advance_run` 后首节点 ready（deps 求值冒烟）
  4. 重复 `ensure_templates` 幂等（版本号不增长）
"""

import os

os.environ.setdefault("ALLOW_RAW_SQL", "1")

import pytest

from meta.core.task_event_schema import ensure_task_event_tables
from meta.core.task_schema import ensure_task_tables
from meta.core.workflow_engine import advance_run, get_run, list_run_tasks
from meta.core.workflow_store import latest_version
from meta.services.fulfillment_routing_service import (
    FulfillmentRoutingService,
    WORKFLOW_MIXED,
    WORKFLOW_SERVICE,
    WORKFLOW_STOCK,
)
from meta.services.fulfillment_templates import WORKFLOW_KEYS

pytestmark = pytest.mark.unit


@pytest.fixture()
def ds(tmp_path):
    from meta.core.datasource import get_data_source

    source = get_data_source("sqlite", database=str(tmp_path / "b4b_routing.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        source.execute(
            "CREATE TABLE fulfillment_routing_rules ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, priority INTEGER, "
            "item_type TEXT, procurement_type TEXT, delivery_mode TEXT, "
            "site_id INTEGER, workflow_key TEXT, is_default INTEGER DEFAULT 0, "
            "enabled INTEGER DEFAULT 1, remark TEXT)")
        for priority, procurement_type, workflow_key, is_default in (
                (10, "stock", WORKFLOW_STOCK, 1),
                (30, "service", WORKFLOW_SERVICE, 1),
                (100, None, WORKFLOW_MIXED, 1)):
            source.execute(
                "INSERT INTO fulfillment_routing_rules "
                "(priority, procurement_type, workflow_key, is_default, enabled) "
                "VALUES (?, ?, ?, ?, 1)",
                (priority, procurement_type, workflow_key, is_default))
    yield source


def _run_ids(ds, run_id):
    return {t["workflow_node_id"]: t for t in list_run_tasks(ds, run_id)}


def test_stock_route_starts_run_with_line_refs(ds):
    service = FulfillmentRoutingService(ds)
    result = service.start_fulfillment_run(
        {"procurement_type": "stock"}, line_refs="S-1", doc_ref="FO-1",
        created_by="u-1")

    assert result["workflow_key"] == WORKFLOW_STOCK
    run = result["run"]
    tasks = _run_ids(ds, run["run_id"])
    assert set(tasks) == {"pick", "ship", "deliver", "exception"}
    assert {t["line_refs"] for t in tasks.values()} == {"S-1"}

    stored_run = get_run(ds, run["run_id"])
    assert stored_run["meta"]["line_refs"] == "S-1"

    advanced = advance_run(ds, run["run_id"])
    assert advanced["promoted"]
    assert _run_ids(ds, run["run_id"])["pick"]["status"] == "ready"


def test_service_route_hits_service_template(ds):
    service = FulfillmentRoutingService(ds)
    result = service.start_fulfillment_run(
        {"procurement_type": "service"}, line_refs="S-2")

    assert result["workflow_key"] == WORKFLOW_SERVICE
    tasks = _run_ids(ds, result["run"]["run_id"])
    assert set(tasks) == {"dispatch", "onsite", "confirm", "close"}
    assert tasks["confirm"]["executor_type"] == "human"
    assert tasks["confirm"]["executor_config"]["decision_actions"]["reject"] \
        == "work_order.rework"


def test_fallback_uses_mixed_template(ds):
    service = FulfillmentRoutingService(ds)
    result = service.start_fulfillment_run({"procurement_type": "buy"})
    assert result["workflow_key"] == WORKFLOW_MIXED
    assert result["matched"] == "default"


def test_start_run_is_idempotent_for_definition_versions(ds):
    service = FulfillmentRoutingService(ds)
    service.start_fulfillment_run({"procurement_type": "stock"}, line_refs="S-3")
    versions = {key: latest_version(ds, key) for key in WORKFLOW_KEYS}

    service.start_fulfillment_run({"procurement_type": "stock"}, line_refs="S-4")
    assert {key: latest_version(ds, key) for key in WORKFLOW_KEYS} == versions

    stored = ds.execute(
        "SELECT COUNT(*) FROM workflows WHERE workflow_key = ?", (WORKFLOW_STOCK,)
    ).fetchone()
    assert stored[0] == 1
