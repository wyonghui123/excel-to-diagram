import pytest

pytestmark = pytest.mark.integration

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 4 Task 17: 性能测试与优化工具

功能：
1. 压力测试（Load Testing）- 模拟高并发场景
2. 缓存命中率监控（Cache Hit Rate Monitoring）
3. 性能基准对比（Performance Benchmarking）
4. 内存使用分析（Memory Usage Analysis）

运行方式：
    python meta/tests/test_performance.py [--mode load|cache|benchmark|all]

依赖：
    - requests (HTTP 客户端)
    - time, threading, concurrent.futures (并发)
    - psutil (内存监控，可选)

作者：AI Assistant
日期：2026-01-09
"""

import sys
import os
import time
import json
import uuid
import statistics
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import argparse

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 尝试导入可选依赖
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


# ============================================================================
# 配置常量
# ============================================================================

# v3.18 P1: 修复端口硬编码 (8000 → 3010 + env var)
BACKEND_URL = os.environ.get('TEST_API_URL', 'http://localhost:3010')
API_BASE_URL = f"{BACKEND_URL}/api/v1"  # v3.18 P1: 路径拼接到 BACKEND_URL
TEST_TIMEOUT = 30  # 秒

# 测试配置
LOAD_TEST_CONFIG = {
    "concurrent_users": [10, 50, 100],  # 并发用户数
    "requests_per_user": 20,             # 每用户请求数
    "ramp_up_time": 5,                   # 启动时间（秒）
    "enum_types_to_test": [
        "annotation_category",
        "relation_type",
        "priority_level"
    ]
}

CACHE_CONFIG = {
    "max_cache_size": 100,
    "cache_timeout_ms": 300000,  # 5分钟
    "test_duration_seconds": 60,
    "monitor_interval_ms": 1000
}

BENCHMARK_CONFIG = {
    "iterations": 1000,
    "warmup_iterations": 100,
    "endpoints": {
        "high_speed": "/enums/{type}/options",
        "standard": "/enum-types/{id}/values"
    }
}


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class PerformanceMetric:
    """性能指标数据类"""
    timestamp: float
    endpoint: str
    response_time_ms: float
    status_code: int
    cache_hit: Optional[bool] = None
    error: Optional[str] = None


@dataclass
class CacheStatistics:
    """缓存统计信息"""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    hit_rate: float = 0.0
    avg_response_time_ms: float = 0.0
    p50_response_time: float = 0.0
    p95_response_time: float = 0.0
    p99_response_time: float = 0.0
    memory_usage_mb: float = 0.0
    eviction_count: int = 0


@dataclass
class LoadTestResult:
    """压力测试结果"""
    concurrent_users: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time_ms: float
    min_response_time_ms: float
    max_response_time_ms: float
    p50_response_time: float
    p95_response_time: float
    p99_response_time: float
    throughput_per_second: float
    error_rate: float
    metrics: List[PerformanceMetric] = field(default_factory=list)


# ============================================================================
# 颜色输出工具
# ============================================================================

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(title: str):
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'=' * 70}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{title:^70}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'=' * 70}{Colors.RESET}")


def print_success(message: str):
    print(f"{Colors.GREEN}[OK]{Colors.RESET} {message}")


def print_error(message: str):
    print(f"{Colors.RED}[X]{Colors.RESET} {message}")


def print_warning(message: str):
    print(f"{Colors.YELLOW}[WARNING]{Colors.RESET}  {message}")


def print_info(message: str):
    print(f"{Colors.BLUE}ℹ{Colors.RESET}  {message}")


# ============================================================================
# API 客户端
# ============================================================================

class APIClient:
    """API 客户端封装"""

    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.session = None

        if HAS_REQUESTS:
            self.session = requests.Session()
            self.session.headers.update({
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            })

    def get(self, endpoint: str, params: dict = None) -> Tuple[int, dict, float]:
        """
        发送 GET 请求

        Returns:
            tuple: (status_code, response_data, response_time_ms)
        """
        if not HAS_REQUESTS or not self.session:
            return 503, {"success": False, "message": "Service unavailable"}, 0

        url = f"{self.base_url}{endpoint}"
        start_time = time.time()

        try:
            response = self.session.get(url, params=params, timeout=TEST_TIMEOUT)
            response_time = (time.time() - start_time) * 1000

            try:
                data = response.json()
            except:
                data = {"success": False, "raw_response": response.text[:500]}

            return response.status_code, data, response_time

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return 503, {"success": False, "message": str(e)}, response_time

    def close(self):
        if self.session:
            self.session.close()


# ============================================================================
# 1. 压力测试模块
# ============================================================================

class LoadTester:
    """压力测试器"""

    def __init__(self):
        self.client = APIClient()
        self.results: List[LoadTestResult] = []

    def run_single_load_test(
        self,
        concurrent_users: int,
        requests_per_user: int,
        enum_types: List[str]
    ) -> LoadTestResult:
        """
        运行单次压力测试

        Args:
            concurrent_users: 并发用户数
            requests_per_user: 每用户请求数
            enum_types: 要测试的枚举类型列表

        Returns:
            LoadTestResult: 测试结果
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        print_info(f"Starting load test with {concurrent_users} concurrent users...")
        print_info(f"Requests per user: {requests_per_user}")
        print_info(f"Enum types to test: {len(enum_types)}")

        metrics = []
        lock = threading.Lock()
        start_time = time.time()

        def user_worker(user_id: int) -> List[PerformanceMetric]:
            """单个用户的工作函数"""
            user_metrics = []

            for i in range(requests_per_user):
                # 轮询选择枚举类型
                enum_type = enum_types[(user_id + i) % len(enum_types)]

                # 使用高速端点
                status_code, data, response_time = self.client.get(
                    f"/enums/{enum_type}/options",
                    params={"is_active": "true"}
                )

                metric = PerformanceMetric(
                    timestamp=time.time(),
                    endpoint=f"/enums/{enum_type}/options",
                    response_time_ms=response_time,
                    status_code=status_code,
                    cache_hit=None  # 无法从外部确定
                )

                if status_code != 200:
                    metric.error = f"HTTP {status_code}"

                user_metrics.append(metric)

            return user_metrics

        # 使用线程池模拟并发用户
        with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = {
                executor.submit(user_worker, user_id): user_id
                for user_id in range(concurrent_users)
            }

            for future in as_completed(futures):
                user_id = futures[future]
                try:
                    user_metrics = future.result()
                    with lock:
                        metrics.extend(user_metrics)
                except Exception as e:
                    print_error(f"User {user_id} failed: {e}")

        end_time = time.time()
        total_time = end_time - start_time

        # 计算统计结果
        successful = [m for m in metrics if m.status_code == 200]
        failed = [m for m in metrics if m.status_code != 200]

        response_times = [m.response_time_ms for m in successful]

        result = LoadTestResult(
            concurrent_users=concurrent_users,
            total_requests=len(metrics),
            successful_requests=len(successful),
            failed_requests=len(failed),
            avg_response_time_ms=statistics.mean(response_times) if response_times else 0,
            min_response_time_ms=min(response_times) if response_times else 0,
            max_response_time_ms=max(response_times) if response_times else 0,
            p50_response_time=self._percentile(response_times, 50),
            p95_response_time=self._percentile(response_times, 95),
            p99_response_time=self._percentile(response_times, 99),
            throughput_per_second=len(metrics) / total_time if total_time > 0 else 0,
            error_rate=len(failed) / len(metrics) if metrics else 0,
            metrics=metrics
        )

        return result

    def _percentile(self, data: List[float], percentile: float) -> float:
        """计算百分位数"""
        if not data:
            return 0.0

        sorted_data = sorted(data)
        index = (len(sorted_data) - 1) * (percentile / 100)
        lower = int(index)
        upper = lower + 1

        if upper >= len(sorted_data):
            return sorted_data[-1]

        weight = index - lower
        return sorted_data[lower] * (1 - weight) + sorted_data[upper] * weight

    def run_all_load_tests(self) -> List[LoadTestResult]:
        """运行所有配置的压力测试"""
        results = []

        for num_users in LOAD_TEST_CONFIG["concurrent_users"]:
            print_header(f"Load Test: {num_users} Concurrent Users")

            result = self.run_single_load_test(
                concurrent_users=num_users,
                requests_per_user=LOAD_TEST_CONFIG["requests_per_user"],
                enum_types=LOAD_TEST_CONFIG["enum_types_to_test"]
            )

            results.append(result)
            self._print_load_test_result(result)

        return results

    def _print_load_test_result(self, result: LoadTestResult):
        """打印压力测试结果"""
        print(f"\n{Colors.BOLD}Results:{Colors.RESET}")
        print(f"  Total Requests:     {result.total_requests:,}")
        print(f"  Successful:         {result.successful_requests:,} ({Colors.GREEN}{(result.successful_requests/result.total_requests*100):.1f}%{Colors.RESET})")
        print(f"  Failed:             {result.failed_requests:,} ({Colors.RED}{(result.error_rate*100):.2f}%{Colors.RESET})")
        print(f"\n{Colors.BOLD}Response Times (ms):{Colors.RESET}")
        print(f"  Average:            {result.avg_response_time_ms:.2f}")
        print(f"  Min:                {result.min_response_time_ms:.2f}")
        print(f"  Max:                {result.max_response_time_ms:.2f}")
        print(f"  P50 (Median):       {result.p50_response_time:.2f}")
        print(f"  P95:                {result.p95_response_time_ms:.2f}")
        print(f"  P99:                {result.p99_response_time_ms:.2f}")
        print(f"\n{Colors.BOLD}Throughput:{Colors.RESET}")
        print(f"  Requests/second:    {result.throughput_per_second:.2f}")

        # 性能评估
        if result.p95_response_time < 100:
            print_success("Performance: EXCELLENT [DECORATIVE]")
        elif result.p95_response_time < 300:
            print_success("Performance: GOOD [OK]")
        elif result.p95_response_time < 500:
            print_warning("Performance: ACCEPTABLE [WARNING]")
        else:
            print_error("Performance: POOR [X]")


