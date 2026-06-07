import pytest

pytestmark = pytest.mark.integration

import pytest
from meta.core.condition_evaluator import ConditionEvaluator
from meta.core.models import (
    DeletabilityConfig,
    AddabilityConfig,
    ActionPrecondition,
    ActionEffect,
    ActionBehavior,
    MetaAction,
    ActionType,
)
from meta import get_meta_object


class TestConditionEvaluatorBasic:
    def test_empty_condition_returns_true(self):
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate("") is True
        assert evaluator.evaluate("  ") is True

    def test_equality_operator(self):
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate("status == 'active'", {"self": {"status": "active"}}) is True
        assert evaluator.evaluate("status == 'active'", {"self": {"status": "inactive"}}) is False

    def test_inequality_operator(self):
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate("status != 'released'", {"self": {"status": "draft"}}) is True
        assert evaluator.evaluate("status != 'released'", {"self": {"status": "released"}}) is False

    def test_comparison_operators(self):
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate("count > 0", {"self": {"count": 5}}) is True
        assert evaluator.evaluate("count > 0", {"self": {"count": 0}}) is False
        assert evaluator.evaluate("count >= 5", {"self": {"count": 5}}) is True
        assert evaluator.evaluate("count < 10", {"self": {"count": 3}}) is True
        assert evaluator.evaluate("count <= 3", {"self": {"count": 3}}) is True

    def test_and_operator(self):
        evaluator = ConditionEvaluator()
        ctx = {"self": {"status": "active", "count": 0}}
        assert evaluator.evaluate("status == 'active' and count == 0", ctx) is True
        assert evaluator.evaluate("status == 'active' and count > 0", ctx) is False

    def test_or_operator(self):
        evaluator = ConditionEvaluator()
        ctx = {"self": {"status": "draft", "count": 0}}
        assert evaluator.evaluate("status == 'draft' or count > 0", ctx) is True
        assert evaluator.evaluate("status == 'active' or count > 0", ctx) is False

    def test_not_operator(self):
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate("not status == 'released'", {"self": {"status": "draft"}}) is True
        assert evaluator.evaluate("not status == 'released'", {"self": {"status": "released"}}) is False

    def test_in_operator(self):
        evaluator = ConditionEvaluator()
        ctx = {"self": {"status": "open"}}
        assert evaluator.evaluate("status in ['open', 'draft']", ctx) is True
        assert evaluator.evaluate("status in ['released', 'closed']", ctx) is False

    def test_boolean_values(self):
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate("is_active == True", {"self": {"is_active": True}}) is True
        assert evaluator.evaluate("is_active == False", {"self": {"is_active": False}}) is True

    def test_self_field_access(self):
        evaluator = ConditionEvaluator()
        ctx = {"self": {"relation_count": 0}}
        assert evaluator.evaluate("self.relation_count == 0", ctx) is True
        assert evaluator.evaluate("self.relation_count > 0", ctx) is False

    def test_parent_field_access(self):
        evaluator = ConditionEvaluator()
        ctx = {"self": {}, "parent": {"status": "open"}}
        assert evaluator.evaluate("parent.status == 'open'", ctx) is True
        assert evaluator.evaluate("parent.status == 'closed'", ctx) is False

    def test_evaluate_with_message_success(self):
        evaluator = ConditionEvaluator()
        result, msg = evaluator.evaluate_with_message(
            "status == 'active'",
            "状态不活跃",
            context={"self": {"status": "active"}},
        )
        assert result is True
        assert msg == ""

    def test_evaluate_with_message_failure(self):
        evaluator = ConditionEvaluator()
        result, msg = evaluator.evaluate_with_message(
            "status == 'active'",
            "状态不活跃",
            context={"self": {"status": "inactive"}},
        )
        assert result is False
        assert msg == "状态不活跃"

    def test_invalid_expression_returns_false(self):
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate("invalid syntax here @#$", {"self": {}}) is False

    def test_missing_field_returns_falsy(self):
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate("self.nonexistent == 'x'", {"self": {}}) is False


class TestDeletabilityConfig:
    def test_deletability_config_creation(self):
        config = DeletabilityConfig(
            condition="status != 'released'",
            message="已发布的数据不能删除",
        )
        assert config.condition == "status != 'released'"
        assert config.message == "已发布的数据不能删除"

    def test_deletability_config_defaults(self):
        config = DeletabilityConfig()
        assert config.condition == ""
        assert config.message == ""


