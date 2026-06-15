#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
服务层业务逻辑扫描器 v3 (T-v3-1)
==================================

从 meta/services/ 和 meta/core/ 扫描业务规则:

扫描模式:
  1. raise 异常 → 业务规则(不允许)
  2. return False → 业务规则(不通过)
  3. if not X: return ... → 业务规则(校验)
  4. conflict_strategy → 业务规则(冲突处理)
  5. assert X → 业务规则(断言)
  6. raise ValueError → 业务规则(参数无效)
  7. abort/cancel → 业务规则(取消)
  8. permission check → 业务规则(权限)

输出: .trae/specs/_business_rules/<object>.service-rules.yaml

用法:
    python .trae/scripts/discover_business_rules_v3.py --all
    python .trae/scripts/discover_business_rules_v3.py --object product
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Iterable

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required", file=sys.stderr)
    sys.exit(1)


DEFAULT_SERVICES_DIR = Path("meta/services")
DEFAULT_CORE_DIR = Path("meta/core")
DEFAULT_OUTPUT_DIR = Path(".trae/specs/_business_rules")

# 业务规则模式
RULE_PATTERNS = {
    "raise_exception": re.compile(r"raise\s+(HTTPException|BadRequest|Forbidden|ValidationError|Exception)\(([^)]+)\)"),
    "return_false": re.compile(r"return\s+False\b"),
    "return_error": re.compile(r"return\s+.*?['\"]error['\"]|error_message"),
    "if_not_return": re.compile(r"if\s+not\s+(\w+).*?:\s*return"),
    "assert_check": re.compile(r"assert\s+(.*?)(?=,|$|\n)"),
    "conflict_strategy": re.compile(r"conflict_strategy\s*[=:]?\s*['\"](\w+)['\"]"),
    "permission_check": re.compile(r"(check_permission|check_authorization|require_permission|has_permission)\("),
    "abort_cancel": re.compile(r"\.(abort|cancel|rollback|undo)\("),
    "validation": re.compile(r"validate_(\w+)\("),
    "guard": re.compile(r"(_check_|_guard_|_validate_)(\w+)\("),
}


def extract_rules_from_file(file_path: Path) -> list:
    """从单个 Python 文件中提取业务规则"""
    rules = []
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return rules

    # 提取关联的对象 (从文件路径推断)
    rel_path = str(file_path).replace("\\", "/")

    # 业务对象 -> 业务规则映射
    obj_mapping = {
        "product": "product",
        "version": "version",
        "domain": "domain",
        "sub_domain": "sub_domain",
        "service_module": "service_module",
        "business_object": "business_object",
        "relationship": "relationship",
        "enum": "enum_type",
        "user": "user",
        "user_group": "user_group",
        "permission": "permission",
        "role": "role",
        "audit": "audit_log",
        "annotation": "annotation",
    }

    detected_obj = None
    for keyword, obj_id in obj_mapping.items():
        if keyword in rel_path.lower():
            detected_obj = obj_id
            break

    if not detected_obj:
        return rules

    # 解析每行
    line_num = 0
    for line in content.split("\n"):
        line_num += 1
        for rule_type, pattern in RULE_PATTERNS.items():
            matches = pattern.findall(line)
            for m in matches:
                # 尝试从代码中识别业务对象
                code_lower = line.lower()
                line_obj = detected_obj
                for keyword, obj_id in obj_mapping.items():
                    if keyword in code_lower:
                        line_obj = obj_id
                        break
                rule_id = f"BR-{line_obj}-SRV-{rule_type.upper().replace('_', '-')}-{file_path.stem}-{line_num}"
                rules.append({
                    "id": rule_id,
                    "type": "service_logic",
                    "subtype": rule_type,
                    "object": line_obj,
                    "source": f"service:{file_path.name}:L{line_num}",
                    "code_snippet": line.strip()[:200],
                    "derived_scenarios": [
                        {
                            "id": f"T_{line_obj.upper()}_SRV_{rule_type.upper()}_{line_num}_001",
                            "title": f"服务层: {line.strip()[:80]}",
                            "priority": "P1",
                            "assertion": f"BusinessRuleAssertor.assertRule('{rule_id}', {{ trigger: 'service.{rule_type}' }})",
                        },
                    ],
                })
    return rules


def extract_rules_from_dir(dir_path: Path) -> dict:
    """扫描目录下所有 Python 文件"""
    if not dir_path.exists():
        return {}
    result = {}
    for py_file in dir_path.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        rules = extract_rules_from_file(py_file)
        if not rules:
            continue
        for rule in rules:
            obj = rule["object"]
            if obj not in result:
                result[obj] = []
            result[obj].append(rule)
    return result


def main():
    parser = argparse.ArgumentParser(description="服务层业务规则扫描器 v3")
    parser.add_argument("--object")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--services-dir", type=Path, default=DEFAULT_SERVICES_DIR)
    parser.add_argument("--core-dir", type=Path, default=DEFAULT_CORE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    if args.object:
        # 单对象模式
        all_rules = extract_rules_from_dir(args.services_dir)
        all_rules.update(extract_rules_from_dir(args.core_dir))
        rules = all_rules.get(args.object, [])
        result = {
            "object": args.object,
            "source": "service_layer",
            "total_rules": len(rules),
            "rules": rules,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.all:
        all_rules = {}
        all_rules.update(extract_rules_from_dir(args.services_dir))
        all_rules.update(extract_rules_from_dir(args.core_dir))

        total_new = 0
        for obj, rules in all_rules.items():
            if not rules:
                continue
            output_path = args.output_dir / f"{obj}.service-rules.yaml"
            content = {
                "object": obj,
                "source": "service_layer",
                "total_rules": len(rules),
                "rules": rules,
            }
            output_path.write_text(
                yaml.safe_dump(content, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            total_new += len(rules)
            print(f"✓ {obj}: {len(rules)} service rules → {output_path}")

        # 更新 _index.json
        index_path = args.output_dir / "_index.json"
        if index_path.exists():
            idx = json.loads(index_path.read_text(encoding="utf-8"))
            # 合并 service 规则
            for obj, rules in all_rules.items():
                service_rids = [r["id"] for r in rules]
                obj_entry = next((o for o in idx["objects"] if o["object_id"] == obj), None)
                if obj_entry:
                    # 追加
                    for rid in service_rids:
                        if rid not in obj_entry["rule_ids"]:
                            obj_entry["rule_ids"].append(rid)
                    obj_entry["rule_count"] = len(obj_entry["rule_ids"])
            idx["total_rules"] = sum(o["rule_count"] for o in idx["objects"])
            index_path.write_text(
                json.dumps(idx, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\n✓ 更新 _index.json: 总规则 {idx['total_rules']}")


if __name__ == "__main__":
    main()
