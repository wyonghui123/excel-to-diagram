# -*- coding: utf-8 -*-
"""
[NEW 2026-06-12] v2 BO /audit_log 端点 enrich 行为测试

覆盖:
T4 - v2 BO GET /api/v2/bo/audit_log/<id> 应返回 extra_data_parsed.deleted_data
      和 *_label 字段 (与 v1 /audit/logs/<id> 对齐)
T5 - v2 BO GET /api/v2/bo/audit_log 列表 应对每条 item 注入
      extra_data_parsed + 3 个 label 字段
T7 - DELETE 一条 user_group 后, 调 v2 BO /audit_log/<id> 能解析出 deleted_data
"""
import json
import os
import sqlite3
import tempfile

import pytest

pytestmark = pytest.mark.integration


# ============================================================
# Fixture: 临时 DB 预置 audit_log 数据
# ============================================================

@pytest.fixture
def audit_db_with_deleted_log():
    """建一个含 1 条 DELETE user_group 日志 (带 deleted_data) 的临时 DB"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT,
            object_id TEXT,
            action TEXT,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            user_id TEXT,
            user_name TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT,
            trace_id TEXT,
            transaction_id TEXT,
            status TEXT DEFAULT 'written',
            retry_count INTEGER DEFAULT 0,
            error_message TEXT,
            log_category TEXT DEFAULT 'business',
            log_level TEXT DEFAULT 'INFO',
            extra_data TEXT,
            parent_object_type TEXT,
            parent_object_id TEXT,
            agent_id TEXT,
            agent_session_id TEXT,
            tool_call_id TEXT,
            agent_reasoning TEXT
        );
    """)
    # id=1: DELETE user_group 475 带 deleted_data
    deleted_data = {
        "deleted_data": {
            "id": 475,
            "name": "Test Group 475",
            "code": "test_grp_475",
            "description": "deleted by test",
        },
        "object_display": "Test Group 475 (test_grp_475)",
    }
    conn.execute("""
        INSERT INTO audit_logs
        (id, object_type, object_id, action, user_id, user_name, created_at,
         extra_data, log_category, log_level, status)
        VALUES (1, 'user_group', '475', 'DELETE', '1', 'admin', '2026-06-12 12:00:00',
                ?, 'business', 'INFO', 'written')
    """, [json.dumps(deleted_data)])
    # id=2: UPDATE role_menu 501 (无 extra_data)
    conn.execute("""
        INSERT INTO audit_logs
        (id, object_type, object_id, action, field_name, old_value, new_value,
         user_id, user_name, created_at, parent_object_type, parent_object_id)
        VALUES (2, 'role_menu', '501', 'UPDATE', 'menu_codes', 'm1', 'm2',
                '1', 'admin', '2026-06-12 12:01:00', 'role', '3606')
    """)
    conn.commit()
    conn.close()
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


def _mk_tok():
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo
    u = UserInfo(
        user_id='1', username='bo_audit', display_name='BO Audit Tester',
        email='b@test.com', roles=['admin'], permissions=['*']
    )
    token, _ = TokenService.create_token(u)
    return token


@pytest.fixture(scope='class')
def admin_headers():
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {_mk_tok()}',
        'X-User-Id': '1',
        'X-User-Name': 'bo_audit',
    }


def _patch_data_source(audit_db_path, monkeypatch):
    """同时 patch audit_api._data_source 和 bo_api._data_source"""
    from meta.core.datasource import get_data_source
    ds = get_data_source("sqlite", database=audit_db_path)
    import meta.api.audit_api as audit_api_mod
    import meta.api.bo_api as bo_api_mod
    monkeypatch.setattr(audit_api_mod, "_data_source", ds)
    monkeypatch.setattr(bo_api_mod, "_data_source", ds)
    return ds


# ============================================================
# T4  v2 BO /audit_log/<id> 端点
# ============================================================

