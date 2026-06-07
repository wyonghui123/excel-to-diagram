# -*- coding: utf-8 -*-
"""
[MODULE] D.8 hypothesis property-based testing 实施 (v3.18)
[DESCRIPTION] 5+ action 用 @given 自动生成边界 input
"""
import os
import sys

sys.path.insert(0, r'd:\filework\excel-to-diagram\tests\fixtures')

from admin_token import call_action  # noqa: E402

# hypothesis 库
from hypothesis import given, settings, HealthCheck  # noqa: E402
import hypothesis.strategies as st  # noqa: E402

# 自定义 strategy
from meta.tests.hypothesis_strategies import (  # noqa: E402
    st_username, st_email, st_role, st_object_id, st_event_type,
    st_channel, st_action_id, st_safe_text,
)


# [DECORATIVE] v3.18 D.8: hypothesis 装饰器顺序 — @settings 在下, @given 在上 (从下往上执行)
# 注意: 装饰器从下往上, 1. 先 @given, 2. 后 @settings

@given(username=st_username(min_size=1, max_size=20),
       password=st.text(min_size=0, max_size=30))
@settings(max_examples=10, deadline=2000,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_user_authenticate_robust(bo_action_server_check, admin_cookie, username, password):
    """[DECORATIVE] D.8: 任意 username/password, user.authenticate 不崩溃"""
    _, b = call_action('user.authenticate',
                       {'username': username, 'password': password},
                       cookie=admin_cookie)
    # 期望: 返回 dict, 不崩溃
    assert isinstance(b, dict)


@given(user_id=st_object_id())
@settings(max_examples=10, deadline=2000,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_role_check_robust(bo_action_server_check, admin_cookie, user_id):
    """[DECORATIVE] D.8: 任意 user_id, role.check 不崩溃"""
    _, b = call_action('role.check', {'user_id': user_id}, cookie=admin_cookie)
    assert isinstance(b, dict)


@given(object_type=st.text(min_size=1, max_size=30, alphabet='abcdefghijklmnopqrstuvwxyz_'))
@settings(max_examples=10, deadline=2000,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_enum_type_query_robust(bo_action_server_check, admin_cookie, object_type):
    """[DECORATIVE] D.8: 任意 object_type, enum_type.query 不崩溃"""
    _, b = call_action('enum_type.query', {'object_type': object_type}, cookie=admin_cookie)
    assert isinstance(b, dict)


@given(channel=st_channel(),
       event=st_event_type(),
       obj_id=st_object_id())
@settings(max_examples=10, deadline=2000,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_subscription_create_robust(bo_action_server_check, admin_cookie, channel, event, obj_id):
    """[DECORATIVE] D.8: 任意 channel/event, subscription.create 不崩溃"""
    _, b = call_action('subscription.create', {
        'object_type': 'user',
        'event_types': [event],
        'channel': channel,
        'webhook_url': f'http://localhost:9999/test_{event}',
    }, cookie=admin_cookie)
    assert isinstance(b, dict)


@given(text=st_safe_text(max_size=50))
@settings(max_examples=10, deadline=2000,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_batch_save_safe_text(bo_action_server_check, admin_cookie, text):
    """[DECORATIVE] D.8: 任意 safe text, batch_save 不崩溃 (含 xss 等)"""
    _, b = call_action('batch_save', {
        'object_type': 'enum_type',
        'drafts': [{
            'row_id': '__new_hypo_' + text[:5],
            'is_new': True,
            'fields': {'code': text[:20] if text else 'empty'},
        }],
    }, cookie=admin_cookie)
    assert isinstance(b, dict)
