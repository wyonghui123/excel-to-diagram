# -*- coding: utf-8 -*-
"""
性能测试基础设施

提供性能测试的核心工具类：
- PerformanceTimer: 高精度计时器
- PerformanceBenchmark: 基准测试框架
- PerformanceReport: 性能报告生成
- performance_context: 上下文管理器
"""

import time
import statistics
import json
import os
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from contextlib import contextmanager
from functools import wraps


@dataclass
class PerformanceMetric:
    """性能指标"""
    name: str
    value: float
    unit: str
    iterations: int = 1
    min_value: float = 0.0
    max_value: float = 0.0
    std_dev: float = 0.0
    percentile_95: float = 0.0
    percentile_99: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class PerformanceTimer:
    """高精度性能计时器
    
    支持多次迭代、统计分析、百分位数计算。
    
    使用示例：
    ```python
    timer = PerformanceTimer("query_test")
    
    for _ in range(100):
        timer.start()
        # 执行被测代码
        timer.stop()
    
    metric = timer.get_metric()
    print(f"平均耗时: {metric.value:.2f}ms")
    print(f"P95: {metric.percentile_95:.2f}ms")
    ```
    """
    
    def __init__(self, name: str, unit: str = "ms"):
        self.name = name
        self.unit = unit
        self._start_time: Optional[float] = None
        self._measurements: List[float] = []
        self._metadata: Dict[str, Any] = {}
    
    def start(self):
        """开始计时"""
        self._start_time = time.perf_counter()
    
    def stop(self) -> float:
        """停止计时并记录测量值"""
        if self._start_time is None:
            raise RuntimeError("Timer not started")
        
        elapsed = time.perf_counter() - self._start_time
        self._measurements.append(elapsed)
        self._start_time = None
        return elapsed
    
    def reset(self):
        """重置计时器"""
        self._start_time = None
        self._measurements.clear()
        self._metadata.clear()
    
    def set_metadata(self, key: str, value: Any):
        """设置元数据"""
        self._metadata[key] = value
    
    def get_measurements(self) -> List[float]:
        """获取所有测量值（秒）"""
        return self._measurements.copy()
    
    def get_measurements_ms(self) -> List[float]:
        """获取所有测量值（毫秒）"""
        return [m * 1000 for m in self._measurements]
    
    def get_metric(self) -> PerformanceMetric:
        """生成性能指标"""
        if not self._measurements:
            return PerformanceMetric(
                name=self.name,
                value=0,
                unit=self.unit,
            )
        
        measurements_ms = self.get_measurements_ms()
        
        return PerformanceMetric(
            name=self.name,
            value=statistics.mean(measurements_ms),
            unit=self.unit,
            iterations=len(measurements_ms),
            min_value=min(measurements_ms),
            max_value=max(measurements_ms),
            std_dev=statistics.stdev(measurements_ms) if len(measurements_ms) > 1 else 0,
            percentile_95=self._percentile(measurements_ms, 95),
            percentile_99=self._percentile(measurements_ms, 99),
            metadata=self._metadata.copy(),
        )
    
    @staticmethod
    def _percentile(data: List[float], percentile: int) -> float:
        """计算百分位数"""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = (len(sorted_data) - 1) * percentile / 100
        lower = int(index)
        upper = lower + 1
        if upper >= len(sorted_data):
            return sorted_data[-1]
        weight = index - lower
        return sorted_data[lower] * (1 - weight) + sorted_data[upper] * weight


@contextmanager
def performance_context(name: str, metadata: Dict[str, Any] = None):
    """性能测量上下文管理器
    
    使用示例：
    ```python
    with performance_context("database_query") as timer:
        # 执行被测代码
        execute_query()
    
    metric = timer.get_metric()
    ```
    """
    timer = PerformanceTimer(name)
    if metadata:
        for k, v in metadata.items():
            timer.set_metadata(k, v)
    
    timer.start()
    try:
        yield timer
    finally:
        timer.stop()


