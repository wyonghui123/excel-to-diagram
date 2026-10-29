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


class TestSensitiveFieldSingleSource:
    """[P1 2026-10-29] 敏感字段单一声明的一致性锁定

    依据: docs/superpowers/specs/2026-10-29-pii-field-level-security-spec.md §7
    三处调用点（写面脱敏 / UI 隐藏 / 日志文本匹配）均为同一张声明表的派生视图，
    任一派生集合漂移即由本组断言拦截。
    """

    def test_declaration_ids_unique(self):
        from meta.core.security.sensitive_fields import SECRET_FIELD_DECLARATIONS
        ids = [d.id for d in SECRET_FIELD_DECLARATIONS]
        assert len(ids) == len(set(ids))

    def test_derived_views_match_declarations(self):
        from meta.core.security import sensitive_fields as sf
        assert sf.LOG_REDACT_IDS == frozenset(
            d.id for d in sf.SECRET_FIELD_DECLARATIONS if d.log_redact)
        assert sf.UI_HIDDEN_IDS == frozenset(
            d.id for d in sf.SECRET_FIELD_DECLARATIONS if d.ui_hidden)

    def test_three_call_sites_are_derived_views(self):
        """三处 re-export 必须是同一对象，不得各自维护副本"""
        from meta.core.action_models import SENSITIVE_FIELDS as write_side
        from meta.core.ui_config.config_constants import SENSITIVE_FIELDS as ui_side
        from meta.services.log_filter_service import SENSITIVE_KEYS as log_side
        from meta.core.security import sensitive_fields as sf
        assert write_side is sf.LOG_REDACT_IDS
        assert ui_side is sf.UI_HIDDEN_IDS
        assert log_side is sf.LOG_TEXT_KEYS

    def test_password_visible_in_ui_but_redacted_in_log(self):
        """`password` 是 virtual 输入字段：UI 必须可见，写面/日志必须脱敏"""
        from meta.core.security import sensitive_fields as sf
        assert 'password' in sf.LOG_REDACT_IDS
        assert 'password' not in sf.UI_HIDDEN_IDS

    def test_non_field_log_keys_not_promoted_to_field_ids(self):
        """日志键（cookie/ssn 等）不是字段 id，不得混入派生的字段集合"""
        from meta.core.security import sensitive_fields as sf
        field_ids = {d.id for d in sf.SECRET_FIELD_DECLARATIONS}
        for key in ('cookie', 'ssn', 'id_number'):
            assert key in sf.LOG_TEXT_KEYS
            assert key not in field_ids


class TestSensitivityAnnotationParsing:
    """[P3 2026-10-29] sensitivity / 字段级权限位必须真正进入 semantics

    背景：`user.yaml` 早就写了 `sensitivity: restricted`，但 parse_semantics
    未透传、SemanticAnnotation 无该字段 ⇒ `_should_export_field` 的
    getattr 恒为 None，标记是"死"的（TBD-10 同类坑）。本组锁定解析链路，
    防止再次出现"写了不生效"。
    """

    def test_parse_semantics_carries_sensitivity(self):
        from meta.core.yaml_loader import parse_semantics
        ann = parse_semantics({'meaning': 'x', 'sensitivity': 'restricted'})
        assert ann.sensitivity == 'restricted'

    def test_parse_semantics_carries_permission_bits(self):
        from meta.core.yaml_loader import parse_semantics
        ann = parse_semantics({
            'meaning': 'x',
            'read_permission': 'person_profile_read',
            'write_permission': 'person_profile_update',
        })
        assert ann.read_permission == 'person_profile_read'
        assert ann.write_permission == 'person_profile_update'

    def test_parse_semantics_defaults_are_empty(self):
        from meta.core.yaml_loader import parse_semantics
        ann = parse_semantics({'meaning': 'x'})
        assert ann.sensitivity == ''
        assert ann.read_permission == ''
        assert ann.write_permission == ''


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
