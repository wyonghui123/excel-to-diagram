# -*- coding: utf-8 -*-
"""
用户服务测试

合并以下测试文件:
- test_user_state_transitions.py (用户状态转换)

测试范围:
- 用户状态转换规则
- activate_user / lock_user / deactivate_user 转换
- 状态转换执行器
"""

import pytest
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

pytestmark = pytest.mark.integration


# ==================== 用户状态转换测试 ====================

class TestUserStateTransitions:
    """用户状态转换测试"""

    def test_user_has_state_transitions(self):
        """验证用户有状态转换配置"""
        from meta.core.yaml_loader import load_yaml_file, get_yaml_schema_dir

        schema_dir = get_yaml_schema_dir()
        user_file = os.path.join(schema_dir, 'user.yaml')
        user_meta = load_yaml_file(user_file)

        state_transitions = user_meta.get_state_transitions()

        # [测试对齐 2026-10-29] lock/unlock 拆分为独立转换后共 6 条
        # （activate/deactivate/lock/unlock/freeze/unfreeze）；
        # 本用例只锁定三条核心转换的存在性，不再断言精确条数。
        st_ids = [st.id for st in state_transitions]
        assert len(state_transitions) >= 3
        assert 'activate_user' in st_ids
        assert 'lock_user' in st_ids
        assert 'deactivate_user' in st_ids

    def test_activate_user_transition(self):
        """测试 activate_user 状态转换"""
        from meta.core.yaml_loader import load_yaml_file, get_yaml_schema_dir

        schema_dir = get_yaml_schema_dir()
        user_file = os.path.join(schema_dir, 'user.yaml')
        user_meta = load_yaml_file(user_file)

        st = None
        for rule in user_meta.get_state_transitions():
            if rule.id == 'activate_user':
                st = rule
                break

        assert st is not None, "activate_user transition not found"

        assert st.state_field == 'status'
        assert 'inactive' in st.from_states
        # [PM 反馈 2026-09-13] locked 必须走 unlock_user，activate 不再兼任解锁
        assert 'locked' not in st.from_states
        assert st.to_state == 'active'
        assert st.ui_hints is not None
        assert st.ui_hints.label == '激活'
        assert st.ui_hints.icon == 'check_circle'
        assert st.ui_hints.highlight is True

    def test_lock_user_transition(self):
        """测试 lock_user 状态转换"""
        from meta.core.yaml_loader import load_yaml_file, get_yaml_schema_dir

        schema_dir = get_yaml_schema_dir()
        user_file = os.path.join(schema_dir, 'user.yaml')
        user_meta = load_yaml_file(user_file)

        st = None
        for rule in user_meta.get_state_transitions():
            if rule.id == 'lock_user':
                st = rule
                break

        assert st is not None, "lock_user transition not found"

        assert st.state_field == 'status'
        assert 'active' in st.from_states
        # [PM 反馈 2026-09-13] 锁定只能从 active 进入，inactive 需先激活
        assert 'inactive' not in st.from_states
        assert st.to_state == 'locked'

    def test_deactivate_user_transition(self):
        """测试 deactivate_user 状态转换"""
        from meta.core.yaml_loader import load_yaml_file, get_yaml_schema_dir

        schema_dir = get_yaml_schema_dir()
        user_file = os.path.join(schema_dir, 'user.yaml')
        user_meta = load_yaml_file(user_file)

        st = None
        for rule in user_meta.get_state_transitions():
            if rule.id == 'deactivate_user':
                st = rule
                break

        assert st is not None, "deactivate_user transition not found"

        assert st.state_field == 'status'
        assert 'active' in st.from_states
        # [PM 反馈 2026-09-13] locked 用户须先 unlock 才能停用
        assert 'locked' not in st.from_states
        assert st.to_state == 'inactive'

    def test_state_transition_execution(self):
        """测试状态转换执行器"""
        from meta.core.rule_executor import RuleEngine, RuleContext
        from meta.core.yaml_loader import load_yaml_file, get_yaml_schema_dir

        schema_dir = get_yaml_schema_dir()
        user_file = os.path.join(schema_dir, 'user.yaml')
        user_meta = load_yaml_file(user_file)

        engine = RuleEngine()

        st = None
        for rule in user_meta.get_state_transitions():
            if rule.id == 'activate_user':
                st = rule
                break

        assert st is not None, "activate_user transition not found"

        # [测试对齐 2026-10-29] 显式 action 调用语义：data 先写入目标状态。
        # StateTransitionExecutor 以 effective_state == to_state 判定显式切换；
        # 若 data 仍为 inactive 会命中 Case 1.5「用户未改状态」提前返回，
        # result.data 中不会带 from_state。
        context = RuleContext(
            meta_object=user_meta,
            data={'id': 1, 'username': 'test', 'status': 'active'},
            original_data={'id': 1, 'username': 'test', 'status': 'inactive'}
        )

        result = engine.state_transition_executor.execute(st, context)

        assert result.success
        assert result.data['from_state'] == 'inactive'
        assert result.data['to_state'] == 'active'
        assert context.get_field_value('status') == 'active'
