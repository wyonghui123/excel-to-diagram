# -*- coding: utf-8 -*-
"""[C1] 编排定义层存储 —— Workflow 版本化发布 / 读取

职责:
- `publish_workflow()`: 校验（C2）→ 分配版本号 → 单事务写 `workflows` 1 行 +
  `task_templates` N 行
- 读取：版本序列 / 指定版本 / 完整定义（含节点与边）

纪律（定义层无状态，§12 C1）:
- **只 INSERT 版本行，绝不 UPDATE 旧版本** → 在途 Run 的 `definition_snapshot`
  天然不受新版本影响（同一纪律见 `doc_flow_rule_store`：声明字段 upsert、
  不覆盖运行态）
- 版本号由本模块分配（`max(version)+1`），调用方不传 → 避免错版 / 回退
- 内容等价时**幂等返回现有版本**（不产生空版本行）—— 靠逐字段比对，
  不新增 fingerprint 列（schema 冻结，不做无谓演进）

边界: 只做定义层（`workflows` + `task_templates`）；Run 实例化归 `workflow_engine`。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from meta.core.task_schema import TASK_TEMPLATE_TABLE, WORKFLOW_TABLE
from meta.core.workflow_definition import (
    assert_definition,
    group_of,
    node_id_of,
    parent_of,
    _as_int,
)

#: 触发方式值域（与 `workflows.trigger_kind` 列注释一致）
TRIGGER_KINDS = ("manual", "schedule", "event", "api")

#: 节点定义的「内容字段」白名单 —— 幂等比对与落库同源（避免两处漂移）
NODE_CONTENT_FIELDS = (
    "node_id", "step_number", "parent_step_number", "group_name", "title",
    "description", "type", "priority", "executor_type", "executor_assignee",
    "executor_candidates", "assign_policy", "executor_config",
    "executor_fallback", "claim_timeout_seconds", "timeout_seconds",
    "retry_policy", "inputs_schema", "outputs_schema", "acceptance", "sla", "meta",
)

_NODE_COLUMNS = (
    "id", "workflow_id", "workflow_version", "node_id", "step_number",
    "parent_step_number", "group_name", "title", "description", "type",
    "priority", "executor_type", "executor_assignee", "executor_candidates",
    "assign_policy", "executor_config", "executor_fallback",
    "claim_timeout_seconds", "timeout_seconds", "retry_policy",
    "inputs_schema", "outputs_schema", "acceptance", "sla", "meta",
    "created_at", "updated_at",
)

_WORKFLOW_COLUMNS = (
    "id", "workflow_key", "version", "name", "description", "owner",
    "trigger_kind", "trigger_expr", "edges", "sla", "meta",
    "created_by", "created_at", "updated_at",
)

#: JSON 列（读取时反序列化）
_WORKFLOW_JSON = ("edges", "sla", "meta")
_NODE_JSON = (
    "executor_candidates", "executor_config", "executor_fallback", "retry_policy",
    "inputs_schema", "outputs_schema", "acceptance", "sla", "meta",
)


class WorkflowStoreError(RuntimeError):
    """发布 / 读取失败（参数非法、版本缺失等）。"""


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json_text(value: Any) -> Optional[str]:
    """JSON 列写入文本；None/空 → None（保持列可空语义）。"""
    if value is None or value == "" or value == [] or value == {}:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _canonical(value: Any) -> str:
    """规范化 JSON 文本（幂等比对用；排序键 + 稳定分隔符）。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _row_to_dict(cursor_row, description, json_columns: Sequence[str]) -> Dict[str, Any]:
    record = {col[0]: value for col, value in zip(description, cursor_row)}
    for key in json_columns:
        raw = record.get(key)
        if isinstance(raw, str) and raw:
            try:
                record[key] = json.loads(raw)
            except json.JSONDecodeError:
                pass
    return record


def _select_one(data_source, sql: str, params: tuple, json_columns: Sequence[str]):
    cursor = data_source.execute(sql, params)
    row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_dict(row, cursor.description, json_columns)


