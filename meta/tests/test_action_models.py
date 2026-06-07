"""Test action_models.py - FR-LOG-001/002"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestActionKind:
    """FR-LOG-001: ActionKind 枚举（2 种）"""

    def test_instance_value(self):
        from meta.core.action_models import ActionKind
        assert ActionKind.INSTANCE.value == "instance"

    def test_static_value(self):
        from meta.core.action_models import ActionKind
        assert ActionKind.STATIC.value == "static"

    def test_only_two_kinds(self):
        """2 种（用户决策）"""
        from meta.core.action_models import ActionKind
        assert len(ActionKind) == 2


class TestActionOutcome:
    """FR-LOG-002: ActionOutcome 枚举（4 种）"""

    def test_success_value(self):
        from meta.core.action_models import ActionOutcome
        assert ActionOutcome.SUCCESS.value == "success"

    def test_failure_value(self):
        from meta.core.action_models import ActionOutcome
        assert ActionOutcome.FAILURE.value == "failure"

    def test_denied_value(self):
        from meta.core.action_models import ActionOutcome
        assert ActionOutcome.DENIED.value == "denied"

    def test_retry_value(self):
        from meta.core.action_models import ActionOutcome
        assert ActionOutcome.RETRY.value == "retry"

    def test_four_outcomes(self):
        from meta.core.action_models import ActionOutcome
        assert len(ActionOutcome) == 4


class TestActionMeta:
    """ActionMeta dataclass + FR-LOG-003 默认值"""

    def test_default_kind_is_instance(self):
        from meta.core.action_models import ActionMeta, ActionKind
        m = ActionMeta(id="x")
        assert m.kind == ActionKind.INSTANCE

    def test_default_audit_is_true(self):
        """opt-out 默认 false (audit 默认 true)"""
        from meta.core.action_models import ActionMeta
        m = ActionMeta(id="x")
        assert m.audit is True

    def test_opt_out(self):
        from meta.core.action_models import ActionMeta, ActionKind
        m = ActionMeta(id="export", kind=ActionKind.STATIC, audit=False)
        assert m.audit is False
        assert m.kind == ActionKind.STATIC

    def test_resource_verb_property(self):
        from meta.core.action_models import ActionMeta
        m = ActionMeta(id="user.updated", verb="updated")
        assert m.resource_verb == "updated"

    def test_to_dict(self):
        from meta.core.action_models import ActionMeta, ActionKind
        m = ActionMeta(id="set_current", kind=ActionKind.STATIC, audit=False, verb="set_current")
        d = m.to_dict()
        assert d["id"] == "set_current"
        assert d["kind"] == "static"
        assert d["audit"] is False
        assert d["verb"] == "set_current"


class TestConstants:
    """默认常量"""

    def test_default_retention_days_is_180(self):
        """FR-LOG-008: 6 月保留 = 180 天"""
        from meta.core.action_models import DEFAULT_RETENTION_DAYS
        assert DEFAULT_RETENTION_DAYS == 180

    def test_sensitive_fields_contains_password(self):
        """TBD-5: 敏感字段脱敏"""
        from meta.core.action_models import SENSITIVE_FIELDS
        assert "password" in SENSITIVE_FIELDS
        assert "token" in SENSITIVE_FIELDS
        assert "secret" in SENSITIVE_FIELDS


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
