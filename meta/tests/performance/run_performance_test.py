# -*- coding: utf-8 -*-
"""
性能测试执行脚本

自动化执行性能测试并生成报告。

使用方式：
    python meta/tests/performance/run_performance_test.py
    
    或指定参数：
    python meta/tests/performance/run_performance_test.py \
        --host http://localhost:5000 \
        --users 50 \
        --spawn-rate 10 \
        --run-time 5m
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PerformanceTestRunner:
    """性能测试执行器"""
    
    def __init__(
        self,
        host: str = None,  # v3.18 P1: env var override (TEST_API_URL 或 TEST_PERF_HOST)
        users: int = 50,
        spawn_rate: int = 10,
        run_time: str = "5m",
        locust_file: str = None
    ):
        """
        初始化性能测试执行器
        
        Args:
            host: 目标主机地址
            users: 并发用户数
            spawn_rate: 用户生成速率（用户/秒）
            run_time: 运行时间（如 5m, 1h）
            locust_file: Locust 文件路径
        """
        # v3.18 P1: host=None 时用 env var 覆盖 (TEST_API_URL 或 TEST_PERF_HOST)
        self.host = host or os.environ.get('TEST_API_URL', os.environ.get('TEST_PERF_HOST', 'http://localhost:3010'))
        self.users = users
        self.spawn_rate = spawn_rate
        self.run_time = run_time
        self.locust_file = locust_file or self._get_default_locust_file()
        
        self.start_time = None
        self.end_time = None
        self.results = {}
    
    def _get_default_locust_file(self) -> str:
        """获取默认的 Locust 文件路径"""
        return os.path.join(
            os.path.dirname(__file__),
            "locustfile.py"
        )
    
    def run_pre_test_checks(self) -> bool:
        """
        运行测试前检查
        
        Returns:
            检查是否通过
        """
        logger.info("[SEARCH] 运行测试前检查...")
        
        if not os.path.exists(self.locust_file):
            logger.error(f"[X] Locust 文件不存在: {self.locust_file}")
            return False
        
        try:
            result = subprocess.run(
                ["locust", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info(f"[OK] Locust 版本: {result.stdout.strip()}")
            else:
                logger.error("[X] Locust 未安装或不可用")
                return False
        except Exception as e:
            logger.error(f"[X] 检查 Locust 失败: {e}")
            return False
        
        try:
            import requests
            response = requests.get(f"{self.host}/api/v1/meta/cache-stats", timeout=5)
            if response.status_code == 200:
                logger.info(f"[OK] 目标主机可访问: {self.host}")
            else:
                logger.warning(f"[WARNING] 目标主机响应异常: HTTP {response.status_code}")
        except Exception as e:
            logger.warning(f"[WARNING] 无法访问目标主机: {e}")
        
        return True
    
    def run_test(self) -> bool:
        """
        执行性能测试
        
        Returns:
            测试是否成功
        """
        logger.info("=" * 70)
        logger.info("开始执行性能测试")
        logger.info("=" * 70)
        logger.info(f"目标主机: {self.host}")
        logger.info(f"并发用户: {self.users}")
        logger.info(f"生成速率: {self.spawn_rate} 用户/秒")
        logger.info(f"运行时间: {self.run_time}")
        logger.info(f"Locust 文件: {self.locust_file}")
        logger.info("=" * 70)
        
        self.start_time = datetime.now()
        
        cmd = [
            "locust",
            "-f", self.locust_file,
            "--host", self.host,
            "--users", str(self.users),
            "--spawn-rate", str(self.spawn_rate),
            "--run-time", self.run_time,
            "--headless",
            "--only-summary",
            "--html", self._get_report_path("html"),
            "--json", self._get_report_path("json"),
        ]
        
        logger.info(f"\n执行命令: {' '.join(cmd)}\n")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600
            )
            
            self.end_time = datetime.now()
            
            if result.returncode == 0:
                logger.info("[OK] 性能测试执行成功")
                self._parse_locust_output(result.stdout)
                return True
            else:
                logger.error(f"[X] 性能测试执行失败: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("[X] 性能测试超时")
            self.end_time = datetime.now()
            return False
        except Exception as e:
            logger.error(f"[X] 执行性能测试异常: {e}")
            self.end_time = datetime.now()
            return False
    
    def _parse_locust_output(self, output: str):
        """解析 Locust 输出"""
        lines = output.split('\n')
        
        for line in lines:
            if 'Total' in line or 'Aggregated' in line:
                logger.info(line)
    
    def _get_report_path(self, format: str) -> str:
        """
        获取报告文件路径
        
        Args:
            format: 报告格式 (html, json)
            
        Returns:
            报告文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_dir = os.path.join(
            os.path.dirname(__file__),
            "reports"
        )
        
        os.makedirs(report_dir, exist_ok=True)
        
        return os.path.join(
            report_dir,
            f"performance_report_{timestamp}.{format}"
        )
    
    def generate_summary_report(self) -> Dict[str, Any]:
        """
        生成测试摘要报告
        
        Returns:
            测试摘要
        """
        duration = None
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
        
        summary = {
            'test_info': {
                'host': self.host,
                'users': self.users,
                'spawn_rate': self.spawn_rate,
                'run_time': self.run_time,
                'start_time': self.start_time.isoformat() if self.start_time else None,
                'end_time': self.end_time.isoformat() if self.end_time else None,
                'duration_seconds': duration,
            },
            'performance_targets': {
                'concurrent_users': 50,
                'avg_response_time_ms': 200,
                'p95_response_time_ms': 500,
                'error_rate_percent': 1.0,
            },
            'results': self.results,
        }
        
        report_path = self._get_report_path("summary.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        logger.info(f"[SYMBOL] 摘要报告已生成: {report_path}")
        
        return summary
    
    def print_summary(self):
        """打印测试摘要"""
        logger.info("\n" + "=" * 70)
        logger.info("性能测试摘要")
        logger.info("=" * 70)
        
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
            logger.info(f"测试时长: {duration:.2f} 秒")
        
        logger.info(f"并发用户: {self.users}")
        logger.info(f"目标主机: {self.host}")
        
        logger.info("\n性能目标:")
        logger.info("  - 并发用户: 50")
        logger.info("  - 平均响应时间: < 200ms")
        logger.info("  - 95% 响应时间: < 500ms")
        logger.info("  - 错误率: < 1%")
        
        logger.info("\n报告文件:")
        logger.info(f"  - HTML: {self._get_report_path('html')}")
        logger.info(f"  - JSON: {self._get_report_path('json')}")
        logger.info(f"  - 摘要: {self._get_report_path('summary.json')}")
        
        logger.info("=" * 70)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='管理维度权限系统性能测试')
    parser.add_argument('--host', type=str, default='http://localhost:5000',
                        help='目标主机地址')
    parser.add_argument('--users', type=int, default=50,
                        help='并发用户数')
    parser.add_argument('--spawn-rate', type=int, default=10,
                        help='用户生成速率')
    parser.add_argument('--run-time', type=str, default='5m',
                        help='运行时间（如 5m, 1h）')
    parser.add_argument('--verbose', action='store_true',
                        help='详细日志')
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    runner = PerformanceTestRunner(
        host=args.host,
        users=args.users,
        spawn_rate=args.spawn_rate,
        run_time=args.run_time
    )
    
    if not runner.run_pre_test_checks():
        logger.error("[X] 测试前检查失败，请检查环境配置")
        sys.exit(1)
    
    success = runner.run_test()
    
    runner.generate_summary_report()
    runner.print_summary()
    
    if success:
        logger.info("\n[OK] 性能测试完成")
        sys.exit(0)
    else:
        logger.error("\n[X] 性能测试失败")
        sys.exit(1)


if __name__ == '__main__':
    main()
