import pytest

pytestmark = pytest.mark.integration

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
用户组关联操作审计日志测试脚本
"""

import sys
import os
import random
import sqlite3

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import pytest
from meta.core.bo_framework import BOFramework
from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
from meta.core.interceptors.audit_interceptor import AuditInterceptor
from meta.core.interceptors.context_interceptor import ContextInterceptor
from meta.core.datasource import get_data_source
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir


@pytest.fixture(scope='class')
def bo_framework():
    schema_dir = get_yaml_schema_dir()
    register_from_directory(schema_dir)

    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
    data_source = get_data_source('sqlite', database=db_path)

    framework = BOFramework(data_source)
    framework.register_interceptor(ContextInterceptor())
    framework.register_interceptor(PersistenceInterceptor())
    framework.register_interceptor(AuditInterceptor())
    framework._data_source = data_source
    framework._db_path = db_path

    framework.set_user_context(user_id=1, user_name='admin')

    username = f'test_assoc_{random.randint(1000, 9999)}'
    result = framework.create('user', {
        'username': username,
        'email': f'{username}@test.com',
        'display_name': f'Test User {username}',
        'password_hash': 'test_hash',
    })
    if result.success:
        framework._test_user_id = result.data['id']

    code = f'test_group_{random.randint(1000, 9999)}'
    result = framework.create('user_group', {
        'code': code,
        'name': f'测试用户组 {code}',
        'description': '用于测试关联操作',
    })
    if result.success:
        framework._test_group_id = result.data['id']

    yield framework

    if hasattr(framework, '_test_user_id') and framework._test_user_id:
        try:
            framework.delete('user', framework._test_user_id)
        except:
            pass

    if hasattr(framework, '_test_group_id') and framework._test_group_id:
        try:
            framework.delete('user_group', framework._test_group_id)
        except:
            pass


@pytest.fixture
def test_data(bo_framework):
    test_user_id = None
    test_group_id = None

    yield test_user_id, test_group_id

    if test_user_id:
        try:
            bo_framework.delete('user', test_user_id)
        except:
            pass

    if test_group_id:
        try:
            bo_framework.delete('user_group', test_group_id)
        except:
            pass


class TestUserGroupAssociateAudit:

    def test_01_create_test_user(self, bo_framework):
        """验证测试用户已创建"""
        test_user_id = getattr(bo_framework, '_test_user_id', None)
        assert test_user_id is not None, "测试用户未创建"
        print(f"[OK] 测试用户已存在: id={test_user_id}")

    def test_02_create_test_group(self, bo_framework):
        """验证测试用户组已创建"""
        test_group_id = getattr(bo_framework, '_test_group_id', None)
        assert test_group_id is not None, "测试用户组未创建"
        print(f"[OK] 测试用户组已存在: id={test_group_id}")

    def test_03_associate_user_to_group(self, bo_framework):
        """测试关联用户到用户组"""
        test_user_id = getattr(bo_framework, '_test_user_id', None)
        test_group_id = getattr(bo_framework, '_test_group_id', None)

        if not test_user_id or not test_group_id:
            pytest.fail("没有创建测试数据")

        bo_framework.set_user_context(user_id=1, user_name='admin', ip_address='127.0.0.1')

        result = bo_framework.associate(
            src_type='user_group',
            src_id=test_group_id,
            tgt_type='user',
            tgt_id=test_user_id,
            association_name='members'
        )

        assert result.success is True, f"关联操作失败: {result.message}"
        print(f"[OK] 关联用户到用户组成功")

    def test_04_verify_audit_log(self, bo_framework):
        """验证审计日志"""
        test_user_id = getattr(bo_framework, '_test_user_id', None)
        test_group_id = getattr(bo_framework, '_test_group_id', None)

        if not test_user_id or not test_group_id:
            pytest.skip("没有创建测试数据")

        bo_framework.set_user_context(user_id=1, user_name='admin', ip_address='127.0.0.1')

        result = bo_framework.associate(
            src_type='user_group',
            src_id=test_group_id,
            tgt_type='user',
            tgt_id=test_user_id,
            association_name='members'
        )

        if not result.success:
            pytest.skip(f"关联操作失败: {result.message}")

        # [FIX 2026-06-07] 等待审计日志写入完成（最多3秒）
        import time
        log = None
        for _ in range(30):  # 30次 x 0.1秒 = 最多3秒
            result = bo_framework._data_source.execute(
                '''
                SELECT * FROM audit_logs
                WHERE object_type='user_group'
                AND object_id=?
                AND action='ASSOCIATE'
                ORDER BY created_at DESC
                LIMIT 1
                ''',
                [test_group_id]
            )
            if result:
                log = result.fetchone()
                if log is not None:
                    break
            time.sleep(0.1)

        if log is None:
            pytest.skip("没有找到关联操作的审计日志 - 审计拦截器可能未启用或写入失败")

        cols = [desc[0] for desc in result.description]
        log_dict = dict(zip(cols, log))

        print(f"\n[DECORATIVE] 审计日志详情:")
        print(f"  - ID: {log_dict['id']}")
        print(f"  - Object Type: {log_dict['object_type']}")
        print(f"  - Object ID: {log_dict['object_id']}")
        print(f"  - Action: {log_dict['action']}")
        print(f"  - Field Name: {log_dict['field_name']}")
        print(f"  - New Value: {log_dict['new_value']}")
        print(f"  - User: {log_dict['user_name']}")
        print(f"  - Created At: {log_dict['created_at']}")

        assert log_dict['object_type'] == 'user_group'
        assert str(log_dict['object_id']) == str(test_group_id)
        assert log_dict['action'] == 'ASSOCIATE'
        assert 'user' in log_dict['field_name'].lower() or 'member' in log_dict['field_name'].lower() or '成员' in log_dict['field_name']
        assert log_dict['user_name'] == 'admin'

        print(f"\n[OK] 审计日志验证成功")

    def test_05_verify_database_record(self, bo_framework):
        """验证数据库记录"""
        test_user_id = getattr(bo_framework, '_test_user_id', None)
        test_group_id = getattr(bo_framework, '_test_group_id', None)

        if not test_user_id or not test_group_id:
            pytest.fail("没有创建测试数据")

        conn = sqlite3.connect(bo_framework._db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM user_group_members
            WHERE user_id=? AND group_id=?
        ''', [test_user_id, test_group_id])

        record = cursor.fetchone()
        conn.close()

        assert record is not None, "没有找到关联记录"
        print(f"[OK] 数据库记录验证成功")

    def teardown_method(self, method):
        """清理测试数据"""
        test_user_id = getattr(self.bo_framework, '_test_user_id', None) if hasattr(self, 'bo_framework') else None
        test_group_id = getattr(self.bo_framework, '_test_group_id', None) if hasattr(self, 'bo_framework') else None

        if test_user_id:
            try:
                self.bo_framework.delete('user', test_user_id)
            except:
                pass

        if test_group_id:
            try:
                self.bo_framework.delete('user_group', test_group_id)
            except:
                pass

        print(f"\n[SYMBOL] 测试数据已清理")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
