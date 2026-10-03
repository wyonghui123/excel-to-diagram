#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
规则编排 P0 审计（只读）
============================

用途：为「编排收口」方案提供 Step 0 实测证据
（方案见 docs/superpowers/specs/2026-10-03-rule-orchestration-ordering-and-propagation.md）

回答两个问题：
  Q1 存量 schema 里到底有没有「环」？（若有，加载期硬失败会拒掉哪些对象）
  Q2 「平铺 priority 顺序」与「数据流拓扑顺序」差异有多大？
     哪些规则会被两条路径重复覆盖？

纪律：
  - 纯只读：不修改任何 yaml / 源码，不写库；除非显式 --json 否则不落盘
  - 不改变运行期行为：本脚本独立运行，不被生产代码引用

用法：
  python .trae/scripts/audit_rule_orchestration.py
  python .trae/scripts/audit_rule_orchestration.py --json .tmp_orchestration_audit.json
  python .trae/scripts/audit_rule_orchestration.py --fail-on-findings
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from meta.core.models import MetaObject                      # noqa: E402
from meta.core.models_enums import RuleTrigger, RuleType     # noqa: E402
from meta.core.rule_chain import RuleDependencyAnalyzer     # noqa: E402
from meta.core.rule_provider import get_rule_provider        # noqa: E402
from meta.core.yaml_loader import load_yaml_directory        # noqa: E402


def schema_dirs() -> List[Path]:
    """平台 schema 目录 + 各应用 schema 目录"""
    dirs = [ROOT / "meta" / "schemas"]
    apps_dir = ROOT / "apps"
    if apps_dir.exists():
        dirs.extend(sorted(p for p in apps_dir.glob("*/schemas") if p.is_dir()))
    return dirs


def load_all() -> Tuple[List[Tuple[str, MetaObject]], List[str]]:
    """加载全部对象；返回 [(来源目录, 对象)] 与告警列表"""
    records: List[Tuple[str, MetaObject]] = []
    warnings: List[str] = []
    for d in schema_dirs():
        if not d.exists():
            continue
        try:
            objs = load_yaml_directory(str(d))
        except Exception as e:  # noqa: BLE001 - 审计脚本，任何加载异常都只记录不中断
            warnings.append("目录加载失败 {0}: {1}".format(d, e))
            continue
        for obj in objs:
            if not getattr(obj, "id", None):
                warnings.append("{0} 中存在缺少 id 的对象，已跳过".format(d))
                continue
            records.append((str(d.relative_to(ROOT)), obj))
    return records, warnings


def analyze_object(obj: MetaObject) -> Dict[str, Any]:
    """对单个对象做环扫描 + 两套顺序对比（只读）"""
    rules = get_rule_provider().get_rules(obj)
    graph = RuleDependencyAnalyzer.analyze(obj)
    cycle = RuleDependencyAnalyzer.detect_cycle(graph)
    # [G10 2026-10-03] topological_sort 现在遇环会抛 ValueError（不再静默返回残缺序列），
    # 审计脚本据此如实记录，避免脚本本身在"正是要检测的情形"下崩溃。
    try:
        topo_ids = RuleDependencyAnalyzer.topological_sort(graph)
        topo_error = None
    except ValueError as e:
        topo_ids = []
        topo_error = str(e)

    # 对拓扑链不可见的规则（rule_type 无对应节点，或类型不匹配）
    invisible = [
        {"id": getattr(r, "id", ""),
         "rule_type": getattr(getattr(r, "rule_type", None), "value", "?")}
        for r in rules if getattr(r, "id", "") not in graph.nodes
    ]

    per_trigger: Dict[str, Any] = {}
    for trig in RuleTrigger:
        # 镜像 RuleEngine.execute_rules 的选取口径：enabled + trigger 命中 + 排除 DEFAULT
        flat = [
            r for r in rules
            if trig in (getattr(r, "triggers", None) or [])
            and getattr(r, "enabled", True)
            and getattr(r, "rule_type", None) != RuleType.DEFAULT
        ]
        flat_ids = [r.id for r in sorted(flat, key=lambda r: r.priority)]

        topo_ids_t = [
            nid for nid in topo_ids
            if trig in (getattr(graph.nodes[nid].rule, "triggers", None) or [])
            and getattr(graph.nodes[nid].rule, "enabled", True)
        ]

        if not flat_ids and not topo_ids_t:
            continue

        flat_set, topo_set = set(flat_ids), set(topo_ids_t)
        per_trigger[trig.value] = {
            "flat": flat_ids,
            "topo": topo_ids_t,
            "same_sequence": flat_ids == topo_ids_t,
            "overlap": [i for i in flat_ids if i in topo_set],
            "flat_only": [i for i in flat_ids if i not in topo_set],
            "topo_only": [i for i in topo_ids_t if i not in flat_set],
        }

    return {
        "object_id": obj.id,
        "rule_count": len(rules),
        "graph_node_count": len(graph.nodes),
        "cycle": cycle,
        "topo_error": topo_error,
        "invisible_rules": invisible,
        "per_trigger": per_trigger,
    }


