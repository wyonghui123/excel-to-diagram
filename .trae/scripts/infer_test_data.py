#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
业务流测试数据推演 (T-017 / FR-023)
====================================

从 schema.yaml 字段约束推演:
  - 有效数据
  - 无效数据
  - 边界值

借鉴 2026 业界"测试数据生成"实践,避免违反业务约束。

用法:
    python .trae/scripts/infer_test_data.py --object business_object
    python .trae/scripts/infer_test_data.py --all
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required", file=sys.stderr)
    sys.exit(1)


DEFAULT_SCHEMA_DIR = Path("meta/schemas")
DEFAULT_OUTPUT_DIR = Path(".trae/specs/_business_rules")


def infer_field(field_def: dict) -> dict:
    """推演单个字段的有效/无效/边界值"""
    result = {
        "valid": [],
        "invalid": [],
        "boundary": [],
    }
    ftype = field_def.get("type", "string")
    required = field_def.get("required", False)
    pattern = field_def.get("pattern")
    min_val = field_def.get("min") or field_def.get("minLength")
    max_val = field_def.get("max") or field_def.get("maxLength")
    enum = field_def.get("enum") or field_def.get("choices")

    if ftype == "string":
        # 有效值
        if pattern:
            # 简化: 用 pattern 字符串作示例
            result["valid"].append(f"符合 {pattern} 的示例")
        elif enum:
            result["valid"].extend([str(e) for e in enum[:3]])
        else:
            result["valid"].append("valid_string")

        # 无效值
        if required:
            result["invalid"].append("")  # 空字符串

        # 边界值
        if isinstance(max_val, int):
            result["boundary"].extend([
                "a" * (max_val + 1),  # 超出
                "a" * (max_val or 1),
            ])

    elif ftype in ("integer", "number"):
        # 有效值
        if min_val is not None and max_val is not None:
            mid = (min_val + max_val) // 2 if min_val and max_val else 0
            result["valid"].append(mid)
        else:
            result["valid"].append(0)

        # 边界
        if min_val is not None:
            result["boundary"].append(min_val - 1)  # 低于最小
        if max_val is not None:
            result["boundary"].append(max_val + 1)  # 高于最大

    elif ftype == "boolean":
        result["valid"].extend([True, False])

    return result


def infer_object(object_id: str, schema_dir: Path) -> dict:
    """推演对象的测试数据"""
    schema_path = schema_dir / f"{object_id}.yaml"
    if not schema_path.exists():
        return {}
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    fields = schema.get("fields", [])

    valid_data = {}
    invalid_data = {}
    boundary_data = {}

    for field in fields:
        if not isinstance(field, dict):
            continue
        fname = field.get("id", field.get("name", "unknown"))
        inference = infer_field(field)
        if inference["valid"]:
            valid_data[fname] = inference["valid"][0]
        if inference["invalid"]:
            invalid_data[fname] = inference["invalid"][0]
        if inference["boundary"]:
            boundary_data[fname] = inference["boundary"]

    return {
        "object_id": object_id,
        "valid_data": valid_data,
        "invalid_data": invalid_data,
        "boundary_data": boundary_data,
        "field_count": len(fields),
    }


def main():
    parser = argparse.ArgumentParser(description="测试数据推演")
    parser.add_argument("--object")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--schema-dir", type=Path, default=DEFAULT_SCHEMA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    if args.object:
        result = infer_object(args.object, args.schema_dir)
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # 推演所有
        for schema_path in args.schema_dir.glob("*.yaml"):
            if schema_path.name.startswith("_"):
                continue
            obj_id = schema_path.stem
            inference = infer_object(obj_id, args.schema_dir)
            if not inference:
                continue
            output_path = args.output_dir / f"{obj_id}.inferred.json"
            output_path.write_text(
                json.dumps(inference, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"✓ {obj_id}: {inference['field_count']} fields, valid/invalid/boundary → {output_path}")


if __name__ == "__main__":
    main()
