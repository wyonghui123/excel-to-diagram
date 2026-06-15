import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
AggregateManager 单元测试

测试聚合管理器的核心功能：
1. 注册聚合定义
2. 全量刷新聚合数据
3. 查询聚合数据
4. 缓存TTL和新鲜度
5. 事件驱动刷新
"""

import pytest
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import meta
from meta.core.aggregate_manager import AggregateManager
from meta.core.aggregate_refresh_handler import AggregateRefreshHandler
from meta.core.table_name_validator import register_table_name

register_table_name('relationships')
register_table_name('products')
register_table_name('versions')
register_table_name('domains')
register_table_name('sub_domains')
register_table_name('service_modules')
register_table_name('business_objects')
register_table_name('users')
register_table_name('roles')
register_table_name('user_groups')
register_table_name('user_group_members')
register_table_name('role_permissions')
register_table_name('annotations')


class TestAggregateManagerRegistration:
    """测试聚合注册"""
    
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_agg_manager.db"
        self.ds.connect(path=str(db_path))
        
        self.manager = AggregateManager(self.ds)
    
    def test_register_from_analytical_model(self):
        """测试从分析模型注册聚合"""
        count = self.manager.register_from_analytical_model('relationship')
        
        if count < 2: pytest.fail("relationship 应该有至少 2 个聚合")
    
    def test_register_business_object(self):
        """测试注册 business_object 的聚合"""
        count = self.manager.register_from_analytical_model('business_object')
        
        if count < 1: pytest.fail("business_object 应该有至少 1 个聚合")
    
    def test_register_non_analytical_object(self):
        """测试注册没有分析模型的对象"""
        count = self.manager.register_from_analytical_model('product')
        
        assert count == 0
    
    def test_register_all(self):
        """测试注册所有对象的聚合"""
        count = self.manager.register_all()
        
        if count < 3: pytest.fail("应该有至少 3 个聚合")
    
    def test_get_registered_aggregates(self):
        """测试获取已注册聚合列表"""
        self.manager.register_all()
        
        aggregates = self.manager.get_registered_aggregates()
        
        if len(aggregates) < 3: pytest.fail('not enough items')
        
        agg_ids = [a['id'] for a in aggregates]
        assert 'version_relation_stats' in agg_ids
        assert 'version_bo_stats' in agg_ids


class TestAggregateManagerRefresh:
    """测试聚合刷新"""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        from meta.core.sql_adapters import SQLiteAdapter
        from meta.core.table_name_validator import _VALID_TABLES_CACHE
        import meta.core.table_name_validator as tnv
        tnv._VALID_TABLES_CACHE = None

        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_agg_refresh.db"
        self.ds.connect(path=str(db_path))
        
        self._create_tables()
        self._insert_test_data()
        
        self.manager = AggregateManager(self.ds)
        self.manager.register_all()
    
    def _create_tables(self):
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT, name TEXT
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT, product_id INTEGER,
                UNIQUE(product_id, name)
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT, name TEXT, version_id INTEGER
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS sub_domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT, name TEXT, domain_id INTEGER
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS service_modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT, name TEXT, sub_domain_id INTEGER
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS business_objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT, name TEXT, service_module_id INTEGER, version_id INTEGER
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_bo_id INTEGER, target_bo_id INTEGER,
                code TEXT,
                source_code TEXT, target_code TEXT,
                relation_code TEXT, relation_type TEXT, version_id INTEGER
            )
        """)
        self.ds.commit()
    
    def _insert_test_data(self):
        self.ds.insert('products', {'code': 'PROD1', 'name': '产品1'})
        self.ds.insert('versions', {'name': '版本1', 'product_id': 1})
        self.ds.insert('domains', {'code': 'DOM1', 'name': '领域1', 'version_id': 1})
        self.ds.insert('sub_domains', {'code': 'SUB1', 'name': '子领域1', 'domain_id': 1})
        self.ds.insert('service_modules', {'code': 'SVC1', 'name': '服务模块1', 'sub_domain_id': 1})
        
        self.ds.insert('business_objects', {'code': 'BO1', 'name': '业务对象1', 'service_module_id': 1, 'version_id': 1})
        self.ds.insert('business_objects', {'code': 'BO2', 'name': '业务对象2', 'service_module_id': 1, 'version_id': 1})
        self.ds.insert('business_objects', {'code': 'BO3', 'name': '业务对象3', 'service_module_id': 1, 'version_id': 1})
        
        self.ds.insert('relationships', {'source_bo_id': 1, 'target_bo_id': 2, 'source_code': 'BO1', 'target_code': 'BO2', 'relation_code': 'DEPENDS_ON', 'version_id': 1})
        self.ds.insert('relationships', {'source_bo_id': 1, 'target_bo_id': 3, 'source_code': 'BO1', 'target_code': 'BO3', 'relation_code': 'CALLS', 'version_id': 1})
        self.ds.insert('relationships', {'source_bo_id': 2, 'target_bo_id': 3, 'source_code': 'BO2', 'target_code': 'BO3', 'relation_code': 'DEPENDS_ON', 'version_id': 1})
        
        self.ds.commit()
    
    def test_refresh_version_relation_stats(self):
        """测试刷新版本关系统计"""
        row_count = self.manager.refresh('version_relation_stats', force=True)
        
        assert row_count > 0, "刷新后应该有数据行"
    
    def test_refresh_creates_aggregate_table(self):
        """测试刷新时自动创建聚合表"""
        self.manager.refresh('version_relation_stats', force=True)
        
        cursor = self.ds.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agg_version_relation_stats'"
        )
        row = cursor.fetchone()
        
        assert row is not None, "应该自动创建聚合表"
    
    def test_query_after_refresh(self):
        """测试刷新后查询聚合数据"""
        self.manager.refresh('version_relation_stats', force=True)
        
        results = self.manager.query('version_relation_stats')
        
        if len(results) == 0: pytest.fail('no results')
        
        dep_results = [r for r in results if r.get('relation_code') == 'DEPENDS_ON']
        assert len(dep_results) == 1
        assert dep_results[0]['relation_count'] == 2
    
    def test_query_with_filter(self):
        """测试带过滤条件的聚合查询"""
        self.manager.refresh('version_relation_stats', force=True)
        
        results = self.manager.query(
            'version_relation_stats',
            filters={'relation_code': 'CALLS'}
        )
        
        if len(results) != 1: pytest.fail(f'unexpected result count: {len(results)}')
        assert results[0]['relation_count'] == 1
    
    def test_refresh_business_object_stats(self):
        """测试刷新业务对象统计"""
        row_count = self.manager.refresh('version_bo_stats', force=True)
        
        if row_count == 0: pytest.fail('no rows affected')
        
        results = self.manager.query('version_bo_stats')
        if len(results) == 0: pytest.fail('no results')
        assert results[0]['bo_count'] == 3
    
    def test_refresh_unknown_aggregate(self):
        """测试刷新未知的聚合"""
        row_count = self.manager.refresh('nonexistent_aggregate')
        
        assert row_count == 0


