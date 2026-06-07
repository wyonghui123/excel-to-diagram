# -*- coding: utf-8 -*-
"""
管理维度权限系统性能压测脚本

使用 Locust 进行性能测试，模拟并发用户访问。

测试场景：
1. 获取管理维度列表
2. 获取维度实例列表
3. 获取角色权限规则
4. 计算权限影响范围
5. 缓存命中率测试

性能目标：
- 并发 50 用户
- 平均响应时间 < 200ms
- 95% 请求响应时间 < 500ms
- 错误率 < 1%

使用方式：
    locust -f meta/tests/performance/locustfile.py --host=http://localhost:5000
    
    或使用自定义配置：
    locust -f meta/tests/performance/locustfile.py \
        --host=http://localhost:5000 \
        --users 50 \
        --spawn-rate 10 \
        --run-time 5m
"""

import json
import logging
import random
from typing import Dict, List

from locust import HttpUser, between, task, events
from locust.runners import MasterRunner, WorkerRunner

logger = logging.getLogger(__name__)


class PermissionSystemUser(HttpUser):
    """
    权限系统用户行为模拟
    
    模拟真实用户的操作场景：
    1. 登录获取 token
    2. 浏览管理维度列表
    3. 查看维度实例
    4. 配置权限规则
    5. 计算影响范围
    """
    
    wait_time = between(1, 3)
    
    def on_start(self):
        """用户开始时的初始化"""
        self.token = None
        self.role_ids = []
        self.dimension_ids = ['domain', 'sub_domain', 'service_module', 'business_object']
        
        self.login()
        self.load_test_data()
    
    def login(self):
        """登录获取 token"""
        response = self.client.post(
            "/api/v1/auth/login",
            json={
                "username": "admin",
                "password": "admin123"
            },
            name="登录"
        )
        
        if response.status_code == 200:
            data = response.json()
            self.token = data.get('data', {}).get('token')
            logger.debug(f"登录成功: token={self.token[:20] if self.token else 'None'}...")
        else:
            logger.warning(f"登录失败: {response.status_code}")
    
    def load_test_data(self):
        """加载测试数据"""
        if not self.token:
            return
        
        headers = self._get_headers()
        
        response = self.client.get(
            "/api/v1/management-dimensions",
            headers=headers,
            name="获取管理维度列表"
        )
        
        if response.status_code == 200:
            data = response.json().get('data', {})
            dimensions = data.get('dimensions', [])
            if dimensions:
                self.dimension_ids = [d['id'] for d in dimensions if d.get('id')]
        
        response = self.client.get(
            "/api/v1/roles",
            headers=headers,
            name="获取角色列表"
        )
        
        if response.status_code == 200:
            data = response.json().get('data', {})
            roles = data.get('roles', [])
            if roles:
                self.role_ids = [r['id'] for r in roles if r.get('id')]
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        headers = {
            "Content-Type": "application/json"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    @task(10)
    def get_dimensions(self):
        """获取管理维度列表（高频操作）"""
        headers = self._get_headers()
        
        with self.client.get(
            "/api/v1/management-dimensions",
            headers=headers,
            catch_response=True,
            name="获取管理维度列表"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    response.success()
                else:
                    response.failure(f"业务失败: {data.get('message')}")
            else:
                response.failure(f"HTTP {response.status_code}")
    
    @task(8)
    def get_dimension_instances(self):
        """获取维度实例列表（高频操作）"""
        if not self.dimension_ids:
            return
        
        dimension_id = random.choice(self.dimension_ids)
        headers = self._get_headers()
        
        params = {
            "page": random.randint(1, 5),
            "page_size": 20
        }
        
        if random.random() > 0.7:
            params["search"] = random.choice(["销售", "采购", "库存", "财务"])
        
        with self.client.get(
            f"/api/v1/management-dimensions/{dimension_id}/instances",
            headers=headers,
            params=params,
            catch_response=True,
            name="获取维度实例列表"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    response.success()
                else:
                    response.failure(f"业务失败: {data.get('message')}")
            else:
                response.failure(f"HTTP {response.status_code}")
    
    @task(6)
    def get_role_permission_rules(self):
        """获取角色权限规则（中频操作）"""
        if not self.role_ids:
            return
        
        role_id = random.choice(self.role_ids)
        headers = self._get_headers()
        
        with self.client.get(
            f"/api/v1/roles/{role_id}/permission-rules",
            headers=headers,
            catch_response=True,
            name="获取角色权限规则"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    response.success()
                else:
                    response.failure(f"业务失败: {data.get('message')}")
            else:
                response.failure(f"HTTP {response.status_code}")
    
    @task(4)
    def calculate_impact(self):
        """计算权限影响范围（低频操作，计算密集）"""
        if not self.role_ids:
            return
        
        role_id = random.choice(self.role_ids)
        headers = self._get_headers()
        
        with self.client.post(
            f"/api/v1/roles/{role_id}/calculate-impact",
            headers=headers,
            catch_response=True,
            name="计算权限影响范围"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    response.success()
                else:
                    response.failure(f"业务失败: {data.get('message')}")
            else:
                response.failure(f"HTTP {response.status_code}")
    
    @task(2)
    def get_cache_stats(self):
        """获取缓存统计（监控操作）"""
        headers = self._get_headers()
        
        with self.client.get(
            "/api/v1/meta/cache-stats",
            headers=headers,
            catch_response=True,
            name="获取缓存统计"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    response.success()
                else:
                    response.failure(f"业务失败: {data.get('message')}")
            else:
                response.failure(f"HTTP {response.status_code}")
    
    @task(1)
    def save_permission_rule(self):
        """保存权限规则（低频操作，写操作）"""
        if not self.role_ids or not self.dimension_ids:
            return
        
        role_id = random.choice(self.role_ids)
        resource_type = random.choice(self.dimension_ids)
        headers = self._get_headers()
        
        rule_data = {
            "resource_type": resource_type,
            "condition": f"id = {random.randint(1, 100)}",
            "permission_level": random.choice(["read", "write", "admin"]),
            "is_denied": random.random() > 0.8,
            "inherit_to_children": True,
            "propagate_to_parents": False
        }
        
        with self.client.post(
            f"/api/v1/roles/{role_id}/permission-rules",
            headers=headers,
            json=rule_data,
            catch_response=True,
            name="保存权限规则"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    response.success()
                else:
                    response.failure(f"业务失败: {data.get('message')}")
            else:
                response.failure(f"HTTP {response.status_code}")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """测试开始时的回调"""
    logger.info("=" * 70)
    logger.info("管理维度权限系统性能测试开始")
    logger.info("=" * 70)
    logger.info(f"目标主机: {environment.host}")
    logger.info(f"用户数: {environment.runner.target_user_count if hasattr(environment.runner, 'target_user_count') else 'N/A'}")
    logger.info("=" * 70)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """测试结束时的回调"""
    logger.info("=" * 70)
    logger.info("管理维度权限系统性能测试结束")
    logger.info("=" * 70)
    
    if isinstance(environment.runner, MasterRunner):
        stats = environment.runner.stats
        
        logger.info("\n性能统计:")
        logger.info(f"  总请求数: {stats.total.num_requests}")
        logger.info(f"  总失败数: {stats.total.num_failures}")
        logger.info(f"  失败率: {stats.total.fail_ratio * 100:.2f}%")
        logger.info(f"  平均响应时间: {stats.total.avg_response_time:.2f}ms")
        logger.info(f"  中位数响应时间: {stats.total.median_response_time:.2f}ms")
        logger.info(f"  95% 响应时间: {stats.total.get_response_time_percentile(0.95):.2f}ms")
        logger.info(f"  99% 响应时间: {stats.total.get_response_time_percentile(0.99):.2f}ms")
        logger.info(f"  RPS: {stats.total.total_rps:.2f}")
        
        logger.info("\n性能评估:")
        if stats.total.avg_response_time < 200:
            logger.info("  [OK] 平均响应时间达标 (< 200ms)")
        else:
            logger.warning(f"  [WARNING] 平均响应时间超标: {stats.total.avg_response_time:.2f}ms")
        
        if stats.total.get_response_time_percentile(0.95) < 500:
            logger.info("  [OK] 95% 响应时间达标 (< 500ms)")
        else:
            logger.warning(f"  [WARNING] 95% 响应时间超标: {stats.total.get_response_time_percentile(0.95):.2f}ms")
        
        if stats.total.fail_ratio < 0.01:
            logger.info("  [OK] 错误率达标 (< 1%)")
        else:
            logger.warning(f"  [WARNING] 错误率超标: {stats.total.fail_ratio * 100:.2f}%")
        
        logger.info("=" * 70)


class QuickTestUser(HttpUser):
    """
    快速测试用户（用于快速验证）
    
    仅执行最核心的功能，用于快速验证系统可用性。
    """
    
    wait_time = between(0.5, 1)
    
    def on_start(self):
        """初始化"""
        self.token = None
        self.login()
    
    def login(self):
        """登录"""
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
            name="快速登录"
        )
        
        if response.status_code == 200:
            data = response.json()
            self.token = data.get('data', {}).get('token')
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    @task(1)
    def quick_test(self):
        """快速测试核心功能"""
        headers = self._get_headers()
        
        self.client.get(
            "/api/v1/management-dimensions",
            headers=headers,
            name="快速测试-获取维度"
        )
        
        self.client.get(
            "/api/v1/meta/cache-stats",
            headers=headers,
            name="快速测试-缓存统计"
        )


if __name__ == '__main__':
    import os
    # v3.18 P1: host 由 env var 控制 (默认 3010)
    perf_host = os.environ.get('TEST_API_URL', os.environ.get('TEST_PERF_HOST', 'http://localhost:3010'))
    os.system(f"locust -f meta/tests/performance/locustfile.py --host={perf_host}")
