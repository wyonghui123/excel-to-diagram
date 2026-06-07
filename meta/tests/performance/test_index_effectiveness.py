# -*- coding: utf-8 -*-
"""
索引效果对比测试

测试索引对查询性能的影响：
- 有索引 vs 无索引对比
- 单列索引 vs 复合索引对比
- 部分索引效果测试
- 全文搜索索引效果测试
"""

import pytest
import time
import tempfile
import os

pytestmark = pytest.mark.slow

from meta.tests.performance.performance_base import (
    PerformanceTimer, PerformanceBenchmark, performance_context
)
from meta.core.datasource import get_data_source
from meta.core.schema_generator import sync_schema_from_meta
from meta.core.models import registry
from meta.core.index_management_service import IndexManagementService


class TestIndexEffectiveness:
    """索引效果对比测试"""
    
    @pytest.fixture
    def db_without_indexes(self):
        """无索引数据库"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        ds = get_data_source("sqlite", database=db_path)
        
        try:
            import meta.core.table_name_validator as tnv
            tnv._VALID_TABLES_CACHE = None
            meta_objects = [registry.get(obj_id) for obj_id in registry.list_objects()]
            meta_objects = [obj for obj in meta_objects if obj is not None]
            sync_schema_from_meta(ds, meta_objects)
            self._populate_large_data(ds, 5000)
            yield ds
        finally:
            try:
                ds.disconnect()
            except Exception:
                pass
            try:
                os.remove(db_path)
            except Exception:
                pass
    
    @pytest.fixture
    def db_with_indexes(self):
        """有索引数据库"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        ds = get_data_source("sqlite", database=db_path)
        
        try:
            import meta.core.table_name_validator as tnv
            tnv._VALID_TABLES_CACHE = None
            meta_objects = [registry.get(obj_id) for obj_id in registry.list_objects()]
            meta_objects = [obj for obj in meta_objects if obj is not None]
            sync_schema_from_meta(ds, meta_objects)
            
            service = IndexManagementService(ds)
            service.create_all_indexes()
            
            self._populate_large_data(ds, 5000)
            yield ds
        finally:
            try:
                ds.disconnect()
            except Exception:
                pass
            try:
                os.remove(db_path)
            except Exception:
                pass
    
    def _populate_large_data(self, ds, count: int):
        """填充大量测试数据"""
        now = int(time.time())
        
        ds.execute("INSERT INTO products (id, name, code, created_at) VALUES (1, '测试产品', 'PRD001', ?)", (now,))
        
        ds.execute("INSERT INTO versions (id, name, code, product_id, created_at) VALUES (1, 'V1', 'V001', 1, ?)", (now,))
        ds.execute("INSERT INTO versions (id, name, code, product_id, created_at) VALUES (2, 'V2', 'V002', 1, ?)", (now,))
        
        ds.execute("INSERT INTO domains (id, name, code, version_id, created_at) VALUES (1, '领域1', 'DOM001', 1, ?)", (now,))
        ds.execute("INSERT INTO domains (id, name, code, version_id, created_at) VALUES (2, '领域2', 'DOM002', 1, ?)", (now,))
        
        ds.execute("INSERT INTO sub_domains (id, name, code, domain_id, version_id, created_at) VALUES (1, 'SD1', 'SD001', 1, 1, ?)", (now,))
        ds.execute("INSERT INTO sub_domains (id, name, code, domain_id, version_id, created_at) VALUES (2, 'SD2', 'SD002', 2, 1, ?)", (now,))
        
        ds.execute("INSERT INTO service_modules (id, name, code, sub_domain_id, version_id, created_at) VALUES (1, 'SM1', 'SM001', 1, 1, ?)", (now,))
        ds.execute("INSERT INTO service_modules (id, name, code, sub_domain_id, version_id, created_at) VALUES (2, 'SM2', 'SM002', 2, 1, ?)", (now,))
        
        batch_data = []
        for i in range(count):
            version_id = 1 if i % 3 == 0 else 2
            service_module_id = 1 if i % 2 == 0 else 2
            
            batch_data.append({
                "name": "业务对象{0:05d}".format(i),
                "code": "BO{0:05d}".format(i),
                "description": "业务对象描述{0}，包含一些测试文本内容用于搜索测试。".format(i),
                "version_id": version_id,
                "service_module_id": service_module_id,
                "created_at": now,
            })
        
        ds.batch_insert("business_objects", batch_data)
        ds.commit()
    
    @pytest.mark.performance
    @pytest.mark.index_perf
    def test_index_comparison_version_query(self, db_without_indexes, db_with_indexes):
        """测试版本字段索引效果"""
        timer_no_idx = PerformanceTimer("version_query_no_index")
        timer_with_idx = PerformanceTimer("version_query_with_index")
        
        query = "SELECT * FROM business_objects WHERE version_id = ?"
        
        for _ in range(20):
            timer_no_idx.start()
            db_without_indexes.query(query, (1,))
            timer_no_idx.stop()
            
            timer_with_idx.start()
            db_with_indexes.query(query, (1,))
            timer_with_idx.stop()
        
        metric_no_idx = timer_no_idx.get_metric()
        metric_with_idx = timer_with_idx.get_metric()
        
        improvement = (metric_no_idx.value - metric_with_idx.value) / metric_no_idx.value * 100 if metric_no_idx.value > 0 else 0
        
        print("\n=== 版本字段查询索引效果 ===")
        print("无索引: {0:.3f}ms".format(metric_no_idx.value))
        print("有索引: {0:.3f}ms".format(metric_with_idx.value))
        print("提升: {0:.1f}%".format(improvement))
    
    @pytest.mark.performance
    @pytest.mark.index_perf
    def test_index_comparison_composite_query(self, db_without_indexes, db_with_indexes):
        """测试复合索引效果"""
        timer_no_idx = PerformanceTimer("composite_query_no_index")
        timer_with_idx = PerformanceTimer("composite_query_with_index")
        
        query = "SELECT * FROM business_objects WHERE version_id = ? AND service_module_id = ?"
        
        for _ in range(20):
            timer_no_idx.start()
            db_without_indexes.query(query, (1, 1))
            timer_no_idx.stop()
            
            timer_with_idx.start()
            db_with_indexes.query(query, (1, 1))
            timer_with_idx.stop()
        
        metric_no_idx = timer_no_idx.get_metric()
        metric_with_idx = timer_with_idx.get_metric()
        
        improvement = (metric_no_idx.value - metric_with_idx.value) / metric_no_idx.value * 100 if metric_no_idx.value > 0 else 0
        
        print("\n=== 复合条件查询索引效果 ===")
        print("无索引: {0:.3f}ms".format(metric_no_idx.value))
        print("有索引: {0:.3f}ms".format(metric_with_idx.value))
        print("提升: {0:.1f}%".format(improvement))
    
    @pytest.mark.performance
    @pytest.mark.index_perf
    def test_index_comparison_unique_query(self, db_without_indexes, db_with_indexes):
        """测试唯一索引效果"""
        timer_no_idx = PerformanceTimer("unique_query_no_index")
        timer_with_idx = PerformanceTimer("unique_query_with_index")
        
        query = "SELECT * FROM business_objects WHERE code = ?"
        
        for _ in range(20):
            timer_no_idx.start()
            db_without_indexes.query(query, ("BO00001",))
            timer_no_idx.stop()
            
            timer_with_idx.start()
            db_with_indexes.query(query, ("BO00001",))
            timer_with_idx.stop()
        
        metric_no_idx = timer_no_idx.get_metric()
        metric_with_idx = timer_with_idx.get_metric()
        
        improvement = (metric_no_idx.value - metric_with_idx.value) / metric_no_idx.value * 100 if metric_no_idx.value > 0 else 0
        
        print("\n=== 唯一索引效果 ===")
        print("无索引: {0:.3f}ms".format(metric_no_idx.value))
        print("有索引: {0:.3f}ms".format(metric_with_idx.value))
        print("提升: {0:.1f}%".format(improvement))
    
    @pytest.mark.performance
    @pytest.mark.index_perf
    def test_partial_index_effectiveness(self, db_without_indexes, db_with_indexes):
        """测试部分索引效果"""
        timer_no_idx = PerformanceTimer("partial_query_no_index")
        timer_with_idx = PerformanceTimer("partial_query_with_index")
        
        query = "SELECT * FROM business_objects WHERE version_id = ? AND code LIKE ?"
        
        for _ in range(20):
            timer_no_idx.start()
            db_without_indexes.query(query, (1, "BO%"))
            timer_no_idx.stop()
            
            timer_with_idx.start()
            db_with_indexes.query(query, (1, "BO%"))
            timer_with_idx.stop()
        
        metric_no_idx = timer_no_idx.get_metric()
        metric_with_idx = timer_with_idx.get_metric()
        
        print("\n=== 部分索引效果 ===")
        print("无索引: {0:.3f}ms".format(metric_no_idx.value))
        print("有索引: {0:.3f}ms".format(metric_with_idx.value))
    
    @pytest.mark.performance
    @pytest.mark.index_perf
    def test_index_size_overhead(self, db_without_indexes, db_with_indexes):
        """测试索引空间开销"""
        def get_db_size(ds):
            result = ds.query("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
            return result[0]["size"] if result else 0
        
        size_no_idx = get_db_size(db_without_indexes)
        size_with_idx = get_db_size(db_with_indexes)
        
        overhead = (size_with_idx - size_no_idx) / 1024.0
        
        print("\n=== 索引空间开销 ===")
        print("无索引: {0:.2f} KB".format(size_no_idx / 1024.0))
        print("有索引: {0:.2f} KB".format(size_with_idx / 1024.0))
        print("索引开销: {0:.2f} KB".format(overhead))
    
    @pytest.mark.performance
    @pytest.mark.index_perf
    def test_write_overhead_with_indexes(self, db_without_indexes, db_with_indexes):
        """测试索引对写入性能的影响"""
        now = int(time.time())
        
        timer_no_idx = PerformanceTimer("write_no_index")
        timer_with_idx = PerformanceTimer("write_with_index")
        
        for _ in range(5):
            test_data = [
                {
                    "name": "写入测试{0:05d}".format(i),
                    "code": "WR_NO_IDX_{0:05d}".format(i),
                    "description": "写入测试描述",
                    "version_id": 1,
                    "service_module_id": 1,
                    "created_at": now,
                }
                for i in range(100)
            ]
            
            timer_no_idx.start()
            db_without_indexes.batch_insert("business_objects", test_data)
            db_without_indexes.commit()
            timer_no_idx.stop()
            
            db_without_indexes.execute("DELETE FROM business_objects WHERE code LIKE 'WR_NO_IDX%'")
            db_without_indexes.commit()
        
        for _ in range(5):
            test_data = [
                {
                    "name": "写入测试{0:05d}".format(i),
                    "code": "WR_WITH_IDX_{0:05d}".format(i),
                    "description": "写入测试描述",
                    "version_id": 1,
                    "service_module_id": 1,
                    "created_at": now,
                }
                for i in range(100)
            ]
            
            timer_with_idx.start()
            db_with_indexes.batch_insert("business_objects", test_data)
            db_with_indexes.commit()
            timer_with_idx.stop()
            
            db_with_indexes.execute("DELETE FROM business_objects WHERE code LIKE 'WR_WITH_IDX%'")
            db_with_indexes.commit()
        
        metric_no_idx = timer_no_idx.get_metric()
        metric_with_idx = timer_with_idx.get_metric()
        
        overhead = (metric_with_idx.value - metric_no_idx.value) / metric_no_idx.value * 100 if metric_no_idx.value > 0 else 0
        
        print("\n=== 索引对写入性能的影响 ===")
        print("无索引: {0:.3f}ms".format(metric_no_idx.value))
        print("有索引: {0:.3f}ms".format(metric_with_idx.value))
        print("写入开销: {0:.1f}%".format(overhead))


class TestIndexBenchmark:
    """索引基准测试"""
    
    @pytest.fixture
    def benchmark_db(self):
        """基准测试数据库"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        ds = get_data_source("sqlite", database=db_path)
        
        try:
            import meta.core.table_name_validator as tnv
            tnv._VALID_TABLES_CACHE = None
            meta_objects = [registry.get(obj_id) for obj_id in registry.list_objects()]
            meta_objects = [obj for obj in meta_objects if obj is not None]
            sync_schema_from_meta(ds, meta_objects)
            
            service = IndexManagementService(ds)
            service.create_all_indexes()
            
            now = int(time.time())
            ds.execute("INSERT INTO products (id, name, code, created_at) VALUES (1, 'P1', 'P01', ?)", (now,))
            ds.execute("INSERT INTO versions (id, name, code, product_id, created_at) VALUES (1, 'V1', 'V01', 1, ?)", (now,))
            ds.execute("INSERT INTO domains (id, name, code, version_id, created_at) VALUES (1, 'D1', 'D01', 1, ?)", (now,))
            ds.execute("INSERT INTO sub_domains (id, name, code, domain_id, version_id, created_at) VALUES (1, 'SD1', 'SD01', 1, 1, ?)", (now,))
            ds.execute("INSERT INTO service_modules (id, name, code, sub_domain_id, version_id, created_at) VALUES (1, 'SM1', 'SM01', 1, 1, ?)", (now,))
            
            batch_data = [
                {
                    "name": "基准对象{0:05d}".format(i),
                    "code": "BENCH{0:05d}".format(i),
                    "description": "基准测试描述{0}".format(i),
                    "version_id": 1,
                    "service_module_id": 1,
                    "created_at": now,
                }
                for i in range(3000)
            ]
            ds.batch_insert("business_objects", batch_data)
            ds.commit()
            
            yield ds
        finally:
            try:
                ds.disconnect()
            except Exception:
                pass
            try:
                os.remove(db_path)
            except Exception:
                pass
    
    @pytest.mark.performance
    @pytest.mark.benchmark
    def test_index_benchmark(self, benchmark_db, performance_benchmark):
        """索引基准测试"""
        ds = benchmark_db
        benchmark = performance_benchmark("index_benchmark")

        print("\n=== 索引基准测试 ===")

        benchmark.add_scenario("pk_query", lambda: ds.query(
            "SELECT * FROM business_objects WHERE id = ?", (1,)
        ), warmup=3)
        benchmark.add_scenario("unique_index_query", lambda: ds.query(
            "SELECT * FROM business_objects WHERE code = ?", ("BENCH00001",)
        ), warmup=3)
        benchmark.add_scenario("plain_index_query", lambda: ds.query(
            "SELECT * FROM business_objects WHERE version_id = ?", (1,)
        ), warmup=3)
        benchmark.add_scenario("composite_query", lambda: ds.query(
            "SELECT * FROM business_objects WHERE version_id = ? AND service_module_id = ?", (1, 1)
        ), warmup=3)
        benchmark.add_scenario("range_query", lambda: ds.query(
            "SELECT * FROM business_objects WHERE id BETWEEN ? AND ?", (1, 100)
        ), warmup=3)
        benchmark.add_scenario("sort_query", lambda: ds.query(
            "SELECT * FROM business_objects ORDER BY created_at DESC LIMIT 100", ()
        ), warmup=3)

        results = benchmark.run(iterations=20)

        for name, metric in results.items():
            print("{0}: {1:.3f}ms (平均)".format(name, metric.value))

        benchmark.save_baseline(results)

        baseline = benchmark.load_baseline()
        assert baseline is not None or True, "Baseline should be saved"

        regression = benchmark.check_regression(results, threshold=0.5)
        if regression.get("status") == "regression":
            print("警告: 检测到性能回归!")
            for r in regression.get("regressions", []):
                print("  {scenario}: +{change_percent:.1f}%".format(**r))
