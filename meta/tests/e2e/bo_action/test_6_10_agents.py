# -*- coding: utf-8 -*-
"""
[MODULE] P0-2: 6-10 智能体并发测试 (从 tests/load/ 迁入 v3.17)
[DESCRIPTION] 验证 gevent 调度下多智能体并发 + DB 完整性
"""
import time
import http.client
import json
from concurrent.futures import ThreadPoolExecutor


def agent_subflow(agent_id: int, cookie: str) -> dict:
    """模拟 1 个智能体跑 subflow"""
    start = time.time()
    conn = http.client.HTTPConnection('localhost', 3010, timeout=15)
    body = json.dumps({
        'name': f'agent_{agent_id}_test',
        'steps': [
            {'action_id': 'user.get_current', 'as': 'me'},
            {'action_id': 'function.subscription.list'},
        ]
    }).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Content-Length': str(len(body)),
        'Cookie': cookie,
    }
    conn.request('POST', '/api/v2/action/_chain', body=body, headers=headers)
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()
    return {
        'agent_id': agent_id,
        'success': data.get('success'),
        'duration': time.time() - start,
    }


def test_6_agents_concurrent(bo_action_server_check, admin_cookie):
    """6 智能体并发 - 全部成功"""
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda i: agent_subflow(i, admin_cookie), range(6)))

    success = sum(1 for r in results if r['success'])
    assert success == 6, f'6 智能体全部成功 (实际 {success})'


def test_10_agents_concurrent(bo_action_server_check, admin_cookie):
    """10 智能体并发 - 全部成功"""
    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(lambda i: agent_subflow(i, admin_cookie), range(10)))

    success = sum(1 for r in results if r['success'])
    assert success == 10, f'10 智能体全部成功 (实际 {success})'


def test_db_integrity_after_concurrent(bo_action_server_check, admin_cookie):
    """并发后 DB 完整性"""
    import os
    import sqlite3
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        'meta', 'architecture.db'
    )

    # 跑 6 智能体
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(lambda i: agent_subflow(i, admin_cookie), range(6)))

    # 检查 DB 完整性
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            result = conn.execute('PRAGMA integrity_check').fetchone()[0]
            assert result == 'ok', f'并发后 DB 完整性 = ok, 实际 {result}'
        finally:
            conn.close()
