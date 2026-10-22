import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Phase 11 对象适配测试 - Org CRUD

测试范围：
- Org 基本 CRUD 操作
- Org 层级关系 (parent_id)
- Org 管理员 (manager_id, 已废弃但列保留)
- Org 成员计数 (member_count)
- Org YAML 元数据驱动

对应规范: TC-PA-016 ~ TC-PA-030

[迁移 2026-10-22] 原 UserGroup 测试整体迁到 Org：
    user_groups → orgs (v072), user_group.yaml → org.yaml,
    legacy 表由 v089 DROP。英文 object_type 'user_group' 不再是 org 的
    alias（org.yaml 只保留中文 alias「用户组」），故须显式用 'org'。
"""

import pytest
import os
import tempfile


class TestOrgCRUD:
    """Org 基本 CRUD 测试"""

    @pytest.fixture
    def data_source(self):
        from meta.core.datasource import get_data_source
        from meta.core.table_name_validator import invalidate_cache

        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(db_fd)

        ds = get_data_source('sqlite', database=db_path)

        # [夹具补齐] bo_framework.commit / rollback 依赖 get_runtime_config()
        #   单例，该单例只在 server 初始化时由 detect_runtime_config(db_path) 设置。
        #   测试用临时库不经过 server 启动，必须在此补上，否则写路径直接报
        #   "[V007.15 L0] DB config not detected yet"。
        from meta.core.db_config_detector import detect_runtime_config
        detect_runtime_config(db_path)

        # [迁移] 表名 user_groups → orgs。列对齐 org.yaml：
        #   code 有 pattern 约束 (^[a-z][a-z0-9_]*$)、org_type/status 有默认值，
        #   org_scope 为已废弃列（保留待 v095 硬删）。
        ds.execute('''CREATE TABLE IF NOT EXISTS orgs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL,
            org_type VARCHAR(50) DEFAULT 'department',
            org_scope VARCHAR(50) DEFAULT 'internal',
            status VARCHAR(50) DEFAULT 'active',
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

        # [迁移] 关联表 user_group_members → org_members (v072)
        ds.execute('''CREATE TABLE IF NOT EXISTS org_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            is_manager INTEGER DEFAULT 0,
            created_at DATETIME,
            UNIQUE(org_id, user_id)
        )''')
        ds.commit()

        # org 启用了 audit_aspect
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

        # [夹具补齐] 查询路径按 updated_at 派生时会读 v_audit_all；
        #   生产库由迁移 v007_50 创建该视图，临时库需等价补齐。
        ds.execute('CREATE VIEW IF NOT EXISTS v_audit_all AS SELECT * FROM audit_logs')
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

    def _insert_org(self, data_source, code, name, description=None, parent_id=None, manager_id=None):
        data = {'code': code, 'name': name}
        if description is not None:
            data['description'] = description
        if parent_id is not None:
            data['parent_id'] = parent_id
        if manager_id is not None:
            data['manager_id'] = manager_id
        return data_source.insert('orgs', data)

    def _insert_user(self, data_source, username, email):
        return data_source.insert('users', {'username': username, 'email': email})

    def _insert_member(self, data_source, org_id, user_id):
        return data_source.insert('org_members', {'org_id': org_id, 'user_id': user_id})

    def test_create_org_basic(self, bo_framework, data_source):
        result = bo_framework.create('org', {
            'code': 'test_group',
            'name': '测试组织',
            'description': '这是一个测试组织'
        })

        assert result.success, f"创建失败: {result.message}"

        cursor = data_source.execute("SELECT * FROM orgs WHERE code = ?", ('test_group',))
        group = cursor.fetchone()
        assert group is not None

    def test_create_org_with_hierarchy(self, bo_framework, data_source):
        parent_id = self._insert_org(data_source, 'parent_group', '父组织')

        result = bo_framework.create('org', {
            'code': 'child_group',
            'name': '子组织',
            'parent_id': parent_id
        })

        assert result.success, f"创建失败: {result.message}"

        record = data_source.find_by_id('orgs', result.data.get('id') if result.data else None)
        if record:
            assert record.get('parent_id') == parent_id

    def test_create_org_with_manager(self, bo_framework, data_source):
        # [迁移] manager_id 自 v088 起为废弃字段（零数据/无消费点），但列仍保留
        manager_id = self._insert_user(data_source, 'manager_user', 'manager@test.com')

        result = bo_framework.create('org', {
            'code': 'managed_group',
            'name': '有管理员的组织',
            'manager_id': manager_id
        })

        assert result.success, f"创建失败: {result.message}"

    def test_read_org_with_computed_fields(self, bo_framework, data_source):
        org_id = self._insert_org(data_source, 'computed_group', '计算字段测试')
        user_id = self._insert_user(data_source, 'member1', 'member1@test.com')
        self._insert_member(data_source, org_id, user_id)

        result = bo_framework.read('org', org_id)

        assert result.success, f"读取失败: {result.message}"

    def test_update_org_hierarchy(self, bo_framework, data_source):
        org_id = self._insert_org(data_source, 'update_group', '更新前')
        new_parent_id = self._insert_org(data_source, 'new_parent', '新父组')

        result = bo_framework.update('org', org_id, {'parent_id': new_parent_id})

        assert result.success, f"更新失败: {result.message}"

        record = data_source.find_by_id('orgs', org_id)
        assert record is not None
        assert record.get('parent_id') == new_parent_id

    def test_update_org_manager(self, bo_framework, data_source):
        org_id = self._insert_org(data_source, 'manager_update', '管理员更新')
        new_manager_id = self._insert_user(data_source, 'new_manager', 'newmanager@test.com')

        result = bo_framework.update('org', org_id, {'manager_id': new_manager_id})

        assert result.success, f"更新失败: {result.message}"

    def test_delete_org_basic(self, bo_framework, data_source):
        org_id = self._insert_org(data_source, 'delete_group', '删除测试')

        result = bo_framework.delete('org', org_id)

        assert result.success, f"删除失败: {result.message}"

        record = data_source.find_by_id('orgs', org_id)
        assert record is None

    def test_delete_org_with_children(self, bo_framework, data_source):
        # [迁移] org deletion_policy.mode=restrict：有子组时禁止删除
        parent_id = self._insert_org(data_source, 'parent_for_delete', '父组')
        self._insert_org(data_source, 'child_for_delete', '子组', parent_id=parent_id)

        result = bo_framework.delete('org', parent_id)

        assert not result.success, "有子组织时应被 restrict 策略拒绝删除"

    def test_delete_org_with_members(self, bo_framework, data_source):
        # [迁移] org deletion_policy.restrict_on 含 org_members
        org_id = self._insert_org(data_source, 'group_with_members', '有成员组')
        user_id = self._insert_user(data_source, 'member_user', 'member@test.com')
        self._insert_member(data_source, org_id, user_id)

        result = bo_framework.delete('org', org_id)

        assert not result.success, "有成员时应被 restrict 策略拒绝删除"

    def test_list_org_tree_structure(self, bo_framework, data_source):
        root_id = self._insert_org(data_source, 'root_group', '根组')
        self._insert_org(data_source, 'child_in_list', '子组', parent_id=root_id)

        result = bo_framework.execute('org', 'crud_query', {
            'parent_id': root_id
        })

        assert result.success, f"查询失败: {result.message}"
        data = result.data or []
        assert len(data) >= 1

    def test_list_org_top_level(self, bo_framework, data_source):
        self._insert_org(data_source, 'top_level_1', '顶级组1')
        self._insert_org(data_source, 'not_top', '非顶级', parent_id=1)

        result = bo_framework.query('org')

        assert result.success, f"查询失败: {result.message}"

    def test_list_org_search(self, bo_framework, data_source):
        self._insert_org(data_source, 'search_group', '搜索目标组', '包含关键词')
        self._insert_org(data_source, 'other_group', '其他组', '不包含')

        result = bo_framework.execute('org', 'crud_query', {
            'search': '搜索目标'
        })

        assert result.success, f"查询失败: {result.message}"
        data = result.data or []
        assert len(data) >= 1

    def test_org_detail_yaml_config(self, bo_framework):
        from meta.core.models import registry

        group_meta = registry.get('org')
        assert group_meta is not None, "org 元数据未加载"

        assert hasattr(group_meta, 'fields'), "org 应该有 fields 属性"

        field_names = [f.id for f in group_meta.fields]
        assert 'name' in field_names, "org 应该有 name 字段"
        assert 'code' in field_names, "org 应该有 code 字段"

    def test_org_hierarchy_path(self, bo_framework, data_source):
        level1_id = self._insert_org(data_source, 'level1', '一级组')
        level2_id = self._insert_org(data_source, 'level2', '二级组', parent_id=level1_id)
        self._insert_org(data_source, 'level3', '三级组', parent_id=level2_id)

        result = bo_framework.read('org', level2_id)

        assert result.success, f"读取失败: {result.message}"

    def test_org_member_count(self, bo_framework, data_source):
        org_id = self._insert_org(data_source, 'count_group', '计数组')

        for i in range(3):
            user_id = self._insert_user(data_source, f'count_user_{i}', f'count{i}@test.com')
            self._insert_member(data_source, org_id, user_id)

        result = bo_framework.read('org', org_id)

        assert result.success, f"读取失败: {result.message}"


class TestOrgMetaConfiguration:
    """Org 元数据配置测试

    [迁移] 原 TestUserGroupMetaConfiguration：user_groups → orgs（v072），
    user_group.yaml 已删除；group_meta 指向 registry.get('org')。
    """

    def test_org_yaml_loaded(self):
        from meta.core.models import registry

        group_meta = registry.get('org')
        assert group_meta is not None, "org 元数据未加载"
        assert group_meta.id == 'org', f"期望 id='org', 实际={group_meta.id}"

    def test_org_parent_id_field(self):
        from meta.core.models import registry

        group_meta = registry.get('org')
        assert group_meta is not None, "group_meta not found in registry"
        field_map = {f.id: f for f in group_meta.fields}

        assert 'parent_id' in field_map, "缺少 parent_id 字段"

    def test_org_manager_id_field(self):
        from meta.core.models import registry

        group_meta = registry.get('org')
        assert group_meta is not None, "group_meta not found in registry"
        field_map = {f.id: f for f in group_meta.fields}

        assert 'manager_id' in field_map, "缺少 manager_id 字段"

    def test_org_associations_defined(self):
        from meta.core.models import registry

        group_meta = registry.get('org')
        associations = getattr(group_meta, 'associations', None)

        if associations:
            if isinstance(associations, dict):
                assoc_names = list(associations.keys())
            elif isinstance(associations, list):
                assoc_names = [getattr(a, 'name', '') for a in associations]
            else:
                assoc_names = []

            assert 'members' in assoc_names or 'user' in assoc_names, \
                "org 应该定义 members 关联"
        else:
            pytest.fail("org associations not defined in metadata")

    def test_org_computed_fields(self):
        from meta.core.models import registry

        group_meta = registry.get('org')
        assert group_meta is not None, "group_meta not found in registry"
        computed_fields = [
            f for f in group_meta.fields
            if getattr(f, 'computed', False) or getattr(f, 'is_computed', False)
            or (hasattr(f, 'semantics') and getattr(f.semantics, 'computed', False))
        ]

        assert len(computed_fields) > 0, "org 应该有计算字段 (member_count)"

    def test_org_ui_view_config(self):
        from meta.core.models import registry

        group_meta = registry.get('org')
        assert group_meta is not None, "group_meta not found in registry"

        if hasattr(group_meta, 'ui_view_config') and group_meta.ui_view_config:
            assert hasattr(group_meta.ui_view_config, 'list'), \
                "ui_view_config 应该有 list 配置"
