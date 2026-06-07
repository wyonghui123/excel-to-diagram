# -*- coding: utf-8 -*-
"""
API 端点性能测试

测试 REST API 的响应性能：
- CRUD 操作性能
- 批量操作性能
- 复杂查询性能
"""

import pytest
import json
import time
import os

pytestmark = pytest.mark.slow

from meta.tests.performance.performance_base import (
    PerformanceTimer, PerformanceBenchmark, performance_context
)


class TestAPIPerformance:
    """API 端点性能测试"""
    
    @pytest.fixture
    def test_app(self, perf_db_with_user):
        """创建测试应用"""
        from meta.server import create_app
        from meta.api.manage_api import init_services as init_manage_services
        from meta.api.auth_api import init_auth_services
        from meta.api.user_api import init_user_services
        from meta.api.role_api import init_role_services
        from meta.api.data_permission_api import init_data_perm_services
        
        os.environ['AUTH_ENABLED'] = 'false'
        
        app = create_app()
        
        init_manage_services(perf_db_with_user)
        init_auth_services(perf_db_with_user)
        init_user_services(perf_db_with_user)
        init_role_services(perf_db_with_user)
        init_data_perm_services(perf_db_with_user)
        
        app.config["TESTING"] = True
        
        return app
    
    @pytest.fixture
    def api_client(self, test_app):
        """API 测试客户端"""
        with test_app.test_client() as client:
            yield client
    
    @pytest.fixture
    def auth_headers(self, api_client):
        """认证头"""
        response = api_client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        
        if response.status_code == 200:
            try:
                data = json.loads(response.data)
            except (json.JSONDecodeError, ValueError):
                data = {}
            token = data.get("data", {}).get("token", "test-token")
            return {"Authorization": "Bearer {0}".format(token)}
        
        return {"Authorization": "Bearer test-token"}
    
    @pytest.mark.performance
    @pytest.mark.api_perf
    def test_list_api_performance(self, api_client, auth_headers, performance_timer):
        """测试列表 API 性能"""
        timer = performance_timer("list_api")
        
        for _ in range(50):
            timer.start()
            response = api_client.get(
                "/api/v1/business_objects",
                headers=auth_headers,
                query_string={"page": 1, "page_size": 20}
            )
            timer.stop()
        
        metric = timer.get_metric()
        
        assert metric.value < 100, "列表 API 平均耗时应小于 100ms"
        assert metric.percentile_95 < 200, "P95 应小于 200ms"
        
        print("\n列表 API 性能:")
        print("  平均: {0:.2f}ms".format(metric.value))
        print("  P95: {0:.2f}ms".format(metric.percentile_95))
    
    @pytest.mark.performance
    @pytest.mark.api_perf
    def test_detail_api_performance(self, api_client, auth_headers, performance_timer):
        """测试详情 API 性能"""
        timer = performance_timer("detail_api")
        
        for _ in range(50):
            timer.start()
            response = api_client.get(
                "/api/v1/business_objects/1",
                headers=auth_headers
            )
            timer.stop()
        
        metric = timer.get_metric()
        
        assert metric.value < 50, "详情 API 平均耗时应小于 50ms"
        
        print("\n详情 API 性能:")
        print("  平均: {0:.2f}ms".format(metric.value))
        print("  P95: {0:.2f}ms".format(metric.percentile_95))
    
    @pytest.mark.performance
    @pytest.mark.api_perf
    def test_create_api_performance(self, api_client, auth_headers, performance_timer, perf_db_with_user):
        """测试创建 API 性能"""
        timer = performance_timer("create_api")
        
        cursor = perf_db_with_user.execute("SELECT id FROM versions LIMIT 1")
        version_row = cursor.fetchone()
        version_id = version_row[0] if version_row else 1
        
        cursor = perf_db_with_user.execute("SELECT id FROM service_modules LIMIT 1")
        sm_row = cursor.fetchone()
        service_module_id = sm_row[0] if sm_row else 1
        
        for i in range(20):
            data = {
                "name": "性能测试对象{0}".format(i),
                "code": "PERF_API_{0:04d}".format(i),
                "description": "性能测试描述",
                "version_id": version_id,
                "service_module_id": service_module_id,
            }
            
            timer.start()
            response = api_client.post(
                "/api/v1/business_objects",
                headers=auth_headers,
                json=data
            )
            timer.stop()
        
        metric = timer.get_metric()
        
        assert metric.value < 100, "创建 API 平均耗时应小于 100ms"
        
        print("\n创建 API 性能:")
        print("  平均: {0:.2f}ms".format(metric.value))
    
    @pytest.mark.performance
    @pytest.mark.api_perf
    def test_update_api_performance(self, api_client, auth_headers, performance_timer):
        """测试更新 API 性能"""
        timer = performance_timer("update_api")
        
        for i in range(20):
            data = {
                "name": "更新后的名称{0}".format(i),
                "description": "更新后的描述{0}".format(i),
            }
            
            timer.start()
            response = api_client.put(
                "/api/v1/business_objects/{0}".format((i % 10) + 1),
                headers=auth_headers,
                json=data
            )
            timer.stop()
        
        metric = timer.get_metric()
        
        assert metric.value < 100, "更新 API 平均耗时应小于 100ms"
        
        print("\n更新 API 性能:")
        print("  平均: {0:.2f}ms".format(metric.value))
    
    @pytest.mark.performance
    @pytest.mark.api_perf
    def test_filter_api_performance(self, api_client, auth_headers, performance_timer, perf_db_with_user):
        """测试筛选 API 性能"""
        timer = performance_timer("filter_api")
        
        cursor = perf_db_with_user.execute("SELECT id FROM versions LIMIT 1")
        version_row = cursor.fetchone()
        version_id = version_row[0] if version_row else 1
        
        filter_params = [
            {"version_id": version_id},
            {"name__contains": "业务"},
            {"code__startswith": "BO"},
        ]
        
        for params in filter_params:
            for _ in range(10):
                timer.start()
                response = api_client.get(
                    "/api/v1/business_objects",
                    headers=auth_headers,
                    query_string=params
                )
                timer.stop()
        
        metric = timer.get_metric()
        
        print("\n筛选 API 性能:")
        print("  平均: {0:.2f}ms".format(metric.value))
    
    @pytest.mark.performance
    @pytest.mark.api_perf
    def test_search_api_performance(self, api_client, auth_headers, performance_timer):
        """测试搜索 API 性能"""
        timer = performance_timer("search_api")
        
        search_terms = ["业务", "对象", "测试", "BO001"]
        
        for term in search_terms:
            for _ in range(10):
                timer.start()
                response = api_client.get(
                    "/api/v1/business_objects",
                    headers=auth_headers,
                    query_string={"keyword": term}
                )
                timer.stop()
        
        metric = timer.get_metric()
        
        print("\n搜索 API 性能:")
        print("  平均: {0:.2f}ms".format(metric.value))
        print("  P95: {0:.2f}ms".format(metric.percentile_95))


