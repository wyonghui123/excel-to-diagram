import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
AnalyticalEngine 单元测试

测试分析引擎的核心功能：
1. 解析 analytical_model 定义
2. 构建星形查询 SQL
3. 执行 OLAP 查询
4. 下钻/上卷分析
5. 维度层级和度量查询
"""

import pytest
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import meta
from meta.core.analytical_engine import AnalyticalEngine


class TestAnalyticalModelParsing:
    """测试分析模型解析"""
    
    @pytest.fixture(autouse=True)
    def setup_engine(self, tmp_path):
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_analytical.db"
        self.ds.connect(path=str(db_path))
        
        self.engine = AnalyticalEngine(self.ds)
    
    def test_parse_relationship_model(self):
        """测试解析 relationship 的分析模型"""
        model = self.engine.get_analytical_model('relationship')
        
        if model is None:
            pytest.fail('analytical model not available')
        assert model.enabled == True
        assert model.fact_table == 'relationships'
        assert model.fact_alias == 'r'
    
    def test_parse_measures(self):
        """测试解析度量定义"""
        model = self.engine.get_analytical_model('relationship')

        if model is None:
            pytest.fail('analytical model not available')
        
        assert 'relation_count' in model.measures
        assert model.measures['relation_count'].aggregation == 'count'
        
        assert 'distinct_source_count' in model.measures
        assert model.measures['distinct_source_count'].aggregation == 'count_distinct'
    
    def test_parse_dimensions(self):
        """测试解析维度定义"""
        model = self.engine.get_analytical_model('relationship')

        if model is None:
            pytest.fail('analytical model not available')
        
        assert 'version_id' in model.dimensions
        assert 'relation_code' in model.dimensions
        assert 'source_domain_id' in model.dimensions
        
        assert model.dimensions['version_id'].hierarchy_level == 1
        assert model.dimensions['relation_code'].hierarchy_level == 2
        assert model.dimensions['source_domain_id'].hierarchy_level == 3
    
    def test_parse_dimension_join_path(self):
        """测试解析维度的 JOIN 路径"""
        model = self.engine.get_analytical_model('relationship')

        if model is None:
            pytest.fail('analytical model not available')
        
        source_domain = model.dimensions['source_domain_id']
        assert len(source_domain.join_path) == 4
        
        tables = [step.get('table', '').split()[0] for step in source_domain.join_path]
        assert 'business_objects' in tables[0]
    
    def test_parse_aggregates(self):
        """测试解析聚合定义"""
        model = self.engine.get_analytical_model('relationship')

        if model is None:
            pytest.fail('analytical model not available')
        
        assert 'version_relation_stats' in model.aggregates
        agg = model.aggregates['version_relation_stats']
        assert agg.type == 'materialized'
        assert 'version_id' in agg.dimensions
        assert 'relation_count' in agg.measures
    
    def test_parse_business_object_model(self):
        """测试解析 business_object 的分析模型"""
        model = self.engine.get_analytical_model('business_object')
        
        if model is None:
            pytest.fail('analytical model not available')
        assert model.enabled == True
        assert model.fact_table == 'business_objects'
        assert 'bo_count' in model.measures
    
    def test_parse_non_analytical_object(self):
        """测试解析没有分析模型的对象"""
        model = self.engine.get_analytical_model('product')
        
        assert model is None or not model.enabled


class TestBuildStarQuery:
    """测试构建星形查询"""
    
    @pytest.fixture(autouse=True)
    def setup_engine(self, tmp_path):
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_analytical.db"
        self.ds.connect(path=str(db_path))
        
        self.engine = AnalyticalEngine(self.ds)
    
    def test_build_simple_query(self):
        """测试构建简单查询"""
        sql, params = self.engine.build_star_query(
            'relationship',
            dimensions=['version_id', 'relation_code'],
            measures=['relation_count']
        )
        
        assert sql != ""
        assert "SELECT" in sql
        assert "FROM relationships r" in sql
        assert "GROUP BY" in sql
        assert "COUNT" in sql
    
    def test_build_query_with_filters(self):
        """测试构建带过滤条件的查询"""
        sql, params = self.engine.build_star_query(
            'relationship',
            dimensions=['version_id', 'relation_code'],
            measures=['relation_count'],
            filters={'version_id': 1}
        )
        
        assert "WHERE" in sql
        assert len(params) == 1
        assert params[0] == 1
    
    def test_build_query_with_count_distinct(self):
        """测试构建 COUNT DISTINCT 查询"""
        sql, params = self.engine.build_star_query(
            'relationship',
            dimensions=['version_id'],
            measures=['distinct_source_count']
        )
        
        assert "COUNT(DISTINCT" in sql
    
    def test_build_query_non_analytical_object(self):
        """测试构建不支持分析的对象查询"""
        sql, params = self.engine.build_star_query(
            'product',
            dimensions=['id'],
            measures=['id']
        )
        
        assert sql == ""


class TestExecuteOlapQuery:
    """测试执行 OLAP 查询"""
    
    @pytest.fixture(autouse=True)
    def setup_database(self, tmp_path):
        from meta.core.sql_adapters import SQLiteAdapter
        
        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test.db"
        self.ds.connect(path=str(db_path))
        
        self._create_tables()
        self._insert_test_data()
        
        self.engine = AnalyticalEngine(self.ds)
    
    def _create_tables(self):
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
                service_module_id INTEGER,
                version_id INTEGER
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
    
    def _insert_test_data(self):
        self.ds.insert('products', {'code': 'PROD1', 'name': '产品1'})
        self.ds.insert('versions', {'code': 'V1', 'name': '版本1', 'product_id': 1})
        self.ds.insert('domains', {'code': 'DOM1', 'name': '领域1', 'version_id': 1})
        self.ds.insert('domains', {'code': 'DOM2', 'name': '领域2', 'version_id': 1})
        self.ds.insert('sub_domains', {'code': 'SUB1', 'name': '子领域1', 'domain_id': 1})
        self.ds.insert('service_modules', {'code': 'SVC1', 'name': '服务模块1', 'sub_domain_id': 1})
        
        self.ds.insert('business_objects', {'code': 'BO1', 'name': '业务对象1', 'service_module_id': 1, 'version_id': 1})
        self.ds.insert('business_objects', {'code': 'BO2', 'name': '业务对象2', 'service_module_id': 1, 'version_id': 1})
        self.ds.insert('business_objects', {'code': 'BO3', 'name': '业务对象3', 'service_module_id': 1, 'version_id': 1})
        
        self.ds.insert('relationships', {'source_bo_id': 1, 'target_bo_id': 2, 'source_code': 'BO1', 'target_code': 'BO2', 'relation_code': 'DEPENDS_ON', 'version_id': 1})
        self.ds.insert('relationships', {'source_bo_id': 1, 'target_bo_id': 3, 'source_code': 'BO1', 'target_code': 'BO3', 'relation_code': 'CALLS', 'version_id': 1})
        self.ds.insert('relationships', {'source_bo_id': 2, 'target_bo_id': 3, 'source_code': 'BO2', 'target_code': 'BO3', 'relation_code': 'DEPENDS_ON', 'version_id': 1})
        
        self.ds.commit()
    
    def test_execute_simple_olap(self):
        """测试执行简单 OLAP 查询"""
        results = self.engine.execute_olap_query(
            'relationship',
            dimensions=['version_id', 'relation_code'],
            measures=['relation_count']
        )
        
        if len(results) == 0: pytest.fail('no results')
        
        dep_result = [r for r in results if r.get('relation_code') == 'DEPENDS_ON']
        assert len(dep_result) == 1
        assert dep_result[0]['relation_count'] == 2
        
        calls_result = [r for r in results if r.get('relation_code') == 'CALLS']
        assert len(calls_result) == 1
        assert calls_result[0]['relation_count'] == 1
    
    def test_execute_olap_with_filter(self):
        """测试执行带过滤的 OLAP 查询"""
        results = self.engine.execute_olap_query(
            'relationship',
            dimensions=['relation_code'],
            measures=['relation_count'],
            filters={'version_id': 1}
        )
        
        if len(results) == 0: pytest.fail('no results')
    
    def test_execute_olap_count_distinct(self):
        """测试 COUNT DISTINCT 度量"""
        results = self.engine.execute_olap_query(
            'relationship',
            dimensions=['version_id'],
            measures=['distinct_source_count', 'distinct_target_count']
        )
        
        if len(results) == 0: pytest.fail('no results')
        assert 'distinct_source_count' in results[0]
        assert 'distinct_target_count' in results[0]
    
    def test_drill_down(self):
        """测试下钻分析"""
        results = self.engine.drill_down(
            'relationship',
            current_dimensions=['version_id'],
            drill_dimension='relation_code',
            measures=['relation_count']
        )
        
        if len(results) == 0: pytest.fail('no results')
        assert 'relation_code' in results[0]
    
    def test_roll_up(self):
        """测试上卷分析"""
        results = self.engine.roll_up(
            'relationship',
            current_dimensions=['version_id', 'relation_code'],
            roll_to_dimensions=['version_id'],
            measures=['relation_count']
        )
        
        if len(results) == 0: pytest.fail('no results')
        assert 'version_id' in results[0]
        assert 'relation_code' not in results[0]
    
    def test_business_object_olap(self):
        """测试业务对象 OLAP 查询"""
        results = self.engine.execute_olap_query(
            'business_object',
            dimensions=['version_id'],
            measures=['bo_count']
        )
        
        if len(results) == 0: pytest.fail('no results')
        assert results[0]['bo_count'] == 3


class TestDimensionHierarchy:
    """测试维度层级"""
    
    @pytest.fixture(autouse=True)
    def setup_engine(self, tmp_path):
        from meta.core.sql_adapters import SQLiteAdapter

        self.ds = SQLiteAdapter()
        # v3.13+ :memory: 不支持，改用临时文件
        db_path = tmp_path / "test_analytical.db"
        self.ds.connect(path=str(db_path))
        
        self.engine = AnalyticalEngine(self.ds)
    
    def test_get_dimension_hierarchy(self):
        """测试获取维度层级"""
        hierarchy = self.engine.get_dimension_hierarchy('relationship')
        
        assert len(hierarchy) > 0
        
        levels = [d['hierarchy_level'] for d in hierarchy]
        assert levels == sorted(levels)
    
    def test_get_available_measures(self):
        """测试获取可用度量"""
        measures = self.engine.get_available_measures('relationship')
        
        assert len(measures) > 0
        
        measure_ids = [m['id'] for m in measures]
        assert 'relation_count' in measure_ids
        assert 'distinct_source_count' in measure_ids
    
    def test_get_aggregate_info(self):
        """测试获取聚合信息"""
        aggregates = self.engine.get_aggregate_info('relationship')
        
        assert len(aggregates) > 0
        
        agg_ids = [a['id'] for a in aggregates]
        assert 'version_relation_stats' in agg_ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
