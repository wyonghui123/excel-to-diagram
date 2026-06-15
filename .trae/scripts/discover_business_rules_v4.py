#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跨对象组合规则推导器 v4 (T-v3-3)
====================================

从 schema + 业务对象间的关系推导"组合业务规则",例如:
  - 创建产品 → 自动创建默认版本 (1:N)
  - 创建关系 → 必须 source/target 存在
  - 删除版本 → 子领域必须先清空
  - 创建用户 → 自动关联默认 user_group
  - 创建权限包 → 必须含至少 1 个权限

数据源:
  1. schema.relations (parent_child 1:N)
  2. schema.associations (composition)
  3. schema.dimension_bindings
  4. schema.hierarchy
  5. 业务对象间引用 (FK 反查)

用法:
    python .trae/scripts/discover_business_rules_v4.py --all
"""

import argparse
import json
from pathlib import Path
from typing import Iterable

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required", file=sys.stderr)
    sys.exit(1)


DEFAULT_SCHEMA_DIR = Path("meta/schemas")
DEFAULT_OUTPUT_DIR = Path(".trae/specs/_business_rules/_composite")


# 跨对象组合规则模式
COMPOSITE_PATTERNS = {
    "auto_create_child": {
        "description": "创建父对象时应自动创建默认子对象",
        "template": "创建{parent}时,应自动创建至少1个{child}",
        "priority": "P1",
    },
    "cascade_delete": {
        "description": "删除父对象时子对象应级联处理",
        "template": "删除{parent}时,{child}应级联删除或阻止",
        "priority": "P0",
    },
    "reference_integrity": {
        "description": "子对象必须引用已存在的父对象",
        "template": "{child}的{parent_field}必须引用已存在的{parent}",
        "priority": "P0",
    },
    "auto_owner_inherit": {
        "description": "子对象应继承父对象的 owner",
        "template": "{child}应继承{parent}的 owner 权限",
        "priority": "P1",
    },
    "scope_inherit": {
        "description": "子对象的可见性由父对象决定",
        "template": "{child}的可见性由{parent}的 visibility 决定",
        "priority": "P1",
    },
    "at_least_one": {
        "description": "聚合根应至少含 1 个子对象",
        "template": "{parent}应至少含1个{child}",
        "priority": "P2",
    },
    "uniqueness_within_parent": {
        "description": "子对象在父对象范围内唯一",
        "template": "{child}的{field}在{parent}范围内应唯一",
        "priority": "P0",
    },
    "sequential_codegen": {
        "description": "子对象 code 由父对象 code 派生",
        "template": "{child}的 code 应基于{parent}的 code 自动生成",
        "priority": "P1",
    },
    "audit_log_cascade": {
        "description": "父对象的 audit log 应包含子对象",
        "template": "删除{parent}时,audit log 应同时记录{child}的处理",
        "priority": "P2",
    },
    "permission_inherit_chain": {
        "description": "权限沿父链继承",
        "template": "对{child}的权限应通过{parent}链追溯",
        "priority": "P1",
    },
}


def find_relations(schema: dict) -> list:
    """提取关系定义"""
    rels = []
    for r in schema.get("relations", []):
        if isinstance(r, dict) and r.get("type") in ("parent_child", "composition"):
            rels.append({
                "type": r["type"],
                "target": r.get("target", ""),
                "cardinality": r.get("cardinality", ""),
                "source_key": r.get("source_key", ""),
            })
    # associations
    for a in schema.get("associations", []):
        if isinstance(a, dict) and a.get("type") in ("parent_child", "composition"):
            rels.append({
                "type": a["type"],
                "target": a.get("target_type", ""),
                "cardinality": "1:N",
                "source_key": a.get("source_key", ""),
            })
    return rels


def derive_composite_rules(obj_id: str, schema: dict, all_schemas: dict) -> list:
    """推导跨对象组合规则"""
    rules = []
    obj_name = schema.get("name", obj_id)
    rels = find_relations(schema)
    hierarchy = schema.get("hierarchy", {})

    for rel in rels:
        target = rel["target"]
        if target not in all_schemas:
            continue
        target_schema = all_schemas[target]
        target_name = target_schema.get("name", target)

        # 1. cascade_delete
        rules.append({
            "id": f"BR-{obj_id}-COMP-cascade-delete-{target}",
            "type": "composite",
            "subtype": "cascade_delete",
            "object": obj_id,
            "target": target,
            "description": f"删除{obj_name}时,{target_name}应级联处理 (cardinality={rel['cardinality']})",
            "source": f"derived:schema:{obj_id}.yaml+{target}.yaml",
            "derived_scenarios": [
                {
                    "id": f"T_{obj_id.upper()}_COMP_CASCADE_{target.upper()}_001",
                    "title": f"删除{obj_name}时,{target_name}应被级联处理",
                    "priority": "P0",
                    "assertion": f"BusinessRuleAssertor.assertRule('BR-{obj_id}-COMP-cascade-delete-{target}', {{ parent: 'xxx', expected: 'cascade' }})",
                },
            ],
        })

        # 2. reference_integrity
        rules.append({
            "id": f"BR-{target}-COMP-ref-integrity-{obj_id}",
            "type": "composite",
            "subtype": "reference_integrity",
            "object": target,
            "target": obj_id,
            "description": f"{target_name}的{rel['source_key']}必须引用已存在的{obj_name}",
            "source": f"derived:schema:{obj_id}.yaml:relations",
            "derived_scenarios": [
                {
                    "id": f"T_{target.upper()}_COMP_REF_{obj_id.upper()}_001",
                    "title": f"创建{target_name}时,引用已删除的{obj_name}应失败",
                    "priority": "P0",
                    "assertion": f"BusinessRuleAssertor.assertRule('BR-{target}-COMP-ref-integrity-{obj_id}', {{ invalid_ref: true, expected: 'error' }})",
                },
            ],
        })

        # 3. permission_inherit_chain
        rules.append({
            "id": f"BR-{target}-COMP-permission-inherit-{obj_id}",
            "type": "composite",
            "subtype": "permission_inherit_chain",
            "object": target,
            "target": obj_id,
            "description": f"对{target_name}的权限应通过{obj_name}链追溯",
            "source": f"derived:schema:{obj_id}.yaml:authorization",
            "derived_scenarios": [
                {
                    "id": f"T_{target.upper()}_COMP_PERM_{obj_id.upper()}_001",
                    "title": f"对{obj_name}有权限时,应自动获得{target_name}权限",
                    "priority": "P1",
                    "assertion": f"BusinessRuleAssertor.assertRule('BR-{target}-COMP-permission-inherit-{obj_id}', {{ parentAccess: true, expectedChildAccess: true }})",
                },
            ],
        })

        # 4. scope_inherit (visibility)
        fields = schema.get("fields", [])
        if isinstance(fields, list) and "visibility" in [f.get("id", "") for f in fields if isinstance(f, dict)]:
            rules.append({
                "id": f"BR-{target}-COMP-scope-inherit-{obj_id}",
                "type": "composite",
                "subtype": "scope_inherit",
                "object": target,
                "target": obj_id,
                "description": f"{target_name}的可见性由{obj_name}的 visibility 决定",
                "source": f"derived:schema:{obj_id}.yaml:fields[visibility]",
                "derived_scenarios": [
                    {
                        "id": f"T_{target.upper()}_COMP_SCOPE_{obj_id.upper()}_001",
                        "title": f"{obj_name}设为 private 时,{target_name}应同步受限",
                        "priority": "P1",
                        "assertion": f"BusinessRuleAssertor.assertRule('BR-{target}-COMP-scope-inherit-{obj_id}', {{ parentVisibility: 'private', expectedChildAccess: 'restricted' }})",
                },
            ],
        })

    # 5. hierarchy-derived
    if hierarchy.get("enabled"):
        level = hierarchy.get("level", 0)
        parent_field = hierarchy.get("parent_field")
        if parent_field and level > 0:
            # 跨层级组合规则
            rules.append({
                "id": f"BR-{obj_id}-COMP-hierarchy-path",
                "type": "composite",
                "subtype": "sequential_codegen",
                "object": obj_id,
                "description": f"{obj_name}的 hierarchy_path 应基于父链自动生成 (level={level})",
                "source": f"derived:schema:{obj_id}.yaml:hierarchy",
                "derived_scenarios": [
                    {
                        "id": f"T_{obj_id.upper()}_COMP_HIER_PATH_001",
                        "title": f"创建{obj_name}时 hierarchy_path 应基于父链派生",
                        "priority": "P2",
                        "assertion": f"BusinessRuleAssertor.assertRule('BR-{obj_id}-COMP-hierarchy-path', {{ parentPath: '...', expected: '.../...' }})",
                    },
                ],
            })

    return rules


def main():
    parser = argparse.ArgumentParser(description="跨对象组合规则推导器 v4")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--schema-dir", type=Path, default=DEFAULT_SCHEMA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    # 加载所有 schema
    all_schemas = {}
    for schema_path in sorted(args.schema_dir.glob("*.yaml")):
        if schema_path.name.startswith("_"):
            continue
        obj_id = schema_path.stem
        try:
            schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
            all_schemas[obj_id] = schema
        except Exception as e:
            print(f"WARN: Failed to load {schema_path}: {e}", file=sys.stderr)

    if args.all:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        all_composite = {"total_rules": 0, "rules": []}
        for obj_id, schema in all_schemas.items():
            rules = derive_composite_rules(obj_id, schema, all_schemas)
            if not rules:
                continue
            all_composite["total_rules"] += len(rules)
            all_composite["rules"].extend(rules)

        # 写文件
        output_path = args.output_dir / "_composite.yaml"
        output_path.write_text(
            yaml.safe_dump(all_composite, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        print(f"✓ 推导 {all_composite['total_rules']} 条跨对象组合规则")
        print(f"  → {output_path}")

        # 更新 _index.json
        index_path = args.output_dir.parent / "_index.json"
        if index_path.exists():
            idx = json.loads(index_path.read_text(encoding="utf-8"))
            # 添加 composite 规则
            for rule in all_composite["rules"]:
                obj_id = rule["object"]
                target = rule.get("target", "")
                # 添加到对象 entry
                obj_entry = next((o for o in idx["objects"] if o["object_id"] == obj_id), None)
                if obj_entry and rule["id"] not in obj_entry["rule_ids"]:
                    obj_entry["rule_ids"].append(rule["id"])
                    obj_entry["rule_count"] = len(obj_entry["rule_ids"])
                # 关联到 target 对象
                if target:
                    tgt_entry = next((o for o in idx["objects"] if o["object_id"] == target), None)
                    if tgt_entry and rule["id"] not in tgt_entry["rule_ids"]:
                        tgt_entry["rule_ids"].append(rule["id"])
                        tgt_entry["rule_count"] = len(tgt_entry["rule_ids"])
            idx["total_rules"] = sum(o["rule_count"] for o in idx["objects"])
            index_path.write_text(
                json.dumps(idx, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"✓ 更新 _index.json: 总规则 {idx['total_rules']}")


if __name__ == "__main__":
    main()
