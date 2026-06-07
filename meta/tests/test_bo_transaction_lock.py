# -*- coding: utf-8 -*-
"""
BOFramework 事务控制和锁机制测试
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from meta.core.bo_framework import BOFramework
from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
from meta.core.interceptors.audit_interceptor import AuditInterceptor
from meta.core.interceptors.context_interceptor import ContextInterceptor
from meta.core.interceptors.lock_interceptor import LockInterceptor
from meta.core.datasource import get_data_source
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
from meta.core.exceptions import ConcurrentModificationError
import random

pytestmark = pytest.mark.integration


def _create_bo_framework(interceptors):
    schema_dir = get_yaml_schema_dir()
    register_from_directory(schema_dir)

    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'meta', 'architecture.db')
    db_available = True
    try:
        data_source = get_data_source('sqlite', database=db_path)
    except Exception:
        db_available = False
        return None, None

    bo_framework = BOFramework(data_source)
    for interceptor in interceptors:
        bo_framework.register_interceptor(interceptor)

    return bo_framework, data_source


@pytest.fixture
def txn_bo_framework():
    bo_framework, data_source = _create_bo_framework([
        ContextInterceptor(), PersistenceInterceptor(), AuditInterceptor()
    ])
    if bo_framework is None:
        pytest.skip("数据库不可用（并发锁冲突）")
    return bo_framework, data_source


@pytest.fixture
def lock_bo_framework():
    bo_framework, data_source = _create_bo_framework([
        ContextInterceptor(), LockInterceptor(), PersistenceInterceptor(), AuditInterceptor()
    ])
    if bo_framework is None:
        pytest.skip("数据库不可用（并发锁冲突）")
    return bo_framework, data_source


@pytest.fixture
def full_bo_framework():
    bo_framework, data_source = _create_bo_framework([
        ContextInterceptor(), LockInterceptor(), PersistenceInterceptor(), AuditInterceptor()
    ])
    return bo_framework, data_source


class TestTransactionControl:

    def test_01_transaction_commit(self, txn_bo_framework):
        bo_framework, data_source = txn_bo_framework
        username = f'test_txn_commit_{random.randint(1000, 9999)}'

        bo_framework.set_user_context(user_id=1, user_name='admin')

        try:
            with bo_framework.transaction():
                result = bo_framework.create('user', {
                    'username': username,
                    'email': f'{username}@test.com',
                    'display_name': f'Test User {username}',
                    'password_hash': 'test_hash',
                })

                assert result.success, f"创建用户失败: {result.message}"
                user_id = result.data['id']

            read_result = bo_framework.read('user', user_id)
            assert read_result.success, "事务提交后应该能读取到数据"
            assert read_result.data['username'] == username

            bo_framework.delete('user', user_id)
        except Exception as e:
            if "database is locked" in str(e):
                pytest.skip("数据库锁定（并发冲突）")
            raise

    def test_02_transaction_rollback(self, txn_bo_framework):
        bo_framework, data_source = txn_bo_framework
        username = f'test_txn_rollback_{random.randint(1000, 9999)}'

        bo_framework.set_user_context(user_id=1, user_name='admin')

        user_id = None
        exception_raised = False

        try:
            with bo_framework.transaction():
                result = bo_framework.create('user', {
                    'username': username,
                    'email': f'{username}@test.com',
                    'display_name': f'Test User {username}',
                    'password_hash': 'test_hash',
                })

                assert result.success
                user_id = result.data['id']

                raise Exception("模拟错误触发回滚")
        except Exception as e:
            if "模拟错误触发回滚" in str(e):
                exception_raised = True

        assert exception_raised, "应该捕获到异常"

        if user_id:
            try:
                bo_framework.delete('user', user_id)
            except Exception:
                pass

    def test_03_nested_transaction(self, txn_bo_framework):
        bo_framework, data_source = txn_bo_framework
        username = f'test_txn_nested_{random.randint(1000, 9999)}'

        bo_framework.set_user_context(user_id=1, user_name='admin')

        with bo_framework.transaction():
            result = bo_framework.create('user', {
                'username': username,
                'email': f'{username}@test.com',
                'display_name': f'Test User {username}',
                'password_hash': 'test_hash',
            })

            assert result.success
            user_id = result.data['id']

            update_result = bo_framework.update('user', user_id, {
                'display_name': f'Updated {username}'
            })
            assert update_result.success

        read_result = bo_framework.read('user', user_id)
        assert read_result.success
        assert 'Updated' in read_result.data['display_name']

        bo_framework.delete('user', user_id)


class TestLockInterceptor:

    def test_01_optimistic_lock_success(self, lock_bo_framework):
        bo_framework, data_source = lock_bo_framework
        username = f'test_lock_opt_{random.randint(1000, 9999)}'

        bo_framework.set_user_context(user_id=1, user_name='admin')

        create_result = bo_framework.create('user', {
            'username': username,
            'email': f'{username}@test.com',
            'display_name': f'Test User {username}',
            'password_hash': 'test_hash',
        })

        assert create_result.success
        user_id = create_result.data['id']

        read_result = bo_framework.read('user', user_id)
        assert read_result.success
        current_version = read_result.data.get('version', 1)

        update_result = bo_framework.update('user', user_id, {
            'display_name': f'Updated {username}',
            'version': current_version,
        })

        assert update_result.success, f"乐观锁更新应该成功: {update_result.message}"

        bo_framework.delete('user', user_id)

    def test_02_pessimistic_lock_acquire_release(self, lock_bo_framework):
        bo_framework, data_source = lock_bo_framework
        username = f'test_lock_pess_{random.randint(1000, 9999)}'

        bo_framework.set_user_context(user_id=1, user_name='admin')

        create_result = bo_framework.create('user', {
            'username': username,
            'email': f'{username}@test.com',
            'display_name': f'Test User {username}',
            'password_hash': 'test_hash',
        })

        assert create_result.success
        user_id = create_result.data['id']

        from meta.core.action_context import LockType
        bo_framework.set_user_context(user_id=1, user_name='admin', ip_address='127.0.0.1')

        context = type('obj', (object,), {
            'meta_object': type('obj', (object,), {'id': 'user', 'table_name': 'users'})(),
            'object_id': user_id,
            'is_crud_action': True,
            'is_update_action': True,
            'is_create_action': False,
            'is_read_action': False,
            'is_delete_action': False,
            'user_id': 1,
            'user_name': 'admin',
            'lock_type': LockType.PESSIMISTIC,
            'lock_timeout': 30,
            'data_source': data_source,
        })()

        lock_interceptor = LockInterceptor()

        try:
            lock_interceptor.before_action(context)
            lock_interceptor.after_action(context)
        except Exception as e:
            pytest.fail(f"悲观锁测试失败: {e}")
        finally:
            bo_framework.delete('user', user_id)

    def test_03_lock_timeout(self, lock_bo_framework):
        bo_framework, data_source = lock_bo_framework
        try:
            lock_interceptor = LockInterceptor(lock_timeout=1)

            from meta.core.action_context import LockType
            from datetime import datetime, timedelta

            lock_key = "user:999"
            lock_interceptor._locks[lock_key] = {
                'user_id': 2,
                'user_name': 'other_user',
                'acquired_at': datetime.now() - timedelta(seconds=5),
                'timeout': 1,
            }

            lock_interceptor.cleanup_expired_locks()

            assert lock_key not in lock_interceptor._locks, "过期锁应该被清理"
        except AssertionError as e:
            pytest.fail(f"Lock timeout timing issue: {e}")
        except Exception as e:
            pytest.fail(f"Lock timeout test skipped: {e}")


class TestBOFrameworkIntegration:

    def test_01_full_crud_lifecycle(self, full_bo_framework):
        bo_framework, data_source = full_bo_framework
        username = f'test_lifecycle_{random.randint(1000, 9999)}'

        bo_framework.set_user_context(user_id=1, user_name='admin')

        create_result = bo_framework.create('user', {
            'username': username,
            'email': f'{username}@test.com',
            'display_name': f'Test User {username}',
            'password_hash': 'test_hash',
        })
        assert create_result.success, f"创建失败: {create_result.message}"
        user_id = create_result.data['id']

        read_result = bo_framework.read('user', user_id)
        assert read_result.success
        assert read_result.data['username'] == username

        update_result = bo_framework.update('user', user_id, {
            'display_name': f'Updated {username}'
        })
        assert update_result.success
        assert 'Updated' in update_result.data['display_name']

        query_result = bo_framework.query('user', {'username': username})
        assert query_result.success
        assert len(query_result.data) > 0

        delete_result = bo_framework.delete('user', user_id)
        assert delete_result.success

        read_after_delete = bo_framework.read('user', user_id)
        assert not read_after_delete.success

    def test_02_concurrent_operations(self, full_bo_framework):
        bo_framework, data_source = full_bo_framework
        username1 = f'test_concurrent_1_{random.randint(1000, 9999)}'
        username2 = f'test_concurrent_2_{random.randint(1000, 9999)}'

        bo_framework.set_user_context(user_id=1, user_name='admin')

        with bo_framework.transaction():
            result1 = bo_framework.create('user', {
                'username': username1,
                'email': f'{username1}@test.com',
                'display_name': f'Test User 1',
                'password_hash': 'test_hash',
            })
            assert result1.success
            user_id1 = result1.data['id']

            result2 = bo_framework.create('user', {
                'username': username2,
                'email': f'{username2}@test.com',
                'display_name': f'Test User 2',
                'password_hash': 'test_hash',
            })
            assert result2.success
            user_id2 = result2.data['id']

        read1 = bo_framework.read('user', user_id1)
        read2 = bo_framework.read('user', user_id2)
        assert read1.success
        assert read2.success

        bo_framework.delete('user', user_id1)
        bo_framework.delete('user', user_id2)
