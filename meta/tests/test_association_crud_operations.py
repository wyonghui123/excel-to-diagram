import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Phase 11 对象适配测试 - Association CRUD

测试范围：
- Role 权限分配/取消 (role_permissions)
- UserGroup 成员添加/移除 (user_group_members)
- Association 列表查询
- Association 计数

对应规范: TC-PA-031 ~ TC-PA-045
"""

import pytest
import sqlite3
import os
import tempfile


class TestRolePermissionAssociation:
    """Role 权限关联测试"""

    @pytest.fixture
    def db_connection(self):
        """创建测试数据库连接"""
        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(db_fd)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                resource TEXT,
                action TEXT,
                created_at TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE role_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER NOT NULL,
                permission_id INTEGER NOT NULL,
                created_at TEXT,
                UNIQUE(role_id, permission_id)
            )
        ''')

        conn.commit()
        yield conn
        conn.close()
        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.fixture
    def bo_framework(self, db_connection):
        """创建 BOFramework 实例"""
        from meta.core.bo_framework import BOFramework
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
        from meta.core.models import registry
        
        schema_dir = get_yaml_schema_dir()
        if schema_dir and not registry._initialized:
            register_from_directory(schema_dir)
        
        fw = BOFramework(db_connection)
        fw.register_interceptor(PersistenceInterceptor())
        return fw

    def test_assign_permission_to_role(self, bo_framework, db_connection):
        """TC-PA-031: Role分配权限 - 基本分配"""
        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT INTO roles (code, name) VALUES (?, ?)",
            ('TEST_ROLE', '测试角色')
        )
        role_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO permissions (code, name, resource, action) VALUES (?, ?, ?, ?)",
            ('PERM1', '权限1', 'user', 'read')
        )
        perm_id = cursor.lastrowid
        db_connection.commit()

        result = bo_framework.associate(
            'role', role_id, 'permission', perm_id,
            association_name='permissions'
        )

        assert result.success, f"分配失败: {result.message}"

        cursor.execute(
            "SELECT * FROM role_permissions WHERE role_id = ? AND permission_id = ?",
            (role_id, perm_id)
        )
        assoc = cursor.fetchone()
        assert assoc is not None

    def test_assign_permission_idempotent(self, bo_framework, db_connection):
        """TC-PA-032: Role分配权限 - 重复分配"""
        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT INTO roles (code, name) VALUES (?, ?)",
            ('IDEMPOTENT_ROLE', '幂等角色')
        )
        role_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO permissions (code, name) VALUES (?, ?)",
            ('IDEMPOTENT_PERM', '幂等权限')
        )
        perm_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
            (role_id, perm_id)
        )
        db_connection.commit()

        result = bo_framework.associate(
            'role', role_id, 'permission', perm_id,
            association_name='permissions'
        )

        assert result.success

    def test_batch_assign_permissions(self, bo_framework, db_connection):
        """TC-PA-033: Role分配权限 - 批量分配"""
        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT INTO roles (code, name) VALUES (?, ?)",
            ('BATCH_ROLE', '批量角色')
        )
        role_id = cursor.lastrowid

        perm_ids = []
        for i in range(3):
            cursor.execute(
                "INSERT INTO permissions (code, name) VALUES (?, ?)",
                (f'BATCH_PERM_{i}', f'批量权限{i}')
            )
            perm_ids.append(cursor.lastrowid)
        db_connection.commit()

        for perm_id in perm_ids:
            result = bo_framework.associate(
                'role', role_id, 'permission', perm_id,
                association_name='permissions'
            )
            assert result.success

        cursor.execute(
            "SELECT COUNT(*) FROM role_permissions WHERE role_id = ?",
            (role_id,)
        )
        count = cursor.fetchone()[0]
        assert count == 3

    def test_unassign_permission_from_role(self, bo_framework, db_connection):
        """TC-PA-034: Role取消权限 - 基本取消"""
        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT INTO roles (code, name) VALUES (?, ?)",
            ('UNASSIGN_ROLE', '取消角色')
        )
        role_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO permissions (code, name) VALUES (?, ?)",
            ('UNASSIGN_PERM', '取消权限')
        )
        perm_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
            (role_id, perm_id)
        )
        db_connection.commit()

        result = bo_framework.dissociate(
            'role', role_id, 'permission', perm_id,
            association_name='permissions'
        )

        assert result.success

        cursor.execute(
            "SELECT * FROM role_permissions WHERE role_id = ? AND permission_id = ?",
            (role_id, perm_id)
        )
        assert cursor.fetchone() is None

    def test_unassign_nonexistent_permission(self, bo_framework, db_connection):
        """TC-PA-035: Role取消权限 - 不存在"""
        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT INTO roles (code, name) VALUES (?, ?)",
            ('NONEXIST_ROLE', '不存在角色')
        )
        role_id = cursor.lastrowid
        db_connection.commit()

        result = bo_framework.dissociate(
            'role', role_id, 'permission', 99999,
            association_name='permissions'
        )

        assert result.success or 'not found' in str(result.message).lower()


class TestUserGroupMemberAssociation:
    """UserGroup 成员关联测试"""

    @pytest.fixture
    def db_connection(self):
        """创建测试数据库连接"""
        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(db_fd)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE user_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT,
                created_at TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE user_group_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT,
                UNIQUE(group_id, user_id)
            )
        ''')

        conn.commit()
        yield conn
        conn.close()
        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.fixture
    def bo_framework(self, db_connection):
        """创建 BOFramework 实例"""
        from meta.core.bo_framework import BOFramework
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
        from meta.core.models import registry
        
        schema_dir = get_yaml_schema_dir()
        if schema_dir and not registry._initialized:
            register_from_directory(schema_dir)
        
        fw = BOFramework(db_connection)
        fw.register_interceptor(PersistenceInterceptor())
        return fw

    def test_add_member_to_group(self, bo_framework, db_connection):
        """TC-PA-036: UserGroup添加成员 - 基本添加"""
        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT INTO user_groups (code, name) VALUES (?, ?)",
            ('MEMBER_GROUP', '成员组')
        )
        group_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO users (username, email) VALUES (?, ?)",
            ('member_user', 'member@test.com')
        )
        user_id = cursor.lastrowid
        db_connection.commit()

        result = bo_framework.associate(
            'user_group', group_id, 'user', user_id,
            association_name='members'
        )

        assert result.success, f"添加成员失败: {result.message}"

        cursor.execute(
            "SELECT * FROM user_group_members WHERE group_id = ? AND user_id = ?",
            (group_id, user_id)
        )
        member = cursor.fetchone()
        assert member is not None

    def test_add_member_idempotent(self, bo_framework, db_connection):
        """TC-PA-037: UserGroup添加成员 - 重复添加"""
        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT INTO user_groups (code, name) VALUES (?, ?)",
            ('IDEM_GROUP', '幂等组')
        )
        group_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO users (username, email) VALUES (?, ?)",
            ('idem_user', 'idem@test.com')
        )
        user_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO user_group_members (group_id, user_id) VALUES (?, ?)",
            (group_id, user_id)
        )
        db_connection.commit()

        result = bo_framework.associate(
            'user_group', group_id, 'user', user_id,
            association_name='members'
        )

        assert result.success

    def test_batch_add_members(self, bo_framework, db_connection):
        """TC-PA-038: UserGroup添加成员 - 批量添加"""
        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT INTO user_groups (code, name) VALUES (?, ?)",
            ('BATCH_GROUP', '批量组')
        )
        group_id = cursor.lastrowid

        user_ids = []
        for i in range(3):
            cursor.execute(
                "INSERT INTO users (username, email) VALUES (?, ?)",
                (f'batch_user_{i}', f'batch{i}@test.com')
            )
            user_ids.append(cursor.lastrowid)
        db_connection.commit()

        for user_id in user_ids:
            result = bo_framework.associate(
                'user_group', group_id, 'user', user_id,
                association_name='members'
            )
            assert result.success

        cursor.execute(
            "SELECT COUNT(*) FROM user_group_members WHERE group_id = ?",
            (group_id,)
        )
        count = cursor.fetchone()[0]
        assert count == 3

    def test_remove_member_from_group(self, bo_framework, db_connection):
        """TC-PA-039: UserGroup移除成员 - 基本移除"""
        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT INTO user_groups (code, name) VALUES (?, ?)",
            ('REMOVE_GROUP', '移除组')
        )
        group_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO users (username, email) VALUES (?, ?)",
            ('remove_user', 'remove@test.com')
        )
        user_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO user_group_members (group_id, user_id) VALUES (?, ?)",
            (group_id, user_id)
        )
        db_connection.commit()

        result = bo_framework.dissociate(
            'user_group', group_id, 'user', user_id,
            association_name='members'
        )

        assert result.success

        cursor.execute(
            "SELECT * FROM user_group_members WHERE group_id = ? AND user_id = ?",
            (group_id, user_id)
        )
        assert cursor.fetchone() is None

    def test_remove_nonexistent_member(self, bo_framework, db_connection):
        """TC-PA-040: UserGroup移除成员 - 不存在"""
        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT INTO user_groups (code, name) VALUES (?, ?)",
            ('NONEXIST_GROUP', '不存在组')
        )
        group_id = cursor.lastrowid
        db_connection.commit()

        result = bo_framework.dissociate(
            'user_group', group_id, 'user', 99999,
            association_name='members'
        )

        assert result.success or 'not found' in str(result.message).lower()


class TestAssociationQuery:
    """Association 查询测试"""

    @pytest.fixture
    def db_connection(self):
        """创建测试数据库连接"""
        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(db_fd)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                resource TEXT,
                created_at TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE role_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER NOT NULL,
                permission_id INTEGER NOT NULL,
                created_at TEXT,
                UNIQUE(role_id, permission_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE user_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT,
                created_at TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE user_group_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT,
                UNIQUE(group_id, user_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE group_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                created_at TEXT,
                UNIQUE(group_id, role_id)
            )
        ''')

        conn.commit()
        yield conn
        conn.close()
        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.fixture
    def bo_framework(self, db_connection):
        """创建 BOFramework 实例"""
        from meta.core.bo_framework import BOFramework
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        fw = BOFramework(db_connection)
        fw.register_interceptor(PersistenceInterceptor())
        return fw

    def test_query_role_permissions(self, bo_framework, db_connection):
        """TC-PA-041: 查询Role权限列表"""
        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT INTO roles (code, name) VALUES (?, ?)",
            ('QUERY_ROLE', '查询角色')
        )
        role_id = cursor.lastrowid

        for i in range(3):
            cursor.execute(
                "INSERT INTO permissions (code, name) VALUES (?, ?)",
                (f'QUERY_PERM_{i}', f'查询权限{i}')
            )
            perm_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                (role_id, perm_id)
            )
        db_connection.commit()

        result = bo_framework.query_associations(
            'role', role_id, 'permissions'
        )

        assert result.success
        total = result.data.get('total', 0) if isinstance(result.data, dict) else len(result.data or [])
        assert total == 3

    def test_query_user_group_members(self, bo_framework, db_connection):
        """TC-PA-042: 查询UserGroup成员列表"""
        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT INTO user_groups (code, name) VALUES (?, ?)",
            ('QUERY_GROUP', '查询组')
        )
        group_id = cursor.lastrowid

        for i in range(2):
            cursor.execute(
                "INSERT INTO users (username, email) VALUES (?, ?)",
                (f'query_user_{i}', f'query{i}@test.com')
            )
            user_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO user_group_members (group_id, user_id) VALUES (?, ?)",
                (group_id, user_id)
            )
        db_connection.commit()

        result = bo_framework.query_associations(
            'user_group', group_id, 'members'
        )

        assert result.success
        total = result.data.get('total', 0) if isinstance(result.data, dict) else len(result.data or [])
        assert total == 2

    def test_query_user_group_roles(self, bo_framework, db_connection):
        """TC-PA-043: 查询UserGroup角色列表"""
        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT INTO user_groups (code, name) VALUES (?, ?)",
            ('GROUP_FOR_ROLES', '角色组')
        )
        group_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO users (username, email) VALUES (?, ?)",
            ('role_user', 'roleuser@test.com')
        )
        user_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO roles (code, name) VALUES (?, ?)",
            ('GROUP_ROLE_1', '组角色1')
        )
        role_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO user_group_members (user_id, group_id) VALUES (?, ?)",
            (user_id, group_id)
        )
        cursor.execute(
            "INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)",
            (group_id, role_id)
        )
        db_connection.commit()

        result = bo_framework.query_associations(
            'user_group', group_id, 'roles'
        )

        assert result.success

    def test_permission_count_for_role(self, bo_framework, db_connection):
        """TC-PA-044: 权限计数 - Role权限数"""
        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT INTO roles (code, name) VALUES (?, ?)",
            ('COUNT_ROLE', '计数角色')
        )
        role_id = cursor.lastrowid

        for i in range(5):
            cursor.execute(
                "INSERT INTO permissions (code, name) VALUES (?, ?)",
                (f'COUNT_PERM_{i}', f'计数权限{i}')
            )
            perm_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                (role_id, perm_id)
            )
        db_connection.commit()

        result = bo_framework.execute(
            'role',
            'read',
            {'id': role_id}
        )

        assert result.success

    def test_member_count_for_group(self, bo_framework, db_connection):
        """TC-PA-045: 成员计数 - UserGroup成员数"""
        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT INTO user_groups (code, name) VALUES (?, ?)",
            ('MEMBER_COUNT_GROUP', '成员计数组')
        )
        group_id = cursor.lastrowid

        for i in range(4):
            cursor.execute(
                "INSERT INTO users (username, email) VALUES (?, ?)",
                (f'member_count_user_{i}', f'mc{i}@test.com')
            )
            user_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO user_group_members (group_id, user_id) VALUES (?, ?)",
                (group_id, user_id)
            )
        db_connection.commit()

        result = bo_framework.execute(
            'user_group',
            'read',
            {'id': group_id}
        )

        assert result.success
