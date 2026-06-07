# -*- coding: utf-8 -*-
"""
缓存性能监控服务

提供缓存命中率监控、性能指标收集、告警等功能。

监控指标：
1. 缓存命中率（目标 > 95%）
2. 平均响应时间（目标 < 0.1ms）
3. 缓存大小和容量
4. 失效频率

使用方式：
    from meta.services.cache_monitor import CacheMonitor
    
    monitor = CacheMonitor(engine)
    
    # 获取监控报告
    report = monitor.get_performance_report()
    
    # 检查健康状态
    is_healthy = monitor.check_health()
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CachePerformanceMetrics:
    """缓存性能指标"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """重置指标"""
        self.total_requests = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_hit_time_ms = 0.0
        self.total_miss_time_ms = 0.0
        self.invalidations = 0
        self.evictions = 0
        self.errors = 0
        
        self.slow_queries = []
        self.error_log = []
        
        self.start_time = datetime.now()
    
    @property
    def hit_rate(self) -> float:
        """缓存命中率（百分比）"""
        if self.total_requests == 0:
            return 100.0
        return (self.cache_hits / self.total_requests) * 100
    
    @property
    def avg_hit_time_ms(self) -> float:
        """平均命中时间（毫秒）"""
        if self.cache_hits == 0:
            return 0.0
        return self.total_hit_time_ms / self.cache_hits
    
    @property
    def avg_miss_time_ms(self) -> float:
        """平均未命中时间（毫秒）"""
        if self.cache_misses == 0:
            return 0.0
        return self.total_miss_time_ms / self.cache_misses
    
    def record_hit(self, elapsed_ms: float):
        """记录缓存命中"""
        self.total_requests += 1
        self.cache_hits += 1
        self.total_hit_time_ms += elapsed_ms
    
    def record_miss(self, elapsed_ms: float):
        """记录缓存未命中"""
        self.total_requests += 1
        self.cache_misses += 1
        self.total_miss_time_ms += elapsed_ms
    
    def record_slow_query(self, query_key: str, elapsed_ms: float, query_type: str = 'miss'):
        """记录慢查询"""
        if elapsed_ms > 100:
            self.slow_queries.append({
                'key': query_key,
                'elapsed_ms': elapsed_ms,
                'type': query_type,
                'timestamp': datetime.now().isoformat()
            })
            
            if len(self.slow_queries) > 100:
                self.slow_queries = self.slow_queries[-100:]
    
    def record_error(self, error_msg: str, query_key: str = None):
        """记录错误"""
        self.errors += 1
        self.error_log.append({
            'message': error_msg,
            'key': query_key,
            'timestamp': datetime.now().isoformat()
        })
        
        if len(self.error_log) > 50:
            self.error_log = self.error_log[-50:]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        # [FIX BUG-007] 2026-06-07: 之前漏写 () 导致 total_seconds 是个方法对象
        # TypeError: type builtin_function_or_method doesn't define __round__ method
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()
        
        return {
            'uptime_seconds': round(uptime_seconds, 2),
            'uptime_human': str(timedelta(seconds=int(uptime_seconds))),
            'total_requests': self.total_requests,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'hit_rate': f"{self.hit_rate:.2f}%",
            'hit_rate_value': round(self.hit_rate, 2),
            'avg_hit_time_ms': round(self.avg_hit_time_ms, 4),
            'avg_miss_time_ms': round(self.avg_miss_time_ms, 4),
            'total_hit_time_ms': round(self.total_hit_time_ms, 4),
            'total_miss_time_ms': round(self.total_miss_time_ms, 4),
            'invalidations': self.invalidations,
            'evictions': self.evictions,
            'errors': self.errors,
            'slow_queries_count': len(self.slow_queries),
            'requests_per_second': round(self.total_requests / uptime_seconds, 2) if uptime_seconds > 0 else 0,
        }


class CacheMonitor:
    """
    缓存性能监控器
    
    提供实时监控、性能分析、健康检查等功能。
    """
    
    def __init__(
        self,
        engine,
        target_hit_rate: float = 95.0,
        target_avg_time_ms: float = 0.1,
        alert_threshold: float = 90.0
    ):
        """
        初始化监控器
        
        Args:
            engine: ManagementDimensionEngine 实例
            target_hit_rate: 目标命中率（百分比）
            target_avg_time_ms: 目标平均响应时间（毫秒）
            alert_threshold: 告警阈值（百分比）
        """
        self.engine = engine
        self.target_hit_rate = target_hit_rate
        self.target_avg_time_ms = target_avg_time_ms
        self.alert_threshold = alert_threshold
        
        self.metrics = CachePerformanceMetrics()
        
        logger.info(
            f"[OK] CacheMonitor 初始化完成 "
            f"(目标命中率={target_hit_rate}%, 目标响应时间={target_avg_time_ms}ms)"
        )
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return self.engine.get_cache_stats()
    
    def get_performance_report(self) -> Dict[str, Any]:
        """
        获取性能报告
        
        Returns:
            包含缓存统计、性能指标、健康状态的报告
        """
        cache_stats = self.get_cache_stats()
        metrics = self.metrics.to_dict()
        
        health_status = self._evaluate_health(cache_stats, metrics)
        
        recommendations = self._generate_recommendations(cache_stats, metrics)
        
        return {
            'timestamp': datetime.now().isoformat(),
            'cache_stats': cache_stats,
            'performance_metrics': metrics,
            'health_status': health_status,
            'recommendations': recommendations,
            'targets': {
                'hit_rate': f"{self.target_hit_rate}%",
                'avg_time_ms': self.target_avg_time_ms
            }
        }
    
    def check_health(self) -> bool:
        """
        检查缓存健康状态
        
        Returns:
            是否健康
        """
        cache_stats = self.get_cache_stats()
        metrics = self.metrics.to_dict()
        
        health = self._evaluate_health(cache_stats, metrics)
        return health['is_healthy']
    
    def _evaluate_health(
        self,
        cache_stats: Dict[str, Any],
        metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        评估健康状态
        
        Args:
            cache_stats: 缓存统计
            metrics: 性能指标
            
        Returns:
            健康状态评估结果
        """
        issues = []
        warnings = []
        
        hit_rate = metrics.get('hit_rate_value', 100.0)
        if hit_rate < self.alert_threshold:
            issues.append(f"缓存命中率过低: {hit_rate:.2f}% (目标: {self.target_hit_rate}%)")
        elif hit_rate < self.target_hit_rate:
            warnings.append(f"缓存命中率接近阈值: {hit_rate:.2f}%")
        
        avg_hit_time = metrics.get('avg_hit_time_ms', 0)
        if avg_hit_time > self.target_avg_time_ms * 10:
            issues.append(f"平均命中时间过长: {avg_hit_time:.4f}ms (目标: {self.target_avg_time_ms}ms)")
        elif avg_hit_time > self.target_avg_time_ms:
            warnings.append(f"平均命中时间偏高: {avg_hit_time:.4f}ms")
        
        cache_size = cache_stats.get('cache_size', 0)
        max_size = cache_stats.get('max_size', 0)
        if max_size > 0 and cache_size >= max_size * 0.9:
            warnings.append(f"缓存容量接近上限: {cache_size}/{max_size}")
        
        error_rate = (metrics.get('errors', 0) / max(metrics.get('total_requests', 1), 1)) * 100
        if error_rate > 5:
            issues.append(f"错误率过高: {error_rate:.2f}%")
        
        is_healthy = len(issues) == 0
        
        return {
            'is_healthy': is_healthy,
            'issues': issues,
            'warnings': warnings,
            'score': self._calculate_health_score(hit_rate, avg_hit_time, error_rate)
        }
    
    def _calculate_health_score(
        self,
        hit_rate: float,
        avg_time: float,
        error_rate: float
    ) -> int:
        """
        计算健康分数（0-100）
        
        Args:
            hit_rate: 命中率
            avg_time: 平均时间
            error_rate: 错误率
            
        Returns:
            健康分数
        """
        score = 100
        
        if hit_rate < self.target_hit_rate:
            score -= (self.target_hit_rate - hit_rate) * 0.5
        
        if avg_time > self.target_avg_time_ms:
            score -= min(20, (avg_time / self.target_avg_time_ms) * 5)
        
        score -= min(30, error_rate * 3)
        
        return max(0, min(100, int(score)))
    
    def _generate_recommendations(
        self,
        cache_stats: Dict[str, Any],
        metrics: Dict[str, Any]
    ) -> List[str]:
        """
        生成优化建议
        
        Args:
            cache_stats: 缓存统计
            metrics: 性能指标
            
        Returns:
            优化建议列表
        """
        recommendations = []
        
        hit_rate = metrics.get('hit_rate_value', 100.0)
        if hit_rate < 90:
            recommendations.append("建议增加热点数据预热，提高缓存命中率")
            recommendations.append("检查缓存失效策略，避免过度失效")
        elif hit_rate < 95:
            recommendations.append("建议优化缓存键设计，减少缓存未命中")
        
        avg_miss_time = metrics.get('avg_miss_time_ms', 0)
        if avg_miss_time > 50:
            recommendations.append("缓存未命中加载时间过长，建议优化数据加载逻辑")
            recommendations.append("考虑增加数据库索引优化查询性能")
        
        cache_size = cache_stats.get('cache_size', 0)
        max_size = cache_stats.get('max_size', 0)
        if max_size > 0 and cache_size >= max_size * 0.8:
            recommendations.append(f"缓存容量使用率 {cache_size}/{max_size}，建议增加缓存大小")
        
        if metrics.get('slow_queries_count', 0) > 10:
            recommendations.append("存在较多慢查询，建议分析慢查询日志进行优化")
        
        if not recommendations:
            recommendations.append("缓存性能良好，继续保持当前配置")
        
        return recommendations
    
    def reset_metrics(self):
        """重置性能指标"""
        self.metrics.reset()
        logger.info("[DECORATIVE] 性能指标已重置")
    
    def export_metrics(self, file_path: str):
        """
        导出性能指标到文件
        
        Args:
            file_path: 导出文件路径
        """
        report = self.get_performance_report()
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"[SYMBOL] 性能指标已导出到: {file_path}")


