# -*- coding: utf-8 -*-
"""
ENG-004: metrics_store (16 测试) - v3.18 M.4 P50/P95/P99 sliding window

[MARKER] unit - 单元测试 (无外部依赖)
[FEATURE] SlidingWindow 时间窗口 / MetricsStore 指标存储 / get_metrics_store 单例
"""
import time
import pytest
from meta.core.metrics_store import SlidingWindow, MetricsStore, get_metrics_store

pytestmark = [pytest.mark.unit]


class TestSlidingWindow:
    """SlidingWindow 滑动窗口测试 (9)"""
    def test_empty_window(self):
        w = SlidingWindow(window_seconds=60)
        assert w.count() == 0
        assert w.values() == []
        assert w.percentile(50) == 0.0
        assert w.avg() == 0.0

    def test_add_value(self):
        w = SlidingWindow(window_seconds=60)
        w.add(10.0)
        w.add(20.0)
        assert w.count() == 2
        assert sorted(w.values()) == [10.0, 20.0]

    def test_add_with_custom_timestamp(self):
        w = SlidingWindow(window_seconds=60)
        now = time.time()
        w.add(10.0, ts=now - 100)  # 超出窗口
        w.add(20.0, ts=now)
        # 旧的被 evict
        assert w.count() == 1
        assert w.values() == [20.0]

    def test_evict_old_values(self):
        w = SlidingWindow(window_seconds=10)
        now = time.time()
        for i in range(5):
            w.add(float(i), ts=now - 20)  # 都过期
        w.add(100.0, ts=now)
        # 5 个过期被清空, 1 个保留
        assert w.count() == 1
        assert w.values() == [100.0]

    # ---------- percentile 合并 (3 → 1) ----------
    # 排序后 [1..10], idx = int(10 * p / 100)
    @pytest.mark.parametrize('percentile,expected', [
        pytest.param(50, 6.0, id='p50_idx5'),
        pytest.param(95, 10.0, id='p95_idx9'),
        pytest.param(99, 10.0, id='p99_idx9'),
    ])
    def test_percentile(self, percentile, expected):
        w = SlidingWindow(window_seconds=60)
        for v in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
            w.add(float(v))
        assert w.percentile(percentile) == expected

    # ---------- avg 合并 (2 → 1, 2 cases) ----------
    @pytest.mark.parametrize('values,expected', [
        pytest.param([1.0, 2.0, 3.0], 2.0, id='with_data'),
        pytest.param([], 0.0, id='empty'),
    ])
    def test_avg(self, values, expected):
        w = SlidingWindow(window_seconds=60)
        for v in values:
            w.add(v)
        assert w.avg() == expected


class TestMetricsStore:
    def test_record_basic(self):
        store = MetricsStore(window_seconds=60)
        store.record('api.latency', 100.0)
        store.record('api.latency', 200.0)
        assert store.count('api.latency') == 0  # 计数器没 tags, 不增
        # 窗口里有 2 个数据点
        assert store.avg('api.latency') == 150.0

    def test_record_with_tags(self):
        store = MetricsStore(window_seconds=60)
        store.record('api.latency', 100.0, tags={'endpoint': '/users'})
        store.record('api.latency', 200.0, tags={'endpoint': '/users'})
        # 有 tags → counter 增加
        assert store.count() == 2
        assert store.count('api.latency|endpoint=/users') == 2

    def test_p50_p95_p99(self):
        store = MetricsStore(window_seconds=60)
        for v in range(1, 101):
            store.record('latency', float(v))
        assert store.p50('latency') == 51.0
        assert store.p95('latency') == 96.0
        assert store.p99('latency') == 100.0

    def test_count_no_name(self):
        store = MetricsStore(window_seconds=60)
        store.record('a', 1.0, tags={'k': 'v'})
        store.record('b', 2.0, tags={'k': 'v'})
        assert store.count() == 2  # 总计

    def test_count_unknown_name(self):
        store = MetricsStore(window_seconds=60)
        assert store.count('unknown') == 0


class TestGetMetricsStore:
    def test_returns_singleton(self):
        s1 = get_metrics_store()
        s2 = get_metrics_store()
        assert s1 is s2

    def test_singleton_works(self):
        store = get_metrics_store()
        store.record('test.metric', 50.0)
        # 验证真的写入了
        assert store.avg('test.metric') >= 50.0
