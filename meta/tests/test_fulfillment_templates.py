# -*- coding: utf-8 -*-
"""T4b.3 / T4b.3b 履约模板定义 + 幂等发布 + 动态性声明

覆盖目标:
  1. 4 个 `workflow_key` 全部发布，定义经 C2 校验零 findings
  2. `ensure_templates()` 二次调用幂等：`published=False`、版本号不增长
  3. `ship` 失败分支：stock / mto 有 `ship → exception (when=failed)`，exception 为 human
  4. `confirm` / `accept` 决策节点：`decision_actions` approve/reject 成对且可解析
  5. system 节点只引用已注册的 8 个业务 action（produce 默认 human，不引用）
"""

import pytest

from meta.core.task_schema import ensure_task_tables
from meta.core.workflow_definition import validate_definition
from meta.core.workflow_store import get_nodes, latest_version
from meta.services.fulfillment_templates import (
    TEMPLATES,
    WORKFLOW_KEYS,
    WORKFLOW_MIXED,
    WORKFLOW_MTO,
    WORKFLOW_SERVICE,
    WORKFLOW_STOCK,
    ensure_templates,
)

pytestmark = pytest.mark.unit

EXPECTED_SYSTEM_ACTIONS = {
    "shipment.pick", "shipment.ship", "shipment.deliver",
    "work_order.produce", "work_order.dispatch", "work_order.install",
    "work_order.confirm", "work_order.close",
}


@pytest.fixture()
def ds(tmp_path):
    from meta.core.datasource import get_data_source

    source = get_data_source("sqlite", database=str(tmp_path / "b4b_templates.db"))
    with source.transaction():
        ensure_task_tables(source)
    yield source


def _node_by_id(spec, node_id):
    return next(node for node in spec["nodes"] if node["node_id"] == node_id)


def _system_action_ids():
    found = set()
    for spec in TEMPLATES.values():
        for node in spec["nodes"]:
            config = node.get("executor_config") or {}
            if config.get("action_id"):
                found.add(config["action_id"])
    return found


def test_four_templates_defined_and_valid():
    assert set(TEMPLATES) == set(WORKFLOW_KEYS)
    for key, spec in TEMPLATES.items():
        assert validate_definition(spec["nodes"], spec["edges"]) == [], key


def test_ensure_templates_publishes_all(ds):
    results = ensure_templates(ds)
    assert set(results) == set(WORKFLOW_KEYS)
    for key, result in results.items():
        assert result["published"] is True, key
        assert result["version"] == 1, key
        assert latest_version(ds, key) == 1


def test_ensure_templates_is_idempotent(ds):
    ensure_templates(ds)
    before = {key: latest_version(ds, key) for key in WORKFLOW_KEYS}

    again = ensure_templates(ds)
    for key, result in again.items():
        assert result["published"] is False, key
        assert result["version"] == before[key], key
        assert latest_version(ds, key) == before[key], key


def test_stock_and_mto_ship_failure_routes_to_exception():
    for key in (WORKFLOW_STOCK, WORKFLOW_MTO):
        spec = TEMPLATES[key]
        failed = [e for e in spec["edges"]
                  if e["from"] == "ship" and e["when"] == "failed"]
        assert len(failed) == 1, key
        assert failed[0]["to"] == "exception", key
        exception = _node_by_id(spec, "exception")
        assert exception["executor_type"] == "human", key


def test_decision_nodes_have_paired_actions():
    from meta.core.decision_effect import resolve_decision_action

    for key, node_id in ((WORKFLOW_SERVICE, "confirm"), (WORKFLOW_MIXED, "accept")):
        node = _node_by_id(TEMPLATES[key], node_id)
        assert node["executor_type"] == "human", key
        assert node["type"] == "approval", key

        config = node["executor_config"]
        assert resolve_decision_action(config, "approve")
        assert resolve_decision_action(config, "reject")


def test_system_nodes_only_use_registered_actions():
    # produce 默认 B（human 节点），work_order.produce 仍注册但模板不引用
    assert _system_action_ids() <= EXPECTED_SYSTEM_ACTIONS


def test_confirm_and_accept_decision_actions():
    service = _node_by_id(TEMPLATES[WORKFLOW_SERVICE], "confirm")["executor_config"]
    assert service["decision_actions"] == {
        "approve": "work_order.confirm", "reject": "work_order.rework"}

    mixed = _node_by_id(TEMPLATES[WORKFLOW_MIXED], "accept")["executor_config"]
    assert mixed["decision_actions"] == {
        "approve": "work_order.close", "reject": "work_order.rework"}


def test_published_nodes_keep_executor_config(ds):
    ensure_templates(ds)
    expected = {
        WORKFLOW_STOCK: ("ship", "shipment.ship"),
        WORKFLOW_MTO: ("ship", "shipment.ship"),
        WORKFLOW_SERVICE: ("dispatch", "work_order.dispatch"),
        WORKFLOW_MIXED: ("ship", "shipment.ship"),
    }
    for key, (node_id, action_id) in expected.items():
        workflow = ds.execute(
            "SELECT id FROM workflows WHERE workflow_key = ? AND version = 1",
            (key,),
        ).fetchone()
        nodes = get_nodes(ds, workflow[0], 1)
        node = next(n for n in nodes if n["node_id"] == node_id)
        assert node["executor_config"]["action_id"] == action_id