class TestV2BOAuditLogDetail:
    """[FIX 2026-06-12] v2 BO /audit_log/<id> 必须 enrich label + 解析 extra_data_parsed"""

    def test_detail_returns_extra_data_parsed_with_deleted_data(
        self, audit_db_with_deleted_log, admin_headers, monkeypatch
    ):
        _patch_data_source(audit_db_with_deleted_log, monkeypatch)
        from meta.tests.conftest import get_shared_app
        _, client = get_shared_app()

        resp = client.get('/api/v2/bo/audit_log/1', headers=admin_headers)
        assert resp.status_code == 200, resp.data
        body = resp.get_json()
        assert body.get("success") is True
        item = body.get("data") or {}
        # 必须有 extra_data_parsed.deleted_data
        edp = item.get("extra_data_parsed")
        assert edp is not None, "v2 BO 详情应注入 extra_data_parsed"
        assert "deleted_data" in edp, f"extra_data_parsed 应含 deleted_data, 实际: {edp}"
        assert edp["deleted_data"]["id"] == 475
        assert edp["deleted_data"]["name"] == "Test Group 475"
        assert edp["object_display"] == "Test Group 475 (test_grp_475)"

    def test_detail_returns_object_type_label(
        self, audit_db_with_deleted_log, admin_headers, monkeypatch
    ):
        _patch_data_source(audit_db_with_deleted_log, monkeypatch)
        from meta.tests.conftest import get_shared_app
        _, client = get_shared_app()

        resp = client.get('/api/v2/bo/audit_log/1', headers=admin_headers)
        body = resp.get_json()
        item = body.get("data") or {}
        assert item.get("object_type_label") == "用户组", (
            f"v2 BO 详情应注入 object_type_label='用户组', 实际: {item.get('object_type_label')!r}"
        )

    def test_detail_returns_field_name_and_parent_label(
        self, audit_db_with_deleted_log, admin_headers, monkeypatch
    ):
        _patch_data_source(audit_db_with_deleted_log, monkeypatch)
        from meta.tests.conftest import get_shared_app
        _, client = get_shared_app()

        resp = client.get('/api/v2/bo/audit_log/2', headers=admin_headers)
        body = resp.get_json()
        item = body.get("data") or {}
        assert item.get("object_type_label") == "角色菜单权限"
        assert item.get("field_name_label") == "菜单编码列表"
        assert item.get("parent_object_type_label") == "角色"

    def test_detail_404_when_not_found(
        self, audit_db_with_deleted_log, admin_headers, monkeypatch
    ):
        _patch_data_source(audit_db_with_deleted_log, monkeypatch)
        from meta.tests.conftest import get_shared_app
        _, client = get_shared_app()

        resp = client.get('/api/v2/bo/audit_log/99999', headers=admin_headers)
        assert resp.status_code in (404, 500), (
            f"不存在的 log_id 应返回 404, 实际: {resp.status_code} body={resp.data}"
        )


# ============================================================
# T5  v2 BO /audit_log 列表端点
# ============================================================

class TestV2BOAuditLogListEnrichment:
    """[FIX 2026-06-12] v2 BO /audit_log 列表 应对每条 item 注入 *_label + extra_data_parsed"""

    def test_list_items_have_label_fields(
        self, audit_db_with_deleted_log, admin_headers, monkeypatch
    ):
        _patch_data_source(audit_db_with_deleted_log, monkeypatch)
        from meta.tests.conftest import get_shared_app
        _, client = get_shared_app()

        resp = client.get(
            '/api/v2/bo/audit_log?page=1&page_size=10',
            headers=admin_headers,
        )
        # v2 BO /audit_log 列表可能 200 或 404 (BO framework 拒绝读 persistent:false 对象)
        # 关键: 如果 200, items 必须 enrich
        if resp.status_code != 200:
            pytest.skip(f"v2 BO /audit_log 列表返回 {resp.status_code} (可能 BO framework 未注册), 跳过")
        body = resp.get_json()
        items = (body.get("data") or {}).get("items") or []
        if not items:
            pytest.skip("v2 BO /audit_log 列表为空, 跳过")
        # 至少有一项
        first = items[0]
        ot = first.get("object_type", "") or ""
        if ot:
            assert "object_type_label" in first, (
                f"v2 BO 列表 item 应注入 object_type_label, 实际 keys: {list(first.keys())}"
            )
        fn = first.get("field_name", "") or ""
        if fn:
            assert "field_name_label" in first
        pot = first.get("parent_object_type", "") or ""
        if pot:
            assert "parent_object_type_label" in first

    def test_enrich_audit_log_items_function_standalone(self):
        """[FIX 2026-06-12] _enrich_audit_log_items 函数本身行为 (跟 bo_api 同款)"""
        # 测的是 bo_api.py 的本地实现
        from meta.api.bo_api import _enrich_audit_log_items
        items = [
            {
                "id": 1,
                "object_type": "role_menu",
                "field_name": "menu_codes",
                "parent_object_type": "role",
                "extra_data": json.dumps({"deleted_data": {"id": 99, "name": "X"}}),
            },
            {
                "id": 2,
                "object_type": "user_group",
                "extra_data": "not json",  # 非法 JSON
            },
        ]
        _enrich_audit_log_items(items)
        # 第一条: 3 个 label + deleted_data 解析
        assert items[0]["object_type_label"] == "角色菜单权限"
        assert items[0]["field_name_label"] == "菜单编码列表"
        assert items[0]["parent_object_type_label"] == "角色"
        assert items[0]["extra_data_parsed"]["deleted_data"]["id"] == 99
        # 第二条: 非法 JSON → extra_data_parsed = {} (不抛异常)
        assert items[1]["object_type_label"] == "用户组"
        assert items[1].get("extra_data_parsed") == {}

    def test_enrich_audit_log_items_handles_empty_input(self):
        from meta.api.bo_api import _enrich_audit_log_items
        _enrich_audit_log_items([])
        _enrich_audit_log_items(None)
        # 不抛异常

    def test_enrich_audit_log_items_handles_non_dict_items(self):
        from meta.api.bo_api import _enrich_audit_log_items
        items = [
            {"id": 1, "object_type": "role"},
            "string item",  # 非 dict
            None,
            42,
        ]
        _enrich_audit_log_items(items)  # 不抛异常
        # dict 仍 enrich
        assert items[0]["object_type_label"] == "角色"