# ============================================================================
# 2. 缓存命中率监控模块
# ============================================================================

class CacheMonitor:
    """缓存命中率监控器"""

    def __init__(self):
        self.client = APIClient()
        self.metrics_history: List[PerformanceMetric] = []

    def monitor_cache_performance(
        self,
        duration_seconds: int = CACHE_CONFIG["test_duration_seconds"],
        interval_ms: int = CACHE_CONFIG["monitor_interval_ms"]
    ) -> CacheStatistics:
        """
        监控缓存性能

        Args:
            duration_seconds: 监控时长（秒）
            interval_ms: 采样间隔（毫秒）

        Returns:
            CacheStatistics: 缓存统计信息
        """
        print_header("Cache Hit Rate Monitor")

        print_info(f"Monitoring duration: {duration_seconds}s")
        print_info(f"Sampling interval: {interval_ms}ms")

        metrics = []
        start_time = time.time()
        end_time = start_time + duration_seconds
        request_count = 0

        enum_types = LOAD_TEST_CONFIG["enum_types_to_test"]

        while time.time() < end_time:
            for enum_type in enum_types:
                request_count += 1

                status_code, data, response_time = self.client.get(
                    f"/enums/{enum_type}/options",
                    params={"is_active": "true"}
                )

                metric = PerformanceMetric(
                    timestamp=time.time(),
                    endpoint=f"/enums/{enum_type}/options",
                    response_time_ms=response_time,
                    status_code=status_code
                )
                metrics.append(metric)

            # 等待采样间隔
            time.sleep(interval_ms / 1000)

        # 计算统计信息
        stats = self._calculate_cache_statistics(metrics, request_count)

        self._print_cache_statistics(stats)

        return stats

    def _calculate_cache_statistics(
        self,
        metrics: List[PerformanceMetric],
        total_requests: int
    ) -> CacheStatistics:
        """计算缓存统计信息"""
        successful = [m for m in metrics if m.status_code == 200]
        response_times = [m.response_time_ms for m in successful]

        # 基于响应时间估算缓存命中率
        # 假设缓存命中的响应时间 < 10ms
        estimated_hits = sum(1 for rt in response_times if rt < 10)
        estimated_misses = len(response_times) - estimated_hits

        stats = CacheStatistics(
            total_requests=total_requests,
            cache_hits=estimated_hits,
            cache_misses=estimated_misses,
            hit_rate=(estimated_hits / len(response_times) * 100) if response_times else 0,
            avg_response_time_ms=statistics.mean(response_times) if response_times else 0,
            p50_response_time=self._percentile(response_times, 50),
            p95_response_time=self._percentile(response_times, 95),
            p99_response_time=self._percentile(response_times, 99),
            eviction_count=0  # 需要从服务端获取
        )

        # 内存使用情况
        if HAS_PSUTIL:
            process = psutil.Process(os.getpid())
            stats.memory_usage_mb = process.memory_info().rss / 1024 / 1024

        return stats

    def _percentile(self, data: List[float], percentile: float) -> float:
        """计算百分位数"""
        if not data:
            return 0.0

        sorted_data = sorted(data)
        index = (len(sorted_data) - 1) * (percentile / 100)
        lower = int(index)
        upper = lower + 1

        if upper >= len(sorted_data):
            return sorted_data[-1]

        weight = index - lower
        return sorted_data[lower] * (1 - weight) + sorted_data[upper] * weight

    def _print_cache_statistics(self, stats: CacheStatistics):
        """打印缓存统计信息"""
        print(f"\n{Colors.BOLD}Cache Performance Summary:{Colors.RESET}")
        print(f"  Total Requests:     {stats.total_requests:,}")
        print(f"  Estimated Hits:     {stats.cache_hits:,} ({Colors.GREEN}{stats.hit_rate:.1f}%{Colors.RESET})")
        print(f"  Estimated Misses:   {stats.cache_misses:,} ({Colors.RED}{100-stats.hit_rate:.1f}%{Colors.RESET})")
        print(f"\n{Colors.BOLD}Response Time Distribution:{Colors.RESET}")
        print(f"  Average:            {stats.avg_response_time_ms:.2f}ms")
        print(f"  P50 (Median):       {stats.p50_response_time:.2f}ms")
        print(f"  P95:                {stats.p95_response_time:.2f}ms")
        print(f"  P99:                {stats.p99_response_time:.2f}ms")

        if stats.memory_usage_mb > 0:
            print(f"\n{Colors.BOLD}Memory Usage:{Colors.RESET}")
            print(f"  Process Memory:     {stats.memory_usage_mb:.2f} MB")

        # 缓存效率评估
        if stats.hit_rate >= 90:
            print_success("Cache Efficiency: EXCELLENT [DECORATIVE] (>90% hit rate)")
        elif stats.hit_rate >= 70:
            print_success("Cache Efficiency: GOOD [OK] (70-90% hit rate)")
        elif stats.hit_rate >= 50:
            print_warning("Cache Efficiency: ACCEPTABLE [WARNING] (50-70% hit rate)")
        else:
            print_error("Cache Efficiency: POOR [X] (<50% hit rate)")