class PerformanceBenchmark:
    """性能基准测试框架
    
    支持基准对比、回归检测、多场景测试。
    
    使用示例：
    ```python
    benchmark = PerformanceBenchmark("api_performance")
    
    benchmark.add_scenario("list_100_items", lambda: list_items(100))
    benchmark.add_scenario("list_1000_items", lambda: list_items(1000))
    
    results = benchmark.run(iterations=10)
    benchmark.save_baseline(results)
    
    # 检测回归
    regression = benchmark.check_regression(results)
    ```
    """
    
    def __init__(self, name: str, baseline_dir: str = None):
        self.name = name
        self.scenarios: Dict[str, Callable] = {}
        self.baseline_dir = baseline_dir or os.path.join(
            os.path.dirname(__file__), "baselines"
        )
    
    def add_scenario(self, name: str, func: Callable, warmup: int = 3):
        """添加测试场景
        
        Args:
            name: 场景名称
            func: 测试函数
            warmup: 预热次数（不计入统计）
        """
        self.scenarios[name] = {"func": func, "warmup": warmup}
    
    def run(self, iterations: int = 10, warmup_all: bool = True) -> Dict[str, PerformanceMetric]:
        """运行所有场景
        
        Args:
            iterations: 每个场景的迭代次数
            warmup_all: 是否在测量前预热
            
        Returns:
            场景名称 -> 性能指标
        """
        results = {}
        
        for name, config in self.scenarios.items():
            func = config["func"]
            warmup = config["warmup"]
            
            if warmup_all and warmup > 0:
                for _ in range(warmup):
                    try:
                        func()
                    except Exception:
                        pass
            
            timer = PerformanceTimer(name)
            
            for _ in range(iterations):
                timer.start()
                try:
                    func()
                    timer.stop()
                except Exception as e:
                    timer.set_metadata("error", str(e))
                    timer.stop()
            
            results[name] = timer.get_metric()
        
        return results
    
    def save_baseline(self, results: Dict[str, PerformanceMetric], filename: str = None):
        """保存基准结果"""
        if not os.path.exists(self.baseline_dir):
            os.makedirs(self.baseline_dir)
        
        if filename is None:
            filename = "{0}_baseline.json".format(self.name)
        
        filepath = os.path.join(self.baseline_dir, filename)
        
        baseline = {
            "name": self.name,
            "timestamp": datetime.now().isoformat(),
            "scenarios": {
                name: {
                    "value": metric.value,
                    "unit": metric.unit,
                    "iterations": metric.iterations,
                    "min_value": metric.min_value,
                    "max_value": metric.max_value,
                    "std_dev": metric.std_dev,
                    "percentile_95": metric.percentile_95,
                    "percentile_99": metric.percentile_99,
                }
                for name, metric in results.items()
            }
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(baseline, f, indent=2, ensure_ascii=False)
    
    def load_baseline(self, filename: str = None) -> Optional[Dict[str, Any]]:
        """加载基准结果"""
        if filename is None:
            filename = "{0}_baseline.json".format(self.name)
        
        filepath = os.path.join(self.baseline_dir, filename)
        
        if not os.path.exists(filepath):
            return None
        
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def check_regression(
        self,
        results: Dict[str, PerformanceMetric],
        threshold: float = 0.2,
        filename: str = None
    ) -> Dict[str, Any]:
        """检测性能回归
        
        Args:
            results: 当前测试结果
            threshold: 回归阈值（百分比，如 0.2 表示 20%）
            filename: 基准文件名
            
        Returns:
            回归报告
        """
        baseline = self.load_baseline(filename)
        if baseline is None:
            return {"status": "no_baseline", "message": "未找到基准数据"}
        
        regressions = []
        improvements = []
        
        for name, metric in results.items():
            if name not in baseline["scenarios"]:
                continue
            
            baseline_value = baseline["scenarios"][name]["value"]
            current_value = metric.value
            
            if baseline_value == 0:
                continue
            
            change = (current_value - baseline_value) / baseline_value
            
            if change > threshold:
                regressions.append({
                    "scenario": name,
                    "baseline": baseline_value,
                    "current": current_value,
                    "change_percent": change * 100,
                })
            elif change < -threshold:
                improvements.append({
                    "scenario": name,
                    "baseline": baseline_value,
                    "current": current_value,
                    "change_percent": abs(change) * 100,
                })
        
        return {
            "status": "regression" if regressions else "ok",
            "threshold_percent": threshold * 100,
            "regressions": regressions,
            "improvements": improvements,
            "baseline_timestamp": baseline.get("timestamp"),
        }


@dataclass
class PerformanceReport:
    """性能测试报告"""
    name: str
    timestamp: str
    metrics: List[PerformanceMetric]
    summary: Dict[str, Any] = field(default_factory=dict)
    comparisons: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "metrics": [
                {
                    "name": m.name,
                    "value": m.value,
                    "unit": m.unit,
                    "iterations": m.iterations,
                    "min": m.min_value,
                    "max": m.max_value,
                    "std_dev": m.std_dev,
                    "p95": m.percentile_95,
                    "p99": m.percentile_99,
                    "metadata": m.metadata,
                }
                for m in self.metrics
            ],
            "comparisons": self.comparisons,
        }
    
    def save(self, filepath: str):
        """保存报告到文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, filepath: str) -> 'PerformanceReport':
        """从文件加载报告"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        metrics = [
            PerformanceMetric(
                name=m["name"],
                value=m["value"],
                unit=m["unit"],
                iterations=m.get("iterations", 1),
                min_value=m.get("min", 0),
                max_value=m.get("max", 0),
                std_dev=m.get("std_dev", 0),
                percentile_95=m.get("p95", 0),
                percentile_99=m.get("p99", 0),
                metadata=m.get("metadata", {}),
            )
            for m in data.get("metrics", [])
        ]
        
        return cls(
            name=data["name"],
            timestamp=data["timestamp"],
            metrics=metrics,
            summary=data.get("summary", {}),
            comparisons=data.get("comparisons", []),
        )
    
    def generate_markdown(self) -> str:
        """生成 Markdown 格式报告"""
        lines = [
            "# {0}".format(self.name),
            "",
            "**测试时间**: {0}".format(self.timestamp),
            "",
        ]
        
        if self.summary:
            lines.append("## 摘要")
            lines.append("")
            for k, v in self.summary.items():
                lines.append("- **{0}**: {1}".format(k, v))
            lines.append("")
        
        lines.append("## 性能指标")
        lines.append("")
        lines.append("| 场景 | 平均值 | 最小值 | 最大值 | P95 | P99 | 标准差 |")
        lines.append("|------|--------|--------|--------|-----|-----|--------|")
        
        for m in self.metrics:
            lines.append(
                "| {0} | {1:.2f}{2} | {3:.2f}{2} | {4:.2f}{2} | {5:.2f}{2} | {6:.2f}{2} | {7:.2f} |".format(
                    m.name, m.value, m.unit, m.min_value, m.max_value,
                    m.percentile_95, m.percentile_99, m.std_dev
                )
            )
        
        if self.comparisons:
            lines.append("")
            lines.append("## 对比分析")
            lines.append("")
            lines.append("| 场景 | 基准值 | 当前值 | 变化 | 状态 |")
            lines.append("|------|--------|--------|------|------|")
            
            for c in self.comparisons:
                status = "[CRITICAL] 回归" if c.get("regression") else "[LOW] 正常"
                lines.append(
                    "| {0} | {1:.2f} | {2:.2f} | {3:+.1f}% | {4} |".format(
                        c["scenario"], c["baseline"], c["current"],
                        c.get("change_percent", 0), status
                    )
                )
        
        return "\n".join(lines)
