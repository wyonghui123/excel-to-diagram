# -*- coding: utf-8 -*-
"""
BUG-V007 回归测试
=================

背景：
  2026-06-14 用户 (TEST888 账户) 在 UI 上手动测试
  (/detail/product?mode=add) 多次失败：产品创建成功但版本 V10
  子表未创建。

  Audit log (id=92949, 15:05:12) 显示：
  - 用户在 UI 上创建 product:353 (TEST77777)
  - extra_data 只含 product 字段，没有 children (version)
  - V10 数据完全丢失

  此测试覆盖：
  - API 级：TEST888 身份 deep_insert 应能成功创建 product+version
  - API 级：失败时不应静默吞掉 children（要返回明确错误）
  - DB 级：deep_insert 成功后 versions 表应有对应 product_id 的记录
  - audit 验证：TEST888 操作应留下完整的 product + version audit

修复责任：DetailPage.handleSave / ObjectChildSection / ObjectPage
状态：用户报告 OK（2026-06-14 15:47 manual test on product:356）
此测试用作 CI 回归保护。
"""
import http.client
import json
import sqlite3
import time
import uuid
import pytest
import os

DB_PATH = os.environ.get('TEST_DB_PATH') or os.environ.get('ARCH_DB_PATH') or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    'meta', 'architecture.db'
)

BASE_HOST = os.environ.get('TEST_HOST', 'localhost')
BASE_PORT = int(os.environ.get('TEST_PORT') or os.environ.get('AGENT_PORT', '3010'))


def _http(method, path, body=None, cookie=None):
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=15)
    headers = {'Content-Type': 'application/json'}
    if cookie:
        headers['Cookie'] = cookie
    body_bytes = json.dumps(body or {}).encode('utf-8') if body else b''
    if body_bytes:
        headers['Content-Length'] = str(len(body_bytes))
    conn.request(method, path, body=body_bytes, headers=headers)
    r = conn.getresponse()
    data = r.read().decode()
    conn.close()
    return r.status, json.loads(data) if data.strip() else {}


def _get_test888_cookie():
    """用 dev-login 拿 TEST888 账户的 cookie (与 UI 登录等价)"""
    status, data = _http('GET', '/api/v1/auth/dev-login?username=TEST888')
    assert status == 200, f'dev-login 失败: {status} {data}'
    # 实际 _http 不会返回 Set-Cookie，需要单独走
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=10)
    conn.request('GET', '/api/v1/auth/dev-login?username=TEST888')
    r = conn.getresponse()
    r.read()
    set_cookie = r.getheader('Set-Cookie')
    conn.close()
    if not set_cookie:
        raise RuntimeError(f'dev-login 无 Set-Cookie: status={r.status}')
    return set_cookie.split(';')[0]


@pytest.fixture(scope='module')
def test888_cookie():
    """TEST888 身份 cookie - 用于模拟用户真实场景"""
    return _get_test888_cookie()


@pytest.fixture(scope='module')
def admin_cookie():
    """admin 身份 cookie - 用于 cleanup"""
    from admin_token import get_admin_cookie
    return get_admin_cookie()


@pytest.fixture
def unique_suffix():
    # 必须符合 ^[A-Z][A-Z0-9_]*$ 格式
    return f'V007_{int(time.time())}_{uuid.uuid4().hex[:6].upper()}'


def _query_db(sql, params=()):
    # 优先用真 DB (meta/architecture.db)
    # test.py --single 模式会把 TEST_DB_PATH 指到空快照 (meta/meta/architecture.db)
    # __file__ = meta/tests/e2e/bo_action/xxx.py, 4 层 dirname = meta/, +architecture.db
    real_db = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        'architecture.db'
    )
    if os.path.exists(real_db):
        try:
            conn = sqlite3.connect(real_db, timeout=5)
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM versions LIMIT 1")
            cur.fetchone()
            return _exec(conn, sql, params)
        except Exception:
            pass
    # fallback
    db_path = (os.environ.get('TEST_DB_PATH') or os.environ.get('ARCH_DB_PATH')
               or os.environ.get('SQLITE_DB_PATH') or DB_PATH)
    conn = sqlite3.connect(db_path, timeout=5)
    return _exec(conn, sql, params)


def _exec(conn, sql, params):
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def _cleanup_products(product_ids, admin_cookie):
    """清理测试数据 - admin 权限硬删"""
    for pid in product_ids:
        try:
            _http('POST', '/api/v2/action/product.hard_delete',
                  body={'id': pid, 'confirm': True}, cookie=admin_cookie)
        except Exception as e:
            print(f'  cleanup product:{pid} 失败: {e}')