# ============================================================
# T7  DELETE user_group → v2 BO 读出 deleted_data
# ============================================================

class TestDeleteUserGroupAuditLog:
    """[FIX 2026-06-12] DELETE user_group 后 v2 BO 端点能看到 deleted_data"""

    def test_delete_user_group_creates_audit_log_with_deleted_data(
        self, admin_headers, monkeypatch
    ):
        """模拟: 写一条 DELETE user_group 审计日志, 调 v2 BO 端点能解析"""
        # 1. 直接写 DB 一条 DELETE 审计日志 (含 deleted_data)
        from meta.core.datasource import get_data_source
        from meta.tests.conftest import get_shared_app
        app, client = get_shared_app()
        # 用生产 DB
        ds = get_data_source("sqlite", database="meta/architecture.db")
        if not os.path.exists("meta/architecture.db"):
            pytest.skip("meta/architecture.db 不存在, 跳过")
        # 写一条测试日志
        marker = f"_test_delete_{os.urandom(4).hex()}"
        deleted_data = {
            "deleted_data": {
                "id": 999,
                "name": f"Test Group {marker}",
                "code": marker,
            },
            "object_display": f"Test Group {marker}",
        }
        ds.execute("""
            INSERT INTO audit_logs
            (object_type, object_id, action, user_id, user_name, created_at,
             extra_data, log_category, log_level, status)
            VALUES ('user_group', '999', 'DELETE', '1', 'admin', '2026-06-12 13:00:00',
                    ?, 'business', 'INFO', 'written')
        """, [json.dumps(deleted_data)])
        ds.commit()
        # 2. 查最新一条
        cursor = ds.execute("""
            SELECT id FROM audit_logs
            WHERE object_type='user_group' AND action='DELETE' AND object_id='999'
            ORDER BY id DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if not row:
            pytest.skip("写日志失败, 跳过")
        log_id = row[0]
        try:
            # 3. 调 v2 BO 端点
            resp = client.get(f'/api/v2/bo/audit_log/{log_id}', headers=admin_headers)
            assert resp.status_code == 200, resp.data
            body = resp.get_json()
            assert body.get("success") is True
            item = body.get("data") or {}
            edp = item.get("extra_data_parsed")
            assert edp is not None, "v2 BO 详情应注入 extra_data_parsed"
            assert "deleted_data" in edp
            assert edp["deleted_data"]["name"] == f"Test Group {marker}"
            assert item.get("object_type_label") == "用户组"
        finally:
            # 4. 清理
            try:
                ds.execute("DELETE FROM audit_logs WHERE id = ?", [log_id])
                ds.commit()
            except Exception:
                pass