# ============================================================================
# 3. 性能基准对比模块
# ============================================================================

class PerformanceBenchmark:
    """性能基准对比测试"""

    def __init__(self):
        self.client = APIClient()

    def run_benchmark_comparison(self) -> Dict[str, Any]:
        """
        运行高速端点 vs 标准端点的性能对比

        Returns:
            dict: 包含两个端点的性能数据
        """
        print_header("Performance Benchmark: High-Speed vs Standard Endpoint")

        config = BENCHMARK_CONFIG
        enum_type = LOAD_TEST_CONFIG["enum_types_to_test"][0]

        print_info(f"Benchmarking with {config['iterations']} iterations...")
        print_info(f"Warmup: {config['warmup_iterations']} iterations")
        print_info(f"Enum type: {enum_type}")

        # 预热
        print_info("\nWarming up...")
        for _ in range(config['warmup_iterations']):
            self.client.get(f"/enums/{enum_type}/options", params={"is_active": "true"})
            self.client.get("/enum-types/1/values", params={"is_active": "true"})

        # 测试高速端点
        print_info("\nBenchmarking HIGH-SPEED endpoint...")
        high_speed_metrics = self._benchmark_endpoint(
            f"/enums/{enum_type}/options",
            {"is_active": "true"},
            config['iterations']
        )

        # 测试标准端点
        print_info("Benchmarking STANDARD endpoint...")
        standard_metrics = self._benchmark_endpoint(
            "/enum-types/1/values",
            {"is_active": "true"},
            config['iterations']
        )

        # 打印对比结果
        comparison = self._print_benchmark_comparison(high_speed_metrics, standard_metrics)

        return comparison

    def _benchmark_endpoint(
        self,
        endpoint: str,
        params: dict,
        iterations: int
    ) -> Dict[str, float]:
        """对单个端点进行基准测试"""
        metrics = []
        errors = 0

        for _ in range(iterations):
            status_code, _, response_time = self.client.get(endpoint, params=params)

            if status_code == 200:
                metrics.append(response_time)
            else:
                errors += 1

        if not metrics:
            return {
                "avg": 0, "min": 0, "max": 0,
                "p50": 0, "p95": 0, "p99": 0,
                "errors": errors, "success_rate": 0
            }

        sorted_metrics = sorted(metrics)

        return {
            "avg": statistics.mean(metrics),
            "min": min(metrics),
            "max": max(metrics),
            "p50": self._percentile(sorted_metrics, 50),
            "p95": self._percentile(sorted_metrics, 95),
            "p99": self._percentile(sorted_metrics, 99),
            "errors": errors,
            "success_rate": (iterations - errors) / iterations * 100
        }

    def _percentile(self, sorted_data: List[float], percentile: float) -> float:
        """计算百分位数"""
        if not sorted_data:
            return 0.0

        index = (len(sorted_data) - 1) * (percentile / 100)
        lower = int(index)
        upper = lower + 1

        if upper >= len(sorted_data):
            return sorted_data[-1]

        weight = index - lower
        return sorted_data[lower] * (1 - weight) + sorted_data[upper] * weight

    def _print_benchmark_comparison(
        self,
        high_speed: Dict[str, float],
        standard: Dict[str, float]
    ) -> Dict[str, Any]:
        """打印基准测试对比结果"""
        print(f"\n{Colors.BOLD}{'Metric':<20} {'High-Speed':>15} {'Standard':>15} {'Improvement':>15}{Colors.RESET}")
        print("-" * 65)

        metrics_to_compare = [
            ("Average (ms)", "avg", "avg"),
            ("Min (ms)", "min", "min"),
            ("Max (ms)", "max", "max"),
            ("P50 (ms)", "p50", "p50"),
            ("P95 (ms)", "p95", "p95"),
            ("P99 (ms)", "p99", "p99"),
            ("Success Rate (%)", "success_rate", "success_rate"),
        ]

        for label, hs_key, std_key in metrics_to_compare:
            hs_val = high_speed[hs_key]
            std_val = standard[std_key]

            if std_val > 0 and hs_key != "success_rate":
                improvement = ((std_val - hs_val) / std_val) * 100
                improvement_str = f"{improvement:+.1f}%"
                color = Colors.GREEN if improvement > 0 else Colors.RED
            else:
                improvement_str = "-"
                color = Colors.RESET

            print(f"  {label:<18} {hs_val:>14.2f} {std_val:>14.2f} {color}{improvement_str:>14}{Colors.RESET}")

        print("-" * 65)

        # 计算总体提升
        if standard["avg"] > 0:
            overall_improvement = ((standard["avg"] - high_speed["avg"]) / standard["avg"]) * 100

            print(f"\n{Colors.BOLD}Overall Performance Improvement:{Colors.RESET}")
            if overall_improvement > 20:
                print_success(f"High-Speed endpoint is {overall_improvement:.1f}% FASTER! [DECORATIVE]")
            elif overall_improvement > 0:
                print_success(f"High-Speed endpoint is {overall_improvement:.1f}% faster [OK]")
            elif overall_improvement == 0:
                print_warning("No significant performance difference [WARNING]")
            else:
                print_error(f"High-Speed endpoint is {abs(overall_improvement):.1f}% slower [X]")

        return {
            "high_speed": high_speed,
            "standard": standard,
            "timestamp": datetime.now().isoformat()
        }