def _fmt(items: List[str]) -> str:
    return "[" + ", ".join(items) + "]" if items else "[]"


def main() -> int:
    parser = argparse.ArgumentParser(description="规则编排 P0 只读审计")
    parser.add_argument("--json", dest="json_path", default=None,
                        help="把完整结果写入指定 JSON 文件（默认不落盘）")
    parser.add_argument("--fail-on-findings", action="store_true",
                        help="发现环或顺序差异时以退出码 1 结束（默认恒为 0）")
    args = parser.parse_args()

    records, warnings = load_all()

    results: List[Dict[str, Any]] = []
    for src, obj in records:
        r = analyze_object(obj)
        r["source"] = src
        results.append(r)

    # ── Q1 环扫描 ────────────────────────────────────────────────
    cycled = [r for r in results if r["cycle"]]

    # ── Q2 两套顺序差异 ──────────────────────────────────────────
    with_rules = [r for r in results if r["rule_count"] > 0]
    # [2026-10-03 D7 复测] 口径拆分：此前把「两路都会跑（overlap）」也计入
    # 「顺序差异」，导致 tie-break 统一（D7）后计数仍虚高。
    # 现在：「顺序差异」只统计 same_sequence=False 的 trigger；「两路重叠」单列。
    order_diverged = []
    overlaps = []
    for r in with_rules:
        for trig, info in r["per_trigger"].items():
            if not info["same_sequence"]:
                order_diverged.append((r["object_id"], trig, info))
            if info["overlap"]:
                overlaps.append((r["object_id"], trig, info))

    # 重复执行只在链被调用的 trigger 上真实发生：当前 compute() 固定以 BEFORE_SAVE 调用
    dup_real = [(o, t, i) for (o, t, i) in overlaps
                if t == RuleTrigger.BEFORE_SAVE.value]

    invisible_total = [(r["object_id"], r["invisible_rules"]) for r in results
                       if r["invisible_rules"]]

    # ── 报表 ─────────────────────────────────────────────────────
    print("=" * 72)
    print("规则编排 P0 审计（只读）")
    print("=" * 72)
    print("扫描目录: " + ", ".join(str(d.relative_to(ROOT)) for d in schema_dirs() if d.exists()))
    print("对象总数: {0}   其中有规则的对象: {1}".format(len(results), len(with_rules)))
    if warnings:
        print("\n[告警] {0} 条".format(len(warnings)))
        for w in warnings:
            print("  - " + w)

    print()
    print("-" * 72)
    print("Q1 环扫描（决定「加载期硬失败」能否直接上）")
    print("-" * 72)
    if not cycled:
        print("结果：0 个对象存在环 → 加载期硬失败不会拒掉任何存量 schema。")
    else:
        print("结果：{0} 个对象存在环：".format(len(cycled)))
        for r in cycled:
            print("  - {0}（来源 {1}）".format(r["object_id"], r["source"]))
            print("      环路径: {0}".format(" → ".join(r["cycle"])))

    topo_failed = [r for r in results if r.get("topo_error")]
    print("拓扑排序报错（G10 硬约束生效）: {0} 个对象".format(len(topo_failed)))
    for r in topo_failed:
        print("  - {0}: {1}".format(r["object_id"], r["topo_error"]))

    print()
    print("-" * 72)
    print("Q2 两套顺序差异（平铺 priority  vs  数据流拓扑）")
    print("-" * 72)
    if not order_diverged:
        print("结果：所有有规则的 trigger 上，两套顺序完全一致（无顺序差异）。")
    for oid, trig, info in order_diverged:
        print("  * {0} / {1}".format(oid, trig))
        print("      flat: {0}".format(_fmt(info["flat"])))
        print("      topo: {0}".format(_fmt(info["topo"])))
        if info["overlap"]:
            print("      overlap(两路都会跑): {0}".format(_fmt(info["overlap"])))
        if info["flat_only"]:
            print("      flat_only(链看不到): {0}".format(_fmt(info["flat_only"])))
        if info["topo_only"]:
            print("      topo_only(平铺看不到): {0}".format(_fmt(info["topo_only"])))
    if overlaps:
        print()
        print("  [附] 顺序一致但两路重叠的 trigger（顺序收口后需避免重复执行）: {0} 处".format(
            len(overlaps)))
        for oid, trig, info in overlaps:
            print("      - {0} / {1}: {2}".format(oid, trig, _fmt(info["overlap"])))
        # [G3 修复 2026-10-03] compute() 已不再调用 ImplicitRuleChainExecutor（链只用于
        # 「取顺序」，执行体是平铺各类型执行器），故生产路径上的「两路重复执行」已消除。
        # 本指标保留为**设计探针**：仅当链被重新接回执行路径时需要重新评估。
        print("      （注：G3 修复后 compute() 不再跑链，生产路径已无两路重复；本项为设计探针）")

    print()
    print("-" * 72)
    print("重复执行风险（同一 trigger 被平铺与链各跑一次）")
    print("-" * 72)
    print("说明：链当前仅由 compute() 以 BEFORE_SAVE 调用，故只有 before_save 是真实重复。")
    if not dup_real:
        print("结果：before_save 上无重复覆盖。")
    for oid, trig, info in dup_real:
        print("  - {0} / {1}: {2}".format(oid, trig, _fmt(info["overlap"])))

    print()
    print("-" * 72)
    print("未进入拓扑链的规则（rule_type 无对应节点，链对其不可见）")
    print("-" * 72)
    if not invisible_total:
        print("结果：无（所有规则都已建图）。")
    for oid, items in invisible_total:
        print("  - {0}: {1}".format(
            oid, _fmt(["{0}({1})".format(i["id"], i["rule_type"]) for i in items])))

    print()
    print("=" * 72)
    print("汇总: 环 {0} | 拓扑报错 {1} | 顺序差异 {2} 处 | 两路重叠 {3} 处 | 真实重复覆盖 {4} 处 | 未建图规则对象 {5} 个".format(
        len(cycled), len(topo_failed), len(order_diverged), len(overlaps),
        len(dup_real), len(invisible_total)))
    print("=" * 72)

    if args.json_path:
        payload = {
            "schema_dirs": [str(d.relative_to(ROOT)) for d in schema_dirs() if d.exists()],
            "object_count": len(results),
            "objects_with_rules": len(with_rules),
            "warnings": warnings,
            "cycles": [{"object_id": r["object_id"], "source": r["source"], "cycle": r["cycle"]}
                       for r in cycled],
            "topo_errors": [{"object_id": r["object_id"], "error": r["topo_error"]}
                            for r in topo_failed],
            "order_diverged": [{"object_id": o, "trigger": t, "info": i}
                               for (o, t, i) in order_diverged],
            "overlaps": [{"object_id": o, "trigger": t, "overlap": i["overlap"]}
                         for (o, t, i) in overlaps],
            "duplicate_overlap_before_save": [
                {"object_id": o, "trigger": t, "overlap": i["overlap"]} for (o, t, i) in dup_real],
            "invisible_rules": [{"object_id": o, "rules": i} for (o, i) in invisible_total],
            "objects": results,
        }
        Path(args.json_path).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print("JSON 已写入: {0}".format(args.json_path))

    if args.fail_on_findings and (cycled or order_diverged):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