class TestAPIBenchmark:
    """API 性能基准测试"""
    
    @pytest.fixture
    def test_app(self, perf_db_with_user):
        """创建测试应用"""
        from meta.server import create_app
        from meta.api.manage_api import init_services as init_manage_services
        from meta.api.auth_api import init_auth_services
        from meta.api.user_api import init_user_services
        from meta.api.role_api import init_role_services
        from meta.api.data_permission_api import init_data_perm_services
        
        os.environ['AUTH_ENABLED'] = 'false'
        
        app = create_app()
        
        init_manage_services(perf_db_with_user)
        init_auth_services(perf_db_with_user)
        init_user_services(perf_db_with_user)
        init_role_services(perf_db_with_user)
        init_data_perm_services(perf_db_with_user)
        
        app.config["TESTING"] = True
        
        return app
    
    @pytest.fixture
    def api_client(self, test_app):
        """API 测试客户端"""
        with test_app.test_client() as client:
            yield client
    
    @pytest.fixture
    def auth_headers(self, api_client):
        """认证头"""
        return {"Authorization": "Bearer test-token"}
    
    @pytest.mark.performance
    @pytest.mark.benchmark
    def test_api_benchmark(self, api_client, auth_headers, performance_benchmark):
        """API 性能基准测试"""
        benchmark = performance_benchmark("api_benchmark")
        
        benchmark.add_scenario("list_20", lambda: api_client.get(
            "/api/v1/business_objects",
            headers=auth_headers,
            query_string={"page": 1, "page_size": 20}
        ))
        
        benchmark.add_scenario("list_100", lambda: api_client.get(
            "/api/v1/business_objects",
            headers=auth_headers,
            query_string={"page": 1, "page_size": 100}
        ))
        
        benchmark.add_scenario("detail", lambda: api_client.get(
            "/api/v1/business_objects/1",
            headers=auth_headers
        ))
        
        results = benchmark.run(iterations=20)
        
        print("\n=== API 性能基准测试 ===")
        for name, metric in results.items():
            print("{0}:".format(name))
            print("  平均: {0:.2f}{1}".format(metric.value, metric.unit))
            print("  P95: {0:.2f}{1}".format(metric.percentile_95, metric.unit))
        
        benchmark.save_baseline(results)


