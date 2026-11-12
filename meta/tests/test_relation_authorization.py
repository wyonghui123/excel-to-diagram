"""R-MM-04 关系感知授权测试（Spec §6.4 A-04-1~4）。

覆盖：
  A-04-1  同一夹具判定结果一致，trace 中 decided_by 唯一
  A-04-2  inherit_mode 缺省 endpoint_union（零迁移 / 行为不变）
  A-04-3  explicit + max_depth=2 通过；max_depth=3 明确报错
  A-04-4  lint_metamodel --permissions 校验 explicit 的 relation_code 声明

测试入口: python d:\\filework\\test.py --file meta/tests/test_relation_authorization.py
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from meta.services.resource_inheritance_engine import (  # noqa: E402
    DEFAULT_INHERIT_MODE,
    MAX_ASSOCIATION_INHERIT_DEPTH,
    ResourceInheritanceEngine,
)
from meta.tools.lint_metamodel import lint_permissions  # noqa: E402


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class FakeDataSource:
    """最小 sqlite 游标替身：按 SQL 片段路由到夹具。"""

    def __init__(
        self,
        relationship_row=None,
        product_map=None,
        rules=None,
        fail_relation_field=False,
    ):
        self.relationship_row = relationship_row
        self.product_map = product_map or {}
        self.rules = rules or []
        self.fail_relation_field = fail_relation_field

    def execute(self, sql, params=None):
        params = params or []
        if "FROM relationships" in sql:
            if "relation_code" in sql:
                if self.fail_relation_field:
                    raise RuntimeError("no such column: relation_code")
                return _Cursor([self.relationship_row] if self.relationship_row else [])
            if self.relationship_row:
                return _Cursor([self.relationship_row[:2]])
            return _Cursor([])
        if "FROM business_objects" in sql:
            return _Cursor([(params[0],)])
        if "FROM sub_domains" in sql:
            return _Cursor([(self.product_map.get(params[0]),)])
        if "FROM permission_rules" in sql:
            return _Cursor(list(self.rules))
        raise AssertionError("unexpected SQL: %s" % sql)


# 夹具：relationship 1 = (source 10, target 20)，relation_code=DEPENDS_ON
REL_ROW = (10, 20, "DEPENDS_ON")
PRODUCT_MAP = {10: 1, 20: 2}


def _engine(**kwargs):
    return ResourceInheritanceEngine(data_source=FakeDataSource(**kwargs))


# ────────────────────────────────────────────
# A-04-1 判定一致 + decided_by 唯一
# ────────────────────────────────────────────
def test_decided_by_is_single_value_across_repeated_calls():
    engine = _engine(relationship_row=REL_ROW, product_map=PRODUCT_MAP)
    scope = {"product": {2}}  # 仅 target 端可见
    first = engine.check_association_visibility(1, "relationship", scope)
    first_trace = engine.get_last_decision()
    second = engine.check_association_visibility(1, "relationship", scope)
    second_trace = engine.get_last_decision()

    assert first is True and second is True
    assert first_trace == second_trace
    assert first_trace["decided_by"] == "association.inherit"
    assert isinstance(first_trace["decided_by"], str)


def test_get_last_decision_returns_copy():
    engine = _engine(relationship_row=REL_ROW, product_map=PRODUCT_MAP)
    engine.check_association_visibility(1, "relationship", {"product": {1}})
    trace = engine.get_last_decision()
    trace["decided_by"] = "tampered"
    assert engine.get_last_decision()["decided_by"] == "association.inherit"


# ────────────────────────────────────────────
# A-04-2 缺省 endpoint_union（回归）
# ────────────────────────────────────────────
def test_default_mode_is_endpoint_union():
    assert DEFAULT_INHERIT_MODE == "endpoint_union"
    engine = _engine(relationship_row=REL_ROW, product_map=PRODUCT_MAP)
    assert engine.check_association_visibility(1, "relationship", {"product": {2}}) is True
    assert engine.get_last_decision()["inherit_mode"] == "endpoint_union"
    assert engine.get_last_decision()["decided_by"] == "association.inherit"


def test_none_mode_only_checks_source_endpoint():
    engine = _engine(relationship_row=REL_ROW, product_map=PRODUCT_MAP)
    # target 可见但 source 不可见 → none 模式拒绝
    assert engine.check_association_visibility(
        1, "relationship", {"product": {2}}, inherit_mode="none"
    ) is False
    assert engine.get_last_decision()["decided_by"] == "default_deny"
    # source 可见 → none 模式允许
    assert engine.check_association_visibility(
        1, "relationship", {"product": {1}}, inherit_mode="none"
    ) is True


def test_auth_config_supplies_inherit_mode():
    engine = _engine(relationship_row=REL_ROW, product_map=PRODUCT_MAP)
    allowed = engine.check_association_visibility(
        1, "relationship", {"product": {2}}, auth_config={"inherit_mode": "none"}
    )
    assert allowed is False
    assert engine.get_last_decision()["inherit_mode"] == "none"


def test_unknown_inherit_mode_falls_back_to_default():
    engine = _engine(relationship_row=REL_ROW, product_map=PRODUCT_MAP)
    assert engine.check_association_visibility(
        1, "relationship", {"product": {2}}, inherit_mode="bogus"
    ) is True
    assert engine.get_last_decision()["inherit_mode"] == DEFAULT_INHERIT_MODE


def test_relation_code_column_missing_degrades_gracefully():
    engine = _engine(
        relationship_row=REL_ROW, product_map=PRODUCT_MAP, fail_relation_field=True
    )
    assert engine.check_association_visibility(1, "relationship", {"product": {1}}) is True
    assert engine.get_last_decision()["relation_code"] == ""


# ────────────────────────────────────────────
# A-04-3 explicit + max_depth
# ────────────────────────────────────────────
def test_explicit_deny_rule_wins():
    engine = _engine(
        relationship_row=REL_ROW,
        product_map=PRODUCT_MAP,
        rules=[(7, "*", 1)],  # is_denied 优先
    )
    assert engine.check_association_visibility(
        1, "relationship", {"product": {1}}, inherit_mode="explicit"
    ) is False
    trace = engine.get_last_decision()
    assert trace["decided_by"] == "permission_rule.is_denied"
    assert trace["rule_id"] == 7


def test_explicit_direct_rule_allows():
    engine = _engine(
        relationship_row=REL_ROW,
        product_map=PRODUCT_MAP,
        rules=[(8, "1=1", 0)],
    )
    assert engine.check_association_visibility(
        1, "relationship", set(), inherit_mode="explicit"
    ) is True
    assert engine.get_last_decision()["decided_by"] == "permission_rule.direct"


def test_explicit_without_matching_rule_falls_back_to_association():
    engine = _engine(
        relationship_row=REL_ROW,
        product_map=PRODUCT_MAP,
        rules=[(9, "product_id = 999", 0)],
    )
    assert engine.check_association_visibility(
        1, "relationship", {"product": {2}}, inherit_mode="explicit"
    ) is True
    assert engine.get_last_decision()["decided_by"] == "association.inherit"


def test_max_depth_two_allowed_three_rejected():
    engine = _engine(relationship_row=REL_ROW, product_map=PRODUCT_MAP)
    assert MAX_ASSOCIATION_INHERIT_DEPTH == 2
    assert engine.check_association_visibility(
        1, "relationship", {"product": {1}}, max_depth=2
    ) is True
    with pytest.raises(ValueError):
        engine.check_association_visibility(1, "relationship", {"product": {1}}, max_depth=3)


# ────────────────────────────────────────────
# 默认拒绝 / 非 association / 行缺失
# ────────────────────────────────────────────
def test_default_deny_when_no_endpoint_visible():
    engine = _engine(relationship_row=REL_ROW, product_map=PRODUCT_MAP)
    assert engine.check_association_visibility(1, "relationship", {"product": {99}}) is False
    assert engine.get_last_decision()["decided_by"] == "default_deny"


def test_missing_relationship_row_denies():
    engine = _engine(relationship_row=None)
    assert engine.check_association_visibility(1, "relationship", {"product": {1}}) is False
    assert engine.get_last_decision()["reason"] == "relationship_not_found"


def test_non_association_resource_uses_direct_id_match():
    engine = _engine()
    assert engine.check_association_visibility(5, "product", {"product": {5}}) is True
    assert engine.get_last_decision()["decided_by"] == "association.non_association"


def test_no_data_source_denies():
    engine = ResourceInheritanceEngine()
    assert engine.check_association_visibility(1, "relationship", {"product": {1}}) is False
    assert engine.get_last_decision()["reason"] == "no_data_source"


# ────────────────────────────────────────────
# A-04-4 lint --permissions
# ────────────────────────────────────────────
def test_lint_permissions_accepts_default_and_matching_explicit():
    declarations = [
        {"file": "relationship.yaml", "inherit_mode": "endpoint_union"},
        {"file": "r2.yaml", "inherit_mode": None},
        {"file": "r3.yaml", "inherit_mode": "explicit",
         "relation_codes": ["DEPENDS_ON"]},
    ]
    assert lint_permissions(declarations, {"DEPENDS_ON"}) == []


def test_lint_permissions_rejects_unknown_mode():
    violations = lint_permissions([{"file": "r.yaml", "inherit_mode": "bogus"}])
    assert len(violations) == 1
    assert violations[0][1] == "authorization.inherit_mode"


def test_lint_permissions_rejects_explicit_without_relation_code():
    violations = lint_permissions(
        [{"file": "r.yaml", "inherit_mode": "explicit", "relation_codes": []}]
    )
    assert len(violations) == 1
    assert "R16" in violations[0][2]


def test_lint_permissions_rejects_explicit_without_rule_declaration():
    violations = lint_permissions(
        [{"file": "r.yaml", "inherit_mode": "explicit",
          "relation_codes": ["DEPENDS_ON"]}],
        rule_codes=set(),
    )
    assert len(violations) == 1
    assert violations[0][1] == "authorization.relation_code"


def test_lint_tool_permissions_exit_zero():
    result = subprocess.run(
        [sys.executable, str(ROOT / "meta" / "tools" / "lint_metamodel.py"),
         "--permissions"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "violation(s)" in result.stdout