# -*- coding: utf-8 -*-
"""
ui_actions_resolved 单元测试 (v3.18 enum-mgmt-spec FR-012)

[NEW] 2026-06-13 批次: 验证 compute_ui_actions() 在不同
(category, mutability, value_count) 组合下的返回结果。

规则对应 meta/schemas/enum_type.yaml 中 ui_view_config.ui_actions:
  create_value:   category != 'system' AND mutability != 'locked'
  update_value:   category != 'system' AND mutability != 'locked'
  delete_value:   category != 'system' AND mutability != 'locked'
  toggle_active:  category != 'system' AND mutability != 'locked'
  update_type:    category != 'system'
  delete_type:    category != 'system' AND value_count == 0
"""
import pytest

pytestmark = pytest.mark.unit

from meta.api.enum_api import compute_ui_actions


# ─────────────────────────────────────────────
# 字段完整性: 所有 6 个 action 必须在结果中
# ─────────────────────────────────────────────

class TestUIActionsStructure:
    """结构测试: 6 个 action key 必须在结果中"""

    REQUIRED_ACTIONS = [
        'create_value', 'update_value', 'delete_value',
        'toggle_active', 'update_type', 'delete_type',
    ]

    @pytest.mark.parametrize('enum_type', [
        {'category': 'business', 'mutability': 'fullEditable', 'value_count': 0},
        {'category': 'business', 'mutability': 'extensible', 'value_count': 5},
        {'category': 'business', 'mutability': 'locked', 'value_count': 10},
        {'category': 'system', 'mutability': 'locked', 'value_count': 0},
        {'category': 'system', 'mutability': 'extensible', 'value_count': 100},
    ])
    def test_all_six_actions_present(self, enum_type):
        result = compute_ui_actions(enum_type)
        for action in self.REQUIRED_ACTIONS:
            assert action in result, f"缺少 action '{action}'"

    @pytest.mark.parametrize('enum_type', [
        {'category': 'business', 'mutability': 'fullEditable', 'value_count': 0},
        {'category': 'business', 'mutability': 'extensible', 'value_count': 5},
        {'category': 'business', 'mutability': 'locked', 'value_count': 10},
    ])
    def test_all_values_are_bool(self, enum_type):
        result = compute_ui_actions(enum_type)
        for action, val in result.items():
            assert isinstance(val, bool), (
                f"action '{action}' 应是 bool, 实际: {type(val).__name__}={val}"
            )


# ─────────────────────────────────────────────
# business + fullEditable: 全部允许 (除 delete_type 需 value_count==0)
# ─────────────────────────────────────────────

class TestBusinessFullEditable:

    def test_no_values_all_actions_allowed(self):
        """business + fullEditable + value_count=0: 除 delete_type 不允许 (有值才能删) 外, 全部允许"""
        # Wait, actually delete_type when value_count==0 SHOULD be allowed (delete empty type)
        # Re-read the rule: delete_type: not is_sys_enum AND not has_values
        # not has_values = value_count == 0
        # So delete_type IS allowed when value_count == 0
        result = compute_ui_actions({
            'category': 'business', 'mutability': 'fullEditable', 'value_count': 0,
        })
        assert result == {
            'create_value': True,
            'update_value': True,
            'delete_value': True,
            'toggle_active': True,
            'update_type': True,
            'delete_type': True,  # 因为 value_count=0
        }

    def test_with_values_delete_type_blocked(self):
        """business + fullEditable + value_count>0: delete_type 不可 (有值不能删类型)"""
        result = compute_ui_actions({
            'category': 'business', 'mutability': 'fullEditable', 'value_count': 5,
        })
        assert result == {
            'create_value': True,
            'update_value': True,
            'delete_value': True,
            'toggle_active': True,
            'update_type': True,
            'delete_type': False,  # 因为 value_count>0
        }


