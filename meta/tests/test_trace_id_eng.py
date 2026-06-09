# -*- coding: utf-8 -*-
"""
SVC-012: trace_id (6 测试) - v3.18 M.1 全局 trace_id 管理

[MARKER] unit - 单元测试 (无外部依赖)
[FEATURE] TraceId.generate / get / set / clear / get_or_generate
"""
import pytest
import re
from meta.core.trace_id import TraceId

pytestmark = [pytest.mark.unit]


class TestTraceId:
    """TraceId 测试 (6 用例)"""

    def teardown_method(self):
        """每个测试后清空, 避免污染"""
        TraceId.clear()

    def test_generate_returns_32_chars(self):
        """generate 返回 32 字符 hex (UUID 截断)"""
        tid = TraceId.generate()
        assert len(tid) == 32
        assert re.match(r'^[0-9a-f]{32}$', tid), f"应为 32 字符 hex, 实际: {tid}"

    def test_generate_unique(self):
        """多次 generate 返回不同的 ID"""
        tids = {TraceId.generate() for _ in range(100)}
        assert len(tids) == 100, "100 次 generate 应产生 100 个不同 ID"

    def test_get_returns_none_when_not_set(self):
        """未 set → get 返回 None"""
        assert TraceId.get() is None

    def test_set_and_get(self):
        """set 后 get 返回相同值"""
        TraceId.set('abc123' + '0' * 25)
        assert TraceId.get() == 'abc123' + '0' * 25

    def test_clear(self):
        """clear 后 get 返回 None"""
        TraceId.set('test_id')
        assert TraceId.get() == 'test_id'
        TraceId.clear()
        assert TraceId.get() is None

    def test_get_or_generate(self):
        """get_or_generate: 未 set → generate; 已 set → 用现有"""
        # 未 set: 自动 generate
        tid1 = TraceId.get_or_generate()
        assert len(tid1) == 32
        # 已 set: 返回 set 的值
        TraceId.set('custom_tid_xxxxx' + '0' * 17)
        tid2 = TraceId.get_or_generate()
        assert tid2 == 'custom_tid_xxxxx' + '0' * 17
