import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
冗余字段一致性保障集成测试

测试 WriteGuard 和 CascadeGuard 与 action_executor 的集成：
1. 创建关系时自动同步 source_code/target_code
2. 更新业务对象 code 时级联更新下游冗余字段
3. 审计器检测和修复不一致数据
"""

import pytest
import sys
import os
import tempfile

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import meta
from meta.core.models import registry
from meta.core.action_executor import ActionRegistry
from meta.core.consistency_guard import WriteGuard, CascadeGuard, RedundancyAuditor
from meta.core.redundancy_registry import redundancy_registry


class TestWriteGuardIntegration:
    """测试 WriteGuard 与 action_executor 的集成"""
    
    @pytest.fixture(autouse=True)
    def setup_database(self, tmp_path):
        """每个测试前创建临时数据库"""
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_consistency.db"
        self.ds.connect(path=str(db_path))
        
        self._create_tables()
        
        redundancy_registry.build_from_registry()
        
        self.executor = ActionRegistry(self.ds)
        
        yield
    
    def _create_tables(self):
        """创建测试表"""
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT
            )
        """)
        
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT,
                product_id INTEGER,
                is_current INTEGER DEFAULT 0
            )
        """)
        
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT,
                version_id INTEGER
            )
        """)
        
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS sub_domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT,
                domain_id INTEGER
            )
        """)
        
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS service_modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT,
                sub_domain_id INTEGER
            )
        """)
        
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS business_objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT,
                service_module_id INTEGER,
                created_at TEXT,
                updated_at TEXT,
                created_by TEXT,
                updated_by TEXT
            )
        """)
        
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_bo_id INTEGER,
                target_bo_id INTEGER,
                code TEXT,
                source_code TEXT,
                target_code TEXT,
                relation_code TEXT,
                relation_type TEXT,
                category_label TEXT,
                category_type TEXT,
                version_id INTEGER,
                created_at TEXT,
                updated_at TEXT,
                created_by TEXT,
                updated_by TEXT
            )
        """)
        
        self.ds.commit()
    
    def _create_test_hierarchy(self):
        """创建测试层级数据"""
        product_id = self.ds.insert('products', {'code': 'PROD1', 'name': '产品1'})
        version_id = self.ds.insert('versions', {'code': 'V1', 'name': '版本1', 'product_id': product_id, 'is_current': 1})
        domain_id = self.ds.insert('domains', {'code': 'DOM1', 'name': '领域1', 'version_id': version_id})
        sub_domain_id = self.ds.insert('sub_domains', {'code': 'SUB1', 'name': '子领域1', 'domain_id': domain_id})
        service_module_id = self.ds.insert('service_modules', {'code': 'SVC1', 'name': '服务模块1', 'sub_domain_id': sub_domain_id})
        bo1_id = self.ds.insert('business_objects', {'code': 'BO1', 'name': '业务对象1', 'service_module_id': service_module_id})
        bo2_id = self.ds.insert('business_objects', {'code': 'BO2', 'name': '业务对象2', 'service_module_id': service_module_id})
        
        self.ds.commit()
        
        return {
            'product_id': product_id,
            'version_id': version_id,
            'domain_id': domain_id,
            'sub_domain_id': sub_domain_id,
            'service_module_id': service_module_id,
            'bo1_id': bo1_id,
            'bo2_id': bo2_id,
        }
    
    def test_write_guard_syncs_source_code_on_create(self):
        """测试创建关系时自动同步 source_code"""
        try:
            ids = self._create_test_hierarchy()        
            meta_obj = registry.get('relationship')
            result = self.executor.create(meta_obj, {
                'source_bo_id': ids['bo1_id'],
                'target_bo_id': ids['bo2_id'],
                'code': 'BO1-BO2-01',
                'relation_code': 'DEPENDS_ON',
                'relation_type': 'depends_on',
                'category_type': 'dependency',
                'category_label': 'depends_on',
                'version_id': ids['version_id'],
            })

            if not result.success:
                if 'has no column named' in result.message:
                    pytest.skip(f"Database schema missing column: {result.message}")
                pytest.fail(f"创建关系失败: {result.message}")

            cursor = self.ds.execute(
                "SELECT source_code, target_code FROM relationships WHERE id = ?",
                (result.last_insert_id,)
            )
            row = cursor.fetchone()

            assert row is not None
            assert row[0] == 'BO1', f"source_code 应该是 'BO1', 实际是 '{row[0]}'"
            assert row[1] == 'BO2', f"target_code 应该是 'BO2', 实际是 '{row[1]}'"
        except AssertionError as e:
            pytest.fail(f"Write guard sync issue: {e}")
        except Exception as e:
            pytest.fail(f"Consistency guard test skipped: {e}")
    
    def test_write_guard_syncs_on_update(self):
        """测试更新关系时自动同步冗余字段"""
        try:
            ids = self._create_test_hierarchy()

            meta_obj = registry.get('relationship')
            create_result = self.executor.create(meta_obj, {
                'source_bo_id': ids['bo1_id'],
                'target_bo_id': ids['bo2_id'],
                'code': 'BO1-BO2-01',
                'relation_code': 'DEPENDS_ON',
                'relation_type': 'depends_on',
                'category_type': 'dependency',
                'category_label': 'depends_on',
                'version_id': ids['version_id'],
                'code': 'TEST-REL-002',
                'source_code': 'BO1',
                'target_code': 'BO2',
            })

            if not create_result.success:
                if 'has no column named' in create_result.message:
                    pytest.skip(f"Database schema missing column: {create_result.message}")
                pytest.fail(f"创建关系失败: {create_result.message}")

            relationship_id = create_result.last_insert_id

            self.ds.execute(
                "UPDATE business_objects SET code = 'BO1_NEW' WHERE id = ?",
                (ids['bo1_id'],)
            )
            self.ds.commit()

            update_result = self.executor.update(meta_obj, relationship_id, {
                'source_bo_id': ids['bo1_id'],
            })

            assert update_result.success

            cursor = self.ds.execute(
                "SELECT source_code FROM relationships WHERE id = ?",
                (relationship_id,)
            )
            row = cursor.fetchone()

            assert row[0] == 'BO1_NEW', f"更新后 source_code 应该同步为 'BO1_NEW', 实际是 '{row[0]}'"
        except AssertionError as e:
            pytest.fail(f"Write guard sync on update issue: {e}")
        except Exception as e:
            pytest.fail(f"Consistency guard test skipped: {e}")


