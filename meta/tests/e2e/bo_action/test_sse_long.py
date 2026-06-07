# -*- coding: utf-8 -*-
"""
[MODULE] P3-6: SSE 长连接测试 (从 tests/e2e/ 迁入 v3.17)
[DESCRIPTION] 验证 gevent 长 subflow 仍正常, 走 server
"""
import time
import http.client
import json


def test_20_step_long_subflow(bo_action_server_check, admin_cookie):
    """20 步 subflow, 验证 gevent 长连接不掉线"""
    steps = [{'action_id': 'user.get_current', 'as': f's{i}'} for i in range(20)]

    start = time.time()
    conn = http.client.HTTPConnection('localhost', 3010, timeout=30)
    body = json.dumps({
        'name': 'p36_long_subflow',
        'steps': steps,
    }).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Content-Length': str(len(body)),
        'Cookie': admin_cookie,
    }
    conn.request('POST', '/api/v2/action/_chain', body=body, headers=headers)
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()
    duration = time.time() - start

    assert data.get('success') is True
    assert data['data']['total_steps'] == 20


def test_sse_connection_no_timeout(bo_action_server_check, admin_cookie):
    """SSE 长连接不掉线 (5s 内持续)"""
    start = time.time()
    conn = http.client.HTTPConnection('localhost', 3010, timeout=15)
    body = json.dumps({
        'name': 'p36_sse_long',
        'steps': [{'action_id': 'user.get_current'} for _ in range(5)],
    }).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Content-Length': str(len(body)),
        'Cookie': admin_cookie,
    }
    conn.request('POST', '/api/v2/action/_chain_stream', body=body, headers=headers)
    r = conn.getresponse()

    # 读所有事件
    events_received = []
    buf = b''
    while time.time() - start < 10:
        chunk = r.read(1)
        if not chunk:
            break
        buf += chunk
        if buf.endswith(b'\n\n'):
            ev = buf.decode('utf-8', errors='ignore').strip()
            buf = b''
            for line in ev.split('\n'):
                if line.startswith('event: '):
                    events_received.append(line[7:])
            if events_received and events_received[-1] == 'final':
                break
    conn.close()

    assert 'final' in events_received, 'SSE 连接断, 缺 final 事件'


def test_sse_throughput(bo_action_server_check, admin_cookie):
    """SSE 吞吐: 短时间内 50 个 SSE 连接"""
    from concurrent.futures import ThreadPoolExecutor

    def one_sse_run(_):
        conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
        body = json.dumps({
            'name': 'p36_throughput',
            'steps': [{'action_id': 'user.get_current'}],
        }).encode('utf-8')
        headers = {
            'Content-Type': 'application/json',
            'Content-Length': str(len(body)),
            'Cookie': admin_cookie,
        }
        conn.request('POST', '/api/v2/action/_chain_stream', body=body, headers=headers)
        r = conn.getresponse()
        events = []
        buf = b''
        while True:
            chunk = r.read(1)
            if not chunk:
                break
            buf += chunk
            if buf.endswith(b'\n\n'):
                ev = buf.decode('utf-8', errors='ignore').strip()
                buf = b''
                for line in ev.split('\n'):
                    if line.startswith('event: '):
                        events.append(line[7:])
                if events and events[-1] == 'final':
                    break
        conn.close()
        return 'final' in events

    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(one_sse_run, range(50)))

    success = sum(1 for r in results if r)
    assert success >= 45, f'50 SSE 至少 45 成功 (实际 {success})'
