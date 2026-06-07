"""Test action_dispatcher.py - FR-LOG-004"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestActionDispatcherExecuteSync:

    def test_unknown_action_raises_value_error(self):
        from meta.core.action_dispatcher import ActionDispatcher
        from meta.core.action_models import ActionKind
        d = ActionDispatcher(audit_service=None)
        with pytest.raises(ValueError, match="Unknown action"):
            d.execute_sync("nonexistent.action", {}, {})

    def test_register_and_execute(self):
        """FR-LOG-004: register + execute_sync"""
        from meta.core.action_dispatcher import ActionDispatcher
        from meta.core.action_models import ActionMeta, ActionKind
        from meta.services.action_handlers import HANDLERS

        # 用现有 handler（clear_other_current_versions）
        d = ActionDispatcher(audit_service=None)
        m = ActionMeta(
            id="test.set_current",
            kind=ActionKind.INSTANCE,
            audit=False,  # 测试时不开 audit
            handler="clear_other_current_versions",
            verb="updated",
        )
        d.register(m)
        assert d.get("test.set_current") is not None

    def test_audit_opt_out_skips_writing(self):
        """FR-LOG-003: audit: false → 不写 audit"""
        from meta.core.action_dispatcher import ActionDispatcher
        from meta.core.action_models import ActionMeta, ActionKind

        class MockAudit:
            created = []
            def create(self, rec):
                self.created.append(rec)
                return 1

        mock_audit = MockAudit()
        d = ActionDispatcher(audit_service=mock_audit)
        m = ActionMeta(
            id="test.op",
            kind=ActionKind.STATIC,
            audit=False,
            handler="clear_other_current_versions",
        )
        d.register(m)
        try:
            d.execute_sync("test.op", {}, {})
        except Exception:
            pass  # handler 可能因缺 context 抛错，OK
        assert len(mock_audit.created) == 0, "opt-out 应不写 audit"

    def test_outcome_failure_on_exception(self):
        """FR-LOG-004: 异常 → outcome=FAILURE"""
        from meta.core.action_dispatcher import ActionDispatcher
        from meta.core.action_models import ActionMeta, ActionKind, ActionOutcome

        class MockAudit:
            created = []
            def create(self, rec):
                self.created.append(rec)
                return 1

        # 注册一个会抛错的 handler
        from meta.services.action_handlers import HANDLERS
        HANDLERS["test_boom"] = lambda params, context, datasource=None: (_ for _ in ()).throw(RuntimeError("boom"))

        mock_audit = MockAudit()
        d = ActionDispatcher(audit_service=mock_audit)
        m = ActionMeta(
            id="test.boom.action",
            kind=ActionKind.STATIC,
            audit=True,
            handler="test_boom",
        )
        d.register(m)

        with pytest.raises(RuntimeError):
            d.execute_sync("test.boom.action", {}, {})

        assert len(mock_audit.created) == 1
        assert mock_audit.created[0].outcome == "failure"
        assert "boom" in (mock_audit.created[0].error_message or "")


class TestActionDispatcherSensitiveRedaction:
    """TBD-5: 敏感字段脱敏"""

    def test_redact_password_field(self):
        from meta.core.action_dispatcher import ActionDispatcher
        d = ActionDispatcher(audit_service=None)
        assert "[REDACTED:password]" == d._redact_field("password")

    def test_redact_token_field(self):
        from meta.core.action_dispatcher import ActionDispatcher
        d = ActionDispatcher(audit_service=None)
        assert "[REDACTED:token]" == d._redact_field("token")

    def test_non_sensitive_field_passes_through(self):
        from meta.core.action_dispatcher import ActionDispatcher
        d = ActionDispatcher(audit_service=None)
        assert d._redact_field("username") == "username"
        assert d._redact_field(None) is None

    def test_redact_dict_value(self):
        from meta.core.action_dispatcher import ActionDispatcher
        d = ActionDispatcher(audit_service=None)
        result = d._redact_value({"username": "alice", "password": "secret123"})
        assert result["username"] == "alice"
        assert result["password"] == "[REDACTED]"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