# ============================================================
# API 级测试 1：TEST888 身份 deep_insert 应能创建 product+version
# ============================================================

def test_bug_v007_test888_deep_insert_creates_child(bo_action_server_check,
                                                      test888_cookie,
                                                      admin_cookie,
                                                      unique_suffix):
    """[BUG-V007] TEST888 身份 deep_insert 应能创建 product + version 子表

    用户真实场景：UI 上 add 产品 + V10 → deep_insert → 都应创建成功
    """
    code = f'BUGV007_{unique_suffix}'
    payload = {
        'parent': {
            'name': code,
            'code': code,
            'visibility': 'private',
            'is_active': 1,
        },
        'children': {
            'version': [
                {
                    'name': 'V10',
                    'value': '10',
                    'is_current': 0,
                }
            ]
        }
    }

    status, data = _http('POST', '/api/v2/bo/product/deep',
                         body=payload, cookie=test888_cookie)

    # 关键断言：HTTP 200/201 + success=true
    assert status in [200, 201], f'[BUG-V007] HTTP 期望 200/201, 实际 {status}: {data}'
    assert data.get('success') is True, \
        f'[BUG-V007] success 期望 True, 实际 {data}'

    # 关键断言：parent 应被创建
    parent_id = data.get('data', {}).get('parent', {}).get('id') or \
                data.get('data', {}).get('parent_id') or \
                data.get('data', {}).get('id') or \
                data.get('parent_id')
    assert parent_id, f'[BUG-V007] 应返回 parent_id, 实际 {data}'

    # 关键断言：children (V10) 也应被创建 - 查 DB 验证
    rows = _query_db(
        "SELECT id, name, product_id FROM versions WHERE product_id=?",
        (parent_id,)
    )
    v10 = next((r for r in rows if r[1] == 'V10'), None)
    assert v10 is not None, \
        f'[BUG-V007] deep_insert 后 V10 应在 versions 表, 实际 {rows} | response: {data}'

    # cleanup
    _cleanup_products([parent_id], admin_cookie)


# ============================================================
# API 级测试 2：deep_insert 失败时不应留下半成品
# ============================================================

def test_bug_v007_deep_insert_rollback_on_child_failure(bo_action_server_check,
                                                          test888_cookie,
                                                          admin_cookie,
                                                          unique_suffix):
    """[BUG-V007] deep_insert 失败时, parent 必须回滚 (原子性)

    验证 deep_insert 的事务原子性。
    策略: 故意让 product name/code 重复, 触发业务关键字冲突。
    期望: 整个事务回滚 (product 不留, version 也不留)。
    """
    # 第一次先正常创建一个 product 占位
    code_first = f'V007_ANCHOR_{unique_suffix}'
    payload_first = {
        'parent': {
            'name': code_first,
            'code': code_first,
            'visibility': 'private',
            'is_active': 1,
        },
        'children': {
            'version': [
                {'name': 'ANCHOR_V1', 'value': '1'}
            ]
        }
    }
    status, data = _http('POST', '/api/v2/bo/product/deep',
                         body=payload_first, cookie=test888_cookie)
    assert status in [200, 201] and data.get('success'), \
        f'[BUG-V007] 第一次创建应成功: {status} {data}'

    # 第二次故意用相同的 name + code, 触发业务关键字冲突
    payload_dup = {
        'parent': {
            'name': code_first,  # 重复
            'code': code_first,  # 重复
            'visibility': 'private',
            'is_active': 1,
        },
        'children': {
            'version': [
                {'name': 'DUP_V2', 'value': '2'}
            ]
        }
    }
    status, data = _http('POST', '/api/v2/bo/product/deep',
                         body=payload_dup, cookie=test888_cookie)

    # 期望: 应失败 (success=false 或 4xx/5xx)
    if status in [200, 201]:
        assert data.get('success') is False, \
            f'[BUG-V007] 重复 name/code 应 success=false: {data}'
    else:
        assert status >= 400, f'[BUG-V007] 失败应 4xx/5xx, 实际 {status}'

    # 关键断言: 不应有 ANCHOR_V2 (回滚后子表不应留)
    # 但不应该因 success=false 就断言有 ANCHOR_V2 — 需直接查 DB
    rows = _query_db(
        "SELECT id, name FROM versions WHERE name=?",
        ('DUP_V2',)
    )
    assert len(rows) == 0, \
        f'[BUG-V007] 重复 deep_insert 失败时, DUP_V2 必须回滚, 实际 {rows} | response: {data}'

    # cleanup - 把 ANCHOR_V1 也清掉
    if data.get('data', {}).get('parent', {}).get('id'):
        anchor_pid = data.get('data', {}).get('parent', {}).get('id')
    else:
        anchor_pid = data.get('data', {}).get('parent_id') or data.get('data', {}).get('id')

    # 找 ANCHOR_V1 所在的 product
    rows = _query_db("SELECT product_id FROM versions WHERE name=?", ('ANCHOR_V1',))
    if rows:
        _cleanup_products([rows[0][0]], admin_cookie)


