# -*- coding: utf-8 -*-
"""
业务对象层级测试

合并以下测试文件:
- test_hierarchy_path.py (层级路径)
- test_hierarchy_service.py (层级服务)
- test_set_current_action.py (设置当前版本操作)
- test_scope_mode.py (范围模式)

测试范围:
- 层级路径计算
- 层级树构建
- set_current 操作
- 范围模式过滤
"""

import pytest
import sqlite3
import tempfile
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

pytestmark = pytest.mark.integration


# ==================== 共享 Fixtures ====================

@pytest.fixture(autouse=True)
def clean_registry():
    """清理注册表，测试后恢复"""
    from meta.core.models import registry
    saved = dict(registry._objects)
    registry._objects.clear()
    yield
    registry._objects = saved


@pytest.fixture
def mock_data_source():
    """创建模拟数据源"""
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT
        );
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT,
            product_id INTEGER,
            is_current INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT,
            version_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS sub_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT,
            domain_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS service_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT,
            sub_domain_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS business_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT,
            service_module_id INTEGER
        );
    """)
    conn.commit()

    class MockDS:
        def __init__(self, connection):
            self._conn = connection

        def execute(self, sql, params=None):
            cursor = self._conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            self._conn.commit()
            return cursor

        def commit(self):
            self._conn.commit()

    yield MockDS(conn), db_path
    conn.close()
    os.unlink(db_path)


def _seed_hierarchy_data(ds):
    """填充层级测试数据"""
    ds.execute("INSERT INTO products (name, code) VALUES (?, ?)", ['Product1', 'P1'])
    ds.execute("INSERT INTO versions (name, code, product_id) VALUES (?, ?, ?)", ['V1', 'v1', 1])
    ds.execute("INSERT INTO domains (name, code, version_id) VALUES (?, ?, ?)", ['Domain1', 'd1', 1])
    ds.execute("INSERT INTO sub_domains (name, code, domain_id) VALUES (?, ?, ?)", ['Sub1', 'sd1', 1])
    ds.execute("INSERT INTO service_modules (name, code, sub_domain_id) VALUES (?, ?, ?)", ['SM1', 'sm1', 1])
    ds.execute("INSERT INTO business_objects (name, code, service_module_id) VALUES (?, ?, ?)", ['BO1', 'bo1', 1])


# ==================== 层级路径测试 ====================

class TestHierarchyPath:
    """层级路径测试"""

    def test_hierarchy_depth_levels(self, clean_registry):
        """测试各层级对象的深度"""
        from meta.core.models import MetaObject

        product = MetaObject(
            id="product", name="产品", table_name="products", parent_object=""
        )
        from meta.core.models import registry
        registry.register(product)

        version = MetaObject(
            id="version", name="版本", table_name="versions", parent_object="product"
        )
        registry.register(version)

        domain = MetaObject(
            id="domain", name="领域", table_name="domains", parent_object="version"
        )
        registry.register(domain)

        business_obj = MetaObject(
            id="business_object", name="业务对象",
            table_name="business_objects", parent_object="domain"
        )
        registry.register(business_obj)

        assert product.get_hierarchy_depth() == 0
        assert version.get_hierarchy_depth() == 1
        assert domain.get_hierarchy_depth() == 2
        assert business_obj.get_hierarchy_depth() == 3

    def test_hierarchy_path_template(self, clean_registry):
        """测试层级路径模板"""
        from meta.core.models import MetaObject, registry

        product = MetaObject(
            id="product", name="产品", table_name="products", parent_object=""
        )
        registry.register(product)

        version = MetaObject(
            id="version", name="版本", table_name="versions", parent_object="product"
        )
        registry.register(version)

        domain = MetaObject(
            id="domain", name="领域", table_name="domains", parent_object="version"
        )
        registry.register(domain)

        business_obj = MetaObject(
            id="business_object", name="业务对象",
            table_name="business_objects", parent_object="domain"
        )
        registry.register(business_obj)

        assert product.get_hierarchy_path_template() == "product"
        assert version.get_hierarchy_path_template() == "product/version"
        assert domain.get_hierarchy_path_template() == "product/version/domain"
        assert business_obj.get_hierarchy_path_template() == "product/version/domain/business_object"

    def test_hierarchy_path_field(self, clean_registry):
        """测试层级路径字段"""
        from meta.core.models import MetaObject, MetaField, FieldType, registry

        obj_with_path = MetaObject(
            id="test_obj",
            name="测试对象",
            table_name="test_objects",
            parent_object="parent",
            fields=[
                MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id"),
                MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name"),
                MetaField(
                    id="hierarchy_path", name="层级路径", field_type=FieldType.STRING,
                    db_column="hierarchy_path",
                    computed=True, is_hierarchy_path=True, hierarchy_separator="/"
                ),
                MetaField(
                    id="hierarchy_depth", name="层级深度", field_type=FieldType.INTEGER,
                    db_column="hierarchy_depth", computed=True
                ),
            ]
        )

        path_field = obj_with_path.get_hierarchy_path_field()

        assert path_field is not None
        assert path_field.is_hierarchy_path is True
        assert path_field.hierarchy_separator == "/"


# ==================== 层级服务测试 ====================

class TestHierarchyService:
    """层级服务测试"""

    def test_get_hierarchy_default(self):
        """获取默认层级"""
        from meta.services.hierarchy_service import HierarchyService
        svc = HierarchyService()
        result = svc.get_hierarchy('biz_hierarchy')
        assert result is None or isinstance(result, dict)
        if isinstance(result, dict):
            assert 'levels' in result

    def test_get_levels(self):
        """获取层级列表"""
        from meta.services.hierarchy_service import HierarchyService
        svc = HierarchyService()
        levels = svc.get_levels('biz_hierarchy')
        assert isinstance(levels, list)
        assert len(levels) > 0
        objects = [lv['object'] for lv in levels]
        assert 'product' in objects
        assert 'version' in objects

    def test_build_tree_full(self, mock_data_source):
        """构建完整树"""
        from meta.services.hierarchy_service import HierarchyService
        ds, _ = mock_data_source
        _seed_hierarchy_data(ds)
        svc = HierarchyService()
        tree = svc.build_tree(data_source=ds, include_relation_counts=False)
        assert isinstance(tree, list)
        assert len(tree) >= 1
        root = tree[0]
        assert root['level'] == 'product'
        assert 'children' in root

    def test_build_tree_subtree(self, mock_data_source):
        """构建子树"""
        from meta.services.hierarchy_service import HierarchyService
        ds, _ = mock_data_source
        _seed_hierarchy_data(ds)
        svc = HierarchyService()
        tree = svc.build_tree(
            object_type='version',
            parent_id=1,
            data_source=ds,
            include_relation_counts=False
        )
        assert isinstance(tree, list)
        if tree:
            assert tree[0]['level'] == 'version'

    def test_build_tree_with_version(self, mock_data_source):
        """带版本构建树"""
        from meta.services.hierarchy_service import HierarchyService
        ds, _ = mock_data_source
        _seed_hierarchy_data(ds)
        svc = HierarchyService()
        tree = svc.build_tree(
            version_id=1,
            data_source=ds,
            include_relation_counts=False
        )
        assert isinstance(tree, list)

    def test_hierarchy_config_from_yaml(self):
        """从 YAML 加载层级配置"""
        from meta.services.hierarchy_service import HierarchyService
        svc = HierarchyService()
        hierarchy = svc.get_hierarchy('biz_hierarchy')
        assert hierarchy is None or isinstance(hierarchy, dict)
        if isinstance(hierarchy, dict):
            assert hierarchy['id'] == 'biz_hierarchy'
            assert 'name' in hierarchy

    def test_hierarchy_levels_structure(self):
        """层级结构验证"""
        from meta.services.hierarchy_service import HierarchyService
        svc = HierarchyService()
        levels = svc.get_levels('biz_hierarchy')
        assert len(levels) >= 6
        for lv in levels:
            assert 'object' in lv
            assert 'display_name' in lv
            assert 'level' in lv

    def test_build_tree_empty_data(self, mock_data_source):
        """空数据构建树"""
        from meta.services.hierarchy_service import HierarchyService
        ds, _ = mock_data_source
        svc = HierarchyService()
        tree = svc.build_tree(data_source=ds, include_relation_counts=False)
        assert isinstance(tree, list)
        assert len(tree) == 0


# ==================== set_current 操作测试 ====================

class TestSetCurrentAction:
    """set_current 操作测试"""

    def test_set_current_action_has_behavior(self):
        """验证 set_current 操作有配置的行为"""
        from meta.core.yaml_loader import load_yaml_file, get_yaml_schema_dir

        schema_dir = get_yaml_schema_dir()
        version_file = os.path.join(schema_dir, 'version.yaml')
        version_meta = load_yaml_file(version_file)

        set_current = None
        for action in version_meta.actions:
            if action.id == 'set_current':
                set_current = action
                break

        assert set_current is not None, "set_current action not found in version.yaml"

        assert set_current.behavior is not None
        assert len(set_current.behavior.effects) == 2
        assert set_current.behavior.effects[0].type == 'set_fields'
        assert set_current.behavior.effects[0].fields == {'is_current': True}
        assert set_current.behavior.effects[1].type == 'trigger'

    def test_set_current_action_execution(self):
        """测试 set_current 操作执行"""
        from meta.core.datasource import DataSourceFactory, DataSourceType
        from meta.core.yaml_loader import load_yaml_file, get_yaml_schema_dir
        from meta.core.action_executor import ActionExecutor

        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(db_fd)

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    code TEXT UNIQUE NOT NULL,
                    is_current INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')

            cursor.execute("INSERT INTO versions (product_id, name, code, is_current) VALUES (1, 'V1.0', 'V1.0', 1)")
            cursor.execute("INSERT INTO versions (product_id, name, code, is_current) VALUES (1, 'V2.0', 'V2.0', 0)")
            cursor.execute("INSERT INTO versions (product_id, name, code, is_current) VALUES (1, 'V3.0', 'V3.0', 0)")
            conn.commit()
            conn.close()

            ds = DataSourceFactory.create(DataSourceType.SQLITE, path=db_path)

            schema_dir = get_yaml_schema_dir()
            version_file = os.path.join(schema_dir, 'version.yaml')
            version_meta = load_yaml_file(version_file)

            executor = ActionExecutor(ds)
            result = executor.execute(version_meta, 'set_current', {'id': 2})

            assert result.success

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, is_current FROM versions")
            rows = cursor.fetchall()
            conn.close()

            v1_is_current = [r for r in rows if r[0] == 1][0][2]
            v2_is_current = [r for r in rows if r[0] == 2][0][2]
            v3_is_current = [r for r in rows if r[0] == 3][0][2]

            assert v1_is_current == 0, "V1.0 should no longer be current"
            assert v2_is_current == 1, "V2.0 should be current"
            assert v3_is_current == 0, "V3.0 should not be current"

        finally:
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except:
                    pass


# ==================== 范围模式测试 ====================

class TestScopeMode:
    """范围模式测试"""

    def test_scope_mode_documentation(self):
        """测试 scope_mode 文档"""
        from meta.api.special_routes_api import list_relationships

        doc = list_relationships.__doc__
        if doc is None:
            pytest.skip("list_relationships has no docstring, skipping doc check")
        assert 'scope_mode' in doc
        assert 'involved' in doc
        assert 'internal' in doc
