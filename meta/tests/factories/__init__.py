# -*- coding: utf-8 -*-
"""
[MODULE] meta.tests.factories (v3.18 D.2)
[DESCRIPTION] Test data factories for AI Coding Agent

使用:
  from meta.tests.factories import UserFactory, SubscriptionFactory

  user = UserFactory.create(role='admin')  # 写 DB
  user = UserFactory.build()               # 仅构造, 不写 DB

合规:
  [OK] 走 cookie 认证 (走 tests/fixtures/admin_token.py)
  [OK] 复用 v3.17 体系
"""
import os
import sys
import time
import random
import string
from typing import Optional

# 默认走 admin_token 的 cookie 模式
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
_FIXTURES_DIR = os.path.join(_PROJECT_ROOT, 'tests', 'fixtures')
if _FIXTURES_DIR not in sys.path:
    sys.path.insert(0, _FIXTURES_DIR)


def _random_str(n: int = 8) -> str:
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))


class UserFactory:
    """[DECORATIVE] v3.18 D.2: User factory (AI Agent 直接造测试数据)

    字段:
      username, display_name, email, role, password
    """

    _COUNTER = 0

    @classmethod
    def _next_id(cls) -> int:
        cls._COUNTER += 1
        return cls._COUNTER

    @classmethod
    def build(cls, **kwargs) -> dict:
        """仅构造, 不写 DB"""
        n = cls._next_id()
        ts = int(time.time())
        defaults = {
            'username': kwargs.pop('username', f'user_{n}_{ts}_{_random_str(4)}'),
            'display_name': kwargs.pop('display_name', f'Test User {n}'),
            'email': kwargs.pop('email', f'user_{n}_{ts}@test.local'),
            'role': kwargs.pop('role', 'user'),
            'password': kwargs.pop('password', 'test123'),
        }
        defaults.update(kwargs)
        return defaults

    @classmethod
    def create(cls, **kwargs) -> dict:
        """通过 batch_save 写 DB, 返回创建的 user dict"""
        from admin_token import call_action
        data = cls.build(**kwargs)
        try:
            cookie = kwargs.pop('_cookie', None)
        except KeyError:
            cookie = None
        # 拿 cookie
        if not cookie:
            from admin_token import get_admin_cookie
            cookie = get_admin_cookie()

        _, b = call_action('batch_save', {
            'object_type': 'user',
            'drafts': [{
                'row_id': '__new_' + data['username'],
                'is_new': True,
                'fields': {
                    'username': data['username'],
                    'display_name': data['display_name'],
                    'email': data['email'],
                    'password_hash': 'placeholder',  # server 端 hash
                },
            }],
        }, cookie=cookie)
        if b.get('data', {}).get('created'):
            data['id'] = b['data']['created'][0]
        return data

    @classmethod
    def cleanup(cls, user_id, cookie=None):
        """删除测试 user"""
        from admin_token import call_action
        if not cookie:
            from admin_token import get_admin_cookie
            cookie = get_admin_cookie()
        call_action('batch_delete', {
            'object_type': 'user',
            'row_ids': [user_id],
        }, cookie=cookie)


class SubscriptionFactory:
    """[DECORATIVE] v3.18 D.2: Subscription factory"""

    @classmethod
    def build(cls, **kwargs) -> dict:
        n = int(time.time())
        defaults = {
            'object_type': kwargs.pop('object_type', 'user'),
            'event_types': kwargs.pop('event_types', ['created']),
            'channel': kwargs.pop('channel', 'webhook'),
            'webhook_url': kwargs.pop('webhook_url', f'http://localhost:9999/test_{n}_{_random_str(4)}'),
        }
        defaults.update(kwargs)
        return defaults

    @classmethod
    def create(cls, **kwargs) -> dict:
        from admin_token import call_action
        if not kwargs.get('_cookie'):
            from admin_token import get_admin_cookie
            kwargs['_cookie'] = get_admin_cookie()
        data = cls.build(**kwargs)
        _, b = call_action('subscription.create', data, cookie=kwargs['_cookie'])
        if b.get('data', {}).get('id'):
            data['id'] = b['data']['id']
        return data
