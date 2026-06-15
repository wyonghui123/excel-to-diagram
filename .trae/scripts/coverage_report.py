#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
业务规则覆盖率报告 (T-014)
============================

扫描:
  - .trae/specs/_business_rules/_index.json  (业务规则索引)
  - e2e/business-flow/**/*.spec.js            (业务流 spec)
  - e2e/screenplay/**/*.js                    (业务断言调用)

输出:
  - .trae/specs/_traceability/coverage.json   (机器可读)
  - .trae/state/coverage.html                  (IDE preview 报告)
  - .trae/state/coverage.md                    (Markdown 摘要)

用法:
    python .trae/scripts/coverage_report.py
    python .trae/scripts/coverage_report.py --json
    python .trae/scripts/coverage_report.py --html-only
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_RULES_INDEX = Path(".trae/specs/_business_rules/_index.json")
DEFAULT_SPECS_GLOB = "e2e/business-flow/**/*.spec.js"
DEFAULT_SCREENPLAY_GLOB = "e2e/screenplay/**/*.js"
DEFAULT_OUTPUT_DIR = Path(".trae/state")
DEFAULT_TRACEABILITY_DIR = Path(".trae/specs/_traceability")


# ---------------------------------------------------------------------------
# 1. 加载业务规则
# ---------------------------------------------------------------------------

def load_rules_index(path: Path) -> dict:
    """加载业务规则索引"""
    if not path.exists():
        return {"total_rules": 0, "objects": []}
    return json.loads(path.read_text(encoding="utf-8"))


def get_all_rule_ids(index: dict) -> set:
    """获取所有业务规则 ID"""
    rule_ids = set()
    for obj in index.get("objects", []):
        for rid in obj.get("rule_ids", []):
            rule_ids.add(rid)
    return rule_ids


# ---------------------------------------------------------------------------
# 2. 扫描业务流 spec
# ---------------------------------------------------------------------------

def scan_specs(glob_pattern: str) -> dict:
    """扫描业务流 spec,提取 ruleId 引用"""
    referenced = {}  # {ruleId: [spec_files]}
    spec_files = list(Path(".").glob(glob_pattern))

    # 匹配 BusinessRuleAssertor.assertRule('BR-...', ...) 调用
    rule_pattern = re.compile(
        r"BusinessRuleAssertor\.assertRule\(\s*['\"](BR-[a-zA-Z0-9_-]+)['\"]"
    )

    for spec_file in spec_files:
        try:
            content = spec_file.read_text(encoding="utf-8")
        except Exception:
            continue
        for match in rule_pattern.finditer(content):
            rule_id = match.group(1)
            if rule_id not in referenced:
                referenced[rule_id] = []
            referenced[rule_id].append(str(spec_file))

    return {
        "spec_files": [str(f) for f in spec_files],
        "referenced": referenced,
        "referenced_count": len(referenced),
    }


# ---------------------------------------------------------------------------
# 3. 计算覆盖率
# ---------------------------------------------------------------------------

def compute_coverage(rules_index: dict, scan_result: dict) -> dict:
    """计算业务规则覆盖率"""
    all_rule_ids = get_all_rule_ids(rules_index)
    referenced = set(scan_result["referenced"].keys())
    uncovered = all_rule_ids - referenced
    covered = all_rule_ids & referenced

    total = len(all_rule_ids)
    covered_count = len(covered)
    coverage_pct = (covered_count / total * 100) if total > 0 else 0

    # 按 object 分组
    by_object = []
    for obj in rules_index.get("objects", []):
        obj_covered = []
        obj_uncovered = []
        for rid in obj.get("rule_ids", []):
            if rid in referenced:
                obj_covered.append(rid)
            else:
                obj_uncovered.append(rid)
        obj_total = len(obj.get("rule_ids", []))
        obj_pct = (len(obj_covered) / obj_total * 100) if obj_total > 0 else 0
        by_object.append({
            "object_id": obj["object_id"],
            "object_name": obj["object_name"],
            "total_rules": obj_total,
            "covered_rules": len(obj_covered),
            "uncovered_rules": len(obj_uncovered),
            "coverage_pct": round(obj_pct, 1),
            "uncovered": obj_uncovered,
        })

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_rules": total,
        "covered_rules": covered_count,
        "uncovered_rules": total - covered_count,
        "coverage_pct": round(coverage_pct, 1),
        "target_pct": 80,  # NFR-004
        "target_met": coverage_pct >= 80,
        "by_object": by_object,
        "uncovered_list": sorted(uncovered),
        "spec_files": scan_result["spec_files"],
    }


