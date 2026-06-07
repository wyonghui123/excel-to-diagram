import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
EnrichmentEngine 单元测试

测试 EnrichmentEngine 的核心功能：
1. 单条记录填充
2. 批量记录填充
3. 单层 JOIN 路径解析
4. 多层 JOIN 路径解析
5. 缓存机制
"""

import pytest
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import meta
from meta.core.enrichment_engine import EnrichmentEngine
from meta.core.redundancy_registry import redundancy_registry


class TestEnrichmentEngineBasic:
    """测试 EnrichmentEngine 基础功能"""
    
    @pytest.fixture(autouse=True)
    def setup_database(self, tmp_path):
        """每个测试前创建临时数据库"""
        from meta.core.sql_adapters import SQLiteAdapter
        
        self.ds = SQLiteAdapter()
        # v3.13+ 使用 tmp_path 替代 :memory:
        db_path = tmp_path / "test.db"
        self.ds.connect(path=str(db_path))
        
        self._create_tables()
        
        redundancy_registry.build_from_registry()
        
        self.engine = EnrichmentEngine(self.ds, redundancy_registry)
        
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
                product_id INTEGER
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
                service_module_id INTEGER
            )
        """)
        
        self.ds.commit()
    
    def test_enrich_one_no_redundancy(self):
        """测试没有冗余声明的对象"""
        self.ds.insert('products', {'code': 'PROD1', 'name': '产品1'})
        self.ds.commit()
        
        record = {'id': 1, 'code': 'PROD1', 'name': '产品1'}
        result = self.engine.enrich_one('product', record)
        
        assert result == record
    
    def test_enrich_one_simple_virtual(self):
        """测试单层虚拟冗余字段填充"""
        self.ds.insert('products', {'code': 'PROD1', 'name': '产品1'})
        product_id = self.ds.insert('versions', {'code': 'V1', 'name': '版本1', 'product_id': 1})
        self.ds.commit()
        
        record = {'id': product_id, 'code': 'V1', 'name': '版本1', 'product_id': 1}
        result = self.engine.enrich_one('version', record)
        
        assert 'product_name' in result, 'enrichment engine did not return product_name - check yaml redundancy config'
        assert result.get('product_name') == '产品1'
    
    def test_enrich_one_multi_layer_join(self):
        """测试多层 JOIN 路径填充"""
        self.ds.insert('products', {'code': 'PROD1', 'name': '产品1'})
        self.ds.insert('versions', {'code': 'V1', 'name': '版本1', 'product_id': 1})
        self.ds.insert('domains', {'code': 'DOM1', 'name': '领域1', 'version_id': 1})
        self.ds.insert('sub_domains', {'code': 'SUB1', 'name': '子领域1', 'domain_id': 1})
        sm_id = self.ds.insert('service_modules', {'code': 'SVC1', 'name': '服务模块1', 'sub_domain_id': 1})
        self.ds.commit()
        
        record = {'id': 1, 'code': 'BO1', 'name': '业务对象1', 'service_module_id': sm_id}
        result = self.engine.enrich_one('business_object', record)
        
        assert 'service_module_name' in result, 'enrichment engine did not return service_module_name - check yaml redundancy config'
        assert result.get('service_module_name') == '服务模块1'
        
        assert 'sub_domain_name' in result, 'enrichment engine did not return sub_domain_name - check yaml redundancy config'
        assert result.get('sub_domain_name') == '子领域1'
        
        assert 'domain_name' in result, 'enrichment engine did not return domain_name - check yaml redundancy config'
        assert result.get('domain_name') == '领域1'
    
    def test_enrich_batch(self):
        """测试批量填充"""
        self.ds.insert('products', {'code': 'PROD1', 'name': '产品1'})
        self.ds.insert('versions', {'code': 'V1', 'name': '版本1', 'product_id': 1})
        self.ds.insert('domains', {'code': 'DOM1', 'name': '领域1', 'version_id': 1})
        self.ds.insert('sub_domains', {'code': 'SUB1', 'name': '子领域1', 'domain_id': 1})
        sm_id = self.ds.insert('service_modules', {'code': 'SVC1', 'name': '服务模块1', 'sub_domain_id': 1})
        
        self.ds.insert('business_objects', {'code': 'BO1', 'name': '业务对象1', 'service_module_id': sm_id})
        self.ds.insert('business_objects', {'code': 'BO2', 'name': '业务对象2', 'service_module_id': sm_id})
        self.ds.commit()
        
        records = [
            {'id': 1, 'code': 'BO1', 'name': '业务对象1', 'service_module_id': sm_id},
            {'id': 2, 'code': 'BO2', 'name': '业务对象2', 'service_module_id': sm_id},
        ]
        
        result = self.engine.enrich_batch('business_object', records)
        
        assert len(result) == 2
        assert result[0].get('service_module_name') == '服务模块1'
        assert result[1].get('service_module_name') == '服务模块1'
    
    def test_enrich_empty_record(self):
        """测试空记录"""
        result = self.engine.enrich_one('business_object', {})
        assert result == {}
        
        result = self.engine.enrich_one('business_object', None)
        assert result is None
    
    def test_enrich_missing_source_field(self):
        """测试缺少源字段"""
        record = {'id': 1, 'code': 'BO1', 'name': '业务对象1'}
        result = self.engine.enrich_one('business_object', record)
        
        assert 'service_module_name' not in result


