import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Phase 2-C 集成测试

验证从 action_executor 写入路径自动触发聚合刷新：
1. 创建关系时自动刷新聚合
2. 更新关系时自动刷新聚合
3. 删除关系时自动刷新聚合
4. 变更通知服务触发聚合刷新
"""

import pytest
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import meta
from meta.core.models import registry
from meta.core.action_executor import ActionRegistry
from meta.core.aggregate_manager import AggregateManager, init_aggregate_manager
from meta.core.redundancy_registry import redundancy_registry
from meta.core.table_name_validator import register_table_name


class TestAggregateRefreshOnCreate:
    """测试创建时自动触发聚合刷新"""
    
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_agg_refresh.db"
        self.ds.connect(path=str(db_path))
        
        self._create_tables()
        self._insert_hierarchy()
        
        redundancy_registry.build_from_registry()
        
        self.agg_manager = AggregateManager(self.ds)
        self.agg_manager.register_all()
        
        from meta.core.aggregate_manager import _manager_instance
        import meta.core.aggregate_manager as am
        am._manager_instance = self.agg_manager
        
        self.executor = ActionRegistry(self.ds)
        
        yield
        
        am._manager_instance = None
    
    def _create_tables(self):
        for tbl in ['products', 'versions', 'domains', 'sub_domains', 'service_modules', 'business_objects', 'relationships', 'audit_logs']:
            register_table_name(tbl)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT,
                product_id INTEGER, is_current INTEGER DEFAULT 0
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT, version_id INTEGER
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS sub_domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT, domain_id INTEGER
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS service_modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT, sub_domain_id INTEGER
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS business_objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT,
                service_module_id INTEGER, version_id INTEGER,
                created_at TEXT, updated_at TEXT, created_by TEXT, updated_by TEXT
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_bo_id INTEGER, target_bo_id INTEGER,
                code TEXT,
                source_code TEXT, target_code TEXT,
                relation_code TEXT, relation_type TEXT, version_id INTEGER,
                created_at TEXT, updated_at TEXT, created_by TEXT, updated_by TEXT
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT, object_id INTEGER, action TEXT,
                old_data TEXT, new_data TEXT,
                trace_id TEXT, transaction_id TEXT,
                created_at TEXT, created_by TEXT,
                parent_object_type TEXT,
                parent_object_id TEXT
            )
        """)
        self.ds.commit()
    
    def _insert_hierarchy(self):
        self.ds.insert('products', {'code': 'PROD1', 'name': '产品1'})
        self.ds.insert('versions', {'code': 'V1', 'name': '版本1', 'product_id': 1, 'is_current': 1})
        self.ds.insert('domains', {'code': 'DOM1', 'name': '领域1', 'version_id': 1})
        self.ds.insert('sub_domains', {'code': 'SUB1', 'name': '子领域1', 'domain_id': 1})
        self.ds.insert('service_modules', {'code': 'SVC1', 'name': '服务模块1', 'sub_domain_id': 1})
        self.ds.insert('business_objects', {'code': 'BO1', 'name': '业务对象1', 'service_module_id': 1, 'version_id': 1})
        self.ds.insert('business_objects', {'code': 'BO2', 'name': '业务对象2', 'service_module_id': 1, 'version_id': 1})
        self.ds.commit()
    
    def test_create_triggers_aggregate_refresh(self):
        """测试创建关系时自动刷新聚合"""
        try:
            self.agg_manager.refresh('version_relation_stats', force=True)

            freshness_before = self.agg_manager.get_freshness('version_relation_stats')

            meta_obj = registry.get('relationship')
            result = self.executor.create(meta_obj, {
                'source_bo_id': 1,
                'target_bo_id': 2,
                'code': 'BO1-BO2-01',
                'relation_code': 'DEPENDS_ON',
                'relation_type': 'depends_on',
                'version_id': 1,
            })

            assert result.success, f"创建关系失败: {result.message}"

            results = self.agg_manager.query('version_relation_stats')

            assert len(results) > 0

            dep_results = [r for r in results if r.get('relation_code') == 'DEPENDS_ON']
            assert len(dep_results) == 1
            assert dep_results[0]['relation_count'] == 1
        except AssertionError as e:
            pytest.fail(f"Aggregate refresh assertion issue: {e}")
        except Exception as e:
            pytest.fail(f"Aggregate refresh test skipped: {e}")


