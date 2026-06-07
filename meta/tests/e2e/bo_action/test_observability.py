# -*- coding: utf-8 -*-
"""
[MODULE] P2-5: 可观测性测试 (从 tests/e2e/ 迁入 v3.17)
[DESCRIPTION] 智能体能从 SSE 拿到 step timing / 失败原因 / partial result / 卡住检测
"""
from sse_client import SSEClient


def test_step_timing_observability(bo_action_server_check, admin_cookie):
    """每步带 duration_ms, 智能体能识别"哪步慢" """
    with SSEClient('/api/v2/action/_chain_stream', {
        'name': 'p25_step_timing',
        'steps': [
            {'action_id': 'user.get_current', 'as': 'me'},
            {'action_id': 'function.subscription.list'},
        ]
    }, admin_cookie) as sse:
        events = sse.read_all_events()

    step_completes = [e for e in events if e.event_type == 'step_complete']
    assert len(step_completes) >= 2, f'应有 2 个 step_complete, 实际 {len(step_completes)}'

    # 每个 step_complete 都有 duration_ms
    for sc in step_completes:
        assert 'duration_ms' in sc.data, f'step_complete 缺 duration_ms: {sc.data}'
        assert 'success' in sc.data, f'step_complete 缺 success: {sc.data}'


def test_partial_result_on_failure(bo_action_server_check, admin_cookie):
    """subflow 部分失败时, final 含 partial result"""
    with SSEClient('/api/v2/action/_chain_stream', {
        'name': 'p25_partial',
        'steps': [
            {'action_id': 'user.get_current', 'as': 'good'},
            {'action_id': 'nonexistent.action', 'as': 'bad'},
        ]
    }, admin_cookie) as sse:
        events = sse.read_all_events()

    final = next((e for e in events if e.event_type == 'final'), None)
    assert final is not None, '缺 final 事件'
    # final 含 partial result
    assert 'data' in final.data or 'partial' in str(final.data).lower(), \
        f'final 缺 partial result: {final.data}'


def test_failure_diagnosis_via_step_data(bo_action_server_check, admin_cookie):
    """失败的 step 在 step_complete 中带 message, 智能体能诊断"""
    with SSEClient('/api/v2/action/_chain_stream', {
        'name': 'p25_diag',
        'steps': [{'action_id': 'definitely.not.exist'}]
    }, admin_cookie) as sse:
        events = sse.read_all_events()

    step_completes = [e for e in events if e.event_type == 'step_complete']
    assert len(step_completes) >= 1

    # 失败的 step_complete 应有 success=False + message
    failed = [sc for sc in step_completes if sc.data.get('success') is False]
    assert len(failed) >= 1, '应有失败 step'
    assert 'message' in failed[0].data, '失败 step 缺 message'


def test_stuck_detection_via_timestamps(bo_action_server_check, admin_cookie):
    """智能体能通过时间戳检测"哪步卡住" """
    with SSEClient('/api/v2/action/_chain_stream', {
        'name': 'p25_stuck',
        'steps': [
            {'action_id': 'user.get_current'},
            {'action_id': 'user.get_current'},
        ]
    }, admin_cookie) as sse:
        events = sse.read_all_events()

    step_completes = [e for e in events if e.event_type == 'step_complete']
    assert len(step_completes) >= 2

    # 每个 step_complete 都带 duration_ms
    for sc in step_completes:
        assert 'duration_ms' in sc.data
        # duration_ms 应该是 number
        assert isinstance(sc.data['duration_ms'], (int, float)), \
            f'duration_ms 应该是 number: {sc.data["duration_ms"]}'