class TestEnrichmentEngineCache:
    """测试 EnrichmentEngine 缓存机制"""
    
    @pytest.fixture(autouse=True)
    def setup_database(self, tmp_path):
        """每个测试前创建临时数据库"""
        from meta.core.sql_adapters import SQLiteAdapter
        
        self.ds = SQLiteAdapter()
        db_path = tmp_path / "test.db"
        self.ds.connect(path=str(db_path))
        
        self._create_tables()
        
        redundancy_registry.build_from_registry()
        
        self.engine = EnrichmentEngine(self.ds, redundancy_registry)
        
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
                product_id INTEGER
            )
        """)
        
        self.ds.commit()
    
    def test_cache_reuse(self):
        """测试缓存重用"""
        self.ds.insert('products', {'code': 'PROD1', 'name': '产品1'})
        self.ds.insert('versions', {'code': 'V1', 'name': '版本1', 'product_id': 1})
        self.ds.insert('versions', {'code': 'V2', 'name': '版本2', 'product_id': 1})
        self.ds.commit()
        
        record1 = {'id': 1, 'code': 'V1', 'name': '版本1', 'product_id': 1}
        result1 = self.engine.enrich_one('version', record1)
        
        stats1 = self.engine.get_cache_stats()
        
        record2 = {'id': 2, 'code': 'V2', 'name': '版本2', 'product_id': 1}
        result2 = self.engine.enrich_one('version', record2)
        
        stats2 = self.engine.get_cache_stats()
        
        assert result1.get('product_name') == '产品1'
        assert result2.get('product_name') == '产品1'
    
    def test_clear_cache(self):
        """测试清空缓存"""
        self.ds.insert('products', {'code': 'PROD1', 'name': '产品1'})
        self.ds.insert('versions', {'code': 'V1', 'name': '版本1', 'product_id': 1})
        self.ds.commit()
        
        record = {'id': 1, 'code': 'V1', 'name': '版本1', 'product_id': 1}
        self.engine.enrich_one('version', record)
        
        stats_before = self.engine.get_cache_stats()
        assert stats_before.get('name_cache_entries', 0) > 0 or stats_before.get('record_cache_entries', 0) > 0
        
        self.engine.clear_cache()
        
        stats_after = self.engine.get_cache_stats()
        assert stats_after.get('name_cache_entries', 0) == 0
        assert stats_after.get('record_cache_entries', 0) == 0


class TestEnrichmentEngineRelationship:
    """测试 EnrichmentEngine 对 relationship 的填充"""
    
    @pytest.fixture(autouse=True)
    def setup_database(self, tmp_path):
        """每个测试前创建临时数据库"""
        from meta.core.sql_adapters import SQLiteAdapter
        
        self.ds = SQLiteAdapter()
        db_path = tmp_path / "test.db"
        self.ds.connect(path=str(db_path))
        
        self._create_tables()
        
        redundancy_registry.build_from_registry()
        
        self.engine = EnrichmentEngine(self.ds, redundancy_registry)
        
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
                product_id INTEGER
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
                service_module_id INTEGER
            )
        """)
        
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_bo_id INTEGER,
                target_bo_id INTEGER,
                code TEXT,
                source_code TEXT, target_code TEXT,
                relation_code TEXT, relation_type TEXT, version_id INTEGER
            )
        """)
        
        self.ds.commit()
    
    def _create_test_hierarchy(self):
        """创建测试层级数据"""
        self.ds.insert('products', {'code': 'PROD1', 'name': '产品1'})
        self.ds.insert('versions', {'code': 'V1', 'name': '版本1', 'product_id': 1})
        self.ds.insert('domains', {'code': 'DOM1', 'name': '领域1', 'version_id': 1})
        self.ds.insert('sub_domains', {'code': 'SUB1', 'name': '子领域1', 'domain_id': 1})
        sm_id = self.ds.insert('service_modules', {'code': 'SVC1', 'name': '服务模块1', 'sub_domain_id': 1})
        bo1_id = self.ds.insert('business_objects', {'code': 'BO1', 'name': '业务对象1', 'service_module_id': sm_id})
        bo2_id = self.ds.insert('business_objects', {'code': 'BO2', 'name': '业务对象2', 'service_module_id': sm_id})
        self.ds.commit()
        
        return {'bo1_id': bo1_id, 'bo2_id': bo2_id, 'sm_id': sm_id}
    
    def test_enrich_relationship_source_bo_name(self):
        """测试填充关系的 source_bo_name"""
        ids = self._create_test_hierarchy()
        
        record = {
            'id': 1,
            'source_bo_id': ids['bo1_id'],
            'target_bo_id': ids['bo2_id'],
            'relation_code': 'DEPENDS_ON',
        }
        
        result = self.engine.enrich_one('relationship', record)
        
        assert 'source_bo_name' in result
        assert result['source_bo_name'] == '业务对象1'
        
        assert 'target_bo_name' in result
        assert result['target_bo_name'] == '业务对象2'
    
    def test_enrich_relationship_domain_names(self):
        """测试填充关系的多层 domain_name"""
        ids = self._create_test_hierarchy()
        
        record = {
            'id': 1,
            'source_bo_id': ids['bo1_id'],
            'target_bo_id': ids['bo2_id'],
            'relation_code': 'DEPENDS_ON',
        }
        
        result = self.engine.enrich_one('relationship', record)
        
        assert 'source_domain_name' in result
        assert result['source_domain_name'] == '领域1'
        
        assert 'target_domain_name' in result
        assert result['target_domain_name'] == '领域1'
        
        assert 'source_sub_domain_name' in result
        assert result['source_sub_domain_name'] == '子领域1'
        
        assert 'source_service_module_name' in result
        assert result['source_service_module_name'] == '服务模块1'


class TestEnrichmentEngineBusinessObjectIdFields:
    """测试 business_object 的 ID 类型虚拟字段填充（回归测试）

    覆盖 2026-05-04 修复的关键 bug：
    - domain_id (integer) 和 sub_domain_id (integer) 返回 null
    - 导致前端关系分类逻辑错误
    """

    @pytest.fixture(autouse=True)
    def setup_database(self, tmp_path):
        """每个测试前创建临时数据库并插入层级数据"""
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        # v3.13+ 使用 tmp_path 替代 :memory:
        db_path = tmp_path / "test.db"
        self.ds.connect(path=str(db_path))

        self._create_full_hierarchy()

        redundancy_registry.build_from_registry()
        self.engine = EnrichmentEngine(self.ds, redundancy_registry)

        yield

    def _create_full_hierarchy(self):
        """创建完整的 6 层级数据"""
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT, name TEXT
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT, name TEXT, product_id INTEGER
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
                code TEXT, name TEXT, service_module_id INTEGER
            )
        """)
        self.ds.commit()

    def _insert_test_data(self):
        """插入测试数据，返回 IDs"""
        self.ds.insert('products', {'code': 'PROD1', 'name': '产品A'})
        ver_id = self.ds.insert('versions', {'code': 'V1', 'name': '版本1', 'product_id': 1})
        dom_id = self.ds.insert('domains', {'code': 'DOM1', 'name': '资产云', 'version_id': ver_id})
        sub_id = self.ds.insert('sub_domains', {'code': 'SUB1', 'name': '资产管理与经营', 'domain_id': dom_id})
        sm_id = self.ds.insert('service_modules', {'code': 'SVC1', 'name': '资产管理服务', 'sub_domain_id': sub_id})
        bo_id = self.ds.insert('business_objects', {'code': 'BO1', 'name': '资产卡片', 'service_module_id': sm_id})
        self.ds.commit()

        return {
            'domain_id': dom_id,
            'sub_domain_id': sub_id,
            'service_module_id': sm_id,
            'bo_id': bo_id,
        }

    def test_enrich_domain_id_field(self):
        """测试 domain_id 字段正确填充（integer 类型）"""
        ids = self._insert_test_data()

        record = {'id': ids['bo_id'], 'code': 'BO1', 'name': '资产卡片',
                  'service_module_id': ids['service_module_id']}
        result = self.engine.enrich_one('business_object', record)

        assert 'domain_id' in result, "domain_id 必须被填充"
        assert result['domain_id'] == ids['domain_id'], \
            f"domain_id 应该是 {ids['domain_id']}，实际是 {result.get('domain_id')}"
        assert isinstance(result['domain_id'], int), "domain_id 应该是整数类型"

    def test_enrich_sub_domain_id_field(self):
        """测试 sub_domain_id 字段正确填充（integer 类型）"""
        ids = self._insert_test_data()

        record = {'id': ids['bo_id'], 'code': 'BO1', 'name': '资产卡片',
                  'service_module_id': ids['service_module_id']}
        result = self.engine.enrich_one('business_object', record)

        assert 'sub_domain_id' in result, "sub_domain_id 必须被填充"
        assert result['sub_domain_id'] == ids['sub_domain_id'], \
            f"sub_domain_id 应该是 {ids['sub_domain_id']}，实际是 {result.get('sub_domain_id')}"
        assert isinstance(result['sub_domain_id'], int), "sub_domain_id 应该是整数类型"

    def test_enrich_all_business_object_id_fields_together(self):
        """测试所有 ID 字段一起正确填充"""
        ids = self._insert_test_data()

        record = {'id': ids['bo_id'], 'code': 'BO1', 'name': '资产卡片',
                  'service_module_id': ids['service_module_id']}
        result = self.engine.enrich_one('business_object', record)

        assert 'domain_id' in result, 'enrichment engine did not return domain_id - check yaml redundancy config'
        assert result['domain_id'] == ids['domain_id']
        assert 'sub_domain_id' in result, 'enrichment engine did not return sub_domain_id - check yaml redundancy config'
        assert result['sub_domain_id'] == ids['sub_domain_id']
        assert result['service_module_id'] == ids['service_module_id']

        assert result.get('domain_name') == '资产云'
        assert result.get('sub_domain_name') == '资产管理与经营'

    def test_batch_enrich_preserves_id_fields(self):
        """测试批量填充时 ID 字段保持正确"""
        ids = self._insert_test_data()

        records = [
            {'id': ids['bo_id'], 'code': 'BO1', 'name': '资产卡片',
             'service_module_id': ids['service_module_id']},
            {'id': ids['bo_id'], 'code': 'BO2', 'name': '资产台账',
             'service_module_id': ids['service_module_id']},
        ]

        results = self.engine.enrich_batch('business_object', records)

        for r in results:
            assert 'domain_id' in r, 'enrichment engine did not return domain_id - check yaml redundancy config'
            assert r['domain_id'] == ids['domain_id']
            assert r['sub_domain_id'] == ids['sub_domain_id']
            assert 'domain_id' in r, 'enrichment engine did not return domain_id - check yaml redundancy config'
            assert isinstance(r['domain_id'], int)
            assert isinstance(r['sub_domain_id'], int)

    def test_different_domains_produce_different_ids(self):
        """测试不同领域的业务对象产生不同的 domain_id"""
        ids1 = self._insert_test_data()

        dom2_id = self.ds.insert('domains', {'code': 'DOM2', 'name': '财务云', 'version_id': 1})
        sub2_id = self.ds.insert('sub_domains', {'code': 'SUB2', 'name': '财务管理', 'domain_id': dom2_id})
        sm2_id = self.ds.insert('service_modules', {'code': 'SVC2', 'name': '账务服务', 'sub_domain_id': sub2_id})
        bo2_id = self.ds.insert('business_objects', {'code': 'BO2', 'name': '凭证', 'service_module_id': sm2_id})
        self.ds.commit()

        record1 = {'id': ids1['bo_id'], 'code': 'BO1', 'service_module_id': ids1['service_module_id']}
        record2 = {'id': bo2_id, 'code': 'BO2', 'service_module_id': sm2_id}

        result1 = self.engine.enrich_one('business_object', record1)
        result2 = self.engine.enrich_one('business_object', record2)

        assert result1['domain_id'] != result2['domain_id'], \
            "不同领域的 domain_id 必须不同"
        assert result1['domain_id'] == ids1['domain_id']
        assert result2['domain_id'] == dom2_id


