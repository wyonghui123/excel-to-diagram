# -*- coding: utf-8 -*-
"""[C2] 编排定义层结构校验 —— 主干 + 单亲 + 分支块（**非通用 DAG**）

职责: 纯函数校验 Workflow 的 `nodes` / `edges` 定义（不碰 DB / Flask）。
      C1 发布入口 `workflow_store.publish_workflow()` 在写库前调用本模块 ——
      非法定义在**定义期**即被拒绝，不产生半成品版本行。

节点结构（抄 Oracle 已核实的最小充分集；spec 2026-09-07 §12 C2 / 综合 §1）:
- 主干: `parent_step_number` 空/0，由 `step_number` 显式编号（线性）
- 分支块: `group_name` 非空，块内节点挂载到**同一个** `parent_step_number`
- **非通用 DAG（机器化断言）**: 一个节点出现多条入边（n:1 合并）时，来源必须
  同属**一个**分支块 → 跨块合并被拒（`MULTI_PARENT_NOT_ALLOWED`）。
  这条是本节的存在理由：否则「非通用 DAG」只是文档口号。

边界:
- 不做 `edges[].when` 运行期求值（属 C4）
- 不做版本号分配 / 落库（属 C1 `workflow_store`）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

#: 节点必填键（与 task_templates 的 required 列对齐）
NODE_REQUIRED_KEYS = ("node_id", "title", "executor_type")

#: 边条件值域（task_templates/`tasks.deps[].when` 同口径）
WHEN_VALUES = ("done", "failed", "skipped", "done_or_skipped")

#: 默认边条件（未显式声明时）
DEFAULT_WHEN = "done"

#: 主干标记（parent_step_number 空 / 0 = 主干）
TRUNK_PARENT = 0

#: 输入模板 `run.inputs` 前缀（S2 outputs→inputs）
INPUT_RUN_PREFIX = "run.inputs."


def parse_ref_expr(expr: str) -> Optional[Tuple[Optional[str], str]]:
    """解析单个 `{{...}}` 内部表达式 → `(node_id 或 None=run.inputs, dot_path)`。

    只支持 `run.inputs.<path>` 与 `<node_id>.outputs.<path>`；非法返回 None。
    """
    text = str(expr or "").strip()
    if not text:
        return None
    if text.startswith(INPUT_RUN_PREFIX):
        path = text[len(INPUT_RUN_PREFIX):].strip().strip(".")
        return (None, path) if path else None
    if ".outputs." in text:
        node_id, _, path = text.partition(".outputs.")
        node_id, path = node_id.strip(), path.strip().strip(".")
        return (node_id, path) if node_id and path else None
    return None


def placeholder_refs(value: str) -> Optional[List[Tuple[Optional[str], str]]]:
    """解析字符串中的全部 `{{...}}` 引用。

    Returns:
        None = 语法非法（未闭合 / 表达式非法）；否则引用列表。
    """
    if "{{" not in value and "}}" not in value:
        return []
    if value.count("{{") != value.count("}}"):
        return None
    refs: List[Tuple[Optional[str], str]] = []
    start = 0
    while True:
        begin = value.find("{{", start)
        if begin < 0:
            break
        end = value.find("}}", begin + 2)
        if end < 0:
            return None
        ref = parse_ref_expr(value[begin + 2:end])
        if ref is None:
            return None
        refs.append(ref)
        start = end + 2
    return refs


class WorkflowDefinitionError(ValueError):
    """定义不合法（含全部 findings，便于一次性报错）。"""

    def __init__(self, findings: Sequence["DefinitionFinding"]):
        self.findings = list(findings)
        detail = "; ".join(f"[{f.code}] {f.detail}" for f in self.findings)
        super().__init__(f"编排定义非法: {detail}")


@dataclass(frozen=True)
class DefinitionFinding:
    code: str
    detail: str


@dataclass
class DefinitionReport:
    """校验结果（ok 仅计 error —— 本模块当前只产 error）。"""

    findings: List[DefinitionFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def codes(self) -> List[str]:
        return [f.code for f in self.findings]

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok,
                "findings": [{"code": f.code, "detail": f.detail}
                             for f in self.findings]}


# ─────────────────────────────────────────────────────────────────────────────
# 取值工具
# ─────────────────────────────────────────────────────────────────────────────

def _as_int(value: Any) -> Optional[int]:
    """把 step_number 类取值归一为 int；无法解析返回 None。"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def parent_of(node: Dict[str, Any]) -> int:
    """返回节点的挂载点编号（空 / 0 / 非法 → 0 = 主干）。"""
    value = _as_int(node.get("parent_step_number"))
    return value if value and value > 0 else TRUNK_PARENT


