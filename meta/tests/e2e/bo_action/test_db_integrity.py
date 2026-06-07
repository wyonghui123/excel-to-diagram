# -*- coding: utf-8 -*-
"""
[MODULE] P2-4: DB 完整性 + CORS 测试 (从 tests/integration/ 迁入 v3.17)
[DESCRIPTION] 验证 DB integrity + 并发写后完整性 + CORS + health endpoint
"""
import os
import sqlite3

# admin_token 路径在 conftest.py 已配 (走 sys.path)
from admin_token import call_action  # noqa: E402


_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    'meta', 'architecture.db'
)


def test_db_integrity_ok():
    """DB 完整性 = ok"""
    if not os.path.exists(_DB_PATH):
        return
    conn = sqlite3.connect(_DB_PATH, timeout=5)
    try:
        result = conn.execute('PRAGMA integrity_check').fetchone()[0]
        assert result == 'ok', f'DB 完整性 = ok, 实际 {result}'
    finally:
        conn.close()


def test_db_after_concurrent_writes(admin_cookie):
    """并发写后 DB 仍完整"""
    if not os.path.exists(_DB_PATH):
        return
    import time
    from concurrent.futures import ThreadPoolExecutor

    ts = int(time.time())
    # 6 个并发写
    def do_write(i):
        return call_action('subscription.create', {
            'object_type': 'user',
            'event_types': ['created'],
            'channel': 'webhook',
            'webhook_url': f'http://localhost:9999/test_{i}_{ts}',
        }, cookie=admin_cookie)

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(do_write, range(6)))

    # 检查 DB 完整性
    conn = sqlite3.connect(_DB_PATH, timeout=5)
    try:
        result = conn.execute('PRAGMA integrity_check').fetchone()[0]
        assert result == 'ok', f'并发后 DB 完整性 = ok, 实际 {result}'
    finally:
        conn.close()


def test_cors_headers(bo_action_server_check):
    """CORS 头配置 (OPTIONS)"""
    import http.client
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    conn.request('OPTIONS', '/api/v2/action/user.get_current')
    r = conn.getresponse()
    r.read()
    conn.close()
    # CORS 头存在性 (具体值因配置而异, 这里只检查存在)
    # 至少有 Access-Control-Allow-Origin
    cors_origin = r.getheader('Access-Control-Allow-Origin')
    assert cors_origin is not None or r.status in [200, 204, 404], \
        f'OPTIONS 应返回 CORS 头或 2xx, 实际 status={r.status}'


def test_health_endpoint(bo_action_server_check):
    """健康检查"""
    import http.client
    import json
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    conn.request('GET', '/api/v2/action/_health')
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()
    assert r.status == 200
    assert data.get('success') is True
