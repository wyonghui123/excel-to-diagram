#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
业务规则抽取器 (T-001)
========================

从 meta/schemas/*.yaml 抽取业务规则,生成 .trae/specs/_business_rules/<object>.yaml

支持 9 种规则类型:
  1. deletability     - 删除约束
  2. key_template     - 编码自动生成
  3. cascade_select   - 级联下拉
  4. authorization    - 权限控制
  5. audit            - 审计日志
  6. aspect           - 切面行为
  7. cascade_delete   - 级联删除
  8. owner            - 所有者规则
  9. filter_variant   - 过滤变体

用法:
    python .trae/scripts/discover_business_rules.py --object business_object
    python .trae/scripts/discover_business_rules.py --all
    python .trae/scripts/discover_business_rules.py --object business_object --json

输出:
    .trae/specs/_business_rules/<object>.yaml
    .trae/specs/_business_rules/_index.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# 规则抽取器
# ---------------------------------------------------------------------------

class BusinessRule:
    """单条业务规则"""

    def __init__(
        self,
        rule_id: str,
        rule_type: str,
        condition: Any,
        source: str,
        message: Optional[str] = None,
        derived_scenarios: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.id = rule_id
        self.type = rule_type
        self.condition = condition
        self.source = source
        self.message = message
        self.derived_scenarios = derived_scenarios or []
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "type": self.type,
            "condition": self.condition,
            "source": self.source,
        }
        if self.message:
            result["message"] = self.message
        if self.derived_scenarios:
            result["derived_scenarios"] = self.derived_scenarios
        if self.metadata:
            result["metadata"] = self.metadata
        return result


class RuleExtractor:
    """从单个 schema 抽取业务规则"""

    def __init__(self, schema: Dict[str, Any], schema_path: Path):
        self.schema = schema
        self.schema_path = schema_path
        self.object_id = schema.get("id", schema_path.stem)
        self.object_name = schema.get("name", self.object_id)
        self.display_name = schema.get("display_name", self.object_name)
        self.rules: List[BusinessRule] = []

    def extract_all(self) -> List[BusinessRule]:
        """抽取所有 9 种规则"""
        self.extract_deletability()
        self.extract_key_template()
        self.extract_cascade_select()
        self.extract_authorization()
        self.extract_audit()
        self.extract_aspect()
        self.extract_cascade_delete()
        self.extract_owner()
        self.extract_filter_variant()
        return self.rules

    # ------------------------------------------------------------------
    # 1. deletability 规则
    # ------------------------------------------------------------------
    def extract_deletability(self) -> None:
        if "deletability" not in self.schema:
            return
        d = self.schema["deletability"]
        # 可能为 dict(condition, message) 或 list
        if isinstance(d, dict):
            condition = d.get("condition", "")
            message = d.get("message", "")
        else:
            condition = str(d)
            message = ""

        rule_id = f"BR-{self.object_id}-DEL-condition"
        self.rules.append(BusinessRule(
            rule_id=rule_id,
            rule_type="deletability",
            condition=condition,
            source=f"schema:{self.schema_path.name}:deletability",
            message=message,
            derived_scenarios=[
                {
                    "id": f"T_{self.object_id.upper()}_DEL_001",
                    "title": f"删除有关系的{self.display_name}应失败",
                    "priority": "P0",
                    "page_flow": ["列表", "详情", "关系编辑", "删除确认"],
                    "business_assertion": f"BusinessRuleAssertor.assertRule('{rule_id}', {{ relationCount: 1 }})",
                },
                {
                    "id": f"T_{self.object_id.upper()}_DEL_002",
                    "title": f"删除无关系的{self.display_name}应成功",
                    "priority": "P1",
                    "page_flow": ["列表", "详情", "删除确认", "列表"],
                    "business_assertion": f"BusinessRuleAssertor.assertRule('{rule_id}', {{ relationCount: 0 }})",
                },
            ],
        ))

    # ------------------------------------------------------------------
    # 2. key_template 规则
    # ------------------------------------------------------------------
    def extract_key_template(self) -> None:
        # key_template 可能在 schema 根或 fields 中
        kt = self.schema.get("key_template")
        if not kt:
            # 在 standard_actions 或 naming_aspect 中查找
            std_actions = self.schema.get("standard_actions", {})
            kt = std_actions.get("key_template") if isinstance(std_actions, dict) else None
        if not kt:
            return

        pattern = kt.get("pattern", "") if isinstance(kt, dict) else str(kt)
        rule_id = f"BR-{self.object_id}-KEY"
        self.rules.append(BusinessRule(
            rule_id=rule_id,
            rule_type="key_template",
            condition=pattern,
            source=f"schema:{self.schema_path.name}:key_template",
            message=f"新建{self.display_name}时 code 应自动填充 = {pattern}",
            derived_scenarios=[
                {
                    "id": f"T_{self.object_id.upper()}_KEY_001",
                    "title": f"新建{self.display_name}时 code 应自动填充",
                    "priority": "P0",
                    "page_flow": ["列表", "新建表单", "填写名称", "验证 code 自动填充", "保存"],
                    "business_assertion": f"BusinessRuleAssertor.assertRule('{rule_id}', {{ name: 'test' }})",
                },
                {
                    "id": f"T_{self.object_id.upper()}_KEY_002",
                    "title": f"手动修改 code 后保存应成功",
                    "priority": "P1",
                    "page_flow": ["列表", "新建表单", "修改 code", "保存"],
                    "business_assertion": f"BusinessRuleAssertor.assertRule('{rule_id}', {{ manualCode: true }})",
                },
            ],
        ))

    # ------------------------------------------------------------------
    # 3. cascade_select 规则
    # ------------------------------------------------------------------
    def extract_cascade_select(self) -> None:
        cs_list = self.schema.get("cascade_select", [])
        if not cs_list:
            return
        for idx, cs in enumerate(cs_list):
            if not isinstance(cs, dict):
                continue
            field = cs.get("field", f"unknown_{idx}")
            parent_object = cs.get("parent_object", "unknown")
            parent_display_field = cs.get("parent_display_field", "name")
            filter_by = cs.get("filter_by", "")

            rule_id = f"BR-{self.object_id}-CS-{field}"
            self.rules.append(BusinessRule(
                rule_id=rule_id,
                rule_type="cascade_select",
                condition={
                    "field": field,
                    "parent_object": parent_object,
                    "parent_display_field": parent_display_field,
                    "filter_by": filter_by,
                },
                source=f"schema:{self.schema_path.name}:cascade_select[{idx}]",
                message=f"选择 {parent_object}.{parent_display_field} = 'X',{field} 下拉应只显示 'X' 的 {parent_object}",
                derived_scenarios=[
                    {
                        "id": f"T_{self.object_id.upper()}_CS_{idx}_001",
                        "title": f"级联下拉 {field} 应受 {filter_by} 过滤",
                        "priority": "P0",
                        "page_flow": ["列表", "新建表单", f"选择 {filter_by}", f"验证 {field} 列表"],
                        "business_assertion": f"BusinessRuleAssertor.assertRule('{rule_id}', {{ parent: 'X' }})",
                    },
                ],
            ))

    # ------------------------------------------------------------------
    # 4. authorization 规则
    # ------------------------------------------------------------------
    def extract_authorization(self) -> None:
        if "authorization" not in self.schema:
            return
        a = self.schema["authorization"]
        if not isinstance(a, dict):
            return
        check_enabled = a.get("check", False)
        if not check_enabled:
            return

        rule_id = f"BR-{self.object_id}-AUTH"
        scope = a.get("scope", "")
        auto_owner = a.get("auto_owner", False)
        auto_permission = a.get("auto_permission", "none")

        self.rules.append(BusinessRule(
            rule_id=rule_id,
            rule_type="authorization",
            condition={
                "check": True,
                "scope": scope[:200] + "..." if len(scope) > 200 else scope,
                "auto_owner": auto_owner,
                "auto_permission": auto_permission,
            },
            source=f"schema:{self.schema_path.name}:authorization",
            message=f"{self.display_name}的访问权限应基于 scope 校验",
            derived_scenarios=[
                {
                    "id": f"T_{self.object_id.upper()}_AUTH_001",
                    "title": f"未授权用户访问{self.display_name}应被拒绝",
                    "priority": "P0",
                    "page_flow": ["登录未授权用户", "访问列表", "验证 403/无权限"],
                    "business_assertion": f"BusinessRuleAssertor.assertRule('{rule_id}', {{ authorized: false }})",
                },
                {
                    "id": f"T_{self.object_id.upper()}_AUTH_002",
                    "title": f"已授权用户访问{self.display_name}应成功",
                    "priority": "P1",
                    "page_flow": ["登录已授权用户", "访问列表", "验证可见"],
                    "business_assertion": f"BusinessRuleAssertor.assertRule('{rule_id}', {{ authorized: true }})",
                },
            ],
        ))

    # ------------------------------------------------------------------
    # 5. audit 规则
    # ------------------------------------------------------------------
    def extract_audit(self) -> None:
        if "audit" not in self.schema:
            return
        a = self.schema["audit"]
        if not isinstance(a, dict) or not a.get("enabled", False):
            return

        rule_id = f"BR-{self.object_id}-AUDIT"
        operations = []
        for op in ["create", "update", "delete"]:
            if a.get(op, {}).get("enabled", False):
                operations.append(op)

        self.rules.append(BusinessRule(
            rule_id=rule_id,
            rule_type="audit",
            condition={
                "enabled": True,
                "operations": operations,
            },
            source=f"schema:{self.schema_path.name}:audit",
            message=f"{self.display_name}的 {','.join(operations)} 操作应记录 audit_log",
            derived_scenarios=[
                {
                    "id": f"T_{self.object_id.upper()}_AUDIT_001",
                    "title": f"创建/更新/删除{self.display_name}应记录 audit_log",
                    "priority": "P1",
                    "page_flow": ["列表", "新建/编辑/删除", "检查 audit_log"],
                    "business_assertion": f"BusinessRuleAssertor.assertRule('{rule_id}', {{ operation: 'create' }})",
                },
            ],
        ))

    # ------------------------------------------------------------------
    # 6. aspect 规则
    # ------------------------------------------------------------------
    def extract_aspect(self) -> None:
        aspects = self.schema.get("aspects", [])
        if not aspects:
            return
        for idx, aspect in enumerate(aspects):
            rule_id = f"BR-{self.object_id}-ASPECT-{aspect}"
            self.rules.append(BusinessRule(
                rule_id=rule_id,
                rule_type="aspect",
                condition=aspect,
                source=f"schema:{self.schema_path.name}:aspects[{idx}]",
                message=f"{self.display_name} 应启用 {aspect} 切面",
                derived_scenarios=[
                    {
                        "id": f"T_{self.object_id.upper()}_ASPECT_{idx}_001",
                        "title": f"{self.display_name} 的 {aspect} 切面应正确触发",
                        "priority": "P2",
                        "page_flow": ["触发场景", "验证切面行为"],
                        "business_assertion": f"BusinessRuleAssertor.assertRule('{rule_id}', {{ aspect: '{aspect}' }})",
                    },
                ],
            ))

    # ------------------------------------------------------------------
    # 7. cascade_delete 规则
    # ------------------------------------------------------------------
    def extract_cascade_delete(self) -> None:
        cd = self.schema.get("cascade_delete")
        if not cd:
            return
        rule_id = f"BR-{self.object_id}-CASCADE-DEL"
        self.rules.append(BusinessRule(
            rule_id=rule_id,
            rule_type="cascade_delete",
            condition=cd,
            source=f"schema:{self.schema_path.name}:cascade_delete",
            message=f"删除{self.display_name}应级联处理关联数据",
            derived_scenarios=[
                {
                    "id": f"T_{self.object_id.upper()}_CASCADE_DEL_001",
                    "title": f"删除{self.display_name}应级联删除关联数据",
                    "priority": "P1",
                    "page_flow": ["列表", "详情", "删除确认", "验证关联"],
                    "business_assertion": f"BusinessRuleAssertor.assertRule('{rule_id}', {{ checkRelations: true }})",
                },
            ],
        ))

    # ------------------------------------------------------------------
    # 8. owner 规则
    # ------------------------------------------------------------------
    def extract_owner(self) -> None:
        owner = self.schema.get("owner")
        if not owner:
            return
        rule_id = f"BR-{self.object_id}-OWNER"
        self.rules.append(BusinessRule(
            rule_id=rule_id,
            rule_type="owner",
            condition=owner,
            source=f"schema:{self.schema_path.name}:owner",
            message=f"{self.display_name}应自动关联 owner",
            derived_scenarios=[
                {
                    "id": f"T_{self.object_id.upper()}_OWNER_001",
                    "title": f"新建{self.display_name}应自动设置 owner 为当前用户",
                    "priority": "P1",
                    "page_flow": ["登录", "新建", "验证 owner"],
                    "business_assertion": f"BusinessRuleAssertor.assertRule('{rule_id}', {{ currentUser: '...' }})",
                },
            ],
        ))

    # ------------------------------------------------------------------
    # 9. filter_variant 规则
    # ------------------------------------------------------------------
    def extract_filter_variant(self) -> None:
        fv = self.schema.get("filter_variant")
        if not fv:
            return
        rule_id = f"BR-{self.object_id}-FILTER-VARIANT"
        self.rules.append(BusinessRule(
            rule_id=rule_id,
            rule_type="filter_variant",
            condition=fv,
            source=f"schema:{self.schema_path.name}:filter_variant",
            message=f"{self.display_name} 应支持 filter_variant 过滤",
            derived_scenarios=[
                {
                    "id": f"T_{self.object_id.upper()}_FV_001",
                    "title": f"{self.display_name} 列表应支持 filter_variant",
                    "priority": "P2",
                    "page_flow": ["列表", "选择 filter_variant", "验证过滤"],
                    "business_assertion": f"BusinessRuleAssertor.assertRule('{rule_id}', {{ variant: '...' }})",
                },
            ],
        ))

    # ------------------------------------------------------------------
    # 输出
    # ------------------------------------------------------------------
    def to_yaml_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema_path.name,
            "object_id": self.object_id,
            "object_name": self.object_name,
            "display_name": self.display_name,
            "total_rules": len(self.rules),
            "rules": [r.to_dict() for r in self.rules],
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

DEFAULT_SCHEMA_DIR = Path("meta/schemas")
DEFAULT_OUTPUT_DIR = Path(".trae/specs/_business_rules")


def discover_object(object_id: str, schema_dir: Path) -> Optional[Dict[str, Any]]:
    """抽取单个对象的业务规则"""
    schema_path = schema_dir / f"{object_id}.yaml"
    if not schema_path.exists():
        print(f"ERROR: schema not found: {schema_path}", file=sys.stderr)
        return None
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    extractor = RuleExtractor(schema, schema_path)
    extractor.extract_all()
    return extractor.to_yaml_dict()


def discover_all(schema_dir: Path) -> List[Dict[str, Any]]:
    """抽取所有 schema 的业务规则"""
    results = []
    for schema_path in sorted(schema_dir.glob("*.yaml")):
        # 跳过非业务对象 schema
        if schema_path.name.startswith("_"):
            continue
        if schema_path.name in ("README.md",):
            continue
        try:
            schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
            if not isinstance(schema, dict) or "id" not in schema:
                continue
            extractor = RuleExtractor(schema, schema_path)
            extractor.extract_all()
            results.append(extractor.to_yaml_dict())
        except Exception as e:
            print(f"WARN: skip {schema_path.name}: {e}", file=sys.stderr)
    return results


def write_yaml(data: Dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def write_index(results: List[Dict[str, Any]], output_dir: Path) -> None:
    """写 _index.json 总索引"""
    index = {
        "generated_at": "2026-06-13",
        "total_objects": len(results),
        "total_rules": sum(r["total_rules"] for r in results),
        "objects": [
            {
                "object_id": r["object_id"],
                "object_name": r["object_name"],
                "display_name": r["display_name"],
                "total_rules": r["total_rules"],
                "rule_ids": [rule["id"] for rule in r["rules"]],
                "rule_types": list({rule["type"] for rule in r["rules"]}),
            }
            for r in results
        ],
    }
    index_path = output_dir / "_index.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ Index: {index_path}")


def main():
    parser = argparse.ArgumentParser(description="业务规则抽取器")
    parser.add_argument("--object", help="指定对象 ID,如 business_object")
    parser.add_argument("--all", action="store_true", help="抽取所有 schema")
    parser.add_argument("--schema-dir", type=Path, default=DEFAULT_SCHEMA_DIR, help="schema 目录")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="输出目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON 而非 YAML")
    args = parser.parse_args()

    if not args.object and not args.all:
        parser.print_help()
        sys.exit(1)

    if args.object:
        data = discover_object(args.object, args.schema_dir)
        if data is None:
            sys.exit(1)
        results = [data]
    else:
        results = discover_all(args.schema_dir)

    # 写 YAML
    for r in results:
        output_path = args.output_dir / f"{r['object_id']}.yaml"
        if args.json:
            output_path = output_path.with_suffix(".json")
            output_path.write_text(
                json.dumps(r, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            write_yaml(r, output_path)
        print(f"✓ {r['object_id']}: {r['total_rules']} rules → {output_path}")

    # 写总索引
    if args.all:
        write_index(results, args.output_dir)

    # 汇总
    total_rules = sum(r["total_rules"] for r in results)
    print(f"\n📊 总计: {len(results)} objects, {total_rules} rules")


if __name__ == "__main__":
    main()