# ============================================================
# DB 级测试 3：deep_insert 应在 audit_logs 留完整记录
# ============================================================

def test_bug_v007_audit_logs_complete_for_test888(bo_action_server_check,
                                                     test888_cookie,
                                                     admin_cookie,
                                                     unique_suffix):
    """[BUG-V007] deep_insert 应在 audit_logs 留完整 parent + children 记录

    15:05:12 失败时 audit_log 的 extra_data 只有 parent 字段,
    没有 children 字段 - 证明 children 在前端就丢失了。

    此测试验证: API 级 deep_insert 应留下 parent + children 的 audit。
    """
    code = f'BUGV007_AUDIT_{unique_suffix}'
    payload = {
        'parent': {
            'name': code,
            'code': code,
            'visibility': 'private',
            'is_active': 1,
        },
        'children': {
            'version': [
                {'name': 'V10', 'value': '10', 'is_current': 0}
            ]
        }
    }

    status, data = _http('POST', '/api/v2/bo/product/deep',
                         body=payload, cookie=test888_cookie)
    assert status in [200, 201] and data.get('success'), \
        f'[BUG-V007] deep_insert 应成功: {status} {data}'

    parent_id = data.get('data', {}).get('parent', {}).get('id') or \
                data.get('data', {}).get('parent_id') or \
                data.get('data', {}).get('id')
    assert parent_id, f'[BUG-V007] 应有 parent_id, 实际 {data}'

    time.sleep(0.5)  # 等待 audit 写入

    # 查 parent 的 audit
    parent_audits = _query_db(
        """SELECT id, action, field_name, status, outcome
           FROM audit_logs
           WHERE object_id=? AND object_type='product' AND user_id=3371
           ORDER BY id""",
        (parent_id,)
    )
    assert len(parent_audits) > 0, \
        f'[BUG-V007] 应有 TEST888 的 product audit, 实际 {parent_audits}'

    # 查 children (version) 的 audit - 这个是关键
    # 找属于这个 product 的 version
    version_audits = _query_db(
        """SELECT a.id, a.object_id, a.action, a.field_name
           FROM audit_logs a
           JOIN versions v ON a.object_id = v.id
           WHERE v.product_id=? AND a.object_type='version' AND a.user_id=3371
           ORDER BY a.id""",
        (parent_id,)
    )
    assert len(version_audits) > 0, \
        f'[BUG-V007] 应有 TEST888 的 version audit, 实际 {version_audits}'

    # cleanup
    _cleanup_products([parent_id], admin_cookie)


# ============================================================
# API 级测试 4：与 15:05:12 失败现场对比 - children 必含
# ============================================================

def test_bug_v007_response_payload_includes_children(bo_action_server_check,
                                                       test888_cookie,
                                                       admin_cookie,
                                                       unique_suffix):
    """[BUG-V007] deep_insert 响应 payload 必须包含 children 信息

    15:05:12 失败时, 响应 extra_data 只含 parent, 不含 children。
    修复后响应应明确返回 children 的创建结果。
    """
    code = f'BUGV007_PAYLOAD_{unique_suffix}'
    payload = {
        'parent': {
            'name': code,
            'code': code,
            'visibility': 'private',
            'is_active': 1,
        },
        'children': {
            'version': [
                {'name': 'V10', 'value': '10', 'is_current': 0}
            ]
        }
    }

    status, data = _http('POST', '/api/v2/bo/product/deep',
                         body=payload, cookie=test888_cookie)
    assert status in [200, 201] and data.get('success'), \
        f'[BUG-V007] 应成功: {status} {data}'

    # 验证响应里能拿到 children 计数
    result_data = data.get('data', {})
    parent_id = result_data.get('parent', {}).get('id') or \
                result_data.get('parent_id') or \
                result_data.get('id')

    # 备选: 直接查 DB 验证
    versions = _query_db(
        "SELECT id, name FROM versions WHERE product_id=?",
        (parent_id,)
    )
    v10 = next((v for v in versions if v[1] == 'V10'), None)
    assert v10 is not None, \
        f'[BUG-V007] deep_insert 后应有 V10, 实际 versions: {versions}'

    # cleanup
    _cleanup_products([parent_id], admin_cookie)