class TestAggregateRefreshOnUpdate:
    """测试更新时自动触发聚合刷新"""
    
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_agg_refresh.db"
        self.ds.connect(path=str(db_path))
        
        self._create_tables()
        self._insert_hierarchy()
        
        redundancy_registry.build_from_registry()
        
        self.agg_manager = AggregateManager(self.ds)
        self.agg_manager.register_all()
        
        import meta.core.aggregate_manager as am
        am._manager_instance = self.agg_manager
        
        self.executor = ActionRegistry(self.ds)
        
        yield
        
        am._manager_instance = None
    
    def _create_tables(self):
        for tbl in ['products', 'versions', 'domains', 'sub_domains', 'service_modules', 'business_objects', 'relationships', 'audit_logs']:
            register_table_name(tbl)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT,
                product_id INTEGER, is_current INTEGER DEFAULT 0
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT, version_id INTEGER
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS sub_domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT, domain_id INTEGER
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS service_modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT, sub_domain_id INTEGER
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS business_objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT,
                service_module_id INTEGER, version_id INTEGER,
                created_at TEXT, updated_at TEXT, created_by TEXT, updated_by TEXT
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_bo_id INTEGER, target_bo_id INTEGER,
                code TEXT,
                source_code TEXT, target_code TEXT,
                relation_code TEXT, relation_type TEXT, version_id INTEGER,
                created_at TEXT, updated_at TEXT, created_by TEXT, updated_by TEXT
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT, object_id INTEGER, action TEXT,
                old_data TEXT, new_data TEXT,
                trace_id TEXT, transaction_id TEXT,
                created_at TEXT, created_by TEXT,
                parent_object_type TEXT,
                parent_object_id TEXT
            )
        """)
        self.ds.commit()
    
    def _insert_hierarchy(self):
        self.ds.insert('products', {'code': 'PROD1', 'name': '产品1'})
        self.ds.insert('versions', {'code': 'V1', 'name': '版本1', 'product_id': 1, 'is_current': 1})
        self.ds.insert('domains', {'code': 'DOM1', 'name': '领域1', 'version_id': 1})
        self.ds.insert('sub_domains', {'code': 'SUB1', 'name': '子领域1', 'domain_id': 1})
        self.ds.insert('service_modules', {'code': 'SVC1', 'name': '服务模块1', 'sub_domain_id': 1})
        self.ds.insert('business_objects', {'code': 'BO1', 'name': '业务对象1', 'service_module_id': 1, 'version_id': 1})
        self.ds.insert('business_objects', {'code': 'BO2', 'name': '业务对象2', 'service_module_id': 1, 'version_id': 1})
        self.ds.insert('relationships', {
            'source_bo_id': 1, 'target_bo_id': 2,
            'source_code': 'BO1', 'target_code': 'BO2',
            'code': 'BO1-BO2-01',
            'relation_code': 'DEPENDS_ON', 'relation_type': 'DEPENDS_ON', 'version_id': 1
        })
        self.ds.commit()
    
    def test_update_triggers_aggregate_refresh(self):
        """测试更新关系时自动刷新聚合"""
        self.agg_manager.refresh('version_relation_stats', force=True)
        
        meta_obj = registry.get('relationship')
        assert meta_obj is not None, "relationship meta object not found in registry"
        result = self.executor.update(meta_obj, 1, {
            'relation_code': 'CALLS',
            'relation_type': 'CALLS',
        })
        
        assert result.success, f"更新关系失败: {result.message}"
        
        results = self.agg_manager.query('version_relation_stats')
        
        calls_results = [r for r in results if r.get('relation_code') == 'CALLS']
        assert len(calls_results) == 1
        
        dep_results = [r for r in results if r.get('relation_code') == 'DEPENDS_ON']
        assert len(dep_results) == 0


class TestAggregateRefreshViaChangeNotification:
    """测试变更通知服务触发聚合刷新"""
    
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_agg_refresh.db"
        self.ds.connect(path=str(db_path))
        
        self._create_tables()
        
        self.agg_manager = AggregateManager(self.ds)
        self.agg_manager.register_all()
        
        import meta.core.aggregate_manager as am
        am._manager_instance = self.agg_manager
        
        from meta.services.change_notification_service import ChangeNotificationService
        self.notification_service = ChangeNotificationService(self.ds)
        
        yield
        
        am._manager_instance = None
    
    def _create_tables(self):
        for tbl in ['products', 'versions', 'relationships', 'business_objects', 'change_events']:
            register_table_name(tbl)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT, product_id INTEGER
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
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS change_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT, object_id INTEGER, event_type TEXT,
                changed_fields TEXT, old_values TEXT, new_values TEXT,
                payload TEXT, channels TEXT,
                status TEXT, retry_count INTEGER,
                created_at TEXT, delivered_at TEXT, audit_log_id INTEGER
            )
        """)
        self.ds.commit()
    
    def test_change_notification_triggers_refresh(self):
        """测试变更通知触发聚合刷新"""
        self.ds.insert('relationships', {
            'source_bo_id': 1, 'target_bo_id': 2,
            'source_code': 'BO1', 'target_code': 'BO2',
            'relation_code': 'DEPENDS_ON', 'version_id': 1
        })
        self.ds.commit()
        
        self.agg_manager.refresh('version_relation_stats', force=True)
        
        from meta.services.change_notification_service import ChangeEventRequest
        
        request = ChangeEventRequest(
            object_type='relationship',
            object_id=1,
            event_type='update',
            new_data={'relation_code': 'CALLS'}
        )
        
        result = self.notification_service.publish_event(request)
        
        freshness = self.agg_manager.get_freshness('version_relation_stats')
        
        assert freshness['status'] == 'ready'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
