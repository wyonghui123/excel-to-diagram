#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
discover_business_rules.py 单元测试 (T-001)
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

# 添加 scripts 目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from discover_business_rules import (  # noqa: E402
    BusinessRule,
    RuleExtractor,
    discover_all,
    discover_object,
    write_index,
    write_yaml,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def business_object_schema():
    return {
        "id": "business_object",
        "name": "业务对象",
        "table_name": "business_objects",
        "display_name_field": "name",
        "aspects": ["hierarchy_aspect", "audit_aspect", "naming_aspect"],
        "audit": {
            "enabled": True,
            "create": {"enabled": True, "fields": "all"},
            "update": {"enabled": True, "fields": "changed_only"},
            "delete": {"enabled": True, "fields": "business_only"},
        },
        "deletability": {
            "condition": "self.relation_count == 0",
            "message": "存在关联关系的业务对象不能删除",
        },
        "authorization": {
            "check": True,
            "scope": "service_module_id IN (...)",
            "auto_owner": False,
            "auto_permission": "admin",
        },
        "cascade_select": [
            {
                "field": "domain_id",
                "parent_object": "domain",
                "parent_display_field": "name",
                "filter_by": "version_id",
            },
            {
                "field": "sub_domain_id",
                "parent_object": "sub_domain",
                "parent_display_field": "name",
                "filter_by": "domain_id",
            },
        ],
        "hierarchy": {
            "enabled": True,
            "hierarchy_id": "biz_hierarchy",
        },
    }


@pytest.fixture
def schema_path(temp_dir):
    return temp_dir / "business_object.yaml"


# ---------------------------------------------------------------------------
# 1. deletability 规则测试
# ---------------------------------------------------------------------------

def test_extract_deletability(business_object_schema, schema_path):
    """测试 deletability 规则抽取"""
    extractor = RuleExtractor(business_object_schema, schema_path)
    rules = extractor.extract_all()

    del_rules = [r for r in rules if r.type == "deletability"]
    assert len(del_rules) == 1
    rule = del_rules[0]
    assert rule.id == "BR-business_object-DEL-condition"
    assert rule.condition == "self.relation_count == 0"
    assert rule.message == "存在关联关系的业务对象不能删除"
    assert rule.source == "schema:business_object.yaml:deletability"
    assert len(rule.derived_scenarios) == 2
    assert rule.derived_scenarios[0]["priority"] == "P0"
    assert "BusinessRuleAssertor.assertRule" in rule.derived_scenarios[0]["business_assertion"]


def test_extract_deletability_missing(business_object_schema, schema_path):
    """deletability 字段缺失时不报错"""
    del business_object_schema["deletability"]
    extractor = RuleExtractor(business_object_schema, schema_path)
    rules = extractor.extract_all()
    assert all(r.type != "deletability" for r in rules)


# ---------------------------------------------------------------------------
# 2. cascade_select 规则测试
# ---------------------------------------------------------------------------

def test_extract_cascade_select(business_object_schema, schema_path):
    """测试级联下拉规则抽取"""
    extractor = RuleExtractor(business_object_schema, schema_path)
    rules = extractor.extract_all()

    cs_rules = [r for r in rules if r.type == "cascade_select"]
    assert len(cs_rules) == 2
    assert cs_rules[0].id == "BR-business_object-CS-domain_id"
    assert cs_rules[0].condition["parent_object"] == "domain"
    assert cs_rules[0].condition["filter_by"] == "version_id"
    assert cs_rules[1].id == "BR-business_object-CS-sub_domain_id"


# ---------------------------------------------------------------------------
# 3. authorization 规则测试
# ---------------------------------------------------------------------------

def test_extract_authorization(business_object_schema, schema_path):
    """测试 authorization 规则抽取"""
    extractor = RuleExtractor(business_object_schema, schema_path)
    rules = extractor.extract_all()

    auth_rules = [r for r in rules if r.type == "authorization"]
    assert len(auth_rules) == 1
    rule = auth_rules[0]
    assert rule.id == "BR-business_object-AUTH"
    assert rule.condition["check"] is True
    assert rule.condition["auto_permission"] == "admin"


def test_extract_authorization_disabled(business_object_schema, schema_path):
    """authorization.check=false 时不抽取"""
    business_object_schema["authorization"]["check"] = False
    extractor = RuleExtractor(business_object_schema, schema_path)
    rules = extractor.extract_all()
    assert all(r.type != "authorization" for r in rules)


# ---------------------------------------------------------------------------
# 4. audit 规则测试
# ---------------------------------------------------------------------------

def test_extract_audit(business_object_schema, schema_path):
    """测试 audit 规则抽取"""
    extractor = RuleExtractor(business_object_schema, schema_path)
    rules = extractor.extract_all()

    audit_rules = [r for r in rules if r.type == "audit"]
    assert len(audit_rules) == 1
    rule = audit_rules[0]
    assert rule.id == "BR-business_object-AUDIT"
    assert set(rule.condition["operations"]) == {"create", "update", "delete"}


