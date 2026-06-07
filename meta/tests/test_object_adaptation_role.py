import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Phase 11 对象适配测试 - Role CRUD

测试范围：
- Role 基本 CRUD 操作
- Role YAML 元数据驱动
- Role 计算字段 (menu_count, user_count)
- Role 列表过滤和排序
- Role 详情页 YAML 配置

对应规范: TC-PA-001 ~ TC-PA-015
"""

import pytest
import os
import tempfile


class TestRoleCRUD:
    """Role 基本 CRUD 测试"""

    @pytest.fixture
    def data_source(self):
        from meta.core.datasource import get_data_source
        from meta.core.table_name_validator import invalidate_cache

        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(db_fd)

        ds = get_data_source('sqlite', database=db_path)

        ds.execute('''CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(200) UNIQUE NOT NULL,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            is_system INTEGER DEFAULT 0,
            is_super_admin INTEGER DEFAULT 0,
            priority INTEGER DEFAULT 0,
            created_at DATETIME,
            updated_at DATETIME,
            created_by INTEGER,
            updated_by INTEGER
        )''')
        ds.commit()

        ds.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(200) UNIQUE NOT NULL,
            email VARCHAR(200),
            created_at DATETIME
        )''')
        ds.commit()

        ds.execute('''CREATE TABLE IF NOT EXISTS user_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(200) UNIQUE NOT NULL,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            parent_id INTEGER,
            manager_id INTEGER,
            created_at DATETIME,
            member_count INTEGER DEFAULT 0
        )''')
        ds.commit()

        ds.execute('''CREATE TABLE IF NOT EXISTS user_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            is_manager INTEGER DEFAULT 0,
            joined_at DATETIME,
            UNIQUE(user_id, group_id)
        )''')
        ds.commit()

        ds.execute('''CREATE TABLE IF NOT EXISTS group_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            created_at DATETIME,
            UNIQUE(group_id, role_id)
        )''')
        ds.commit()

        invalidate_cache()
        yield ds

        ds.disconnect()
        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.fixture
    def bo_framework(self, data_source):
        from meta.core.bo_framework import BOFramework
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        from meta.core.interceptors.constraint_validation_interceptor import ConstraintValidationInterceptor
        from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
        from meta.core.models import registry
        
        schema_dir = get_yaml_schema_dir()
        if schema_dir and not registry._initialized:
            register_from_directory(schema_dir)

        fw = BOFramework(data_source=data_source)
        fw.register_interceptor(PersistenceInterceptor())
        # [FIX 2026-06-07] 注册 ConstraintValidationInterceptor 以检查 immutable 字段约束
        fw.register_interceptor(ConstraintValidationInterceptor())
        return fw

    def _insert_role(self, data_source, code, name, description=None):
        data = {'code': code, 'name': name}
        if description is not None:
            data['description'] = description
        return data_source.insert('roles', data)

    def _insert_user(self, data_source, username, email):
        return data_source.insert('users', {'username': username, 'email': email})

    def _create_user_group(self, data_source, code, name):
        cursor = data_source.execute(
            "INSERT INTO user_groups (code, name) VALUES (?, ?)",
            (code, name)
        )
        data_source.commit()
        return cursor.lastrowid

    def _add_user_to_group(self, data_source, user_id, group_id):
        cursor = data_source.execute(
            "INSERT INTO user_group_members (user_id, group_id) VALUES (?, ?)",
            (user_id, group_id)
        )
        data_source.commit()
        return cursor.lastrowid

    def _assign_role_to_group(self, data_source, group_id, role_id):
        cursor = data_source.execute(
            "INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)",
            (group_id, role_id)
        )
        data_source.commit()
        return cursor.lastrowid

    def test_create_role_basic(self, bo_framework, data_source):
        try:
            result = bo_framework.create('role', {
                'code': 'TEST_ROLE',
                'name': '测试角色',
                'description': '这是一个测试角色'
            })

            assert result.success, f"创建失败: {result.message}"

            cursor = data_source.execute("SELECT * FROM roles WHERE code = ?", ('TEST_ROLE',))
            role = cursor.fetchone()
            assert role is not None
        except Exception as e:
            pytest.fail(f"Role CRUD skipped: {e}")

    def test_create_role_with_description(self, bo_framework):
        try:
            result = bo_framework.create('role', {
                'code': 'DESC_ROLE',
                'name': '带描述角色',
                'description': '这个角色有详细描述'
            })

            assert result.success, f"创建失败: {result.message}"
        except Exception as e:
            pytest.fail(f"Role CRUD skipped: {e}")

    def test_create_role_duplicate_code(self, bo_framework):
        try:
            bo_framework.create('role', {'code': 'DUPLICATE', 'name': '角色1'})

            result = bo_framework.create('role', {'code': 'DUPLICATE', 'name': '角色2'})

            assert not result.success
        except Exception as e:
            pytest.fail(f"Role CRUD skipped: {e}")

    def test_read_role_by_id(self, bo_framework, data_source):
        try:
            role_id = self._insert_role(data_source, 'READ_TEST', '读取测试', '用于测试读取')

            result = bo_framework.read('role', role_id)

            assert result.success, f"读取失败: {result.message}"
            assert result.data is not None
            assert result.data.get('code') == 'READ_TEST'
            assert result.data.get('name') == '读取测试'
        except Exception as e:
            pytest.fail(f"Role CRUD skipped: {e}")

    def test_read_role_with_computed_fields(self, bo_framework, data_source):
        try:
            role_id = self._insert_role(data_source, 'COMPUTED', '计算字段测试')
            user_id = self._insert_user(data_source, 'user1', 'user1@test.com')
            group_id = self._create_user_group(data_source, 'TEST_GROUP', '测试用户组')
            self._add_user_to_group(data_source, user_id, group_id)
            self._assign_role_to_group(data_source, group_id, role_id)

            result = bo_framework.read('role', role_id)

            assert result.success, f"读取失败: {result.message}"
        except Exception as e:
            pytest.fail(f"Role CRUD skipped: {e}")

    def test_update_role_basic(self, bo_framework, data_source):
        try:
            role_id = self._insert_role(data_source, 'UPDATE_TEST', '更新前名称')

            result = bo_framework.update('role', role_id, {
                'name': '更新后名称',
                'description': '新描述'
            })

            assert result.success, f"更新失败: {result.message}"

            record = data_source.find_by_id('roles', role_id)
            assert record['name'] == '更新后名称'
            assert record['description'] == '新描述'
        except Exception as e:
            pytest.fail(f"Role CRUD skipped: {e}")

    def test_update_role_description(self, bo_framework, data_source):
        try:
            role_id = self._insert_role(data_source, 'DESC_UPDATE', '描述测试', '旧描述')

            result = bo_framework.update('role', role_id, {'description': '新描述内容'})

            assert result.success, f"更新失败: {result.message}"
        except Exception as e:
            pytest.fail(f"Role CRUD skipped: {e}")

    def test_update_role_code_forbidden(self, bo_framework, data_source):
        try:
            role_id = self._insert_role(data_source, 'CODE_TEST', '代码测试')

            bo_framework.update('role', role_id, {'code': 'NEW_CODE'})

            record = data_source.find_by_id('roles', role_id)
            assert record['code'] == 'CODE_TEST'
        except Exception as e:
            pytest.fail(f"Role CRUD skipped: {e}")

    def test_delete_role_basic(self, bo_framework, data_source):
        try:
            role_id = self._insert_role(data_source, 'DELETE_TEST', '删除测试')

            result = bo_framework.delete('role', role_id)

            assert result.success, f"删除失败: {result.message}"

            record = data_source.find_by_id('roles', role_id)
            assert record is None
        except Exception as e:
            pytest.fail(f"Role CRUD skipped: {e}")

    def test_delete_role_with_user_association(self, bo_framework, data_source):
        try:
            role_id = self._insert_role(data_source, 'ROLE_WITH_USER', '有关联角色')
            user_id = self._insert_user(data_source, 'assoc_user', 'assoc@test.com')
            group_id = self._create_user_group(data_source, 'ASSOC_GROUP', '关联用户组')
            self._add_user_to_group(data_source, user_id, group_id)
            self._assign_role_to_group(data_source, group_id, role_id)

            result = bo_framework.delete('role', role_id)

            assert result.success, f"删除失败: {result.message}"
        except Exception as e:
            pytest.fail(f"Role CRUD skipped: {e}")

    def test_list_role_pagination(self, bo_framework, data_source):
        try:
            for i in range(25):
                self._insert_role(data_source, f'PAGE_ROLE_{i}', f'分页角色{i}')

            result = bo_framework.query('role', page=1, page_size=20)

            assert result.success, f"查询失败: {result.message}"
            total = result.total or 0
            assert total >= 20
            data = result.data or []
            assert len(data) <= 20
        except Exception as e:
            pytest.fail(f"Role CRUD skipped: {e}")

    def test_list_role_with_filter(self, bo_framework, data_source):
        try:
            self._insert_role(data_source, 'FILTER_TEST', '过滤测试角色')
            self._insert_role(data_source, 'OTHER', '其他角色')

            result = bo_framework.execute('role', 'crud_query', {
                'name__like': '过滤测试'
            })

            assert result.success, f"查询失败: {result.message}"
            data = result.data or []
            assert len(data) >= 1
            assert any('过滤测试' in str(r.get('name', '')) for r in data)
        except Exception as e:
            pytest.fail(f"Role CRUD skipped: {e}")

    def test_list_role_with_sorting(self, bo_framework, data_source):
        try:
            self._insert_role(data_source, 'B_ROLE', 'B角色')
            self._insert_role(data_source, 'A_ROLE', 'A角色')

            result = bo_framework.execute('role', 'crud_query', {
                '_order_by': 'name'
            })

            assert result.success, f"查询失败: {result.message}"
            data = result.data or []
            if len(data) >= 2:
                assert data[0]['name'] <= data[1]['name']
        except Exception as e:
            pytest.fail(f"Role CRUD skipped: {e}")

    def test_list_role_with_search(self, bo_framework, data_source):
        try:
            self._insert_role(data_source, 'SEARCH', '搜索目标', '包含关键词')
            self._insert_role(data_source, 'OTHER', '其他', '不包含')

            result = bo_framework.execute('role', 'crud_query', {
                'search': '搜索目标'
            })

            assert result.success, f"查询失败: {result.message}"
            data = result.data or []
            assert len(data) >= 1
        except Exception as e:
            pytest.fail(f"Role CRUD skipped: {e}")

    def test_role_detail_yaml_config(self, bo_framework):
        try:
            from meta.core.models import registry

            role_meta = registry.get('role')
            assert role_meta is not None, "role 元数据未加载"

            assert hasattr(role_meta, 'fields'), "role 应该有 fields 属性"

            field_names = [f.id for f in role_meta.fields]
            assert 'name' in field_names, "role 应该有 name 字段"
            assert 'code' in field_names, "role 应该有 code 字段"

            if hasattr(role_meta, 'ui_view_config') and role_meta.ui_view_config:
                detail_config = getattr(role_meta.ui_view_config, 'detail', None)
                assert detail_config is not None, "role 应该有 detail 配置"
        except Exception as e:
            pytest.fail(f"Role CRUD skipped: {e}")


class TestRoleMetaConfiguration:
    """Role 元数据配置测试"""

    def test_role_yaml_loaded(self):
        from meta.core.models import registry

        role_meta = registry.get('role')
        assert role_meta is not None, "role 元数据未加载"
        assert role_meta.id == 'role', f"期望 id='role', 实际={role_meta.id}"

    def test_role_fields_definition(self):
        from meta.core.models import registry

        role_meta = registry.get('role')
        assert role_meta is not None, "role_meta not found in registry"
        field_map = {f.id: f for f in role_meta.fields}

        assert 'code' in field_map, "缺少 code 字段"
        assert 'name' in field_map, "缺少 name 字段"

    def test_role_associations_defined(self):
        from meta.core.models import registry

        role_meta = registry.get('role')
        associations = getattr(role_meta, 'associations', None)

        if associations:
            if isinstance(associations, dict):
                assoc_names = list(associations.keys())
            elif isinstance(associations, list):
                assoc_names = [getattr(a, 'name', '') for a in associations]
            else:
                assoc_names = []

            assert 'permissions' in assoc_names or 'permission' in assoc_names, \
                "role 应该定义 permissions 关联"
        else:
            pytest.fail("role associations not defined in metadata")

    def test_role_computed_fields(self):
        from meta.core.models import registry

        role_meta = registry.get('role')
        assert role_meta is not None, "role_meta not found in registry"
        computed_fields = [
            f for f in role_meta.fields
            if getattr(f, 'computed', False) or getattr(f, 'is_computed', False)
            or (hasattr(f, 'semantics') and getattr(f.semantics, 'computed', False))
        ]

        assert len(computed_fields) > 0, "role 应该有计算字段"

    def test_role_ui_view_config(self):
        from meta.core.models import registry

        role_meta = registry.get('role')
        assert role_meta is not None, "role_meta not found in registry"

        if hasattr(role_meta, 'ui_view_config') and role_meta.ui_view_config:
            assert hasattr(role_meta.ui_view_config, 'list'), \
                "ui_view_config 应该有 list 配置"
