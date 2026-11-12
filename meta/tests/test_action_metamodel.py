"""R-MM-02 动作元模型声明测试（Spec §4）。

覆盖：
  A-02-1  存量标准动作不受新增字段影响（缺省为空 = 旧行为）
  A-02-2  `lint_metamodel.py --actions` 退出码 0、声明-实现签名差异 0
  结构校验  R5 效果类型枚举 / R6 emits 注册 / R8 role_any ⊆ permission_sets.code

测试入口: python d:\\filework\\test.py --file meta/tests/test_action_metamodel.py
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from meta.core.standard_action_loader import StandardActionLoader  # noqa: E402
from meta.tools.lint_metamodel import lint_actions  # noqa: E402

SCHEMAS_DIR = ROOT / "meta" / "schemas"

SEED_ROLES = {"admin", "editor", "viewer"}


@pytest.fixture()
def loader():
    """加载真实声明，测试结束后复位，避免污染其它用例的类级缓存。"""
    StandardActionLoader.load(str(SCHEMAS_DIR))
    try:
        yield StandardActionLoader
    finally:
        StandardActionLoader.load(str(SCHEMAS_DIR))


# ────────────────────────────────────────────
# A-02-1 零回归：存量动作新字段缺省为空
# ────────────────────────────────────────────
def test_existing_actions_keep_empty_extensions(loader):
    assert loader._actions, "标准动作声明不应为空"
    for action in loader._actions:
        assert action.object_types == []
        assert action.params == []
        assert action.preconditions == {}
        assert action.effects == []
        assert action.emits == []
        assert action.audit is None


def test_loader_reads_six_optional_groups(tmp_path):
    declaration = """
standard_actions:
  - id: demo_action
    name: 演示动作
    action_type: business
    instance_scope: instance
    object_types: [product]
    params:
      - name: reason
        type: string
        required: true
        source: request
    preconditions:
      status_in: [draft]
      role_any: [admin]
      relation_exists:
        name: version
    effects:
      - type: transition
        field: status
        to: active
    emits: [demo.action_done]
    audit:
      record: true
"""
    path = tmp_path / "_standard_actions.yaml"
    path.write_text(declaration, encoding="utf-8")

    try:
        StandardActionLoader.load(str(tmp_path))
        action = StandardActionLoader._actions[0]
        assert action.object_types == ["product"]
        assert action.params[0]["name"] == "reason"
        assert action.preconditions["status_in"] == ["draft"]
        assert action.effects[0]["to"] == "active"
        assert action.emits == ["demo.action_done"]
        assert action.audit == {"record": True}
    finally:
        StandardActionLoader.load(str(SCHEMAS_DIR))


# ────────────────────────────────────────────
# 结构校验（纯函数）
# ────────────────────────────────────────────
def _action(**overrides):
    base = {"id": "demo", "name": "演示", "action_type": "business"}
    base.update(overrides)
    return base


def test_lint_actions_accepts_valid_declaration():
    action = _action(
        object_types=["product"],
        params=[{"name": "reason", "source": "request"}],
        preconditions={"status_in": ["draft"], "role_any": ["admin"]},
        effects=[{"type": "transition", "field": "status", "to": "active"}],
        emits=["demo.done"],
        audit={"record": True, "reason_required": False},
    )
    assert lint_actions([action], SEED_ROLES, {"demo.done"}) == []


def test_lint_actions_rejects_unknown_role():
    action = _action(preconditions={"role_any": ["ghost"]})
    violations = lint_actions([action], SEED_ROLES, set())
    assert any("role_any" in field for _aid, field, _reason in violations)


def test_lint_actions_rejects_unknown_effect_type():
    action = _action(effects=[{"type": "explode"}])
    violations = lint_actions([action], SEED_ROLES, set())
    assert any("effects[0].type" == field for _aid, field, _reason in violations)


def test_lint_actions_transition_requires_field_and_to():
    action = _action(effects=[{"type": "transition"}])
    fields = {field for _aid, field, _reason in lint_actions([action], SEED_ROLES, set())}
    assert "effects[0].field" in fields
    assert "effects[0].to" in fields


def test_lint_actions_rejects_unregistered_emit():
    action = _action(emits=["demo.unknown"])
    violations = lint_actions([action], SEED_ROLES, {"demo.known"})
    assert any("emits" == field for _aid, field, _reason in violations)


def test_lint_actions_rejects_unknown_precondition_key():
    action = _action(preconditions={"whenever": []})
    violations = lint_actions([action], SEED_ROLES, set())
    assert any(field == "preconditions.whenever" for _aid, field, _reason in violations)


# ────────────────────────────────────────────
# A-02-2 lint 退出码
# ────────────────────────────────────────────
def test_lint_metamodel_actions_passes():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "meta" / "tools" / "lint_metamodel.py"), "--actions"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "TEST_ENTRY": "1"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "声明-实现签名差异: 0" in proc.stdout
    assert "0 violation(s)" in proc.stdout