def group_of(node: Dict[str, Any]) -> str:
    value = node.get("group_name")
    return value.strip() if isinstance(value, str) else ""


def node_id_of(node: Dict[str, Any]) -> str:
    value = node.get("node_id")
    return value.strip() if isinstance(value, str) else ""


# ─────────────────────────────────────────────────────────────────────────────
# 视图（供 C1 引擎消费）
# ─────────────────────────────────────────────────────────────────────────────

def node_index(nodes: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """node_id → 节点。"""
    return {node_id_of(n): n for n in nodes if node_id_of(n)}


def main_trunk(nodes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """主干节点（无父），按 step_number 升序。"""
    trunk = [n for n in nodes if parent_of(n) == TRUNK_PARENT
             and _as_int(n.get("step_number")) is not None]
    return sorted(trunk, key=lambda n: _as_int(n.get("step_number")) or 0)


def branch_blocks(nodes: Sequence[Dict[str, Any]]) -> Dict[str, List[str]]:
    """`group_name` → 该分支块的 node_id 列表（按定义顺序）。"""
    blocks: Dict[str, List[str]] = {}
    for n in nodes:
        group = group_of(n)
        if group:
            blocks.setdefault(group, []).append(node_id_of(n))
    return blocks


def incoming_edges(nodes: Sequence[Dict[str, Any]],
                   edges: Optional[Sequence[Dict[str, Any]]] = None,
                   ) -> Dict[str, List[Dict[str, str]]]:
    """按目标节点归并入边：`{to_node_id: [{from, when}, ...]}`（when 已补默认）。"""
    known = node_index(nodes)
    result: Dict[str, List[Dict[str, str]]] = {nid: [] for nid in known}
    for edge in edges or []:
        target = _edge_endpoint(edge, "to")
        if target in result:
            result[target].append({"from": _edge_endpoint(edge, "from"),
                                   "when": _when_of(edge)})
    return result


def _edge_endpoint(edge: Any, key: str) -> str:
    if not isinstance(edge, dict):
        return ""
    value = edge.get(key)
    return value.strip() if isinstance(value, str) else ""


def _when_of(edge: Any) -> str:
    if not isinstance(edge, dict):
        return DEFAULT_WHEN
    value = edge.get("when")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return DEFAULT_WHEN


# ─────────────────────────────────────────────────────────────────────────────
# 校验
# ─────────────────────────────────────────────────────────────────────────────

def validate_definition(nodes: Any,
                        edges: Optional[Iterable[Any]] = None,
                        ) -> List[DefinitionFinding]:
    """校验节点 / 边结构，返回全部 findings（空 = 合法）。"""
    findings: List[DefinitionFinding] = []

    if not isinstance(nodes, (list, tuple)):
        return [DefinitionFinding("NODES_NOT_LIST", "nodes 需为数组")]
    if not nodes:
        return [DefinitionFinding("NODES_EMPTY", "nodes 不能为空（编排至少一个节点）")]

    normalized: List[Dict[str, Any]] = []
    seen_ids: Dict[str, int] = {}
    seen_steps: Dict[int, str] = {}

    for index, node in enumerate(nodes):
        ctx = f"nodes[{index}]"
        if not isinstance(node, dict):
            findings.append(DefinitionFinding("NODE_NOT_OBJECT", f"{ctx} 需为对象"))
            continue

        node_id = node_id_of(node)
        if not node_id:
            findings.append(DefinitionFinding("NODE_ID_MISSING", f"{ctx} 缺少 node_id"))
            continue
        if node_id in seen_ids:
            findings.append(DefinitionFinding(
                "NODE_ID_DUPLICATE",
                f"node_id '{node_id}' 重复（nodes[{seen_ids[node_id]}] 与 {ctx}）"))
            continue
        seen_ids[node_id] = index

        for key in NODE_REQUIRED_KEYS:
            value = node.get(key)
            if not (isinstance(value, str) and value.strip()):
                findings.append(DefinitionFinding(
                    "NODE_KEY_MISSING", f"node '{node_id}' 缺少必填键 '{key}'"))

        step = _as_int(node.get("step_number"))
        parent = parent_of(node)
        group = group_of(node)

        if step is None:
            if parent == TRUNK_PARENT:
                findings.append(DefinitionFinding(
                    "STEP_NUMBER_INVALID",
                    f"主干节点 '{node_id}' 必须提供正整数 step_number"))
        else:
            if step < 1:
                findings.append(DefinitionFinding(
                    "STEP_NUMBER_INVALID",
                    f"node '{node_id}' 的 step_number 必须 ≥1，实际 {step}"))
            elif step in seen_steps:
                findings.append(DefinitionFinding(
                    "STEP_NUMBER_DUPLICATE",
                    f"step_number {step} 重复（'{seen_steps[step]}' 与 '{node_id}'）"))
            else:
                seen_steps[step] = node_id

        if parent and step is not None and parent == step:
            findings.append(DefinitionFinding(
                "PARENT_SELF_REFERENCE",
                f"node '{node_id}' 的 parent_step_number 指向自身（{parent}）"))

        if group and parent == TRUNK_PARENT:
            findings.append(DefinitionFinding(
                "GROUP_PARENT_REQUIRED",
                f"分支块 '{group}' 的节点 '{node_id}' 必须声明 parent_step_number（挂载点）"))

        normalized.append(node)

    # 父引用存在性 + 同组挂载点一致
    known_steps = set(seen_steps)
    group_mount: Dict[str, int] = {}
    for node in normalized:
        node_id = node_id_of(node)
        parent = parent_of(node)
        group = group_of(node)
        if parent != TRUNK_PARENT and parent not in known_steps:
            findings.append(DefinitionFinding(
                "PARENT_NOT_FOUND",
                f"node '{node_id}' 的 parent_step_number={parent} 不在主干节点中"))
        if group:
            previous = group_mount.get(group)
            if previous is None:
                group_mount[group] = parent
            elif previous != parent:
                findings.append(DefinitionFinding(
                    "GROUP_MOUNT_CONFLICT",
                    f"分支块 '{group}' 挂载点不一致（{previous} vs {parent}）"))

    findings.extend(_validate_edges(normalized, edges))
    findings.extend(_validate_no_cross_branch_merge(normalized, edges))
    findings.extend(_validate_input_templates(normalized, edges))
    return findings


def _validate_edges(nodes: Sequence[Dict[str, Any]], edges: Optional[Iterable[Any]],
                    ) -> List[DefinitionFinding]:
    findings: List[DefinitionFinding] = []
    known = set(node_index(nodes))
    seen: set = set()

    for index, edge in enumerate(edges or []):
        ctx = f"edges[{index}]"
        if not isinstance(edge, dict):
            findings.append(DefinitionFinding("EDGE_NOT_OBJECT", f"{ctx} 需为对象"))
            continue

        source = _edge_endpoint(edge, "from")
        target = _edge_endpoint(edge, "to")
        when = _when_of(edge)

        if not source or not target:
            findings.append(DefinitionFinding(
                "EDGE_ENDPOINT_MISSING", f"{ctx} 必须同时提供 from / to"))
            continue

        for role, node_id in (("from", source), ("to", target)):
            if node_id not in known:
                findings.append(DefinitionFinding(
                    "EDGE_NODE_UNKNOWN", f"{ctx}.{role}='{node_id}' 不是已知 node_id"))

        if when not in WHEN_VALUES:
            findings.append(DefinitionFinding(
                "EDGE_WHEN_INVALID",
                f"{ctx}.when='{when}' 不在 {WHEN_VALUES} 内"))

        if source == target:
            findings.append(DefinitionFinding(
                "EDGE_SELF_LOOP", f"{ctx} 自环（from == to == '{source}'）"))

        key = (source, target, when)
        if key in seen:
            findings.append(DefinitionFinding(
                "EDGE_DUPLICATE", f"{ctx} 重复边 {source} → {target} (when={when})"))
        seen.add(key)

    return findings


def _validate_no_cross_branch_merge(nodes: Sequence[Dict[str, Any]],
                                    edges: Optional[Iterable[Any]],
                                    ) -> List[DefinitionFinding]:
    """非通用 DAG 断言：入边 >1 时，来源必须同属一个分支块。"""
    findings: List[DefinitionFinding] = []
    if not edges:
        return findings

    index = node_index(nodes)
    sources_by_target: Dict[str, List[str]] = {}
    for edge in edges:
        target = _edge_endpoint(edge, "to")
        source = _edge_endpoint(edge, "from")
        if target in index and source in index:
            bucket = sources_by_target.setdefault(target, [])
            if source not in bucket:
                bucket.append(source)

    for target, sources in sources_by_target.items():
        if len(sources) <= 1:
            continue
        groups = {group_of(index[s]) for s in sources}
        if len(groups) == 1 and "" not in groups:
            continue  # 同一分支块内合并：允许
        findings.append(DefinitionFinding(
            "MULTI_PARENT_NOT_ALLOWED",
            f"node '{target}' 有多条入边 {sorted(sources)}，但来源不属同一分支块"
            f"（非法：通用 DAG 的跨块合并）"))
    return findings


def _validate_input_templates(nodes: Sequence[Dict[str, Any]],
                              edges: Optional[Iterable[Any]],
                              ) -> List[DefinitionFinding]:
    """S2 发布期闸门：`meta.inputs_template` 引用必须指向直接上游。"""
    findings: List[DefinitionFinding] = []
    upstream = {
        target: {item["from"] for item in items}
        for target, items in incoming_edges(nodes, edges).items()
    }
    for node in nodes:
        meta = node.get("meta")
        if not isinstance(meta, dict) or "inputs_template" not in meta:
            continue
        node_id = node_id_of(node)
        template = meta.get("inputs_template")
        if not isinstance(template, dict):
            findings.append(DefinitionFinding(
                "INPUT_TEMPLATE_INVALID",
                f"node '{node_id}' 的 meta.inputs_template 需为对象"))
            continue
        for key, value in template.items():
            if not isinstance(key, str) or not key.strip():
                findings.append(DefinitionFinding(
                    "INPUT_TEMPLATE_INVALID",
                    f"node '{node_id}' 的 inputs_template 键必须为非空字符串"))
                continue
            if not isinstance(value, str):
                continue  # 字面量（数字 / 布尔 / 对象）原样注入
            refs = placeholder_refs(value)
            if refs is None:
                findings.append(DefinitionFinding(
                    "INPUT_TEMPLATE_INVALID",
                    f"node '{node_id}' inputs_template['{key}'] 引用语法非法"
                    "（仅支持 {{run.inputs.<path>}} / {{<node_id>.outputs.<path>}}）"))
                continue
            allowed = upstream.get(node_id, set())
            for ref_node, path in refs:
                if ref_node is not None and ref_node not in allowed:
                    findings.append(DefinitionFinding(
                        "INPUT_TEMPLATE_INVALID",
                        f"node '{node_id}' inputs_template['{key}'] 引用 "
                        f"'{ref_node}.outputs.{path}'，但 '{ref_node}' 不是直接上游"))
    return findings


def assert_definition(nodes: Any, edges: Optional[Iterable[Any]] = None) -> int:
    """校验失败抛 WorkflowDefinitionError；通过返回节点数。"""
    findings = validate_definition(nodes, edges)
    if findings:
        raise WorkflowDefinitionError(findings)
    return len(nodes)