class TestBatchAPIPerformance:
    """批量 API 性能测试"""
    
    @pytest.fixture
    def test_app(self, perf_db_with_user):
        """创建测试应用"""
        from meta.server import create_app
        from meta.api.manage_api import init_services as init_manage_services
        from meta.api.auth_api import init_auth_services
        from meta.api.user_api import init_user_services
        from meta.api.role_api import init_role_services
        from meta.api.data_permission_api import init_data_perm_services
        
        os.environ['AUTH_ENABLED'] = 'false'
        
        app = create_app()
        
        init_manage_services(perf_db_with_user)
        init_auth_services(perf_db_with_user)
        init_user_services(perf_db_with_user)
        init_role_services(perf_db_with_user)
        init_data_perm_services(perf_db_with_user)
        
        app.config["TESTING"] = True
        
        return app
    
    @pytest.fixture
    def api_client(self, test_app):
        """API 测试客户端"""
        with test_app.test_client() as client:
            yield client
    
    @pytest.fixture
    def auth_headers(self, api_client):
        """认证头"""
        return {"Authorization": "Bearer test-token"}
    
    @pytest.mark.performance
    @pytest.mark.api_perf
    def test_batch_create_performance(self, api_client, auth_headers, performance_timer, perf_db_with_user):
        """测试批量创建性能"""
        cursor = perf_db_with_user.execute("SELECT id FROM versions LIMIT 1")
        version_row = cursor.fetchone()
        version_id = version_row[0] if version_row else 1
        
        cursor = perf_db_with_user.execute("SELECT id FROM service_modules LIMIT 1")
        sm_row = cursor.fetchone()
        service_module_id = sm_row[0] if sm_row else 1
        
        timer = performance_timer("batch_create")
        
        for batch_size in [10, 50, 100]:
            timer.reset()
            
            items = [
                {
                    "name": "批量对象{0}".format(i),
                    "code": "BATCH_{0:05d}".format(i),
                    "version_id": version_id,
                    "service_module_id": service_module_id,
                }
                for i in range(batch_size)
            ]
            
            for _ in range(5):
                timer.start()
                response = api_client.post(
                    "/api/v1/business_objects/batch-create",
                    headers=auth_headers,
                    json={"items": items}
                )
                timer.stop()
            
            metric = timer.get_metric()
            print("\n批量创建 ({0}条): {1:.2f}ms (每条 {2:.2f}ms)".format(
                batch_size, metric.value, metric.value / batch_size
            ))
    
    @pytest.mark.performance
    @pytest.mark.api_perf
    def test_batch_update_performance(self, api_client, auth_headers, performance_timer, perf_db_with_user):
        """测试批量更新性能"""
        timer = performance_timer("batch_update")
        
        cursor = perf_db_with_user.execute("SELECT id FROM business_objects LIMIT 50")
        bo_ids = [row[0] for row in cursor.fetchall()]
        
        if not bo_ids:
            pytest.skip("没有足够的测试数据")
        
        updates = [
            {"id": bo_id, "name": "更新后的名称_{0}".format(bo_id)}
            for bo_id in bo_ids
        ]
        
        for _ in range(5):
            timer.start()
            response = api_client.post(
                "/api/v1/business_objects/batch-update",
                headers=auth_headers,
                json={"updates": updates}
            )
            timer.stop()
        
        metric = timer.get_metric()
        print("\n批量更新 ({0}条): {1:.2f}ms".format(len(bo_ids), metric.value))