def test_extract_audit_disabled(business_object_schema, schema_path):
    """audit.enabled=false 时不抽取"""
    business_object_schema["audit"]["enabled"] = False
    extractor = RuleExtractor(business_object_schema, schema_path)
    rules = extractor.extract_all()
    assert all(r.type != "audit" for r in rules)


# ---------------------------------------------------------------------------
# 5. aspect 规则测试
# ---------------------------------------------------------------------------

def test_extract_aspect(business_object_schema, schema_path):
    """测试 aspect 规则抽取"""
    extractor = RuleExtractor(business_object_schema, schema_path)
    rules = extractor.extract_all()

    aspect_rules = [r for r in rules if r.type == "aspect"]
    assert len(aspect_rules) == 3
    assert aspect_rules[0].id == "BR-business_object-ASPECT-hierarchy_aspect"


# ---------------------------------------------------------------------------
# 6. 综合测试
# ---------------------------------------------------------------------------

def test_extract_all_returns_expected_count(business_object_schema, schema_path):
    """综合测试: 业务对象应有 2(cs) + 1(del) + 1(auth) + 1(audit) + 3(aspect) = 8 条"""
    extractor = RuleExtractor(business_object_schema, schema_path)
    rules = extractor.extract_all()
    assert len(rules) == 8


def test_to_yaml_dict(business_object_schema, schema_path):
    """测试 to_yaml_dict 序列化"""
    extractor = RuleExtractor(business_object_schema, schema_path)
    extractor.extract_all()
    data = extractor.to_yaml_dict()

    assert data["object_id"] == "business_object"
    assert data["object_name"] == "业务对象"
    assert data["total_rules"] == 8
    assert isinstance(data["rules"], list)
    assert all("id" in r and "type" in r and "source" in r for r in data["rules"])


# ---------------------------------------------------------------------------
# 7. CLI/IO 测试
# ---------------------------------------------------------------------------

def test_discover_object_not_found(temp_dir):
    """不存在的对象返回 None"""
    result = discover_object("non_existent", temp_dir)
    assert result is None


def test_discover_object_success(business_object_schema, schema_path, temp_dir):
    """成功抽取"""
    schema_path.write_text(
        yaml.safe_dump(business_object_schema, allow_unicode=True),
        encoding="utf-8",
    )
    result = discover_object("business_object", temp_dir)
    assert result is not None
    assert result["object_id"] == "business_object"
    assert result["total_rules"] == 8


def test_write_yaml(business_object_schema, schema_path, temp_dir):
    """写 YAML 文件"""
    extractor = RuleExtractor(business_object_schema, schema_path)
    extractor.extract_all()
    data = extractor.to_yaml_dict()

    output = temp_dir / "out.yaml"
    write_yaml(data, output)
    assert output.exists()

    # 解析回来验证
    parsed = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert parsed["object_id"] == "business_object"
    assert parsed["total_rules"] == 8


def test_write_index(temp_dir):
    """写 _index.json"""
    results = [
        {
            "object_id": "a",
            "object_name": "A",
            "display_name": "A",
            "total_rules": 3,
            "rules": [
                {"id": "BR-a-DEL", "type": "deletability"},
                {"id": "BR-a-KEY", "type": "key_template"},
                {"id": "BR-a-CS-x", "type": "cascade_select"},
            ],
        },
    ]
    write_index(results, temp_dir)
    index_path = temp_dir / "_index.json"
    assert index_path.exists()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["total_objects"] == 1
    assert index["total_rules"] == 3
    assert "deletability" in index["objects"][0]["rule_types"]


def test_discover_all_skips_underscore_files(temp_dir):
    """跳过以 _ 开头的文件"""
    (temp_dir / "_template.yaml").write_text("id: template", encoding="utf-8")
    (temp_dir / "test_obj.yaml").write_text("id: test_obj", encoding="utf-8")

    results = discover_all(temp_dir)
    object_ids = [r["object_id"] for r in results]
    assert "test_obj" in object_ids
    assert "template" not in object_ids


# ---------------------------------------------------------------------------
# 8. edge case
# ---------------------------------------------------------------------------

def test_empty_schema(temp_dir):
    """空 schema"""
    schema = {"id": "empty", "name": "空"}
    path = temp_dir / "empty.yaml"
    path.write_text(yaml.safe_dump(schema, allow_unicode=True), encoding="utf-8")

    extractor = RuleExtractor(schema, path)
    rules = extractor.extract_all()
    assert rules == []


def test_business_rule_to_dict():
    """BusinessRule.to_dict 测试"""
    rule = BusinessRule(
        rule_id="BR-test-DEL",
        rule_type="deletability",
        condition="x == 0",
        source="schema:test.yaml",
        message="test",
        derived_scenarios=[{"id": "T_test_001", "title": "test"}],
    )
    d = rule.to_dict()
    assert d["id"] == "BR-test-DEL"
    assert d["type"] == "deletability"
    assert d["condition"] == "x == 0"
    assert d["source"] == "schema:test.yaml"
    assert d["message"] == "test"
    assert len(d["derived_scenarios"]) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
