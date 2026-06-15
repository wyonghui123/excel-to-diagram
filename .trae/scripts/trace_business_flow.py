#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
业务流双向追溯工具 (T-015)
============================

建立 spec.md ↔ business-flow.yaml ↔ spec.js ↔ business rules 的双向追溯

用法:
    python .trae/scripts/trace_business_flow.py --feat business-object-lifecycle
    python .trae/scripts/trace_business_flow.py --all
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_SPECS_DIR = Path(".trae/specs")
DEFAULT_OUTPUT_DIR = Path(".trae/specs/_traceability")


def parse_spec_md(spec_path: Path) -> dict:
    """解析 spec.md 头部的追溯标记"""
    if not spec_path.exists():
        return {}
    content = spec_path.read_text(encoding="utf-8")
    info = {
        "path": str(spec_path),
        "business_flow": None,
        "scenario_ids": [],
    }
    # 解析 `## business_flow: ...`
    m = re.search(r"^##\s+business_flow:\s*(\S+)", content, re.MULTILINE)
    if m:
        info["business_flow"] = m.group(1)
    # 解析 `<!-- scenario-id: T_BIZ_BO_001 -->`
    for sm in re.finditer(r"scenario-id:\s*(T_[A-Z_0-9]+)", content):
        info["scenario_ids"].append(sm.group(1))
    return info


def parse_business_flow_yaml(yaml_path: Path) -> dict:
    """解析 business-flow.yaml"""
    if not yaml_path.exists():
        return {}
    content = yaml_path.read_text(encoding="utf-8")
    info = {
        "path": str(yaml_path),
        "review_status": None,
        "actor": None,
        "goal": None,
        "tasks": [],
        "questions": [],
    }
    m = re.search(r"^review_status:\s*(\S+)", content, re.MULTILINE)
    if m:
        info["review_status"] = m.group(1)
    m = re.search(r"^actor:\s*(\S+)", content, re.MULTILINE)
    if m:
        info["actor"] = m.group(1)
    m = re.search(r"^goal:\s*['\"]?(.+?)['\"]?\s*$", content, re.MULTILINE)
    if m:
        info["goal"] = m.group(1)
    # tasks
    for tm in re.finditer(r"^\s*-\s*id:\s*(T_[A-Z_0-9]+)", content, re.MULTILINE):
        info["tasks"].append(tm.group(1))
    # questions/ruleId
    for qm in re.finditer(r"^\s*-\s*ruleId:\s*(BR-[a-zA-Z0-9_-]+)", content, re.MULTILINE):
        info["questions"].append(qm.group(1))
    return info


def find_spec_js(feat_name: str) -> list:
    """查找对应的 spec.js"""
    # 用脚本绝对路径反推项目根
    script_root = Path(__file__).resolve().parent
    project_root = script_root.parent.parent
    base = project_root / "e2e" / "business-flow"
    if not base.exists():
        return []

    # 简化: 用 iterdir + name contains (避免 WindowsPath glob 跨平台问题)
    all_files = [p for p in base.iterdir() if p.is_file() and p.name.endswith('.spec.js')]

    # 智能匹配: 优先精确前缀, 退到包含匹配, 再次退到取 feat 前 2 段
    candidates = [p for p in all_files if p.name.startswith(feat_name)]
    if not candidates:
        candidates = [p for p in all_files if feat_name in p.name]
    if not candidates:
        # 退到取 feat 前 2 段 (e.g. "product-version" 从 "product-version-management")
        parts = feat_name.split('-')
        for n in [3, 2, 1]:
            key = '-'.join(parts[:n])
            if len(key) >= 3:
                candidates = [p for p in all_files if p.name.startswith(key)]
                if candidates:
                    break

    return [str(c.relative_to(project_root)).replace('\\', '/') for c in candidates]


def build_trace(feat_name: str) -> dict:
    """构建单个 feat 的双向追溯"""
    spec_dir = DEFAULT_SPECS_DIR / feat_name
    spec_path = spec_dir / "spec.md"
    yaml_path = spec_dir / "business-flow.yaml"

    spec_info = parse_spec_md(spec_path)
    yaml_info = parse_business_flow_yaml(yaml_path)
    spec_js_files = find_spec_js(feat_name)

    # 解析 spec.js 中的 ruleId 引用
    rule_refs = []
    for spec_js in spec_js_files:
        content = Path(spec_js).read_text(encoding="utf-8")
        for m in re.finditer(r"BusinessRuleAssertor\.assertRule\(\s*['\"](BR-[a-zA-Z0-9_-]+)['\"]", content):
            rule_refs.append(m.group(1))

    return {
        "feat": feat_name,
        "spec_md": spec_info,
        "business_flow_yaml": yaml_info,
        "spec_js_files": spec_js_files,
        "rule_refs_in_spec_js": sorted(set(rule_refs)),
        "reverse_trace": {
            "rule_to_spec_js": sorted(set(rule_refs)),
            "yaml_to_spec_md": str(spec_path) if spec_path.exists() else None,
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def main():
    parser = argparse.ArgumentParser(description="业务流双向追溯")
    parser.add_argument("--feat", help="feat 名称")
    parser.add_argument("--all", action="store_true", help="扫描所有 feat")
    args = parser.parse_args()

    if not args.feat and not args.all:
        parser.print_help()
        sys.exit(1)

    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.feat:
        traces = [build_trace(args.feat)]
    else:
        # 扫描所有有 business-flow.yaml 的 feat
        traces = []
        for yaml_path in (DEFAULT_SPECS_DIR).glob("*/business-flow.yaml"):
            feat_name = yaml_path.parent.name
            traces.append(build_trace(feat_name))

    for trace in traces:
        feat = trace["feat"]
        output_path = DEFAULT_OUTPUT_DIR / f"{feat}.trace.json"
        output_path.write_text(
            json.dumps(trace, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"✓ {feat}: spec.md + business-flow.yaml + {len(trace['spec_js_files'])} spec.js + {len(trace['rule_refs_in_spec_js'])} rules → {output_path}")


if __name__ == "__main__":
    main()