def create_monitoring_api_blueprint():
    """
    创建缓存监控 API 蓝图
    
    Returns:
        Flask Blueprint
    """
    from flask import Blueprint, jsonify
    
    monitor_bp = Blueprint('cache_monitor', __name__, url_prefix='/api/v1/cache')
    
    _monitor: Optional[CacheMonitor] = None
    
    def get_monitor():
        global _monitor
        if _monitor is None:
            from meta.api.management_dimension_api import _get_engine
            engine = _get_engine()
            _monitor = CacheMonitor(engine)
        return _monitor
    
    @monitor_bp.route('/stats', methods=['GET'])
    def get_cache_stats():
        """获取缓存统计"""
        try:
            monitor = get_monitor()
            stats = monitor.get_cache_stats()
            return jsonify({'success': True, 'data': stats})
        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @monitor_bp.route('/performance', methods=['GET'])
    def get_performance_report():
        """获取性能报告"""
        try:
            monitor = get_monitor()
            report = monitor.get_performance_report()
            return jsonify({'success': True, 'data': report})
        except Exception as e:
            logger.error(f"获取性能报告失败: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @monitor_bp.route('/health', methods=['GET'])
    def check_health():
        """检查健康状态"""
        try:
            monitor = get_monitor()
            is_healthy = monitor.check_health()
            report = monitor.get_performance_report()
            
            return jsonify({
                'success': True,
                'data': {
                    'is_healthy': is_healthy,
                    'health_status': report['health_status']
                }
            })
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @monitor_bp.route('/metrics/reset', methods=['POST'])
    def reset_metrics():
        """重置性能指标"""
        try:
            monitor = get_monitor()
            monitor.reset_metrics()
            return jsonify({'success': True, 'message': 'Metrics reset successfully'})
        except Exception as e:
            logger.error(f"重置指标失败: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @monitor_bp.route('/metrics/export', methods=['GET'])
    def export_metrics():
        """导出性能指标"""
        try:
            import tempfile
            monitor = get_monitor()
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                file_path = f.name
            
            monitor.export_metrics(file_path)
            
            from flask import send_file
            return send_file(
                file_path,
                as_attachment=True,
                download_name=f'cache_metrics_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            )
        except Exception as e:
            logger.error(f"导出指标失败: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    return monitor_bp


def main():
    """命令行入口"""
    import argparse
    import os
    import sys
    
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    
    from meta.core.datasource import get_data_source
    from meta.services.management_dimension_engine import ManagementDimensionEngine
    
    parser = argparse.ArgumentParser(description='缓存性能监控')
    parser.add_argument('--db-path', type=str, help='数据库路径')
    parser.add_argument('--export', type=str, help='导出报告到文件')
    parser.add_argument('--verbose', action='store_true', help='详细日志')
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    db_path = args.db_path or os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'architecture.db'
    )
    
    data_source = get_data_source('sqlite', database=db_path)
    engine = ManagementDimensionEngine(data_source, ttl_seconds=300)
    monitor = CacheMonitor(engine)
    
    report = monitor.get_performance_report()
    
    print("\n" + "=" * 70)
    print("缓存性能监控报告")
    print("=" * 70)
    
    print(f"\n时间: {report['timestamp']}")
    
    print(f"\n[DECORATIVE] 缓存统计:")
    cache_stats = report['cache_stats']
    print(f"  缓存大小: {cache_stats.get('cache_size', 0)}/{cache_stats.get('max_size', 0)}")
    print(f"  TTL: {cache_stats.get('ttl_seconds', 0)}秒")
    
    print(f"\n[DECORATIVE] 性能指标:")
    metrics = report['performance_metrics']
    print(f"  总请求数: {metrics.get('total_requests', 0)}")
    print(f"  缓存命中: {metrics.get('cache_hits', 0)}")
    print(f"  缓存未命中: {metrics.get('cache_misses', 0)}")
    print(f"  命中率: {metrics.get('hit_rate', '0.00%')}")
    print(f"  平均命中时间: {metrics.get('avg_hit_time_ms', 0):.4f}ms")
    print(f"  平均未命中时间: {metrics.get('avg_miss_time_ms', 0):.4f}ms")
    print(f"  运行时间: {metrics.get('uptime_human', '0:00:00')}")
    print(f"  QPS: {metrics.get('requests_per_second', 0)}")
    
    print(f"\n[SYMBOL] 健康状态:")
    health = report['health_status']
    print(f"  状态: {'[OK] 健康' if health['is_healthy'] else '[X] 不健康'}")
    print(f"  分数: {health['score']}/100")
    
    if health['issues']:
        print(f"\n[X] 问题:")
        for issue in health['issues']:
            print(f"  - {issue}")
    
    if health['warnings']:
        print(f"\n[WARNING] 警告:")
        for warning in health['warnings']:
            print(f"  - {warning}")
    
    print(f"\n[DECORATIVE] 优化建议:")
    for rec in report['recommendations']:
        print(f"  - {rec}")
    
    print("\n" + "=" * 70)
    
    if args.export:
        monitor.export_metrics(args.export)
        print(f"\n[OK] 报告已导出到: {args.export}")


if __name__ == '__main__':
    main()
