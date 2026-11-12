"""R-MM-01 关联语义扩展测试（Spec §3.5 A-01-1~4）。

覆盖：
  A-01-1  五枚举声明位（semantics.kind / associations[].kind）可读
  A-01-2  `lint_metamodel.py --relations` 退出码 0
  A-01-3  `$associations?kind=` 过滤语义：不匹配 → 空结果；未知取值 → 报错
  A-01-4  缺省 kind = association（零迁移）

测试入口: python d:\\filework\\test.py --file meta/tests/test_relation_metamodel.py
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from meta.core.models_enums import (  # noqa: E402
    AssociationKind,
    normalize_association_kind,
)
from meta.core.yaml_loader import load_yaml_file, parse_association  # noqa: E402


# ────────────────────────────────────────────
# A-01-1 五枚举 + 归一
# ────────────────────────────────────────────
def test_association_kind_enum_has_five_values():
    assert {k.value for k in AssociationKind} == {
        "association", "hierarchy", "reference", "master_detail", "derived",
    }


@pytest.mark.parametrize("raw,expected", [
    ("association", AssociationKind.ASSOCIATION),
    ("HIERARCHY", AssociationKind.HIERARCHY),
    (" reference ", AssociationKind.REFERENCE),
    ("master_detail", AssociationKind.MASTER_DETAIL),
    ("derived", AssociationKind.DERIVED),
])
def test_normalize_association_kind_accepts_declared_values(raw, expected):
    assert normalize_association_kind(raw) is expected


@pytest.mark.parametrize("raw", [None, "", "   ", "unknown_kind"])
def test_normalize_association_kind_rejects_unknown(raw):
    assert normalize_association_kind(raw) is None


def test_parse_association_defaults_to_blank_kind():
    """R1 零迁移：未声明 kind 时保持空串（消费侧按 association 兜底）。"""
    assoc = parse_association({"name": "demo", "type": "reference",
                                "target_entity": "user"})
    assert assoc.kind == ""


def test_parse_association_reads_declared_kind():
    assoc = parse_association({"name": "demo", "type": "reference",
                               "target_entity": "user", "kind": "reference"})
    assert assoc.kind == "reference"


def test_parse_association_drops_unknown_kind():
    """R24 口径：未知取值告警后按未声明处理，不阻断装载。"""
    assoc = parse_association({"name": "demo", "type": "reference",
                               "target_entity": "user", "kind": "bogus"})
    assert assoc.kind == ""


# ────────────────────────────────────────────
# 声明位：真实 schema 的 kind 声明已生效
# ────────────────────────────────────────────
def test_relationship_semantics_kind_is_association():
    obj = load_yaml_file(str(ROOT / "meta" / "schemas" / "relationship.yaml"))
    assert obj is not None
    assert obj.semantics.kind == "association"


def test_product_version_association_declares_master_detail():
    obj = load_yaml_file(str(ROOT / "meta" / "schemas" / "product.yaml"))
    assert obj is not None
    assert obj.associations["version"].kind == "master_detail"


def test_reference_associations_keep_default_semantics():
    """未显式声明 kind 的既有对象关联不受影响（零迁移）。"""
    obj = load_yaml_file(str(ROOT / "meta" / "schemas" / "data_permission.yaml"))
    assert obj is not None
    assert obj.associations["user"].kind == "reference"


# ────────────────────────────────────────────
# A-01-3 消费侧：?kind= 过滤
# ────────────────────────────────────────────
def _dispatch(operation, **params):
    from meta.core.action_context import ActionContext
    from meta.core.association_engine import AssociationEngine

    product = load_yaml_file(str(ROOT / "meta" / "schemas" / "product.yaml"))
    payload = {"association_name": "version"}
    payload.update(params)
    ctx = ActionContext(
        meta_object=product,
        action=operation,
        params=payload,
        data_source=None,
    )
    return AssociationEngine()._dispatch(ctx, operation)


def test_kind_filter_mismatch_returns_empty_result():
    result = _dispatch("query", kind="reference")
    assert result.success is True
    assert result.data == {"items": [], "total": 0, "counts": {}}


def test_kind_filter_mismatch_count_returns_zero():
    result = _dispatch("count", kind="reference")
    assert result.success is True
    assert result.data == {"count": 0}


def test_kind_filter_unknown_value_is_rejected():
    result = _dispatch("query", kind="not_a_kind")
    assert result.success is False
    assert "Unknown association kind" in result.message


# ────────────────────────────────────────────
# A-01-2 lint 退出码
# ────────────────────────────────────────────
def test_lint_metamodel_relations_passes():
    lint = ROOT / "meta" / "tools" / "lint_metamodel.py"
    proc = subprocess.run(
        [sys.executable, str(lint), "--relations"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "TEST_ENTRY": "1"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "violation(s)" in proc.stdout