class TestEnrichmentEngineErrorHandling:
    """测试 EnrichmentEngine 的错误处理和边界情况"""

    @pytest.fixture(autouse=True)
    def setup_database(self, tmp_path):
        """每个测试前创建临时数据库"""
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_enrichment.db"
        self.ds.connect(path=str(db_path))

        self._create_minimal_tables()
        redundancy_registry.build_from_registry()
        self.engine = EnrichmentEngine(self.ds, redundancy_registry)

        yield

    def _create_minimal_tables(self):
        """创建最小化的表结构"""
        self.ds.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, code TEXT, name TEXT)")
        self.ds.execute("CREATE TABLE versions (id INTEGER PRIMARY KEY, code TEXT, name TEXT, product_id INTEGER)")
        self.ds.commit()

    def test_null_source_field_handling(self):
        """测试源字段值为 None 时的处理"""
        record = {'id': 1, 'code': 'V1', 'product_id': None}
        result = self.engine.enrich_one('version', record)

        assert 'product_name' not in result or result.get('product_name') is None

    def test_missing_source_field_in_record(self):
        """测试记录中完全缺少源字段"""
        record = {'id': 1, 'code': 'V1'}
        result = self.engine.enrich_one('version', record)

        assert result is not None
        assert 'id' in result

    def test_nonexistent_foreign_key_reference(self):
        """测试引用不存在的记录"""
        record = {'id': 1, 'code': 'V1', 'product_id': 99999}
        result = self.engine.enrich_one('version', record)

        assert result is not None
        assert 'product_name' not in result or result.get('product_name') is None

    def test_empty_batch_handling(self):
        """测试空列表的批量处理"""
        results = self.engine.enrich_batch('version', [])
        assert results == []

    def test_batch_with_mixed_valid_invalid_records(self):
        """测试批量处理中混合有效和无效记录"""
        self.ds.insert('products', {'code': 'P1', 'name': '存在的产品'})
        self.ds.commit()

        records = [
            {'id': 1, 'code': 'V1', 'product_id': 1},
            {'id': 2, 'code': 'V2', 'product_id': None},
            {'id': 3, 'code': 'V3', 'product_id': 99999},
        ]

        results = self.engine.enrich_batch('version', records)

        assert len(results) == 3
        assert results[0].get('product_name') == '存在的产品'
        assert results[1].get('product_name') is None or 'product_name' not in results[1]

    def test_cache_stats_after_operations(self):
        """测试操作后的缓存统计"""
        self.ds.insert('products', {'code': 'P1', 'name': '产品'})
        self.ds.insert('versions', {'code': 'V1', 'name': '版本', 'product_id': 1})
        self.ds.commit()

        record = {'id': 1, 'code': 'V1', 'product_id': 1}
        self.engine.enrich_one('version', record)

        stats = self.engine.get_cache_stats()
        assert isinstance(stats, dict)
        assert 'name_cache_entries' in stats
        assert 'record_cache_entries' in stats


