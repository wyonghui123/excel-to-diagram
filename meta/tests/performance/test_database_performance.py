# -*- coding: utf-8 -*-
"""
数据库查询性能基准测试

测试数据库操作的基准性能，包括：
- 单条记录查询
- 批量查询
- 关联查询
- 聚合查询
- 写入性能
"""

import pytest
import time

pytestmark = pytest.mark.slow

from meta.tests.performance.performance_base import (
    PerformanceTimer, PerformanceBenchmark, performance_context
)


class TestDatabaseQueryPerformance:
    """数据库查询性能测试"""
    
    @pytest.mark.performance
    @pytest.mark.db_perf
    def test_single_query_performance(self, perf_db_with_data, performance_timer):
        """测试单条记录查询性能"""
        ds = perf_db_with_data
        timer = performance_timer("single_query")
        
        for _ in range(100):
            timer.start()
            result = ds.query(
                "SELECT * FROM business_objects WHERE id = ?",
                (1,)
            )
            timer.stop()
        
        metric = timer.get_metric()
        
        assert metric.value < 1.0, "单条查询平均耗时应小于 1ms"
        assert metric.percentile_95 < 2.0, "P95 应小于 2ms"
        
        print("\n单条查询性能:")
        print("  平均: {0:.3f}ms".format(metric.value))
        print("  P95: {0:.3f}ms".format(metric.percentile_95))
        print("  P99: {0:.3f}ms".format(metric.percentile_99))
    
    @pytest.mark.performance
    @pytest.mark.db_perf
    def test_list_query_performance(self, perf_db_with_data, performance_timer):
        """测试列表查询性能"""
        ds = perf_db_with_data
        timer = performance_timer("list_query")
        
        for _ in range(50):
            timer.start()
            results = ds.query(
                "SELECT * FROM business_objects WHERE version_id = ? LIMIT 100",
                (1,)
            )
            timer.stop()
        
        metric = timer.get_metric()
        
        assert metric.value < 5.0, "列表查询平均耗时应小于 5ms"
        
        print("\n列表查询性能 (100条):")
        print("  平均: {0:.3f}ms".format(metric.value))
        print("  P95: {0:.3f}ms".format(metric.percentile_95))
    
    @pytest.mark.performance
    @pytest.mark.db_perf
    def test_join_query_performance(self, perf_db_with_data, performance_timer):
        """测试关联查询性能"""
        ds = perf_db_with_data
        timer = performance_timer("join_query")
        
        query = """
            SELECT bo.*, sm.name as service_module_name, v.name as version_name
            FROM business_objects bo
            LEFT JOIN service_modules sm ON bo.service_module_id = sm.id
            LEFT JOIN versions v ON bo.version_id = v.id
            WHERE bo.version_id = ?
            LIMIT 100
        """
        
        for _ in range(50):
            timer.start()
            results = ds.query(query, (1,))
            timer.stop()
        
        metric = timer.get_metric()
        
        assert metric.value < 10.0, "关联查询平均耗时应小于 10ms"
        
        print("\n关联查询性能 (2表JOIN, 100条):")
        print("  平均: {0:.3f}ms".format(metric.value))
        print("  P95: {0:.3f}ms".format(metric.percentile_95))
    
    @pytest.mark.performance
    @pytest.mark.db_perf
    def test_aggregation_query_performance(self, perf_db_with_data, performance_timer):
        """测试聚合查询性能"""
        ds = perf_db_with_data
        timer = performance_timer("aggregation_query")
        
        query = """
            SELECT 
                version_id,
                service_module_id,
                COUNT(*) as count,
                MAX(updated_at) as last_updated
            FROM business_objects
            GROUP BY version_id, service_module_id
            ORDER BY count DESC
        """
        
        for _ in range(30):
            timer.start()
            results = ds.query(query)
            timer.stop()
        
        metric = timer.get_metric()
        
        assert metric.value < 20.0, "聚合查询平均耗时应小于 20ms"
        
        print("\n聚合查询性能:")
        print("  平均: {0:.3f}ms".format(metric.value))
        print("  P95: {0:.3f}ms".format(metric.percentile_95))
    
    @pytest.mark.performance
    @pytest.mark.db_perf
    def test_insert_performance(self, perf_db, performance_timer):
        """测试插入性能"""
        timer = performance_timer("insert")
        now = int(time.time())
        
        ds = perf_db
        ds.execute("INSERT INTO products (id, name, code, created_at) VALUES (1, 'P1', 'P01', ?)", (now, now))
        ds.execute("INSERT INTO versions (id, name, code, product_id, created_at) VALUES (1, 'V1', 'V01', 1, ?)", (now, now))
        ds.execute("INSERT INTO domains (id, name, code, version_id, created_at) VALUES (1, 'D1', 'D01', 1, ?)", (now, now))
        ds.execute("INSERT INTO sub_domains (id, name, code, domain_id, version_id, created_at) VALUES (1, 'SD1', 'SD01', 1, 1, ?)", (now, now))
        ds.execute("INSERT INTO service_modules (id, name, code, sub_domain_id, version_id, created_at) VALUES (1, 'SM1', 'SM01', 1, 1, ?)", (now, now))
        ds.commit()
        
        for iteration in range(10):
            test_data = [
                ("BO_{0}_{1:04d}".format(iteration, i), "CODE_{0}_{1:04d}".format(iteration, i), "描述{0}".format(i), 1, 1, now)
                for i in range(100)
            ]
            
            timer.start()
            for data in test_data:
                ds.execute("""
                    INSERT INTO business_objects 
                    (name, code, description, version_id, service_module_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, data)
            perf_db.commit()
            timer.stop()
        
        metric = timer.get_metric()
        
        print("\n插入性能 (100条 x 10次):")
        print("  平均: {0:.3f}ms".format(metric.value))
        print("  每条: {0:.3f}ms".format(metric.value / 100))
    
    @pytest.mark.performance
    @pytest.mark.db_perf
    def test_batch_insert_performance(self, perf_db, performance_timer):
        """测试批量插入性能"""
        timer = performance_timer("batch_insert")
        now = int(time.time())
        
        ds = perf_db
        ds.execute("INSERT INTO products (id, name, code, created_at) VALUES (1, 'P1', 'P01', ?)", (now, now))
        ds.execute("INSERT INTO versions (id, name, code, product_id, created_at) VALUES (1, 'V1', 'V01', 1, ?)", (now, now))
        ds.execute("INSERT INTO domains (id, name, code, version_id, created_at) VALUES (1, 'D1', 'D01', 1, ?)", (now, now))
        ds.execute("INSERT INTO sub_domains (id, name, code, domain_id, version_id, created_at) VALUES (1, 'SD1', 'SD01', 1, 1, ?)", (now, now))
        ds.execute("INSERT INTO service_modules (id, name, code, sub_domain_id, version_id, created_at) VALUES (1, 'SM1', 'SM01', 1, 1, ?)", (now, now))
        ds.commit()
        
        for iteration in range(10):
            test_data = [
                {
                    "name": "BO_{0}_{1:04d}".format(iteration, i),
                    "code": "CODE_{0}_{1:04d}".format(iteration, i),
                    "description": "业务对象{0}".format(i),
                    "version_id": 1,
                    "service_module_id": 1,
                    "created_at": now,
                }
                for i in range(100)
            ]
            
            timer.start()
            perf_db.batch_insert("business_objects", test_data)
            perf_db.commit()
            timer.stop()
        
        metric = timer.get_metric()
        
        print("\n批量插入性能 (100条 x 10次):")
        print("  平均: {0:.3f}ms".format(metric.value))
        print("  每条: {0:.3f}ms".format(metric.value / 100))
    
    @pytest.mark.performance
    @pytest.mark.db_perf
    def test_update_performance(self, perf_db_with_data, performance_timer):
        """测试更新性能"""
        ds = perf_db_with_data
        timer = performance_timer("update")
        
        bo_ids = [row["id"] for row in ds.query("SELECT id FROM business_objects LIMIT 100")]
        
        for _ in range(50):
            timer.start()
            for bo_id in bo_ids:
                ds.execute(
                    "UPDATE business_objects SET name = name || ? WHERE id = ?",
                    ("_updated", bo_id)
                )
            ds.commit()
            timer.stop()
        
        metric = timer.get_metric()
        
        print("\n更新性能 (100条):")
        print("  平均: {0:.3f}ms".format(metric.value))
        print("  每条: {0:.3f}ms".format(metric.value / 100))
    
    @pytest.mark.performance
    @pytest.mark.db_perf
    def test_delete_performance(self, perf_db, performance_timer):
        """测试删除性能"""
        timer = performance_timer("delete")
        now = int(time.time())
        
        ds = perf_db
        ds.execute("INSERT INTO products (id, name, code, created_at) VALUES (1, 'P1', 'P01', ?)", (now, now))
        ds.execute("INSERT INTO versions (id, name, code, product_id, created_at) VALUES (1, 'V1', 'V01', 1, ?)", (now, now))
        ds.execute("INSERT INTO domains (id, name, code, version_id, created_at) VALUES (1, 'D1', 'D01', 1, ?)", (now, now))
        ds.execute("INSERT INTO sub_domains (id, name, code, domain_id, version_id, created_at) VALUES (1, 'SD1', 'SD01', 1, 1, ?)", (now, now))
        ds.execute("INSERT INTO service_modules (id, name, code, sub_domain_id, version_id, created_at) VALUES (1, 'SM1', 'SM01', 1, 1, ?)", (now, now))
        ds.commit()
        
        for iteration in range(10):
            test_data = [
                {
                    "name": "DEL_{0}_{1:04d}".format(iteration, i),
                    "code": "DEL_CODE_{0}_{1:04d}".format(iteration, i),
                    "description": "删除测试{0}".format(i),
                    "version_id": 1,
                    "service_module_id": 1,
                    "created_at": now,
                }
                for i in range(100)
            ]
            
            ds.batch_insert("business_objects", test_data)
            ds.commit()
            
            timer.start()
            ds.execute("DELETE FROM business_objects WHERE name LIKE ?", ("DEL_{0}%".format(iteration),))
            ds.commit()
            timer.stop()
        
        metric = timer.get_metric()
        
        print("\n删除性能 (100条):")
        print("  平均: {0:.3f}ms".format(metric.value))


class TestDatabaseBenchmark:
    """数据库性能基准测试"""
    
    @pytest.mark.performance
    @pytest.mark.benchmark
    def test_query_benchmark(self, perf_db_with_data, performance_benchmark):
        """查询性能基准测试"""
        ds = perf_db_with_data
        benchmark = performance_benchmark("db_query_benchmark")
        
        benchmark.add_scenario("single_query", lambda: ds.query(
            "SELECT * FROM business_objects WHERE id = ?", (1,)
        ))
        
        benchmark.add_scenario("list_10", lambda: ds.query(
            "SELECT * FROM business_objects LIMIT 10"
        ))
        
        benchmark.add_scenario("list_100", lambda: ds.query(
            "SELECT * FROM business_objects LIMIT 100"
        ))
        
        benchmark.add_scenario("list_1000", lambda: ds.query(
            "SELECT * FROM business_objects LIMIT 1000"
        ))
        
        benchmark.add_scenario("filter_query", lambda: ds.query(
            "SELECT * FROM business_objects WHERE version_id = ? AND domain_id = ?",
            (1, 1)
        ))
        
        benchmark.add_scenario("join_query", lambda: ds.query("""
            SELECT bo.*, d.name as domain_name
            FROM business_objects bo
            LEFT JOIN domains d ON bo.domain_id = d.id
            LIMIT 100
        """))
        
        results = benchmark.run(iterations=20)
        
        print("\n=== 数据库查询基准测试 ===")
        for name, metric in results.items():
            print("{0}:".format(name))
            print("  平均: {0:.3f}{1}".format(metric.value, metric.unit))
            print("  P95: {0:.3f}{1}".format(metric.percentile_95, metric.unit))
        
        benchmark.save_baseline(results)
    
    @pytest.mark.performance
    @pytest.mark.benchmark
    def test_write_benchmark(self, perf_db, performance_benchmark):
        """写入性能基准测试"""
        ds = perf_db
        benchmark = performance_benchmark("db_write_benchmark")
        now = int(time.time())
        
        def insert_10():
            for i in range(10):
                ds.execute("""
                    INSERT INTO business_objects 
                    (name, code, description, version_id, domain_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, ("BO_{0}".format(i), "CODE_{0}".format(i), "desc", 1, 1, now))
            ds.commit()
        
        def insert_100():
            for i in range(100):
                ds.execute("""
                    INSERT INTO business_objects 
                    (name, code, description, version_id, domain_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, ("BO_{0}".format(i), "CODE_{0}".format(i), "desc", 1, 1, now))
            ds.commit()
        
        def batch_insert_100():
            data = [("BO_{0}".format(i), "CODE_{0}".format(i), "desc", 1, 1, now) for i in range(100)]
            ds.execute_batch("""
                INSERT INTO business_objects 
                (name, code, description, version_id, domain_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, data)
            ds.commit()
        
        benchmark.add_scenario("insert_10", insert_10)
        benchmark.add_scenario("insert_100", insert_100)
        benchmark.add_scenario("batch_insert_100", batch_insert_100)
        
        results = benchmark.run(iterations=10)
        
        print("\n=== 数据库写入基准测试 ===")
        for name, metric in results.items():
            print("{0}:".format(name))
            print("  平均: {0:.3f}{1}".format(metric.value, metric.unit))
        
        benchmark.save_baseline(results)