class TestAddabilityConfig:
    def test_addability_config_creation(self):
        config = AddabilityConfig(
            condition="parent.status in ['open', 'draft']",
            message="父对象状态不允许新增",
        )
        assert config.condition == "parent.status in ['open', 'draft']"
        assert config.message == "父对象状态不允许新增"


class TestActionBehavior:
    def test_action_precondition(self):
        pc = ActionPrecondition(
            condition="status == 'active'",
            message="非活跃状态不能执行",
        )
        assert pc.condition == "status == 'active'"
        assert pc.message == "非活跃状态不能执行"

    def test_action_effect_set_fields(self):
        effect = ActionEffect(
            type="set_fields",
            target="self",
            fields={"role": "$parameters.new_role", "updated_at": "$now"},
        )
        assert effect.type == "set_fields"
        assert effect.target == "self"
        assert "role" in effect.fields
        assert "updated_at" in effect.fields

    def test_action_effect_trigger(self):
        effect = ActionEffect(
            type="trigger",
            handler="meta.handlers.promote_handler",
        )
        assert effect.type == "trigger"
        assert effect.handler == "meta.handlers.promote_handler"

    def test_action_behavior_full(self):
        behavior = ActionBehavior(
            precondition=ActionPrecondition(
                condition="status == 'active'",
                message="非活跃状态不能执行",
            ),
            effects=[
                ActionEffect(
                    type="set_fields",
                    target="self",
                    fields={"status": "promoted", "promoted_at": "$now"},
                ),
            ],
        )
        assert behavior.precondition is not None
        assert behavior.precondition.condition == "status == 'active'"
        assert len(behavior.effects) == 1
        assert behavior.effects[0].type == "set_fields"

    def test_action_behavior_defaults(self):
        behavior = ActionBehavior()
        assert behavior.precondition is None
        assert len(behavior.effects) == 0


class TestYamlDeletabilityParsing:
    def test_domain_has_deletability(self):
        domain = get_meta_object('domain')
        assert domain is not None, "domain not found in registry"
        assert domain.deletability is not None
        assert "child_count == 0" in domain.deletability.condition
        assert "relation_count == 0" in domain.deletability.condition
        assert domain.deletability.message == "存在子领域或关联关系的领域不能删除"

    def test_business_object_has_deletability(self):
        bo = get_meta_object('business_object')
        assert bo is not None, "bo not found in registry"
        assert bo.deletability is not None
        assert bo.deletability.condition == "self.relation_count == 0"
        assert bo.deletability.message == "存在关联关系的业务对象不能删除"

    def test_schema_without_deletability(self):
        relationship = get_meta_object('relationship')
        assert relationship is not None, "relationship not found in registry"
        assert relationship.deletability is not None, "relationship should have deletability config"
        assert relationship.deletability.condition == "true"
        assert relationship.deletability.message == "关系可随时删除"

    def test_schema_without_addability(self):
        domain = get_meta_object('domain')
        assert domain is not None, "domain not found in registry"
        assert domain.addability is None


class TestManageServiceDeletabilityCheck:
    def test_check_can_delete_no_config(self):
        from meta.services.manage_service import ManageService
        from meta.core.datasource import get_data_source
        import os

        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db'
        )
        ds = get_data_source("sqlite", database=db_path)
        service = ManageService(ds)

        result = service.check_can_delete('user', {'id': 1})
        assert result is True

    def test_check_can_delete_with_config_pass(self):
        from meta.services.manage_service import ManageService
        from meta.core.datasource import get_data_source
        import os

        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db'
        )
        ds = get_data_source("sqlite", database=db_path)
        service = ManageService(ds)

        result = service.check_can_delete('domain', {'relation_count': 0})
        assert result is True

    def test_check_can_delete_with_config_fail(self):
        from meta.services.manage_service import ManageService
        from meta.core.datasource import get_data_source
        import os

        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db'
        )
        ds = get_data_source("sqlite", database=db_path)
        service = ManageService(ds)

        result = service.check_can_delete('domain', {'relation_count': 5})
        assert result is False

    def test_check_can_add_no_config(self):
        from meta.services.manage_service import ManageService
        from meta.core.datasource import get_data_source
        import os

        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db'
        )
        ds = get_data_source("sqlite", database=db_path)
        service = ManageService(ds)

        result = service.check_can_add('domain', {})
        assert result is True
