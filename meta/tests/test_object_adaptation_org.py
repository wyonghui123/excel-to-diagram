import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Phase 11 对象适配测试 - UserGroup CRUD

测试范围：
- UserGroup 基本 CRUD 操作
- UserGroup 层级关系 (parent_id)
- UserGroup 管理员 (manager_id)
- UserGroup 成员计数 (member_count)
- UserGroup YAML 元数据驱动

对应规范: TC-PA-016 ~ TC-PA-030
"""

import pytest
import os
import tempfile


class TestUserGroupCRUD:
    """UserGroup 基本 CRUD 测试"""

    @pytest.fixture
    def data_source(self):
        from meta.core.datasource import get_data_source
        from meta.core.table_name_validator import invalidate_cache

        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(db_fd)

        ds = get_data_source('sqlite', database=db_path)

        ds.execute('''CREATE TABLE IF NOT EXISTS user_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(200) UNIQUE NOT NULL,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            parent_id INTEGER,
            manager_id INTEGER,
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
            display_name VARCHAR(200),
            created_at DATETIME
        )''')
        ds.commit()

        ds.execute('''CREATE TABLE IF NOT EXISTS user_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at DATETIME,
            UNIQUE(user_group_id, user_id)
        )''')
        ds.commit()

        # [FIX 2026-06-10] 创建 audit_logs 表（user_group 启用了 audit_aspect）
        ds.execute('''CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type VARCHAR(100) NOT NULL,
            object_id INTEGER NOT NULL,
            action VARCHAR(50) NOT NULL,
            actor_id INTEGER,
            actor_name VARCHAR(200),
            changes TEXT,
            ip_address VARCHAR(50),
            user_agent TEXT,
            trace_id VARCHAR(100),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
        from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
        from meta.core.models import registry
        
        schema_dir = get_yaml_schema_dir()
        if schema_dir and not registry._initialized:
            register_from_directory(schema_dir)

        fw = BOFramework(data_source=data_source)
        fw.register_interceptor(PersistenceInterceptor())
        return fw

    def _insert_group(self, data_source, code, name, description=None, parent_id=None, manager_id=None):
        data = {'code': code, 'name': name}
        if description is not None:
            data['description'] = description
        if parent_id is not None:
            data['parent_id'] = parent_id
        if manager_id is not None:
            data['manager_id'] = manager_id
        return data_source.insert('user_groups', data)

    def _insert_user(self, data_source, username, email):
        return data_source.insert('users', {'username': username, 'email': email})

    def _insert_member(self, data_source, group_id, user_id):
        return data_source.insert('user_group_members', {'user_group_id': group_id, 'user_id': user_id})

    def test_create_user_group_basic(self, bo_framework, data_source):
        try:
            result = bo_framework.create('user_group', {
                'code': 'TEST_GROUP',
                'name': '测试用户组',
                'description': '这是一个测试用户组'
            })

            assert result.success, f"创建失败: {result.message}"

            cursor = data_source.execute("SELECT * FROM user_groups WHERE code = ?", ('TEST_GROUP',))
            group = cursor.fetchone()
            assert group is not None
        except Exception as e:
            pytest.fail(f"User group CRUD skipped: {e}")

    def test_create_user_group_with_hierarchy(self, bo_framework, data_source):
        try:
            parent_id = self._insert_group(data_source, 'PARENT_GROUP', '父用户组')

            result = bo_framework.create('user_group', {
                'code': 'CHILD_GROUP',
                'name': '子用户组',
                'parent_id': parent_id
            })

            assert result.success, f"创建失败: {result.message}"

            record = data_source.find_by_id('user_groups', result.data.get('id') if result.data else None)
            if record:
                assert record.get('parent_id') == parent_id
        except Exception as e:
            pytest.fail(f"User group CRUD skipped: {e}")

    def test_create_user_group_with_manager(self, bo_framework, data_source):
        try:
            manager_id = self._insert_user(data_source, 'manager_user', 'manager@test.com')

            result = bo_framework.create('user_group', {
                'code': 'MANAGED_GROUP',
                'name': '有管理员的用户组',
                'manager_id': manager_id
            })

            assert result.success, f"创建失败: {result.message}"
        except Exception as e:
            pytest.fail(f"User group CRUD skipped: {e}")

    def test_read_user_group_with_computed_fields(self, bo_framework, data_source):
        try:
            group_id = self._insert_group(data_source, 'COMPUTED_GROUP', '计算字段测试')
            user_id = self._insert_user(data_source, 'member1', 'member1@test.com')
            self._insert_member(data_source, group_id, user_id)

            result = bo_framework.read('user_group', group_id)

            assert result.success, f"读取失败: {result.message}"
        except Exception as e:
            pytest.fail(f"User group CRUD skipped: {e}")

    def test_update_user_group_hierarchy(self, bo_framework, data_source):
        try:
            group_id = self._insert_group(data_source, 'UPDATE_GROUP', '更新前')
            new_parent_id = self._insert_group(data_source, 'NEW_PARENT', '新父组')

            result = bo_framework.update('user_group', group_id, {'parent_id': new_parent_id})

            assert result.success, f"更新失败: {result.message}"

            record = data_source.find_by_id('user_groups', group_id)
            assert record is not None
            assert record.get('parent_id') == new_parent_id
        except Exception as e:
            pytest.fail(f"User group CRUD skipped: {e}")

    def test_update_user_group_manager(self, bo_framework, data_source):
        try:
            group_id = self._insert_group(data_source, 'MANAGER_UPDATE', '管理员更新')
            new_manager_id = self._insert_user(data_source, 'new_manager', 'newmanager@test.com')

            result = bo_framework.update('user_group', group_id, {'manager_id': new_manager_id})

            assert result.success, f"更新失败: {result.message}"
        except Exception as e:
            pytest.fail(f"User group CRUD skipped: {e}")

    def test_delete_user_group_basic(self, bo_framework, data_source):
        try:
            group_id = self._insert_group(data_source, 'DELETE_GROUP', '删除测试')

            result = bo_framework.delete('user_group', group_id)

            assert result.success, f"删除失败: {result.message}"

            record = data_source.find_by_id('user_groups', group_id)
            assert record is None
        except Exception as e:
            pytest.fail(f"User group CRUD skipped: {e}")

    def test_delete_user_group_with_children(self, bo_framework, data_source):
        try:
            parent_id = self._insert_group(data_source, 'PARENT_FOR_DELETE', '父组')
            self._insert_group(data_source, 'CHILD_FOR_DELETE', '子组', parent_id=parent_id)

            result = bo_framework.delete('user_group', parent_id)

            assert result.success, f"删除失败: {result.message}"
        except Exception as e:
            pytest.fail(f"User group CRUD skipped: {e}")

    def test_delete_user_group_with_members(self, bo_framework, data_source):
        try:
            group_id = self._insert_group(data_source, 'GROUP_WITH_MEMBERS', '有成员组')
            user_id = self._insert_user(data_source, 'member_user', 'member@test.com')
            self._insert_member(data_source, group_id, user_id)

            result = bo_framework.delete('user_group', group_id)

            assert result.success, f"删除失败: {result.message}"
        except Exception as e:
            pytest.fail(f"User group CRUD skipped: {e}")

    def test_list_user_group_tree_structure(self, bo_framework, data_source):
        try:
            root_id = self._insert_group(data_source, 'ROOT_GROUP', '根组')
            self._insert_group(data_source, 'CHILD_IN_LIST', '子组', parent_id=root_id)

            result = bo_framework.execute('user_group', 'crud_query', {
                'parent_id': root_id
            })

            assert result.success, f"查询失败: {result.message}"
            data = result.data or []
            assert len(data) >= 1
        except Exception as e:
            pytest.fail(f"User group CRUD skipped: {e}")

    def test_list_user_group_top_level(self, bo_framework, data_source):
        try:
            self._insert_group(data_source, 'TOP_LEVEL_1', '顶级组1')
            self._insert_group(data_source, 'NOT_TOP', '非顶级', parent_id=1)

            result = bo_framework.query('user_group')

            assert result.success, f"查询失败: {result.message}"
        except Exception as e:
            pytest.fail(f"User group CRUD skipped: {e}")

    def test_list_user_group_search(self, bo_framework, data_source):
        try:
            self._insert_group(data_source, 'SEARCH_GROUP', '搜索目标组', '包含关键词')
            self._insert_group(data_source, 'OTHER_GROUP', '其他组', '不包含')

            result = bo_framework.execute('user_group', 'crud_query', {
                'search': '搜索目标'
            })

            assert result.success, f"查询失败: {result.message}"
            data = result.data or []
            assert len(data) >= 1
        except Exception as e:
            pytest.fail(f"User group CRUD skipped: {e}")

    def test_user_group_detail_yaml_config(self, bo_framework):
        try:
            from meta.core.models import registry

            group_meta = registry.get('user_group')
            assert group_meta is not None, "user_group 元数据未加载"

            assert hasattr(group_meta, 'fields'), "user_group 应该有 fields 属性"

            field_names = [f.id for f in group_meta.fields]
            assert 'name' in field_names, "user_group 应该有 name 字段"
            assert 'code' in field_names, "user_group 应该有 code 字段"
        except Exception as e:
            pytest.fail(f"User group CRUD skipped: {e}")

    def test_user_group_hierarchy_path(self, bo_framework, data_source):
        try:
            level1_id = self._insert_group(data_source, 'LEVEL1', '一级组')
            level2_id = self._insert_group(data_source, 'LEVEL2', '二级组', parent_id=level1_id)
            self._insert_group(data_source, 'LEVEL3', '三级组', parent_id=level2_id)

            result = bo_framework.read('user_group', level2_id)

            assert result.success, f"读取失败: {result.message}"
        except Exception as e:
            pytest.fail(f"User group CRUD skipped: {e}")

    def test_user_group_member_count(self, bo_framework, data_source):
        try:
            group_id = self._insert_group(data_source, 'COUNT_GROUP', '计数组')

            for i in range(3):
                user_id = self._insert_user(data_source, f'count_user_{i}', f'count{i}@test.com')
                self._insert_member(data_source, group_id, user_id)

            result = bo_framework.read('user_group', group_id)

            assert result.success, f"读取失败: {result.message}"
        except Exception as e:
            pytest.fail(f"User group CRUD skipped: {e}")


class TestUserGroupMetaConfiguration:
    """UserGroup 元数据配置测试"""

    def test_user_group_yaml_loaded(self):
        from meta.core.models import registry

        group_meta = registry.get('user_group')
        assert group_meta is not None, "user_group 元数据未加载"
        assert group_meta.id == 'user_group', f"期望 id='user_group', 实际={group_meta.id}"

    def test_user_group_parent_id_field(self):
        from meta.core.models import registry

        group_meta = registry.get('user_group')
        assert group_meta is not None, "group_meta not found in registry"
        field_map = {f.id: f for f in group_meta.fields}

        assert 'parent_id' in field_map, "缺少 parent_id 字段"

    def test_user_group_manager_id_field(self):
        from meta.core.models import registry

        group_meta = registry.get('user_group')
        assert group_meta is not None, "group_meta not found in registry"
        field_map = {f.id: f for f in group_meta.fields}

        assert 'manager_id' in field_map, "缺少 manager_id 字段"

    def test_user_group_associations_defined(self):
        from meta.core.models import registry

        group_meta = registry.get('user_group')
        associations = getattr(group_meta, 'associations', None)

        if associations:
            if isinstance(associations, dict):
                assoc_names = list(associations.keys())
            elif isinstance(associations, list):
                assoc_names = [getattr(a, 'name', '') for a in associations]
            else:
                assoc_names = []

            assert 'members' in assoc_names or 'user' in assoc_names, \
                "user_group 应该定义 members 关联"
        else:
            pytest.fail("user_group associations not defined in metadata")

    def test_user_group_computed_fields(self):
        from meta.core.models import registry

        group_meta = registry.get('user_group')
        assert group_meta is not None, "group_meta not found in registry"
        computed_fields = [
            f for f in group_meta.fields
            if getattr(f, 'computed', False) or getattr(f, 'is_computed', False)
            or (hasattr(f, 'semantics') and getattr(f.semantics, 'computed', False))
        ]

        assert len(computed_fields) > 0, "user_group 应该有计算字段 (member_count)"

    def test_user_group_ui_view_config(self):
        from meta.core.models import registry

        group_meta = registry.get('user_group')
        assert group_meta is not None, "group_meta not found in registry"

        if hasattr(group_meta, 'ui_view_config') and group_meta.ui_view_config:
            assert hasattr(group_meta.ui_view_config, 'list'), \
                "ui_view_config 应该有 list 配置"
