# -*- coding: utf-8 -*-
"""
性能测试框架

提供完整的性能测试能力：
- 数据库查询性能基准测试
- 索引效果对比测试
- API 端点性能测试
- 大数据量场景测试
- 并发压力测试
- 性能报告生成

使用方式：
    # 运行所有性能测试
    pytest meta/tests/performance/ -v -m performance
    
    # 运行特定类型的性能测试
    pytest meta/tests/performance/ -v -m "performance and db"
    pytest meta/tests/performance/ -v -m "performance and api"
    pytest meta/tests/performance/ -v -m "performance and stress"
    
    # 生成性能报告
    python -m meta.tests.performance.performance_reporter
"""

from meta.tests.performance.performance_base import (
    PerformanceTimer,
    PerformanceBenchmark,
    PerformanceReport,
    performance_context,
)

__all__ = [
    'PerformanceTimer',
    'PerformanceBenchmark', 
    'PerformanceReport',
    'performance_context',
]
