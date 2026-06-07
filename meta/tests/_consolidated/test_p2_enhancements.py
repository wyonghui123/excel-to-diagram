# -*- coding: utf-8 -*-
"""
P2 增强能力测试

测试 P2 阶段新增的功能：
- P2-8: Render Hints
- P2-7: State Transition 注解
- P2-10: Deep Insert API
"""

import pytest
from meta.core.models import (
    RenderHints,
    StateTransitionSideEffect,
    StateTransitionUIHints,
    UIAnnotation,
)


class TestRenderHints:
    """Render Hints 测试"""

    def test_render_hints_defaults(self):
        """RenderHints 默认值测试"""
        rh = RenderHints()
        assert rh.searchable is True
        assert rh.sortable is True
        assert rh.prominent is False
        assert rh.display_mode == "auto"
        assert rh.hidden_if_empty is False
        assert rh.show_in_summary is True
        assert rh.show_in_detail is True
        assert rh.show_in_list is True
        assert rh.column_width == 0
        assert rh.text_align == "left"

    def test_render_hints_custom_values(self):
        """RenderHints 自定义值测试"""
        rh = RenderHints(
            searchable=False,
            sortable=False,
            prominent=True,
            display_mode="chip",
            column_width=150,
            text_align="center",
            format_pattern="yyyy-MM-dd",
            placeholder="请输入",
            help_text="帮助文本",
        )
        assert rh.searchable is False
        assert rh.sortable is False
        assert rh.prominent is True
        assert rh.display_mode == "chip"
        assert rh.column_width == 150
        assert rh.text_align == "center"
        assert rh.format_pattern == "yyyy-MM-dd"

    def test_ui_annotation_with_render_hints(self):
        """UIAnnotation 包含 render_hints 测试"""
        ui = UIAnnotation(
            widget="input",
            visible=True,
            render_hints=RenderHints(searchable=False, prominent=True),
        )
        assert ui.render_hints is not None
        assert ui.render_hints.searchable is False
        assert ui.render_hints.prominent is True


class TestStateTransitionEnhancements:
    """State Transition 增强测试"""

    def test_side_effect_creation(self):
        """StateTransitionSideEffect 创建测试"""
        se = StateTransitionSideEffect(
            type="set_fields",
            target="self",
            value={"status": "completed"},
        )
        assert se.type == "set_fields"
        assert se.target == "self"
        assert se.value == {"status": "completed"}

    def test_side_effect_with_handler(self):
        """StateTransitionSideEffect 带 handler 测试"""
        se = StateTransitionSideEffect(
            type="trigger",
            handler="meta.handlers.send_notification",
        )
        assert se.type == "trigger"
        assert se.handler == "meta.handlers.send_notification"

    def test_ui_hints_creation(self):
        """StateTransitionUIHints 创建测试"""
        uh = StateTransitionUIHints(
            hidden=False,
            label="提交审批",
            icon="send",
            confirm_message="确定要提交审批吗？",
            highlight=True,
        )
        assert uh.label == "提交审批"
        assert uh.icon == "send"
        assert uh.confirm_message == "确定要提交审批吗？"
        assert uh.highlight is True

    def test_ui_hints_defaults(self):
        """StateTransitionUIHints 默认值测试"""
        uh = StateTransitionUIHints()
        assert uh.hidden is False
        assert uh.label == ""
        assert uh.icon == ""
        assert uh.confirm_message == ""
        assert uh.highlight is False


class TestDeepInsertAPI:
    """Deep Insert API 测试"""

    def test_deep_insert_endpoint_exists(self):
        """Deep Insert 端点存在测试"""
        from meta.tests.conftest import get_shared_app

        app, _ = get_shared_app()
        rules = [r.rule for r in app.url_map.iter_rules()]
        assert any("/<object_type>/deep" in r for r in rules)

    def test_deep_insert_request_format(self):
        """Deep Insert 请求格式测试"""
        request_body = {
            "parent": {
                "name": "测试领域",
                "code": "TEST_DOMAIN",
            },
            "children": {
                "sub_domain": [
                    {"name": "子领域1", "code": "SUB1"},
                    {"name": "子领域2", "code": "SUB2"},
                ]
            }
        }
        assert "parent" in request_body
        assert "children" in request_body
        assert len(request_body["children"]["sub_domain"]) == 2

    def test_deep_insert_simplified_format(self):
        """Deep Insert 简化格式测试"""
        request_body = {
            "name": "测试领域",
            "code": "TEST_DOMAIN",
            "_children": {
                "sub_domain": [
                    {"name": "子领域1", "code": "SUB1"},
                ]
            }
        }
        parent_data = {k: v for k, v in request_body.items() if not k.startswith("_")}
        children_data = request_body.get("_children", {})
        assert parent_data == {"name": "测试领域", "code": "TEST_DOMAIN"}
        assert "sub_domain" in children_data


class TestP2Integration:
    """P2 集成测试"""

    def test_render_hints_in_ui_annotation(self):
        """RenderHints 集成到 UIAnnotation 测试"""
        ui = UIAnnotation(
            widget="select",
            relation="user",
            display_field="display_name",
            render_hints=RenderHints(
                searchable=True,
                sortable=False,
                show_in_list=True,
            )
        )
        assert ui.widget == "select"
        assert ui.render_hints.searchable is True
        assert ui.render_hints.sortable is False

    def test_state_transition_with_enhancements(self):
        """State Transition 增强集成测试"""
        from meta.core.models import MetaStateTransition, RuleScope, RuleTrigger

        st = MetaStateTransition(
            id="submit_for_approval",
            name="提交审批",
            state_field="status",
            from_states=["draft"],
            to_state="pending",
            validation_expression="self.amount > 0",
            validation_message="金额必须大于0",
            side_effects=[
                StateTransitionSideEffect(
                    type="set_fields",
                    target="self",
                    value={"submitted_at": "$now"},
                )
            ],
            ui_hints=StateTransitionUIHints(
                label="提交",
                icon="send",
                confirm_message="确定提交？",
            ),
        )
        assert st.state_field == "status"
        assert st.from_states == ["draft"]
        assert st.to_state == "pending"
        assert st.validation_expression == "self.amount > 0"
        assert len(st.side_effects) == 1
        assert st.ui_hints.label == "提交"
