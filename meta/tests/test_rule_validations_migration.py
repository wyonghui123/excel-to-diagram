import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
规则模型 P2/P3 迁移测试（废弃顶层 validations: 段）

覆盖：
1. G 类迁移：relationship.source_not_equal_target 经 rules: 在保存链路真阻断
2. 字段属性路径：enum_type.id（business_key）不再被 _skip_field 跳过；普通对象 id 仍跳过
3. 残留顶层 validations: 段被加载器拒绝
4. MetaObject 不再持有 validations 容器 / get_validations
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.rule_executor import RuleEngine
from meta.core.yaml_loader import load_yaml_file, DeprecatedSchemaSectionError
from meta.core.metadata_driven_validator import MetadataDrivenValidator

SCHEMA_DIR = os.path.join(PROJECT_ROOT, "meta", "schemas")


def test_relationship_source_not_equal_target_blocks():
    """G 类规则迁入 rules: 后必须真阻断（首次启用 type: validation）。"""
    meta = load_yaml_file(os.path.join(SCHEMA_DIR, "relationship.yaml"))
    assert meta is not None

    rule = meta.get_rule("source_not_equal_target")
    assert rule is not None, "relationship.rules: 缺少 source_not_equal_target"
    assert rule.rule_type.value == "validation"

    engine = RuleEngine()
    bad = engine.validate(meta, {"source_bo_id": 1, "target_bo_id": 1})
    assert bad.success is False, "source_bo_id == target_bo_id 应被阻断"
    assert bad.failed >= 1

    ok = engine.validate(meta, {"source_bo_id": 1, "target_bo_id": 2})
    assert ok.success is True, "source_bo_id != target_bo_id 不应阻断"


def test_enum_type_id_business_key_not_skipped():
    """enum_type.id 声明 business_key，字段属性路径不得再跳过它。"""
    dv = MetadataDrivenValidator(None)
    enum_meta = load_yaml_file(os.path.join(SCHEMA_DIR, "enum_type.yaml"))
    id_field = next(f for f in enum_meta.fields if f.id == "id")
    assert getattr(id_field.semantics, "business_key", False) is True
    assert dv._skip_field(id_field, "create") is False

    annotation_meta = load_yaml_file(os.path.join(SCHEMA_DIR, "annotation.yaml"))
    plain_id = next(f for f in annotation_meta.fields if f.id == "id")
    assert dv._skip_field(plain_id, "create") is True, "普通 id 应保持跳过"


def test_residual_validations_section_rejected(tmp_path):
    """残留顶层 validations: 段必须在加载期被拒绝（防回流）。"""
    bad_schema = tmp_path / "legacy_validations.yaml"
    bad_schema.write_text(
        "id: legacy\nname: 遗留\nvalidations:\n- id: x_required\n  type: field\n  rule: x is not None\n",
        encoding="utf-8",
    )
    with pytest.raises(DeprecatedSchemaSectionError):
        load_yaml_file(str(bad_schema))


def test_meta_object_no_validations_container():
    from meta.core.models import MetaObject

    assert "validations" not in MetaObject.__dataclass_fields__
    assert not hasattr(MetaObject, "get_validations")
