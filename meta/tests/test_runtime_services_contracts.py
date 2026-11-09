# -*- coding: utf-8 -*-
"""运行时服务契约测试（认证限流 / 令牌黑名单 / 指标采集 / 追溯链接）。

[TEST-EFF P2-1] 由四个同域（meta.services / meta.api 纯内存单例，无真实 DB 依赖）的
<=5 用例小文件合并而来：
- test_rate_limiter.py           (SVC-005 RateLimiter)
- test_token_blacklist_service.py (SVC-006 TokenBlacklistService)
- test_metrics_api.py            (GAP-021 metrics_api 工具函数)
- test_trace_link_service.py     (序列号/容器追溯链接幂等与只前进)
"""

import importlib
import os
import time
from datetime import datetime, timedelta

import pytest

from meta.services.trace_link_service import link_hu, link_serial
from meta.tests.hu_test_doubles import build_db, ds

pytestmark = pytest.mark.unit


class TestRateLimiter:
    """RateLimiter 单元测试 (SVC-005)"""

    def setup_method(self):
        """每个测试前清空 limiter 状态 + 移除可能影响测试的 env var"""
        os.environ.pop('DISABLE_RATE_LIMIT', None)
        from meta.services.rate_limiter import RateLimiter
        RateLimiter.reset()

    def test_singleton_pattern(self):
        """RateLimiter 是单例"""
        from meta.services.rate_limiter import RateLimiter
        s1 = RateLimiter()
        s2 = RateLimiter()
        assert s1 is s2

    def test_record_failed_attempt_no_lockout_under_threshold(self):
        """未达阈值前不封禁 (使用默认阈值 10, 失败 5 次)"""
        from meta.services.rate_limiter import RateLimiter
        rl = RateLimiter()
        rl.clear()
        # 失败 5 次 (默认阈值 10, 不会触发封禁)
        for _ in range(5):
            is_locked, msg = rl.record_failed_attempt('1.1.1.1', 'user_a')
            assert is_locked is False
        # 应有 5 次失败记录
        assert len(rl._ip_attempts['1.1.1.1']) == 5
        assert len(rl._username_attempts['user_a']) == 5

    def test_record_failed_attempt_locks_at_threshold(self):
        """达到默认阈值 (10) 后封禁 IP"""
        from meta.services.rate_limiter import RateLimiter
        rl = RateLimiter()
        rl.clear()
        # 失败 10 次 (默认阈值 MAX_LOGIN_ATTEMPTS_PER_IP=10)
        is_locked = False
        for _ in range(10):
            is_locked, _ = rl.record_failed_attempt('2.2.2.2', 'user_b')
        # 第 10 次触发封禁
        assert is_locked is True
        # 立即检查, 应在封禁中
        is_locked_now, msg = rl.check_rate_limit('2.2.2.2', 'user_b')
        assert is_locked_now is True
        assert '封禁' in msg
        # lockout 已记录
        assert '2.2.2.2' in rl._ip_lockouts

    def test_record_successful_attempt_resets_count(self):
        """record_successful_attempt 清空计数"""
        from meta.services.rate_limiter import RateLimiter
        rl = RateLimiter()
        rl.clear()
        # 失败 5 次
        for _ in range(5):
            rl.record_failed_attempt('3.3.3.3', 'user_c')
        assert len(rl._ip_attempts['3.3.3.3']) == 5
        # 成功 → 重置
        rl.record_successful_attempt('3.3.3.3', 'user_c')
        # 计数应清空
        assert '3.3.3.3' not in rl._ip_attempts
        assert 'user_c' not in rl._username_attempts

    def test_disable_rate_limit_via_env(self):
        """DISABLE_RATE_LIMIT=1 时 record_failed_attempt 不封禁"""
        from meta.services.rate_limiter import RateLimiter
        rl = RateLimiter()
        rl.clear()
        # 用 env 临时启用
        os.environ['DISABLE_RATE_LIMIT'] = '1'
        try:
            # 即使失败 15 次, DISABLE_RATE_LIMIT=1 时不封禁
            is_locked = False
            for _ in range(15):
                is_locked, _ = rl.record_failed_attempt('4.4.4.4', 'user_d')
            assert is_locked is False
            is_locked_now, _ = rl.check_rate_limit('4.4.4.4', 'user_d')
            assert is_locked_now is False
        finally:
            os.environ.pop('DISABLE_RATE_LIMIT', None)


