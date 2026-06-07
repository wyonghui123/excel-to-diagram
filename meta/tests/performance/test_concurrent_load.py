# -*- coding: utf-8 -*-
"""
并发压力测试

测试系统在并发场景下的性能表现：
- 并发读取
- 并发写入
- 混合读写
- 连接池压力
"""

import pytest
import time
import tempfile
import os
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

pytestmark = pytest.mark.slow

from meta.tests.performance.performance_base import (
    PerformanceTimer, PerformanceBenchmark, performance_context
)
from meta.core.datasource import get_data_source
from meta.core.schema_generator import sync_schema_from_meta
from meta.core.models import registry
from meta.core.index_management_service import IndexManagementService


class TestConcurrentPerformance:
    """并发性能测试"""
    
    @pytest.fixture
    def concurrent_db(self):
        """并发测试数据库"""
        import meta.core.table_name_validator as tnv
        tnv._VALID_TABLES_CACHE = None
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        ds = get_data_source("sqlite", database=db_path)
        
        try:
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
            
            test_data = [
                {
                    "name": "并发对象{0:05d}".format(i),
                    "code": "CONC{0:05d}".format(i),
                    "description": "并发描述",
                    "version_id": 1,
                    "service_module_id": 1,
                    "created_at": now,
                }
                for i in range(1000)
            ]
            ds.batch_insert("business_objects", test_data)
            ds.commit()
            
            yield db_path
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
    @pytest.mark.stress
    def test_concurrent_read(self, concurrent_db, performance_timer):
        """测试并发读取"""
        db_path = concurrent_db
        results_queue = queue.Queue()
        errors = []
        
        def read_task(task_id):
            try:
                ds = get_data_source("sqlite", database=db_path)
                try:
                    start = time.perf_counter()
                    
                    for _ in range(10):
                        result = ds.query("SELECT * FROM business_objects WHERE version_id = 1 LIMIT 100")
                    
                    elapsed = (time.perf_counter() - start) * 1000
                    results_queue.put(elapsed)
                finally:
                    ds.disconnect()
            except Exception as e:
                errors.append(str(e))
        
        thread_counts = [1, 5, 10, 20]
        
        print("\n=== 并发读取性能 ===")
        
        for thread_count in thread_counts:
            results_queue.queue.clear()
            errors.clear()
            
            start_time = time.perf_counter()
            
            threads = []
            for i in range(thread_count):
                t = threading.Thread(target=read_task, args=(i,))
                threads.append(t)
                t.start()
            
            for t in threads:
                t.join()
            
            total_time = (time.perf_counter() - start_time) * 1000
            
            results = list(results_queue.queue)
            avg_time = sum(results) / len(results) if results else 0
            
            print("线程数 {0}: 总耗时 {1:.2f}ms, 平均单线程 {2:.2f}ms, 错误 {3}".format(
                thread_count, total_time, avg_time, len(errors)
            ))
    
    @pytest.mark.performance
    @pytest.mark.stress
    def test_concurrent_write(self, concurrent_db, performance_timer):
        """测试并发写入"""
        db_path = concurrent_db
        errors = []
        results_queue = queue.Queue()
        
        def write_task(task_id):
            try:
                ds = get_data_source("sqlite", database=db_path)
                try:
                    start = time.perf_counter()
                    
                    now = int(time.time())
                    for i in range(10):
                        ds.execute("""
                            INSERT INTO business_objects 
                            (name, code, description, version_id, service_module_id, created_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, ("写入_{0}_{1}".format(task_id, i), "WR_{0}_{1}".format(task_id, i), "描述", 1, 1, now))
                    ds.commit()
                    
                    elapsed = (time.perf_counter() - start) * 1000
                    results_queue.put(elapsed)
                finally:
                    ds.disconnect()
            except Exception as e:
                errors.append(str(e))
        
        thread_counts = [1, 5, 10]
        
        print("\n=== 并发写入性能 ===")
        
        for thread_count in thread_counts:
            results_queue.queue.clear()
            errors.clear()
            
            start_time = time.perf_counter()
            
            threads = []
            for i in range(thread_count):
                t = threading.Thread(target=write_task, args=(i,))
                threads.append(t)
                t.start()
            
            for t in threads:
                t.join()
            
            total_time = (time.perf_counter() - start_time) * 1000
            
            results = list(results_queue.queue)
            avg_time = sum(results) / len(results) if results else 0
            
            print("线程数 {0}: 总耗时 {1:.2f}ms, 平均单线程 {2:.2f}ms, 错误 {3}".format(
                thread_count, total_time, avg_time, len(errors)
            ))
    
    @pytest.mark.performance
    @pytest.mark.stress
    def test_mixed_read_write(self, concurrent_db, performance_timer):
        """测试混合读写"""
        db_path = concurrent_db
        errors = []
        read_results = queue.Queue()
        write_results = queue.Queue()
        
        def read_task(task_id):
            try:
                ds = get_data_source("sqlite", database=db_path)
                try:
                    start = time.perf_counter()
                    
                    for _ in range(20):
                        result = ds.query("SELECT * FROM business_objects WHERE version_id = 1 LIMIT 50")
                    
                    elapsed = (time.perf_counter() - start) * 1000
                    read_results.put(elapsed)
                finally:
                    ds.disconnect()
            except Exception as e:
                errors.append("读错误: {0}".format(str(e)))
        
        def write_task(task_id):
            try:
                ds = get_data_source("sqlite", database=db_path)
                try:
                    start = time.perf_counter()
                    
                    now = int(time.time())
                    for i in range(5):
                        ds.execute("""
                            INSERT INTO business_objects 
                            (name, code, description, version_id, service_module_id, created_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, ("混合_{0}_{1}".format(task_id, i), "MIX_{0}_{1}".format(task_id, i), "描述", 1, 1, now))
                    ds.commit()
                    
                    elapsed = (time.perf_counter() - start) * 1000
                    write_results.put(elapsed)
                finally:
                    ds.disconnect()
            except Exception as e:
                errors.append("写错误: {0}".format(str(e)))
        
        print("\n=== 混合读写性能 ===")
        
        start_time = time.perf_counter()
        
        threads = []
        for i in range(5):
            t = threading.Thread(target=read_task, args=(i,))
            threads.append(t)
        
        for i in range(3):
            t = threading.Thread(target=write_task, args=(i,))
            threads.append(t)
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        total_time = (time.perf_counter() - start_time) * 1000
        
        read_times = list(read_results.queue)
        write_times = list(write_results.queue)
        
        avg_read = sum(read_times) / len(read_times) if read_times else 0
        avg_write = sum(write_times) / len(write_times) if write_times else 0
        
        print("总耗时: {0:.2f}ms".format(total_time))
        print("平均读取: {0:.2f}ms".format(avg_read))
        print("平均写入: {0:.2f}ms".format(avg_write))
        print("错误数: {0}".format(len(errors)))


class TestThreadPoolBenchmark:
    """线程池基准测试"""
    
    @pytest.fixture
    def pool_db(self):
        """线程池测试数据库"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        ds = get_data_source("sqlite", database=db_path)
        
        try:
            meta_objects = [registry.get(obj_id) for obj_id in registry.list_objects()]
            sync_schema_from_meta(ds, meta_objects)
            
            now = int(time.time())
            ds.execute("INSERT INTO products (id, name, code, created_at) VALUES (1, 'P1', 'P01', ?)", (now,))
            ds.execute("INSERT INTO versions (id, name, code, product_id, created_at) VALUES (1, 'V1', 'V01', 1, ?)", (now,))
            ds.execute("INSERT INTO domains (id, name, code, version_id, created_at) VALUES (1, 'D1', 'D01', 1, ?)", (now,))
            ds.execute("INSERT INTO sub_domains (id, name, code, domain_id, version_id, created_at) VALUES (1, 'SD1', 'SD01', 1, 1, ?)", (now,))
            ds.execute("INSERT INTO service_modules (id, name, code, sub_domain_id, version_id, created_at) VALUES (1, 'SM1', 'SM01', 1, 1, ?)", (now,))
            
            test_data = [
                {
                    "name": "线程池对象{0:05d}".format(i),
                    "code": "POOL{0:05d}".format(i),
                    "description": "线程池描述",
                    "version_id": 1,
                    "service_module_id": 1,
                    "created_at": now,
                }
                for i in range(500)
            ]
            ds.batch_insert("business_objects", test_data)
            ds.commit()
            
            yield db_path
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
    def test_thread_pool_benchmark(self, pool_db, performance_benchmark):
        """线程池基准测试"""
        db_path = pool_db
        benchmark = performance_benchmark("thread_pool_benchmark")

        print("\n=== 线程池基准测试 ===")

        def make_pool_task(size):
            def _run():
                def query_task(_):
                    ds = get_data_source("sqlite", database=db_path)
                    try:
                        result = ds.query("SELECT * FROM business_objects WHERE version_id = 1 LIMIT 100")
                        return len(result)
                    finally:
                        ds.disconnect()

                with ThreadPoolExecutor(max_workers=size) as executor:
                    futures = [executor.submit(query_task, i) for i in range(50)]
                    list(as_completed(futures))
            return _run

        pool_sizes = [1, 5, 10, 20]

        for size in pool_sizes:
            benchmark.add_scenario("pool_{0}".format(size), make_pool_task(size), warmup=1)

        results = benchmark.run(iterations=5)

        for name, metric in results.items():
            throughput = 50 / (metric.value / 1000)
            print("线程池 {0}: {1:.2f}ms, 吞吐量 {2:.1f} 请求/秒".format(
                name, metric.value, throughput
            ))

        benchmark.save_baseline(results)

        regression = benchmark.check_regression(results, threshold=0.5)
        if regression.get("status") == "regression":
            print("警告: 检测到性能回归!")
            for r in regression.get("regressions", []):
                print("  {scenario}: +{change_percent:.1f}%".format(**r))
