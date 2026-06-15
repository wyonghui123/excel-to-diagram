#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PM 边界 case 注入器 (T-v3-4)
================================

PM/BA 通过 chat 标注的边界 case 会写入此文件。
然后跑这个脚本会:
  1. 从 .trae/specs/_business_rules/_pm_boundary.yaml 读取标注
  2. 派生 PM 边界 case 为业务规则
  3. 追加到对应对象的 _business_rules/<obj>.yaml
  4. 更新 _index.json

PM 标注格式 (.trae/specs/_business_rules/_pm_boundary.yaml):
  - object: product
    boundary_cases:
      - id: PM-product-001
        title: 产品名包含 emoji 应拒绝
        rule_type: custom
        severity: error
        priority: P1

用法:
    python .trae/scripts/inject_pm_boundaries.py --dry-run
    python .trae/scripts/inject_pm_boundaries.py --apply
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required", file=sys.stderr)
    sys.exit(1)


DEFAULT_BOUNDARY_FILE = Path(".trae/specs/_business_rules/_pm_boundary.yaml")
DEFAULT_OUTPUT_DIR = Path(".trae/specs/_business_rules")


def load_boundary_cases(file_path: Path) -> list:
    """加载 PM 边界 case 标注"""
    if not file_path.exists():
        return []
    return yaml.safe_load(file_path.read_text(encoding="utf-8"))


def convert_to_rules(boundary_cases: list) -> dict:
    """将 PM 边界 case 转换为业务规则格式"""
    result = {}
    for case in boundary_cases:
        obj_id = case.get("object")
        if not obj_id:
            continue
        if obj_id not in result:
            result[obj_id] = []
        for bc in case.get("boundary_cases", []):
            rule = {
                "id": f"BR-{obj_id}-PM-{bc['id']}",
                "type": "pm_boundary",
                "subtype": bc.get("rule_type", "custom"),
                "object": obj_id,
                "title": bc.get("title", ""),
                "severity": bc.get("severity", "warning"),
                "priority": bc.get("priority", "P2"),
                "source": f"pm:boundary:{bc['id']}",
                "derived_scenarios": [
                    {
                        "id": f"T_{obj_id.upper()}_PM_{bc['id'].upper()}_001",
                        "title": bc.get("title", ""),
                        "priority": bc.get("priority", "P2"),
                        "assertion": f"BusinessRuleAssertor.assertRule('BR-{obj_id}-PM-{bc['id']}', {{ trigger: 'pm.boundary' }})",
                    },
                ],
            }
            result[obj_id].append(rule)
    return result


def main():
    parser = argparse.ArgumentParser(description="PM 边界 case 注入器")
    parser.add_argument("--dry-run", action="store_true", help="仅预览,不应用")
    parser.add_argument("--apply", action="store_true", help="应用变更")
    parser.add_argument("--boundary-file", type=Path, default=DEFAULT_BOUNDARY_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        args.dry_run = True

    cases = load_boundary_cases(args.boundary_file)
    if not cases:
        print("INFO: 没有 PM 边界 case 配置")
        return

    rules_by_obj = convert_to_rules(cases)
    total_new = sum(len(r) for r in rules_by_obj.values())

    print(f"📋 加载 {len(cases)} 个 PM 标注对象,共 {total_new} 条边界 case")
    for obj_id, rules in rules_by_obj.items():
        print(f"  - {obj_id}: {len(rules)} 条")

    if args.dry_run:
        print("\n[DRY-RUN] 不会修改文件")
        return

    # 写入 YAML
    for obj_id, rules in rules_by_obj.items():
        output_path = args.output_dir / f"{obj_id}.pm-boundary.yaml"
        content = {
            "object": obj_id,
            "source": "pm_boundary",
            "total_rules": len(rules),
            "rules": rules,
        }
        output_path.write_text(
            yaml.safe_dump(content, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        print(f"✓ {obj_id}: {len(rules)} pm rules → {output_path}")

    # 更新 _index.json
    index_path = args.output_dir / "_index.json"
    if index_path.exists():
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        for obj_id, rules in rules_by_obj.items():
            obj_entry = next((o for o in idx["objects"] if o["object_id"] == obj_id), None)
            if obj_entry:
                for r in rules:
                    if r["id"] not in obj_entry["rule_ids"]:
                        obj_entry["rule_ids"].append(r["id"])
                        obj_entry["rule_count"] = len(obj_entry["rule_ids"])
        idx["total_rules"] = sum(o["rule_count"] for o in idx["objects"])
        index_path.write_text(
            json.dumps(idx, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n✓ 更新 _index.json: 总规则 {idx['total_rules']}")


if __name__ == "__main__":
    main()