# ---------------------------------------------------------------------------
# 4. 输出 HTML 报告
# ---------------------------------------------------------------------------

def generate_html(coverage: dict) -> str:
    """生成 HTML 报告 (IDE preview)"""
    pct = coverage["coverage_pct"]
    target = coverage["target_pct"]
    color = "#28a745" if pct >= target else "#dc3545"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>业务规则覆盖率报告</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 20px; background: #f5f7fa; }}
  .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 24px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  h1 {{ margin: 0 0 8px; }}
  .meta {{ color: #666; font-size: 12px; margin-bottom: 24px; }}
  .summary {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 16px; margin: 20px 0; }}
  .card {{ padding: 16px; background: #f8f9fa; border-radius: 6px; border-left: 4px solid #007bff; }}
  .card.coverage {{ border-left-color: {color}; }}
  .card .num {{ font-size: 32px; font-weight: 600; color: {color}; }}
  .card .label {{ font-size: 12px; color: #666; margin-top: 4px; }}
  .progress {{ background: #e9ecef; height: 24px; border-radius: 12px; overflow: hidden; margin: 12px 0; }}
  .progress-bar {{ background: {color}; height: 100%; line-height: 24px; color: white; text-align: center; font-size: 12px; transition: width 0.3s; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 24px; font-size: 14px; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #e9ecef; }}
  th {{ background: #f8f9fa; font-weight: 600; color: #495057; }}
  tr:hover {{ background: #f8f9fa; }}
  .badge {{ padding: 2px 8px; border-radius: 12px; font-size: 12px; color: white; }}
  .badge.green {{ background: #28a745; }}
  .badge.red {{ background: #dc3545; }}
  .badge.yellow {{ background: #ffc107; color: black; }}
  .uncovered {{ margin-top: 24px; padding: 16px; background: #fff3cd; border-radius: 6px; }}
  .uncovered h3 {{ margin: 0 0 8px; color: #856404; }}
  .uncovered code {{ background: #fff; padding: 2px 6px; border-radius: 3px; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <h1>📊 业务规则覆盖率报告</h1>
  <div class="meta">生成时间: {coverage['generated_at']} | Spec v2.0 | FR-012/FR-022</div>

  <div class="summary">
    <div class="card">
      <div class="num">{coverage['total_rules']}</div>
      <div class="label">总业务规则</div>
    </div>
    <div class="card">
      <div class="num">{coverage['covered_rules']}</div>
      <div class="label">已覆盖规则</div>
    </div>
    <div class="card">
      <div class="num">{coverage['uncovered_rules']}</div>
      <div class="label">未覆盖规则</div>
    </div>
    <div class="card coverage">
      <div class="num">{pct}%</div>
      <div class="label">覆盖率 (目标 ≥ {target}%)</div>
    </div>
  </div>

  <div class="progress">
    <div class="progress-bar" style="width: {pct}%;">{pct}%</div>
  </div>

  <h2>按业务对象分组</h2>
  <table>
    <thead>
      <tr>
        <th>对象</th>
        <th>规则总数</th>
        <th>已覆盖</th>
        <th>未覆盖</th>
        <th>覆盖率</th>
        <th>状态</th>
      </tr>
    </thead>
    <tbody>
"""

    # 按覆盖率排序
    by_object_sorted = sorted(coverage["by_object"], key=lambda x: -x["coverage_pct"])
    for obj in by_object_sorted:
        obj_pct = obj["coverage_pct"]
        if obj_pct >= 80:
            badge = '<span class="badge green">达成</span>'
        elif obj_pct >= 50:
            badge = '<span class="badge yellow">部分</span>'
        elif obj_pct == 0:
            badge = '<span class="badge red">无覆盖</span>'
        else:
            badge = '<span class="badge yellow">不足</span>'

        html += f"""      <tr>
        <td><b>{obj['object_name']}</b> <small>({obj['object_id']})</small></td>
        <td>{obj['total_rules']}</td>
        <td>{obj['covered_rules']}</td>
        <td>{obj['uncovered_rules']}</td>
        <td>{obj_pct}%</td>
        <td>{badge}</td>
      </tr>
"""

    html += """    </tbody>
  </table>
"""

    if coverage["uncovered_list"]:
        html += f"""
  <div class="uncovered">
    <h3>⚠️ 未覆盖的业务规则 ({len(coverage['uncovered_list'])} 条)</h3>
    <p>建议: 在 chat 中说 <code>派生出 XXX 业务流测试</code> 来补全覆盖</p>
    <ul>
"""
        for rid in coverage["uncovered_list"][:20]:  # 只显示前 20
            html += f"      <li><code>{rid}</code></li>\n"
        if len(coverage["uncovered_list"]) > 20:
            html += f"      <li><em>... 及其他 {len(coverage['uncovered_list']) - 20} 条</em></li>\n"
        html += """    </ul>
  </div>
"""

    html += f"""
  <h2>📁 业务流 Spec 清单</h2>
  <ul>
"""
    for spec in coverage["spec_files"]:
        html += f"    <li><code>{spec}</code></li>\n"

    html += f"""
  </ul>

  <div class="meta" style="margin-top: 32px;">
    <p>📋 <b>修复建议</b>:</p>
    <ul>
      <li>未覆盖规则: 在 TRAE IDE chat 中说 <code>/biz-test &lt;object&gt;</code> 触发业务流生成</li>
      <li>低覆盖率对象: 优先 <code>派生出业务流测试</code> 补全</li>
      <li>已达成目标: 持续监控,新规则需补测试</li>
    </ul>
  </div>
</div>
</body>
</html>
"""
    return html


def generate_markdown(coverage: dict) -> str:
    """生成 Markdown 摘要"""
    md = f"""# 业务规则覆盖率报告

> **生成时间**: {coverage['generated_at']}
> **Spec**: v2.0 (FR-012/FR-022)
> **目标**: ≥ {coverage['target_pct']}%

## 概览

| 指标 | 数值 |
|------|------|
| 总业务规则 | **{coverage['total_rules']}** |
| 已覆盖 | {coverage['covered_rules']} |
| 未覆盖 | {coverage['uncovered_rules']} |
| **覆盖率** | **{coverage['coverage_pct']}%** |
| 目标达成 | {'✅ 是' if coverage['target_met'] else '❌ 否'} |

## 按业务对象

| 对象 | 规则 | 已覆盖 | 覆盖率 | 状态 |
|------|------|--------|--------|------|
"""
    by_object_sorted = sorted(coverage["by_object"], key=lambda x: -x["coverage_pct"])
    for obj in by_object_sorted:
        status = "✅" if obj["coverage_pct"] >= 80 else ("⚠️" if obj["coverage_pct"] >= 50 else "❌")
        md += f"| {obj['object_name']} ({obj['object_id']}) | {obj['total_rules']} | {obj['covered_rules']} | {obj['coverage_pct']}% | {status} |\n"

    if coverage["uncovered_list"]:
        md += f"\n## ⚠️ 未覆盖规则 (Top 20)\n\n"
        for rid in coverage["uncovered_list"][:20]:
            md += f"- `{rid}`\n"

    md += f"""
## 📁 业务流 Spec ({len(coverage['spec_files'])} 个)

"""
    for spec in coverage["spec_files"]:
        md += f"- `{spec}`\n"

    return md


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="业务规则覆盖率报告")
    parser.add_argument("--rules-index", type=Path, default=DEFAULT_RULES_INDEX)
    parser.add_argument("--specs-glob", default=DEFAULT_SPECS_GLOB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--json", action="store_true", help="仅输出 JSON")
    parser.add_argument("--html-only", action="store_true", help="仅生成 HTML")
    parser.add_argument("--md-only", action="store_true", help="仅生成 Markdown")
    args = parser.parse_args()

    # 加载数据
    rules_index = load_rules_index(args.rules_index)
    scan_result = scan_specs(args.specs_glob)
    coverage = compute_coverage(rules_index, scan_result)

    if args.json:
        print(json.dumps(coverage, ensure_ascii=False, indent=2))
        return

    # 写 traceability
    traceability_path = DEFAULT_TRACEABILITY_DIR / "coverage.json"
    traceability_path.parent.mkdir(parents=True, exist_ok=True)
    traceability_path.write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✓ JSON: {traceability_path}")

    if not args.md_only:
        # 写 HTML
        args.output_dir.mkdir(parents=True, exist_ok=True)
        html_path = args.output_dir / "coverage.html"
        html_path.write_text(generate_html(coverage), encoding="utf-8")
        print(f"✓ HTML: {html_path}")

    if not args.html_only:
        # 写 Markdown
        md_path = args.output_dir / "coverage.md"
        md_path.write_text(generate_markdown(coverage), encoding="utf-8")
        print(f"✓ MD:   {md_path}")

    # 汇总
    print(f"\n📊 总计: {coverage['total_rules']} 规则, "
          f"已覆盖 {coverage['covered_rules']} ({coverage['coverage_pct']}%), "
          f"目标 {coverage['target_pct']}%, "
          f"{'✅ 达成' if coverage['target_met'] else '❌ 未达成'}")


if __name__ == "__main__":
    main()