class TestAggregateManagerFreshness:
    """测试聚合新鲜度"""
    
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_agg_manager.db"
        self.ds.connect(path=str(db_path))
        
        self._create_minimal_tables()
        
        self.manager = AggregateManager(self.ds)
        self.manager.register_all()
    
    def _create_minimal_tables(self):
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, product_id INTEGER,
                UNIQUE(product_id, name)
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_bo_id INTEGER, target_bo_id INTEGER,
                code TEXT,
                source_code TEXT, target_code TEXT,
                relation_code TEXT, relation_type TEXT, version_id INTEGER
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS business_objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT, name TEXT, service_module_id INTEGER, version_id INTEGER
            )
        """)
        self.ds.commit()
    
    def test_freshness_before_refresh(self):
        """测试刷新前的新鲜度"""
        freshness = self.manager.get_freshness('version_relation_stats')
        
        assert freshness['status'] in ('empty', 'unknown')
        assert freshness['is_stale'] == True
    
    def test_freshness_after_refresh(self):
        """测试刷新后的新鲜度"""
        self.ds.insert('relationships', {
            'source_bo_id': 1, 'target_bo_id': 2,
            'source_code': 'BO1', 'target_code': 'BO2',
            'relation_code': 'DEPENDS_ON', 'version_id': 1
        })
        self.ds.commit()
        
        self.manager.refresh('version_relation_stats', force=True)
        
        freshness = self.manager.get_freshness('version_relation_stats')
        
        assert freshness['status'] == 'ready'
        assert freshness['last_refreshed_at'] is not None
        assert freshness['row_count'] > 0
    
    def test_get_all_freshness(self):
        """测试获取所有聚合的新鲜度"""
        all_freshness = self.manager.get_all_freshness()
        
        if len(all_freshness) < 3: pytest.fail('not enough items')


class TestAggregateRefreshHandler:
    """测试聚合刷新处理器"""
    
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_agg_manager.db"
        self.ds.connect(path=str(db_path))
        
        self._create_tables()
        self._insert_test_data()
        
        self.manager = AggregateManager(self.ds)
        self.manager.register_all()
        
        self.handler = AggregateRefreshHandler(self.manager)
    
    def _create_tables(self):
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, product_id INTEGER,
                UNIQUE(product_id, name)
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_bo_id INTEGER, target_bo_id INTEGER,
                code TEXT,
                source_code TEXT, target_code TEXT,
                relation_code TEXT, relation_type TEXT, version_id INTEGER
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS business_objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT, name TEXT, service_module_id INTEGER, version_id INTEGER
            )
        """)
        self.ds.commit()
    
    def _insert_test_data(self):
        self.ds.insert('relationships', {
            'source_bo_id': 1, 'target_bo_id': 2,
            'source_code': 'BO1', 'target_code': 'BO2',
            'relation_code': 'DEPENDS_ON', 'version_id': 1
        })
        self.ds.commit()
    
    def test_on_data_changed(self):
        """测试数据变更触发刷新"""
        refreshed = self.handler.on_data_changed(
            'relationship', record_id=1, event_type='updated'
        )
        
        assert refreshed >= 1, "relationship 变更应该触发至少 1 个聚合刷新"
    
    def test_on_data_changed_non_aggregate_object(self):
        """测试变更不触发聚合的对象"""
        refreshed = self.handler.on_data_changed(
            'product', record_id=1, event_type='updated'
        )
        
        assert refreshed == 0
    
    def test_on_batch_changed(self):
        """测试批量变更"""
        refreshed = self.handler.on_batch_changed([
            {'object_type': 'relationship', 'record_id': 1, 'event_type': 'updated'},
            {'object_type': 'relationship', 'record_id': 2, 'event_type': 'created'},
        ])
        
        assert refreshed >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
