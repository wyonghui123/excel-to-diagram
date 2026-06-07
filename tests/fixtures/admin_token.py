# -*- coding: utf-8 -*-
"""
公共测试 fixtures (v3.9)
============================

提供测试常用的工具函数:
- get_admin_token(): 登录获取 admin cookie
- call_action(): 调 BO Action 通用方法
- reset_db(): 重置测试数据
"""
import http.client
import json
import os
import sqlite3
from typing import Any, Dict, Optional, Tuple

BASE_HOST = os.environ.get('TEST_HOST', 'localhost')
BASE_PORT = int(os.environ.get('TEST_PORT', '3010'))
# DB 路径: tests/ 在子目录, 需向上 1 级
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))
DB_PATH = os.path.join(_PROJECT_ROOT, 'meta', 'architecture.db')


def get_admin_cookie() -> str:
    """获取 admin 登录 cookie"""
    # 先解锁 admin (避免 6+ 失败被锁)
    _unlock_admin_if_needed()

    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=10)
    body = json.dumps({'username': 'admin', 'password': 'admin123'})
    conn.request('POST', '/api/v2/action/user.authenticate', body=body,
                 headers={'Content-Type': 'application/json',
                           'Content-Length': str(len(body))})
    r = conn.getresponse()
    data = r.read().decode()
    r.read()  # consume
    set_cookie = r.getheader('Set-Cookie')
    conn.close()
    if not set_cookie:
        raise RuntimeError(f'Login failed: {data}')
    return set_cookie.split(';')[0]  # auth_token=xxx


def _unlock_admin_if_needed():
    """若 admin 被锁, 自动解锁"""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    try:
        status = conn.execute("SELECT status FROM users WHERE username = 'admin'").fetchone()
        if status and status[0] != 'active':
            conn.execute("UPDATE users SET status = 'active' WHERE username = 'admin'")
            conn.commit()
    finally:
        conn.close()


def call_action(action_id: str, body: Optional[Dict] = None, cookie: Optional[str] = None,
                  method: str = 'POST') -> Tuple[int, Dict]:
    """通用 Action 调用"""
    if cookie is None:
        cookie = get_admin_cookie()
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=15)
    body_bytes = json.dumps(body or {}).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Content-Length': str(len(body_bytes)),
        'Cookie': cookie,
    }
    conn.request(method, f'/api/v2/action/{action_id}', body=body_bytes, headers=headers)
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()
    return r.status, data


def check_db_integrity() -> str:
    """检查 DB 完整性"""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    try:
        result = conn.execute('PRAGMA integrity_check').fetchone()[0]
        return result
    finally:
        conn.close()


def reset_subflow_metrics():
    """清空 subflow metrics"""
    try:
        from meta.services.subflow_metrics import SubflowMetrics
        SubflowMetrics.reset()
    except Exception:
        pass