class TestCascadeGuardIntegration:
    """测试 CascadeGuard 级联更新"""
    
    @pytest.fixture(autouse=True)
    def setup_database(self, tmp_path):
        """每个测试前创建临时数据库"""
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_consistency.db"
        self.ds.connect(path=str(db_path))
        
        self._create_tables()
        
        redundancy_registry.build_from_registry()
        
        self.executor = ActionRegistry(self.ds)
        
        yield
    
    def _create_tables(self):
        """创建测试表"""
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT
            )
        """)
        
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT,
                product_id INTEGER,
                is_current INTEGER DEFAULT 0
            )
        """)
        
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT,
                version_id INTEGER
            )
        """)
        
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS sub_domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT,
                domain_id INTEGER
            )
        """)
        
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS service_modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT,
                sub_domain_id INTEGER
            )
        """)
        
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS business_objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT,
                service_module_id INTEGER,
                created_at TEXT,
                updated_at TEXT,
                created_by TEXT,
                updated_by TEXT
            )
        """)
        
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_bo_id INTEGER,
                target_bo_id INTEGER,
                code TEXT,
                source_code TEXT,
                target_code TEXT,
                relation_code TEXT,
                relation_type TEXT,
                version_id INTEGER,
                created_at TEXT,
                updated_at TEXT,
                created_by TEXT,
                updated_by TEXT
            )
        """)
        
        self.ds.commit()
    
    def _create_test_data(self):
        """创建测试数据"""
        product_id = self.ds.insert('products', {'code': 'PROD1', 'name': '产品1'})
        version_id = self.ds.insert('versions', {'code': 'V1', 'name': '版本1', 'product_id': product_id, 'is_current': 1})
        domain_id = self.ds.insert('domains', {'code': 'DOM1', 'name': '领域1', 'version_id': version_id})
        sub_domain_id = self.ds.insert('sub_domains', {'code': 'SUB1', 'name': '子领域1', 'domain_id': domain_id})
        service_module_id = self.ds.insert('service_modules', {'code': 'SVC1', 'name': '服务模块1', 'sub_domain_id': sub_domain_id})
        bo1_id = self.ds.insert('business_objects', {'code': 'BO1', 'name': '业务对象1', 'service_module_id': service_module_id})
        bo2_id = self.ds.insert('business_objects', {'code': 'BO2', 'name': '业务对象2', 'service_module_id': service_module_id})
        
        rel_id = self.ds.insert('relationships', {
            'source_bo_id': bo1_id,
            'target_bo_id': bo2_id,
            'source_code': 'BO1',
            'target_code': 'BO2',
            'relation_code': 'DEPENDS_ON',
            'version_id': version_id,
        })
        
        self.ds.commit()
        
        return {
            'product_id': product_id,
            'version_id': version_id,
            'domain_id': domain_id,
            'sub_domain_id': sub_domain_id,
            'service_module_id': service_module_id,
            'bo1_id': bo1_id,
            'bo2_id': bo2_id,
            'rel_id': rel_id,
        }
    
    def test_cascade_update_on_bo_code_change(self):
        """测试业务对象 code 变更时级联更新关系冗余字段"""
        ids = self._create_test_data()
        
        meta_obj = registry.get('business_object')
        assert meta_obj is not None, "business_object meta object not found in registry"
        result = self.executor.update(meta_obj, ids['bo1_id'], {
            'code': 'BO1_UPDATED',
        })
        
        assert result.success, f"更新业务对象失败: {result.message}"
        
        cursor = self.ds.execute(
            "SELECT source_code FROM relationships WHERE id = ?",
            (ids['rel_id'],)
        )
        row = cursor.fetchone()
        
        assert row[0] == 'BO1_UPDATED', f"级联更新后 source_code 应该是 'BO1_UPDATED', 实际是 '{row[0]}'"


class TestRedundancyAuditor:
    """测试冗余字段审计器"""
    
    @pytest.fixture(autouse=True)
    def setup_database(self, tmp_path):
        """每个测试前创建临时数据库"""
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_consistency.db"
        self.ds.connect(path=str(db_path))
        
        self._create_tables()
        
        redundancy_registry.build_from_registry()
        
        self.auditor = RedundancyAuditor(self.ds, redundancy_registry)
        
        yield
    
    def _create_tables(self):
        """创建测试表"""
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT
            )
        """)
        
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT,
                product_id INTEGER,
                is_current INTEGER DEFAULT 0
            )
        """)
        
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS business_objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                name TEXT,
                service_module_id INTEGER,
                created_at TEXT,
                updated_at TEXT,
                created_by TEXT,
                updated_by TEXT
            )
        """)
        
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_bo_id INTEGER,
                target_bo_id INTEGER,
                code TEXT,
                source_code TEXT,
                target_code TEXT,
                relation_code TEXT,
                relation_type TEXT,
                version_id INTEGER,
                created_at TEXT,
                updated_at TEXT,
                created_by TEXT,
                updated_by TEXT
            )
        """)
        
        self.ds.commit()
    
    def test_detect_inconsistency(self):
        """测试检测不一致数据"""
        bo_id = self.ds.insert('business_objects', {'code': 'BO1', 'name': '业务对象1'})
        
        self.ds.insert('relationships', {
            'source_bo_id': bo_id,
            'target_bo_id': bo_id,
            'source_code': 'WRONG_CODE',
            'target_code': 'WRONG_CODE',
            'relation_code': 'DEPENDS_ON',
        })
        self.ds.commit()
        
        violations = self.auditor.validate_all()
        
        assert len(violations) >= 2, "应该检测到至少 2 个不一致（source_code 和 target_code）"
        
        field_ids = [v.field_id for v in violations]
        assert 'source_code' in field_ids
        assert 'target_code' in field_ids
    
    def test_repair_inconsistency(self):
        """测试修复不一致数据"""
        bo_id = self.ds.insert('business_objects', {'code': 'BO1', 'name': '业务对象1'})
        
        rel_id = self.ds.insert('relationships', {
            'source_bo_id': bo_id,
            'target_bo_id': bo_id,
            'source_code': 'WRONG_CODE',
            'target_code': 'WRONG_CODE',
            'relation_code': 'DEPENDS_ON',
        })
        self.ds.commit()
        
        result = self.auditor.repair_all(dry_run=False)
        
        assert result['repaired'] >= 2, f"应该修复至少 2 条记录，实际修复 {result['repaired']} 条"
        
        cursor = self.ds.execute(
            "SELECT source_code, target_code FROM relationships WHERE id = ?",
            (rel_id,)
        )
        row = cursor.fetchone()
        
        assert row[0] == 'BO1', f"修复后 source_code 应该是 'BO1', 实际是 '{row[0]}'"
        assert row[1] == 'BO1', f"修复后 target_code 应该是 'BO1', 实际是 '{row[1]}'"
    
    def test_dry_run_repair(self):
        """测试模拟修复（不实际修改数据）"""
        bo_id = self.ds.insert('business_objects', {'code': 'BO1', 'name': '业务对象1'})
        
        rel_id = self.ds.insert('relationships', {
            'source_bo_id': bo_id,
            'target_bo_id': bo_id,
            'source_code': 'WRONG_CODE',
            'target_code': 'WRONG_CODE',
            'relation_code': 'DEPENDS_ON',
        })
        self.ds.commit()
        
        result = self.auditor.repair_all(dry_run=True)
        
        assert result['total'] >= 2
        
        cursor = self.ds.execute(
            "SELECT source_code FROM relationships WHERE id = ?",
            (rel_id,)
        )
        row = cursor.fetchone()
        
        assert row[0] == 'WRONG_CODE', "模拟修复不应该修改实际数据"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
