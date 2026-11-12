# -*- coding: utf-8 -*-
"""R24 / R28 能力维度单层承运 lint 测试（Spec §12 验收 A-12-1/A-12-5）。

覆盖：
  · A-12-1：`semantics.category` 未知取值被 lint 捕获，受控枚举/别名通过；
  · A-12-5：同一能力跨层重复声明（对象级级联 + 关联级级联、
    字段级审计、关联级审计）被判违规；
  · 当前 meta/schemas 无跨层重复声明。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from meta.core.models_enums import (  # noqa: E402
    ObjectSemanticsCategory,
    SEMANTICS_CATEGORY_ALIASES,
)
from meta.tools.lint_metamodel import lint_capabilities  # noqa: E402


def _doc(**extra):
    base = {"id": "demo_bo", "name": "示例", "fields": []}
    base.update(extra)
    return base


def test_a_12_1_unknown_semantics_category_reported():
    violations, scanned, _report = lint_capabilities([
        ("demo.yaml", _doc(semantics={"category": "not_a_category"})),
    ])
    assert scanned == 1
    assert any(field == "semantics.category" for _f, field, _r in violations)


def test_a_12_1_known_category_and_alias_accepted():
    known = next(iter(ObjectSemanticsCategory)).value
    alias = next(iter(SEMANTICS_CATEGORY_ALIASES))
    violations, scanned, _report = lint_capabilities([
        ("a.yaml", _doc(id="bo_a", semantics={"category": known})),
        ("b.yaml", _doc(id="bo_b", semantics={"category": alias})),
    ])
    assert scanned == 2
    assert violations == []


def test_a_12_5_duplicate_cascade_across_layers_reported():
    raw = _doc(
        deletion_policy={"cascade_delete": ["demo_lines"]},
        associations=[{"name": "demo_lines", "kind": "master_detail"}],
    )
    violations, _scanned, _report = lint_capabilities([("demo.yaml", raw)])
    assert any(field == "deletion_policy.cascade_delete"
               for _f, field, _r in violations)


def test_a_12_5_single_layer_cascade_accepted():
    raw = _doc(
        deletion_policy={"cascade_delete": ["demo_lines"]},
        associations=[{"name": "demo_lines", "kind": "association"}],
    )
    violations, _scanned, _report = lint_capabilities([("demo.yaml", raw)])
    assert violations == []


def test_a_12_5_field_level_audit_declaration_reported():
    raw = _doc(fields=[{"id": "amount", "audit": True}])
    violations, _scanned, _report = lint_capabilities([("demo.yaml", raw)])
    assert any(field == "fields.amount.audit" for _f, field, _r in violations)


def test_a_12_5_association_level_audit_declaration_reported():
    raw = _doc(associations=[{"name": "demo_lines", "audit": True}])
    violations, _scanned, _report = lint_capabilities([("demo.yaml", raw)])
    assert any(field == "associations.demo_lines.audit"
               for _f, field, _r in violations)


def test_a_12_5_real_schemas_have_no_cross_layer_duplicates():
    violations, scanned, _report = lint_capabilities()
    assert scanned >= 200
    assert violations == []