def _select_all(data_source, sql: str, params: tuple, json_columns: Sequence[str]):
    cursor = data_source.execute(sql, params)
    return [_row_to_dict(r, cursor.description, json_columns) for r in cursor.fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# 归一化
# ─────────────────────────────────────────────────────────────────────────────

def _node_content(node: Dict[str, Any]) -> Dict[str, Any]:
    """节点定义 → 落库内容（不含 id / 版本 / 时间戳），键集 = NODE_CONTENT_FIELDS。"""
    return {
        "node_id": node_id_of(node),
        "step_number": _as_int(node.get("step_number")),
        "parent_step_number": parent_of(node) or None,
        "group_name": group_of(node) or None,
        "title": str(node.get("title", "")).strip(),
        "description": node.get("description") or None,
        "type": str(node.get("type") or "story").strip(),
        "priority": str(node.get("priority") or "P2").strip(),
        "executor_type": str(node.get("executor_type", "")).strip(),
        "executor_assignee": node.get("executor_assignee") or None,
        "executor_candidates": node.get("executor_candidates") or None,
        "assign_policy": str(node.get("assign_policy") or "direct").strip(),
        "executor_config": node.get("executor_config") or None,
        "executor_fallback": node.get("executor_fallback") or None,
        "claim_timeout_seconds": node.get("claim_timeout_seconds", 300),
        "timeout_seconds": node.get("timeout_seconds"),
        "retry_policy": node.get("retry_policy") or None,
        "inputs_schema": node.get("inputs_schema") or None,
        "outputs_schema": node.get("outputs_schema") or None,
        "acceptance": node.get("acceptance") or None,
        "sla": node.get("sla") or None,
        # 兼容 node["meta"] 与保留字规避写法 meta_kv
        "meta": node.get("meta") or node.get("meta_kv") or None,
    }


def _workflow_content(*, workflow_key: str, name: str, description: str, owner: str,
                      trigger_kind: str, trigger_expr: str, edges: Any,
                      sla: Any, meta_kv: Any) -> Dict[str, Any]:
    return {
        "workflow_key": workflow_key,
        "name": name,
        "description": description or None,
        "owner": owner or None,
        "trigger_kind": trigger_kind,
        "trigger_expr": trigger_expr or None,
        "edges": list(edges or []),
        "sla": sla or None,
        "meta": meta_kv or None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 读取
# ─────────────────────────────────────────────────────────────────────────────

def latest_version(data_source, workflow_key: str) -> int:
    """返回当前最大版本号；不存在返回 0。"""
    row = data_source.execute(
        f"SELECT COALESCE(MAX(version), 0) FROM {WORKFLOW_TABLE} WHERE workflow_key = ?",
        (workflow_key,),
    ).fetchone()
    return int(row[0]) if row else 0


def list_versions(data_source, workflow_key: str) -> List[Dict[str, Any]]:
    """按版本升序返回定义行（不含节点）。"""
    return _select_all(
        data_source,
        f"SELECT {', '.join(_WORKFLOW_COLUMNS)} FROM {WORKFLOW_TABLE} "
        "WHERE workflow_key = ? ORDER BY version ASC",
        (workflow_key,),
        _WORKFLOW_JSON,
    )


def get_workflow(data_source, workflow_key: str,
                 version: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """取指定版本定义行；version=None 取最新版。不存在返回 None。"""
    if version is None:
        version = latest_version(data_source, workflow_key)
        if version == 0:
            return None
    return _select_one(
        data_source,
        f"SELECT {', '.join(_WORKFLOW_COLUMNS)} FROM {WORKFLOW_TABLE} "
        "WHERE workflow_key = ? AND version = ?",
        (workflow_key, int(version)),
        _WORKFLOW_JSON,
    )


def get_nodes(data_source, workflow_id: str, version: int) -> List[Dict[str, Any]]:
    """取某版本的节点定义（按主干 step_number → node_id 排序）。"""
    return _select_all(
        data_source,
        f"SELECT {', '.join(_NODE_COLUMNS)} FROM {TASK_TEMPLATE_TABLE} "
        "WHERE workflow_id = ? AND workflow_version = ? "
        "ORDER BY COALESCE(step_number, 1000000) ASC, node_id ASC",
        (workflow_id, int(version)),
        _NODE_JSON,
    )


def load_definition(data_source, workflow_key: str,
                    version: Optional[int] = None) -> Dict[str, Any]:
    """取完整定义 `{workflow, nodes, edges}`；不存在抛 WorkflowStoreError。"""
    workflow = get_workflow(data_source, workflow_key, version)
    if workflow is None:
        raise WorkflowStoreError(
            f"Workflow 不存在: key={workflow_key!r}, version={version!r}")
    nodes = get_nodes(data_source, workflow["id"], workflow["version"])
    return {"workflow": workflow, "nodes": nodes, "edges": workflow.get("edges") or []}


# ─────────────────────────────────────────────────────────────────────────────
# 发布（版本化）
# ─────────────────────────────────────────────────────────────────────────────

def publish_workflow(
    data_source,
    *,
    workflow_key: str,
    name: str,
    nodes: Sequence[Dict[str, Any]],
    edges: Optional[Sequence[Dict[str, Any]]] = None,
    description: str = "",
    owner: str = "",
    trigger_kind: str = "manual",
    trigger_expr: str = "",
    sla: Any = None,
    meta_kv: Any = None,
    created_by: str = "",
) -> Dict[str, Any]:
    """发布一版 Workflow 定义；内容与最新版等价时幂等返回该版本。

    Raises:
        WorkflowStoreError: 参数非法 / 内容等价判定失败
        WorkflowDefinitionError: 节点或边结构非法（C2 校验，映射见 workflow_definition）
    """
    if not (isinstance(workflow_key, str) and workflow_key.strip()):
        raise WorkflowStoreError("workflow_key 不能为空")
    workflow_key = workflow_key.strip()
    if not (isinstance(name, str) and name.strip()):
        raise WorkflowStoreError("name 不能为空")
    name = name.strip()
    if trigger_kind not in TRIGGER_KINDS:
        raise WorkflowStoreError(
            f"trigger_kind 必须为 {TRIGGER_KINDS} 之一，实际 {trigger_kind!r}")

    assert_definition(nodes, edges)  # C2：非法定义 → WorkflowDefinitionError

    node_contents = sorted((_node_content(n) for n in nodes),
                           key=lambda c: c["node_id"])
    content = _workflow_content(
        workflow_key=workflow_key, name=name, description=description, owner=owner,
        trigger_kind=trigger_kind, trigger_expr=trigger_expr,
        edges=edges, sla=sla, meta_kv=meta_kv,
    )

    current_version = latest_version(data_source, workflow_key)
    if current_version:
        latest = get_workflow(data_source, workflow_key, current_version)
        existing_nodes = get_nodes(data_source, latest["id"], current_version)
        if _same_as(latest, existing_nodes, content, node_contents):
            return {"workflow_id": latest["id"], "workflow_key": workflow_key,
                    "version": current_version, "node_count": len(existing_nodes),
                    "published": False}

    version = current_version + 1
    workflow_id = uuid.uuid4().hex
    ts = _now_iso()

    with data_source.transaction():
        data_source.execute(
            f"INSERT INTO {WORKFLOW_TABLE} ({', '.join(_WORKFLOW_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in _WORKFLOW_COLUMNS)})",
            (
                workflow_id, workflow_key, version, name,
                content["description"], content["owner"], trigger_kind,
                content["trigger_expr"], _json_text(content["edges"]),
                _json_text(sla), _json_text(meta_kv), created_by or None, ts, ts,
            ),
        )
        for node_content in node_contents:
            data_source.execute(
                f"INSERT INTO {TASK_TEMPLATE_TABLE} ({', '.join(_NODE_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in _NODE_COLUMNS)})",
                (
                    f"{workflow_key}@{version}.{node_content['node_id']}",
                    workflow_id, version, node_content["node_id"],
                    node_content["step_number"], node_content["parent_step_number"],
                    node_content["group_name"], node_content["title"],
                    node_content["description"], node_content["type"],
                    node_content["priority"], node_content["executor_type"],
                    node_content["executor_assignee"],
                    _json_text(node_content["executor_candidates"]),
                    node_content["assign_policy"],
                    _json_text(node_content["executor_config"]),
                    _json_text(node_content["executor_fallback"]),
                    node_content["claim_timeout_seconds"],
                    node_content["timeout_seconds"],
                    _json_text(node_content["retry_policy"]),
                    _json_text(node_content["inputs_schema"]),
                    _json_text(node_content["outputs_schema"]),
                    _json_text(node_content["acceptance"]),
                    _json_text(node_content["sla"]),
                    _json_text(node_content["meta"]),
                    ts, ts,
                ),
            )

    return {"workflow_id": workflow_id, "workflow_key": workflow_key,
            "version": version, "node_count": len(node_contents), "published": True}


def _same_as(workflow: Dict[str, Any], existing_nodes: Iterable[Dict[str, Any]],
             content: Dict[str, Any], node_contents: List[Dict[str, Any]]) -> bool:
    """最新版与本次请求是否逐字段等价（幂等发布判定）。"""
    existing_content = {
        "workflow_key": workflow.get("workflow_key"),
        "name": workflow.get("name"),
        "description": workflow.get("description") or None,
        "owner": workflow.get("owner") or None,
        "trigger_kind": workflow.get("trigger_kind"),
        "trigger_expr": workflow.get("trigger_expr") or None,
        "edges": workflow.get("edges") or [],
        "sla": workflow.get("sla") or None,
        "meta": workflow.get("meta") or None,
    }
    if _canonical(existing_content) != _canonical(content):
        return False

    existing = sorted((_stored_node_content(n) for n in existing_nodes),
                      key=lambda c: c["node_id"])
    return _canonical(existing) == _canonical(node_contents)


def _stored_node_content(node: Dict[str, Any]) -> Dict[str, Any]:
    """已落库节点行 → 与 `_node_content` 同口径的内容字典（空值归一为 None）。"""
    content: Dict[str, Any] = {}
    for key in NODE_CONTENT_FIELDS:
        value = node.get(key)
        content[key] = None if value in ("", [], {}) else value
    content["parent_step_number"] = node.get("parent_step_number") or None
    content["group_name"] = node.get("group_name") or None
    return content

