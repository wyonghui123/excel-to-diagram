# -*- coding: utf-8 -*-
"""
PerformanceBenchmarkSuite — 权限系统性能基准测试套件

[P4.3 用途]
  灰度切换前的性能验收门禁, 测量:
  - EffectiveIntentChecker 单次/多角色 check 延迟
  - PermissionDerivationPipeline 单角色/批量推导性能
  - 性能基线保存/加载 + 回归检测
  - JSON + Markdown 性能报告

[复用]
  - meta.tests.performance.performance_base.PerformanceTimer (高精度计时器)
  - meta.tests.performance.performance_base.PerformanceMetric (指标数据结构)
  - meta.core.effective_intent_checker.EffectiveIntentChecker (求值引擎)
  - meta.core.derivation_pipeline.PermissionDerivationPipeline (推导管道)
  - meta.core.effective_intent_dao.EffectiveIntentDAO (事实表 CRUD)
"""
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from meta.core.derivation_pipeline import PermissionDerivationPipeline
from meta.core.effective_intent_checker import EffectiveIntentChecker
from meta.core.effective_intent_dao import EffectiveIntentDAO
from meta.tests.performance.performance_base import (
    PerformanceMetric,
    PerformanceTimer,
)


class PerformanceBenchmarkSuite:
    """权限系统性能基准测试套件

    用法:
        suite = PerformanceBenchmarkSuite(db_path='/path/to/db.sqlite')
        metric = suite.benchmark_check_single(
            role_id=1, bo_id='product', action_name='read',
            record_id=1, user_id=999, iterations=50,
        )
        print(f"P95: {metric.percentile_95:.2f}ms")

        suite.save_baseline('/path/to/baseline.json')
        regression = suite.check_regression('/path/to/baseline.json', threshold=0.2)
        suite.save_report('/path/to/report.json')
    """

    def __init__(self, db_path: str):
        """初始化性能测试套件

        Args:
            db_path: SQLite 数据库路径
        """
        self._db_path = db_path
        self._metrics: List[PerformanceMetric] = []
        self._scenario_names: List[str] = []

        # 惰性初始化的组件
        self._checker: Optional[EffectiveIntentChecker] = None
        self._pipeline: Optional[PermissionDerivationPipeline] = None
        self._dao: Optional[EffectiveIntentDAO] = None

    # ============================================================
    # 内部: 惰性初始化组件
    # ============================================================

    def _get_checker(self) -> EffectiveIntentChecker:
        if self._checker is None:
            self._checker = EffectiveIntentChecker(db_path=self._db_path)
        return self._checker

    def _get_dao(self) -> EffectiveIntentDAO:
        if self._dao is None:
            self._dao = EffectiveIntentDAO(self._db_path)
        return self._dao

    def _get_pipeline(self) -> PermissionDerivationPipeline:
        if self._pipeline is None:
            self._pipeline = PermissionDerivationPipeline(
                db_path=self._db_path,
                dao=self._get_dao(),
            )
        return self._pipeline

    def _record_metric(self, metric: PerformanceMetric) -> PerformanceMetric:
        """记录 metric 到内部列表 (供报告生成)"""
        self._metrics.append(metric)
        if metric.name not in self._scenario_names:
            self._scenario_names.append(metric.name)
        return metric

    # ============================================================
    # 公开 API: 性能基准测试
    # ============================================================

    def benchmark_check_single(
        self,
        role_id: int,
        bo_id: str,
        action_name: str,
        record_id: int,
        user_id: int,
        iterations: int = 50,
        warmup: int = 3,
    ) -> PerformanceMetric:
        """测量 EffectiveIntentChecker.check() 单次延迟

        Args:
            role_id: 角色 ID
            bo_id: 业务对象 ID
            action_name: 操作名称
            record_id: 记录 ID
            user_id: 用户 ID
            iterations: 测量次数
            warmup: 预热次数 (不计入统计)

        Returns:
            PerformanceMetric (name='check_single_<bo_id>_<action_name>')
        """
        checker = self._get_checker()
        scenario_name = f'check_single_{bo_id}_{action_name}'

        # 预热
        for _ in range(warmup):
            try:
                checker.check(role_id, bo_id, action_name, record_id, user_id)
            except Exception:
                pass

        timer = PerformanceTimer(scenario_name, unit='ms')
        timer.set_metadata('role_id', role_id)
        timer.set_metadata('bo_id', bo_id)
        timer.set_metadata('action_name', action_name)
        timer.set_metadata('record_id', record_id)
        timer.set_metadata('user_id', user_id)

        for _ in range(iterations):
            timer.start()
            try:
                checker.check(role_id, bo_id, action_name, record_id, user_id)
                timer.stop()
            except Exception as e:
                timer.set_metadata('error', str(e))
                timer.stop()

        metric = timer.get_metric()
        return self._record_metric(metric)

    def benchmark_check_multi_role(
        self,
        role_ids: List[int],
        bo_id: str,
        action_name: str,
        record_id: int,
        user_id: int,
        iterations: int = 30,
        warmup: int = 2,
    ) -> PerformanceMetric:
        """测量 EffectiveIntentChecker.check_multi_role() 多角色延迟

        Args:
            role_ids: 角色 ID 列表
            bo_id: 业务对象 ID
            action_name: 操作名称
            record_id: 记录 ID
            user_id: 用户 ID
            iterations: 测量次数
            warmup: 预热次数

        Returns:
            PerformanceMetric (name='check_multi_role_<n>roles_<bo_id>_<action_name>')
        """
        checker = self._get_checker()
        scenario_name = (
            f'check_multi_role_{len(role_ids)}roles_{bo_id}_{action_name}'
        )

        # 预热
        for _ in range(warmup):
            try:
                checker.check_multi_role(
                    role_ids, bo_id, action_name, record_id, user_id,
                )
            except Exception:
                pass

        timer = PerformanceTimer(scenario_name, unit='ms')
        timer.set_metadata('role_ids', role_ids)
        timer.set_metadata('bo_id', bo_id)
        timer.set_metadata('action_name', action_name)
        timer.set_metadata('record_id', record_id)
        timer.set_metadata('user_id', user_id)

        for _ in range(iterations):
            timer.start()
            try:
                checker.check_multi_role(
                    role_ids, bo_id, action_name, record_id, user_id,
                )
                timer.stop()
            except Exception as e:
                timer.set_metadata('error', str(e))
                timer.stop()

        metric = timer.get_metric()
        return self._record_metric(metric)

    def benchmark_derive_role(
        self,
        role_id: int,
        iterations: int = 10,
        warmup: int = 1,
    ) -> PerformanceMetric:
        """测量 PermissionDerivationPipeline.derive() 单角色延迟

        Args:
            role_id: 角色 ID
            iterations: 测量次数
            warmup: 预热次数

        Returns:
            PerformanceMetric (name='derive_role_<role_id>')
        """
        pipeline = self._get_pipeline()
        scenario_name = f'derive_role_{role_id}'

        # 预热 (推导管道有副作用: 写入 effective_intents, 但幂等)
        for _ in range(warmup):
            try:
                pipeline.derive(role_id)
            except Exception:
                pass

        timer = PerformanceTimer(scenario_name, unit='ms')
        timer.set_metadata('role_id', role_id)

        for _ in range(iterations):
            timer.start()
            try:
                pipeline.derive(role_id)
                timer.stop()
            except Exception as e:
                timer.set_metadata('error', str(e))
                timer.stop()

        metric = timer.get_metric()
        return self._record_metric(metric)

    def benchmark_derive_multi_roles(
        self,
        role_ids: List[int],
        iterations: int = 3,
        warmup: int = 0,
    ) -> PerformanceMetric:
        """测量批量推导多角色延迟 (顺序执行)

        Args:
            role_ids: 角色 ID 列表
            iterations: 测量次数 (每次都顺序推导所有角色)
            warmup: 预热次数

        Returns:
            PerformanceMetric (name='derive_multi_roles_<n>roles')
        """
        pipeline = self._get_pipeline()
        scenario_name = f'derive_multi_roles_{len(role_ids)}roles'

        # 预热
        for _ in range(warmup):
            try:
                for rid in role_ids:
                    pipeline.derive(rid)
            except Exception:
                pass

        timer = PerformanceTimer(scenario_name, unit='ms')
        timer.set_metadata('role_ids', role_ids)
        timer.set_metadata('total_roles', len(role_ids))

        for _ in range(iterations):
            timer.start()
            try:
                for rid in role_ids:
                    pipeline.derive(rid)
                timer.stop()
            except Exception as e:
                timer.set_metadata('error', str(e))
                timer.stop()

        metric = timer.get_metric()
        return self._record_metric(metric)

    # ============================================================
    # 性能基线 + 回归检测
    # ============================================================

    def save_baseline(self, filepath: str) -> None:
        """保存当前 metrics 为基线 JSON

        Args:
            filepath: 基线文件路径
        """
        baseline = {
            'name': 'permission_benchmark_baseline',
            'timestamp': datetime.now().isoformat(),
            'scenarios': {
                m.name: {
                    'value': m.value,
                    'unit': m.unit,
                    'iterations': m.iterations,
                    'min_value': m.min_value,
                    'max_value': m.max_value,
                    'std_dev': m.std_dev,
                    'percentile_95': m.percentile_95,
                    'percentile_99': m.percentile_99,
                }
                for m in self._metrics
            },
        }
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(baseline, f, indent=2, ensure_ascii=False)

    def load_baseline(self, filepath: str) -> Optional[Dict[str, Any]]:
        """加载基线 JSON

        Args:
            filepath: 基线文件路径

        Returns:
            基线 dict 或 None (文件不存在时)
        """
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    def check_regression(
        self,
        baseline_path: str,
        threshold: float = 0.2,
    ) -> Dict[str, Any]:
        """检测性能回归

        Args:
            baseline_path: 基线文件路径
            threshold: 回归阈值 (0.2 = 20%)

        Returns:
            {
                'status': 'no_baseline' | 'ok' | 'regression',
                'threshold_percent': float,
                'regressions': [...],
                'improvements': [...],
                'baseline_timestamp': str,
            }
        """
        baseline = self.load_baseline(baseline_path)
        if baseline is None:
            return {'status': 'no_baseline', 'message': '未找到基准数据'}

        regressions: List[Dict[str, Any]] = []
        improvements: List[Dict[str, Any]] = []

        for metric in self._metrics:
            name = metric.name
            if name not in baseline.get('scenarios', {}):
                continue

            baseline_value = baseline['scenarios'][name]['value']
            current_value = metric.value

            if baseline_value == 0:
                continue

            change = (current_value - baseline_value) / baseline_value

            if change > threshold:
                regressions.append({
                    'scenario': name,
                    'baseline': baseline_value,
                    'current': current_value,
                    'change_percent': change * 100,
                })
            elif change < -threshold:
                improvements.append({
                    'scenario': name,
                    'baseline': baseline_value,
                    'current': current_value,
                    'change_percent': abs(change) * 100,
                })

        return {
            'status': 'regression' if regressions else 'ok',
            'threshold_percent': threshold * 100,
            'regressions': regressions,
            'improvements': improvements,
            'baseline_timestamp': baseline.get('timestamp'),
        }

    # ============================================================
    # 性能报告生成
    # ============================================================

    def generate_report(self) -> Dict[str, Any]:
        """生成性能报告 dict

        Returns:
            {
                'name': str,
                'timestamp': str,
                'metrics': [...],
                'summary': {'scenario_count': int, ...},
            }
        """
        metrics_data = [
            {
                'name': m.name,
                'value': m.value,
                'unit': m.unit,
                'iterations': m.iterations,
                'min': m.min_value,
                'max': m.max_value,
                'std_dev': m.std_dev,
                'p95': m.percentile_95,
                'p99': m.percentile_99,
                'metadata': m.metadata,
            }
            for m in self._metrics
        ]

        # 计算 summary
        avg_p95 = (
            sum(m.percentile_95 for m in self._metrics) / len(self._metrics)
            if self._metrics else 0
        )
        max_p95 = max((m.percentile_95 for m in self._metrics), default=0)

        return {
            'name': 'permission_performance_report',
            'timestamp': datetime.now().isoformat(),
            'metrics': metrics_data,
            'summary': {
                'scenario_count': len(self._metrics),
                'avg_p95_ms': round(avg_p95, 2),
                'max_p95_ms': round(max_p95, 2),
            },
        }

    def save_report(self, filepath: str) -> None:
        """保存性能报告到 JSON 文件

        Args:
            filepath: 报告文件路径
        """
        report = self.generate_report()
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    def generate_markdown_report(self) -> str:
        """生成 Markdown 格式性能报告

        Returns:
            Markdown 字符串
        """
        report = self.generate_report()

        lines = [
            f'# {report["name"]}',
            '',
            f'**测试时间**: {report["timestamp"]}',
            '',
            '## 摘要',
            '',
            f'- **场景总数**: {report["summary"]["scenario_count"]}',
            f'- **平均 P95**: {report["summary"]["avg_p95_ms"]:.2f}ms',
            f'- **最大 P95**: {report["summary"]["max_p95_ms"]:.2f}ms',
            '',
            '## 性能指标',
            '',
            '| 场景 | 平均值 | 最小值 | 最大值 | P95 | P99 | 标准差 | 迭代次数 |',
            '|------|--------|--------|--------|-----|-----|--------|---------|',
        ]

        for m in report['metrics']:
            lines.append(
                f'| {m["name"]} | {m["value"]:.2f}{m["unit"]} | '
                f'{m["min"]:.2f}{m["unit"]} | {m["max"]:.2f}{m["unit"]} | '
                f'{m["p95"]:.2f}{m["unit"]} | {m["p99"]:.2f}{m["unit"]} | '
                f'{m["std_dev"]:.2f} | {m["iterations"]} |'
            )

        return '\n'.join(lines)
