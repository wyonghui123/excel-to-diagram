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
        assert len(state_transitions) == 3

        st_ids = [st.id for st in state_transitions]
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
        assert 'locked' in st.from_states
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
        assert 'inactive' in st.from_states
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
        assert 'locked' in st.from_states
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

        context = RuleContext(
            meta_object=user_meta,
            data={'id': 1, 'username': 'test', 'status': 'inactive'},
            original_data={'id': 1, 'username': 'test', 'status': 'inactive'}
        )

        result = engine.state_transition_executor.execute(st, context)

        assert result.success
        assert result.data['from_state'] == 'inactive'
        assert result.data['to_state'] == 'active'
        assert context.get_field_value('status') == 'active'