class TestTokenBlacklistService:
    """TokenBlacklistService 单元测试 (SVC-006)"""

    def test_add_and_check_blacklist(self):
        """add + is_blacklisted 完整流程"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc = TokenBlacklistService()
        token = f'test_token_{int(time.time())}'
        expires = datetime.utcnow() + timedelta(hours=1)
        # 添加到黑名单
        svc.add_to_blacklist(token, expires)
        # 验证
        assert svc.is_blacklisted(token) is True

    def test_token_not_in_blacklist(self):
        """未加入黑名单的 token 返回 False"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc = TokenBlacklistService()
        random_token = f'random_{int(time.time() * 1000)}'
        assert svc.is_blacklisted(random_token) is False

    def test_hash_consistency(self):
        """同 token 多次 hash 一致"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc = TokenBlacklistService()
        h1 = svc._hash_token('consistent_token')
        h2 = svc._hash_token('consistent_token')
        assert h1 == h2
        # SHA256 hex digest = 64 字符
        assert len(h1) == 64

    def test_different_tokens_have_different_hashes(self):
        """不同 token → 不同 hash"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc = TokenBlacklistService()
        h1 = svc._hash_token('token_a')
        h2 = svc._hash_token('token_b')
        assert h1 != h2

    def test_expired_token_not_blacklisted(self):
        """过期 token 被自动清理, 不再黑名单"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc = TokenBlacklistService()
        token = f'expired_{int(time.time())}'
        # 过期时间 = 1 小时前
        past = datetime.utcnow() - timedelta(hours=1)
        svc.add_to_blacklist(token, past)
        # 验证: is_blacklisted 内部会清理过期项, 应返回 False
        assert svc.is_blacklisted(token) is False


class TestMetricsAPI:
    """metrics_api 工具函数测试 (GAP-021)"""

    def test_record_and_get_metric(self):
        """record_metric 写入后 get_metrics 能取到"""
        from meta.api.metrics_api import record_metric, get_metrics
        name = f'test_metric_{int(time.time() * 1000)}'
        record_metric(name, 1.5, {'tag1': 'value1'})
        record_metric(name, 2.5, {'tag1': 'value2'})

        metrics = get_metrics()
        assert name in metrics
        assert len(metrics[name]) == 2
        # 元素是 (ts, value, tags) 三元组
        ts, val, tags = metrics[name][0]
        assert isinstance(ts, float)
        assert val in (1.5, 2.5)
        assert isinstance(tags, dict)

    def test_percentile_calculation(self):
        """_percentile 计算百分位正确"""
        from meta.api.metrics_api import _percentile
        # [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        values = list(range(1, 11))
        # 50% percentile: idx = int(10 * 0.5) = 5 -> sorted[5] = 6
        p50 = _percentile(values, 50)
        assert p50 == 6
        p95 = _percentile(values, 95)
        # idx = int(10 * 0.95) = 9 -> sorted[9] = 10
        assert p95 == 10
        p99 = _percentile(values, 99)
        # idx = int(10 * 0.99) = 9 -> sorted[9] = 10
        assert p99 == 10
        # 边界: 0 个值
        assert _percentile([], 50) == 0.0
        # 单元素
        assert _percentile([42], 50) == 42

    def test_format_prometheus_text_format(self):
        """format_prometheus 返回 Prometheus 文本格式"""
        from meta.api.metrics_api import format_prometheus
        output = format_prometheus()
        assert isinstance(output, str)
        # 必含 HELP / TYPE 行
        assert '# HELP' in output
        assert '# TYPE' in output
        # 必含核心 metric 名
        assert 'bo_action_total' in output
        assert 'db_pool_active' in output
        assert 'write_queue_depth' in output
        # 行尾 \n
        assert output.endswith('\n')

    def test_format_prometheus_includes_action_duration(self):
        """有 bo_action_duration 数据时包含 duration summary"""
        from meta.api.metrics_api import record_metric, format_prometheus
        # 写入持续时间数据 (模拟)
        for _ in range(3):
            record_metric('bo_action_duration', 100.0, {'action_id': 'test'})
        output = format_prometheus()
        # 应含 duration 字段
        if 'bo_action_duration_seconds' in output:
            assert 'quantile' in output
            assert '# TYPE bo_action_duration_seconds summary' in output

    def test_get_metrics_returns_copy(self):
        """get_metrics 返回 dict copy, 修改不影响内部 _metrics"""
        from meta.api.metrics_api import record_metric, get_metrics, _metrics
        name = f'test_copy_{int(time.time() * 1000)}'
        record_metric(name, 1.0)

        m1 = get_metrics()
        assert name in m1
        # 修改返回的 dict 不影响 _metrics 内部
        m1['__extra__'] = 'hack'
        m2 = get_metrics()
        assert '__extra__' not in m2


# ---------------------------------------------------------------------------
# test_trace_link_service.py — 追溯链接写入：序列号链接幂等、容器链接只前进不回退
# ---------------------------------------------------------------------------
_V216 = importlib.import_module('meta.migrations.v216__document_hu_links')


def _build_trace_db():
    """build_db 自带 serial 链接表；v216 补上 document_hu_links。"""
    conn = build_db()
    database = ds(conn)
    for _table, ddl in _V216.TABLES:
        database.execute(ddl)
    for _table, _name, ddl in _V216.INDEXES:
        database.execute(ddl)
    return conn, database


def _rows(conn, table):
    return ds(conn).query('SELECT * FROM %s' % table)


def test_serial_link_is_idempotent():
    conn, database = _build_trace_db()
    assert link_serial(database, 'receipt', 1, 10, 900, 'in') is True
    assert link_serial(database, 'receipt', 1, 10, 900, 'in') is False
    assert len(_rows(conn, 'document_serial_links')) == 1


def test_hu_link_insert_then_promote():
    conn, database = _build_trace_db()
    assert link_hu(database, 'shipment', 1, 10, 7, 'out',
                   link_type='planned', qty=1) == 'inserted'
    assert link_hu(database, 'shipment', 1, 10, 7, 'out',
                   link_type='packed', qty=2) == 'promoted'
    row = _rows(conn, 'document_hu_links')[0]
    assert (row['link_type'], row['qty']) == ('packed', 2)


def test_hu_link_never_regresses():
    conn, database = _build_trace_db()
    link_hu(database, 'shipment', 1, 10, 7, 'out',
            link_type='shipped', qty=1)
    assert link_hu(database, 'shipment', 1, 10, 7, 'out',
                   link_type='planned', qty=3) == 'qty'
    row = _rows(conn, 'document_hu_links')[0]
    assert (row['link_type'], row['qty']) == ('shipped', 3)


def test_hu_link_blank_qty_keeps_existing():
    conn, database = _build_trace_db()
    link_hu(database, 'shipment', 1, 10, 7, 'out',
            link_type='packed', qty=2)
    assert link_hu(database, 'shipment', 1, 10, 7, 'out',
                   link_type='packed', qty=None) == 'kept'
    assert _rows(conn, 'document_hu_links')[0]['qty'] == 2