# ============================================================================
# 主程序入口
# ============================================================================

def main():
    """主程序入口"""
    parser = argparse.ArgumentParser(
        description="Phase 4 Performance Testing & Optimization Tool"
    )
    parser.add_argument(
        "--mode",
        choices=["load", "cache", "benchmark", "all"],
        default="all",
        help="Test mode to run (default: all)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path for JSON results"
    )

    args = parser.parse_args()

    print("=" * 70)
    print(f"{Colors.MAGENTA}{Colors.BOLD}Phase 4: Performance Testing & Optimization Tool{Colors.RESET}")
    print("=" * 70)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mode: {args.mode.upper()}")
    print("=" * 70)

    all_results = {}

    try:
        if args.mode in ["load", "all"]:
            # 1. 压力测试
            load_tester = LoadTester()
            load_results = load_tester.run_all_load_tests()
            all_results["load_tests"] = [
                {
                    "concurrent_users": r.concurrent_users,
                    "total_requests": r.total_requests,
                    "successful_requests": r.successful_requests,
                    "failed_requests": r.failed_requests,
                    "avg_response_time_ms": r.avg_response_time_ms,
                    "p95_response_time": r.p95_response_time,
                    "throughput_per_second": r.throughput_per_second,
                    "error_rate": r.error_rate
                }
                for r in load_results
            ]

            load_tester.client.close()

        if args.mode in ["cache", "all"]:
            # 2. 缓存命中率监控
            cache_monitor = CacheMonitor()
            cache_stats = cache_monitor.monitor_cache_performance(duration_seconds=10)
            all_results["cache_stats"] = {
                "total_requests": cache_stats.total_requests,
                "hit_rate": cache_stats.hit_rate,
                "avg_response_time_ms": cache_stats.avg_response_time_ms,
                "p95_response_time": cache_stats.p95_response_time,
                "memory_usage_mb": cache_stats.memory_usage_mb
            }

            cache_monitor.client.close()

        if args.mode in ["benchmark", "all"]:
            # 3. 性能基准对比
            benchmark = PerformanceBenchmark()
            benchmark_result = benchmark.run_benchmark_comparison()
            all_results["benchmark"] = benchmark_result

            benchmark.client.close()

        # 输出结果到文件
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(all_results, f, indent=2, ensure_ascii=False)
            print_success(f"\nResults saved to: {args.output}")

        print_header("Testing Completed")
        print_success("All performance tests completed successfully!")
        return True

    except KeyboardInterrupt:
        print_warning("\n\nTesting interrupted by user")
        return False
    except Exception as e:
        print_error(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
