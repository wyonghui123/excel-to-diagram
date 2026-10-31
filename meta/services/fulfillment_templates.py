# -*- coding: utf-8 -*-
"""履约编排模板 —— 批次 4b：4 个 `workflow_key` 的静态定义 + 幂等发布

依据: docs/superpowers/specs/2026-10-29-so-wave3/batch4b_orchestration_design.md §3/§5
      docs/superpowers/specs/2026-10-29-so-wave3/spec.md §10.18.3

口径:
  · 模板属「定义数据」：用 `workflow_store.publish_workflow()` 幂等发布，
    **不新增迁移、不新增表**。
  · 节点 `executor_type` 决定执行通道：`system` → BO Action（`executor_config.action_id`）；
    `human` → 任务收件箱。`executor_config` 只声明，不写业务表（写权经 service）。
  · 动态性分层见设计 §3.1：链内不做任意跳转；`ship` 失败走 `exception` 异常节点，
    `confirm` / `accept` 用 `decision_actions` 成对声明（approve / reject）。
"""

from __future__ import annotations

from typing import Any, Dict, List

from meta.core.workflow_store import publish_workflow

WORKFLOW_STOCK = "wf-fulfill-stock"
WORKFLOW_MTO = "wf-fulfill-mto"
WORKFLOW_SERVICE = "wf-fulfill-service"
WORKFLOW_MIXED = "wf-fulfilled-mixed"

WORKFLOW_KEYS = (
    WORKFLOW_STOCK, WORKFLOW_MTO, WORKFLOW_SERVICE, WORKFLOW_MIXED,
)


def _system(node_id: str, step: int, title: str, action_id: str,
            *, target_object: str, description: str = "") -> Dict[str, Any]:
    return {
        "node_id": node_id,
        "step_number": step,
        "title": title,
        "description": description or None,
        "type": "task",
        "executor_type": "system",
        "assign_policy": "direct",
        "executor_assignee": "system",
        "executor_config": {
            "action_id": action_id,
            "target_object": target_object,
        },
        "meta": {"target_object": target_object},
    }


def _human(node_id: str, step: int, title: str, *,
           task_type: str = "task", description: str = "",
           decision_actions: Dict[str, str] | None = None) -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    if decision_actions:
        config["decision_actions"] = dict(decision_actions)
    return {
        "node_id": node_id,
        "step_number": step,
        "title": title,
        "description": description or None,
        "type": task_type,
        "executor_type": "human",
        "assign_policy": "claim",
        "executor_config": config or None,
    }


def _chain(*node_ids: str) -> List[Dict[str, str]]:
    return [{"from": src, "to": dst, "when": "done"}
            for src, dst in zip(node_ids, node_ids[1:])]


# ─────────────────────────────────────────────────────────────────────────────
# 4 个模板
# ─────────────────────────────────────────────────────────────────────────────

STOCK_NODES = [
    _system("pick", 1, "拣货", "shipment.pick", target_object="shipments"),
    _system("ship", 2, "发货", "shipment.ship", target_object="shipments"),
    _system("deliver", 3, "签收", "shipment.deliver", target_object="shipments"),
    _human("exception", 4, "发运异常处置", description="承运商改派 / 重试决策"),
]

MTO_NODES = [
    _human("produce", 1, "生产完工确认", description="生产负责人确认工单完工"),
    _system("pick", 2, "拣货", "shipment.pick", target_object="shipments"),
    _system("ship", 3, "发货", "shipment.ship", target_object="shipments"),
    _system("deliver", 4, "签收", "shipment.deliver", target_object="shipments"),
    _human("exception", 5, "发运异常处置", description="承运商改派 / 重试决策"),
]

SERVICE_NODES = [
    _system("dispatch", 1, "服务派工", "work_order.dispatch",
            target_object="work_orders"),
    _human("onsite", 2, "上门服务"),
    _human("confirm", 3, "服务确认", task_type="approval",
           decision_actions={"approve": "work_order.confirm",
                             "reject": "work_order.rework"}),
    _system("close", 4, "工单关闭", "work_order.close",
            target_object="work_orders"),
]

MIXED_NODES = [
    _system("ship", 1, "发货", "shipment.ship", target_object="shipments"),
    _system("deliver", 2, "签收", "shipment.deliver", target_object="shipments"),
    _system("install", 3, "上门安装", "work_order.install",
            target_object="work_orders"),
    _human("accept", 4, "客户验收", task_type="approval",
           decision_actions={"approve": "work_order.close",
                             "reject": "work_order.rework"}),
]

TEMPLATES: Dict[str, Dict[str, Any]] = {
    WORKFLOW_STOCK: {
        "name": "履约编排 - 备货出库",
        "description": "拣货 → 发货 → 签收（发运失败转异常处置）",
        "nodes": STOCK_NODES,
        "edges": _chain("pick", "ship", "deliver") + [
            {"from": "ship", "to": "exception", "when": "failed"},
        ],
    },
    WORKFLOW_MTO: {
        "name": "履约编排 - 按单生产",
        "description": "生产完工 → 拣货 → 发货 → 签收（发运失败转异常处置）",
        "nodes": MTO_NODES,
        "edges": _chain("produce", "pick", "ship", "deliver") + [
            {"from": "ship", "to": "exception", "when": "failed"},
        ],
    },
    WORKFLOW_SERVICE: {
        "name": "履约编排 - 现场服务",
        "description": "派工 → 上门 → 服务确认 → 工单关闭",
        "nodes": SERVICE_NODES,
        "edges": _chain("dispatch", "onsite", "confirm", "close"),
    },
    WORKFLOW_MIXED: {
        "name": "履约编排 - 发货安装混合",
        "description": "发货 → 签收 → 上门安装 → 客户验收",
        "nodes": MIXED_NODES,
        "edges": _chain("ship", "deliver", "install", "accept"),
    },
}


def ensure_templates(data_source, *, created_by: str = "system",
                     ) -> Dict[str, Dict[str, Any]]:
    """幂等发布 4 个履约模板。

    - 内容与最新版等价 → `publish_workflow` 返回 `published=False`（SKIP）
    - 内容变更 → 发布新版本；在途 Run 的 `definition_snapshot` 不受影响
    """
    results: Dict[str, Dict[str, Any]] = {}
    for workflow_key in WORKFLOW_KEYS:
        spec = TEMPLATES[workflow_key]
        results[workflow_key] = publish_workflow(
            data_source,
            workflow_key=workflow_key,
            name=spec["name"],
            nodes=spec["nodes"],
            edges=spec["edges"],
            description=spec.get("description") or "",
            owner=spec.get("owner") or "",
            trigger_kind="manual",
            meta_kv={"source": "fulfillment_templates"},
            created_by=created_by,
        )
    return results