class TestEnrichmentEngineServiceModuleIdFields:
    """测试 service_module 的 ID 类型虚拟字段填充（回归测试）

    覆盖 2026-05-04 修复的 bug：
    - service_module.domain_id 返回 None 导致编辑页面无法回显领域
    """

    @pytest.fixture(autouse=True)
    def setup_database(self, tmp_path):
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        # v3.13+ 使用 tmp_path 替代 :memory:
        db_path = tmp_path / "test.db"
        self.ds.connect(path=str(db_path))

        self._create_hierarchy_tables()

        redundancy_registry.build_from_registry()
        self.engine = EnrichmentEngine(self.ds, redundancy_registry)

        yield

    def _create_hierarchy_tables(self):
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY, code TEXT, name TEXT
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY, code TEXT, name TEXT, product_id INTEGER
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS domains (
                id INTEGER PRIMARY KEY, code TEXT, name TEXT, version_id INTEGER
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS sub_domains (
                id INTEGER PRIMARY KEY, code TEXT, name TEXT, domain_id INTEGER
            )
        """)
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS service_modules (
                id INTEGER PRIMARY KEY, code TEXT, name TEXT,
                sub_domain_id INTEGER, version_id INTEGER
            )
        """)
        self.ds.commit()

    def _insert_service_module_data(self):
        self.ds.insert('products', {'code': 'PROD1', 'name': '产品A'})
        ver_id = self.ds.insert('versions', {'code': 'V1', 'name': '版本1', 'product_id': 1})
        dom_id = self.ds.insert('domains', {'code': 'DOM1', 'name': '资产云', 'version_id': ver_id})
        sub_id = self.ds.insert('sub_domains', {'code': 'SUB1', 'name': '资产管理与经营', 'domain_id': dom_id})
        sm_id = self.ds.insert(
            'service_modules',
            {'code': 'AUM', 'name': '资产使用管理', 'sub_domain_id': sub_id, 'version_id': ver_id}
        )
        self.ds.commit()

        return {'domain_id': dom_id, 'sub_domain_id': sub_id, 'sm_id': sm_id}

    def test_enrich_service_module_domain_id(self):
        """测试 service_module.domain_id 正确填充（1步JOIN: sub_domains）"""
        ids = self._insert_service_module_data()

        record = {'id': ids['sm_id'], 'code': 'AUM', 'name': '资产使用管理',
                  'sub_domain_id': ids['sub_domain_id']}
        result = self.engine.enrich_one('service_module', record)

        assert 'domain_id' in result, "domain_id 必须被填充"
        assert result['domain_id'] == ids['domain_id'], \
            f"期望 domain_id={ids['domain_id']}，实际={result.get('domain_id')}"
        assert isinstance(result['domain_id'], int), "domain_id 应为整数"

    def test_enrich_service_module_all_virtual_fields(self):
        """测试 service_module 所有虚拟字段一起正确填充"""
        ids = self._insert_service_module_data()

        record = {'id': ids['sm_id'], 'code': 'AUM', 'name': '资产使用管理',
                  'sub_domain_id': ids['sub_domain_id']}
        result = self.engine.enrich_one('service_module', record)

        assert 'domain_id' in result, 'enrichment engine did not return domain_id - check yaml redundancy config'
        assert result['domain_id'] == ids['domain_id']
        assert result.get('domain_name') == '资产云'
        assert result.get('sub_domain_name') == '资产管理与经营'

    def test_enrich_service_module_batch(self):
        """测试批量填充 service_module 的 domain_id"""
        ids = self._insert_service_module_data()

        sm2_id = self.ds.insert(
            'service_modules',
            {'code': 'AUM2', 'name': '资产使用管理2', 'sub_domain_id': ids['sub_domain_id']}
        )
        self.ds.commit()

        records = [
            {'id': ids['sm_id'], 'code': 'AUM', 'sub_domain_id': ids['sub_domain_id']},
            {'id': sm2_id, 'code': 'AUM2', 'sub_domain_id': ids['sub_domain_id']},
        ]

        results = self.engine.enrich_batch('service_module', records)

        for r in results:
            assert 'domain_id' in r, 'enrichment engine did not return domain_id - check yaml redundancy config'
            assert r['domain_id'] == ids['domain_id']
            assert 'domain_id' in r, 'enrichment engine did not return domain_id - check yaml redundancy config'
            assert isinstance(r['domain_id'], int)

    def test_service_module_different_subdomains_different_domains(self):
        """测试不同子领域的服务模块产生不同的 domain_id"""
        ids1 = self._insert_service_module_data()

        dom2_id = self.ds.insert('domains', {'code': 'DOM2', 'name': '财务云', 'version_id': 1})
        sub2_id = self.ds.insert('sub_domains', {'code': 'SUB2', 'name': '财务管理', 'domain_id': dom2_id})
        sm2_id = self.ds.insert(
            'service_modules',
            {'code': 'FIN', 'name': '财务管理服务', 'sub_domain_id': sub2_id}
        )
        self.ds.commit()

        r1 = self.engine.enrich_one('service_module',
                                    {'id': ids1['sm_id'], 'code': 'AUM', 'sub_domain_id': ids1['sub_domain_id']})
        r2 = self.engine.enrich_one('service_module',
                                    {'id': sm2_id, 'code': 'FIN', 'sub_domain_id': sub2_id})

        assert r1['domain_id'] != r2['domain_id'], "不同子领域的 domain_id 必须不同"
        assert r1['domain_id'] == ids1['domain_id']
        assert r2['domain_id'] == dom2_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
