# -*- coding: utf-8 -*-
"""
[MODULE] D.8 hypothesis property-based testing (v3.18)
[DESCRIPTION] 给 AI Coding Agent 用的 property-based testing strategies

使用:
  from hypothesis import given, settings
  from meta.tests.hypothesis_strategies import st_username, st_action_id

  @given(st_action_id())
  @settings(max_examples=20, deadline=2000)
  def test_x_action_never_crashes(action_id):
      # ... 测 action 鲁棒性

合规:
  [OK] 走 test.py 入口 (v3.17 合规)
  [OK] 用 cookie 认证
  [OK] max_examples 防止超时
"""
import string
import hypothesis.strategies as st


# [DECORATIVE] v3.18: 常用 strategy
@st.composite
def st_username(draw, min_size=3, max_size=20):
    """生成合法 username (字母数字下划线)"""
    chars = string.ascii_letters + string.digits + '_'
    return draw(st.text(alphabet=chars, min_size=min_size, max_size=max_size))


@st.composite
def st_email(draw):
    """生成 email (含 @)"""
    user = draw(st.text(alphabet=string.ascii_lowercase + string.digits + '._-',
                         min_size=1, max_size=20))
    domain = draw(st.text(alphabet=string.ascii_lowercase,
                          min_size=2, max_size=10))
    tld = draw(st.sampled_from(['com', 'org', 'net', 'io', 'test', 'local']))
    return f'{user}@{domain}.{tld}'


@st.composite
def st_password(draw, min_size=4, max_size=30):
    """生成 password (混合字符)"""
    chars = string.ascii_letters + string.digits + '!@#$%^&*'
    return draw(st.text(alphabet=chars, min_size=min_size, max_size=max_size))


@st.composite
def st_role(draw):
    """生成 role 字符串"""
    return draw(st.sampled_from(['user', 'admin', 'guest', 'operator', 'reviewer']))


@st.composite
def st_object_id(draw):
    """生成正整数 object_id"""
    return draw(st.integers(min_value=1, max_value=2**31 - 1))


@st.composite
def st_event_type(draw):
    """生成 event 类型"""
    return draw(st.sampled_from(['created', 'updated', 'deleted', 'viewed', 'shared']))


@st.composite
def st_channel(draw):
    """生成 channel 类型"""
    return draw(st.sampled_from(['webhook', 'email', 'sms', 'push']))


@st.composite
def st_action_id(draw):
    """生成 action_id (object.action 格式)"""
    objects = ['user', 'role', 'subscription', 'enum_type', 'permission',
               'session', 'audit', 'batch', 'file', 'notification']
    actions = ['get', 'list', 'create', 'update', 'delete', 'export',
               'import', 'count', 'search', 'validate']
    obj = draw(st.sampled_from(objects))
    act = draw(st.sampled_from(actions))
    return f'{obj}.{act}'


@st.composite
def st_safe_text(draw, min_size=1, max_size=100):
    """生成无特殊字符的文本 (避免 SQL 注入测试)"""
    chars = string.ascii_letters + string.digits + ' '
    return draw(st.text(alphabet=chars, min_size=min_size, max_size=max_size))


# [DECORATIVE] v3.18: 配置默认 settings
DEFAULT_SETTINGS = {
    'max_examples': 20,  # 避免超时
    'deadline': 2000,     # 2s
    'suppress_health_check': True,  # 减少 health check 警告
}