# ─────────────────────────────────────────────
# business + extensible: 跟 fullEditable 行为一致
# (因为 rules 都不区分 fullEditable vs extensible, 都是非 locked)
# ─────────────────────────────────────────────

class TestBusinessExtensible:

    def test_no_values(self):
        result = compute_ui_actions({
            'category': 'business', 'mutability': 'extensible', 'value_count': 0,
        })
        assert result['create_value'] is True
        assert result['update_value'] is True
        assert result['delete_value'] is True
        assert result['toggle_active'] is True
        assert result['update_type'] is True
        assert result['delete_type'] is True

    def test_with_values(self):
        result = compute_ui_actions({
            'category': 'business', 'mutability': 'extensible', 'value_count': 3,
        })
        assert result['create_value'] is True
        assert result['update_value'] is True
        assert result['delete_value'] is True
        assert result['toggle_active'] is True
        assert result['update_type'] is True
        assert result['delete_type'] is False


# ─────────────────────────────────────────────
# business + locked: enum_value 相关禁止, enum_type 仍可改 (但 delete_type 看 value_count)
# ─────────────────────────────────────────────

class TestBusinessLocked:

    def test_no_values_value_actions_blocked(self):
        """business + locked + value_count=0: 4 个 value action 全部禁止, type 仍可改可删"""
        result = compute_ui_actions({
            'category': 'business', 'mutability': 'locked', 'value_count': 0,
        })
        assert result == {
            'create_value': False,  # locked
            'update_value': False,  # locked
            'delete_value': False,  # locked
            'toggle_active': False,  # locked
            'update_type': True,    # business 可改类型
            'delete_type': True,    # value_count=0 可删类型
        }

    def test_with_values_delete_type_blocked(self):
        """business + locked + value_count>0: value 全部禁 + delete_type 也禁"""
        result = compute_ui_actions({
            'category': 'business', 'mutability': 'locked', 'value_count': 10,
        })
        assert result == {
            'create_value': False,
            'update_value': False,
            'delete_value': False,
            'toggle_active': False,
            'update_type': True,    # 业务枚举可改
            'delete_type': False,   # 有值不能删
        }


# ─────────────────────────────────────────────
# system + 任何 mutability: 全部禁止 (system 不可改)
# ─────────────────────────────────────────────

class TestSystemAnyMutability:

    @pytest.mark.parametrize('mutability', ['fullEditable', 'extensible', 'locked'])
    def test_system_all_actions_blocked(self, mutability):
        """system 枚举: 任何 mutability, 任何 value_count → 全部禁止"""
        # system + has values → delete_type 也不允许
        result = compute_ui_actions({
            'category': 'system', 'mutability': mutability, 'value_count': 5,
        })
        assert result == {
            'create_value': False,
            'update_value': False,
            'delete_value': False,
            'toggle_active': False,
            'update_type': False,  # system 不可改
            'delete_type': False,  # system 不可删
        }

    @pytest.mark.parametrize('mutability', ['fullEditable', 'extensible', 'locked'])
    def test_system_no_values_still_all_blocked(self, mutability):
        """system 枚举 + value_count=0: 仍然全部禁止 (system 比 has_values 优先级高)"""
        result = compute_ui_actions({
            'category': 'system', 'mutability': mutability, 'value_count': 0,
        })
        assert result['delete_type'] is False, "system 不可删, 即使 value_count=0"
        assert result['update_type'] is False, "system 不可改"


# ─────────────────────────────────────────────
# 边界: value_count 缺失 / None / 负数
# ─────────────────────────────────────────────

class TestValueCountEdgeCases:

    def test_missing_value_count_treated_as_zero(self):
        """value_count 字段缺失 → 当 0 处理 → delete_type 允许"""
        result = compute_ui_actions({
            'category': 'business', 'mutability': 'extensible',
            # value_count 缺失
        })
        # value_count 缺失 → has_values=False → delete_type=True
        assert result['delete_type'] is True

    def test_none_value_count_treated_as_zero(self):
        result = compute_ui_actions({
            'category': 'business', 'mutability': 'extensible', 'value_count': None,
        })
        assert result['delete_type'] is True

    def test_zero_value_count(self):
        result = compute_ui_actions({
            'category': 'business', 'mutability': 'extensible', 'value_count': 0,
        })
        assert result['delete_type'] is True


