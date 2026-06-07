# -*- coding: utf-8 -*-
"""
[MODULE] P0-1: SSE 真流式测试 (从 tests/e2e/ 迁入 v3.17)
[DESCRIPTION] 验证 gevent 真流式, 走 server (localhost:3010)
"""
from sse_client import SSEClient


def test_real_time_streaming(bo_action_server_check, admin_cookie):
    """验证多步 subflow 的事件按时间顺序到达"""
    with SSEClient('/api/v2/action/_chain_stream', {
        'name': 'p01_sse_streaming',
        'steps': [
            {'action_id': 'user.get_current', 'as': 'me'},
            {'action_id': 'user.get_current'},
            {'action_id': 'user.get_current'},
            {'action_id': 'user.get_current'},
        ]
    }, admin_cookie) as sse:
        events = sse.read_all_events()

    # 关键断言
    assert len(events) >= 8, \
        f'事件数 >= 8 (期望 start + step_start×4 + step_complete×4 + final, 实际 {len(events)})'

    event_types = [e.event_type for e in events]
    assert 'start' in event_types, '缺 start 事件'
    assert 'final' in event_types, '缺 final 事件'

    # 验证时间顺序
    assert events[0].event_type == 'start', '第 1 个事件应是 start'
    assert events[-1].event_type == 'final', '最后 1 个事件应是 final'

    # 关键: gevent 真流式 - start 立即收
    assert events[0].timestamp < 0.5, \
        f'start 事件应在 500ms 内收 (实际 {events[0].timestamp:.3f}s)'


def test_events_have_timestamps(bo_action_server_check, admin_cookie):
    """验证每个事件都带时间戳, 可观测性 OK"""
    with SSEClient('/api/v2/action/_chain_stream', {
        'name': 'p01_timestamps',
        'steps': [{'action_id': 'user.get_current'}]
    }, admin_cookie) as sse:
        events = sse.read_all_events()

    assert len(events) >= 3, '至少 3 事件'
    # 验证时间戳单调递增
    for i in range(1, len(events)):
        assert events[i].timestamp >= events[i-1].timestamp, \
            f'事件 {i} 时间戳 {events[i].timestamp} < 前一个 {events[i-1].timestamp}'


def test_step_complete_includes_data(bo_action_server_check, admin_cookie):
    """验证 step_complete 含 success / duration_ms (可观测性关键)"""
    with SSEClient('/api/v2/action/_chain_stream', {
        'name': 'p01_step_data',
        'steps': [{'action_id': 'user.get_current'}]
    }, admin_cookie) as sse:
        events = sse.read_all_events()

    step_completes = [e for e in events if e.event_type == 'step_complete']
    assert len(step_completes) >= 1, '至少 1 个 step_complete'

    sc = step_completes[0]
    assert 'action_id' in sc.data, 'step_complete 含 action_id'
    assert 'success' in sc.data, 'step_complete 含 success'
    assert 'duration_ms' in sc.data, 'step_complete 含 duration_ms (可观测性关键)'