# ─────────────────────────────────────────────
# 边界: category / mutability 缺失
# ─────────────────────────────────────────────

class TestCategoryMutabilityDefaults:

    def test_missing_category_defaults_to_business(self):
        """category 缺失 → 默认 business → value 行为允许"""
        result = compute_ui_actions({
            'mutability': 'extensible', 'value_count': 0,
        })
        assert result['create_value'] is True
        assert result['update_type'] is True
        assert result['delete_type'] is True

    def test_missing_mutability_defaults_to_extensible(self):
        """mutability 缺失 → 默认 extensible (非 locked) → value 行为允许"""
        result = compute_ui_actions({
            'category': 'business', 'value_count': 0,
        })
        assert result['create_value'] is True
        assert result['update_value'] is True
        assert result['delete_value'] is True
        assert result['toggle_active'] is True

    def test_empty_dict_defaults(self):
        """空 dict: category=business, mutability=extensible, value_count=0 → 全允许"""
        result = compute_ui_actions({})
        assert result == {
            'create_value': True,
            'update_value': True,
            'delete_value': True,
            'toggle_active': True,
            'update_type': True,
            'delete_type': True,
        }


# ─────────────────────────────────────────────
# 关键 case: system + has_values (组合矩阵)
# ─────────────────────────────────────────────

class TestSystemWithValues:

    def test_system_with_values_delete_type_blocked_by_system(self):
        """system + value_count>0: system 阻止 (即使 value_count=0 也会被 system 阻止)"""
        result = compute_ui_actions({
            'category': 'system', 'mutability': 'extensible', 'value_count': 100,
        })
        # system 优先级最高, delete_type=False
        assert result['delete_type'] is False


# ─────────────────────────────────────────────
# 关键 case: 验证 locked + system 双重保护
# ─────────────────────────────────────────────

class TestDoubleProtection:

    def test_locked_and_system_still_all_blocked(self):
        """locked + system 双重保护: 全部 false"""
        result = compute_ui_actions({
            'category': 'system', 'mutability': 'locked', 'value_count': 0,
        })
        for action, val in result.items():
            assert val is False, f"system+locked 下 {action} 应为 False, 实际 {val}"


# ─────────────────────────────────────────────
# 元数据一致性: 跟 enum_type.yaml ui_view_config.ui_actions 字段对齐
# ─────────────────────────────────────────────

class TestConsistencyWithYAMLSchema:
    """结果 action 列表必须跟 YAML ui_view_config.ui_actions 完全对齐"""

    EXPECTED_ACTIONS = {
        'create_value', 'update_value', 'delete_value',
        'toggle_active', 'update_type', 'delete_type',
    }

    def test_action_set_matches_yaml(self):
        """compute_ui_actions 返回的 keys 应是 YAML 中定义的 6 个 actions"""
        result = compute_ui_actions({
            'category': 'business', 'mutability': 'extensible', 'value_count': 0,
        })
        assert set(result.keys()) == self.EXPECTED_ACTIONS

    def test_no_extra_actions(self):
        result = compute_ui_actions({
            'category': 'business', 'mutability': 'extensible', 'value_count': 0,
        })
        extra = set(result.keys()) - self.EXPECTED_ACTIONS
        assert not extra, f"compute_ui_actions 返回了 YAML 没定义的 actions: {extra}"

    def test_no_missing_actions(self):
        result = compute_ui_actions({
            'category': 'business', 'mutability': 'extensible', 'value_count': 0,
        })
        missing = self.EXPECTED_ACTIONS - set(result.keys())
        assert not missing, f"compute_ui_actions 漏掉了 actions: {missing}"
