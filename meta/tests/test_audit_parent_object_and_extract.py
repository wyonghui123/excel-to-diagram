# -*- coding: utf-8 -*-
"""
[NEW 2026-06-12] audit_api parent_object 联合查询 + _extract_deleted_data 测试

覆盖:
T2  - 仅 parent_object 查询: ?parent_object_type=role&parent_object_id=TEST_ROLE_ID
      → 返回所有 parent_object_type='role' AND parent_object_id=TEST_ROLE_ID 的日志
T3  - OR 联合查询: ?object_type=role&object_id=TEST_ROLE_ID&parent_object_type=role&parent_object_id=TEST_ROLE_ID
      → 返回 (object_type=role AND object_id=TEST_ROLE_ID) OR (parent_object_type=role AND parent_object_id=TEST_ROLE_ID)
T10 - _extract_deleted_data 解析 null / 空字符串 / 非法 JSON / 正常 JSON / bytes / dict 6 种输入
T11 - parent_object_type 单独传 (无 id) 不抛 500

设计: 真实 HTTP 链路 + 真实生产 DB (test.py 已有自动快照保护), 用 unique
TEST_ROLE_ID (基于 os.urandom) 隔离测试数据, 测试结束自动清理. 这比 mock
data_source 更稳: 因为 audit_api 在 init_audit_services 时固定了 _data_source,
而 Flask request handler 是按需查 _data_source, 但部分代码可能在初始化时缓存.

如果未来需要重构成不依赖生产 DB, 改成在 audit_api 层加一个可注入的
get_data_source() 函数.
"""
import json
import os
import sqlite3
import sys
import time
import uuid

import pytest

pytestmark = pytest.mark.integration


# ============================================================
# Helper: 真实生产 DB fixture, 用 unique parent_object_id 隔离
# ============================================================

def _now_str():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _rand_id():
    """生成一个不跟现有 ID 冲突的测试用 ID (8 位 hex)"""
    return int(os.urandom(3).hex(), 16) + 10000000  # > 10M 肯定不冲突


@pytest.fixture
def inserted_audit_logs():
    """在生产 DB 插入 7 条 parent_object=role + 1 条 role 自身 + 1 条另一个 role 的日志.

    返回 (TEST_ROLE_ID, OTHER_ROLE_ID, [log_ids]).

    测试结束自动清理 (DELETE FROM audit_logs WHERE id IN (...)).
    """
    from meta.core.datasource import get_data_source
    ds = get_data_source("sqlite", database="meta/architecture.db")
    if not os.path.exists("meta/architecture.db"):
        pytest.skip("meta/architecture.db 不存在, 跳过")

    TEST_ROLE_ID = _rand_id()
    OTHER_ROLE_ID = _rand_id()
    test_user_name = f"test_audit_parent_{os.urandom(2).hex()}"

    rows = []
    # 1 条 role 自身
    rows.append({
        "object_type": "role", "object_id": str(TEST_ROLE_ID),
        "action": "UPDATE", "field_name": "display_name",
        "old_value": "Old", "new_value": "New",
        "user_id": "1", "user_name": test_user_name,
        "ip_address": "127.0.0.1", "user_agent": "test",
        "created_at": _now_str(), "trace_id": uuid.uuid4().hex,
        "transaction_id": uuid.uuid4().hex,
        "log_category": "business", "log_level": "INFO",
        "extra_data": "", "parent_object_type": "", "parent_object_id": "",
    })
    # 6 条子对象, 全部 parent_object=role + parent_object_id=TEST_ROLE_ID
    for sub_type in ["role_menu", "role_dimension_scope", "role_permissions",
                     "role_data_permission", "role_v2_menu_permissions", "permission_rule"]:
        rows.append({
            "object_type": sub_type, "object_id": str(_rand_id()),
            "action": "UPDATE", "field_name": "menu_codes",
            "old_value": "old", "new_value": "new",
            "user_id": "1", "user_name": test_user_name,
            "ip_address": "127.0.0.1", "user_agent": "test",
            "created_at": _now_str(), "trace_id": uuid.uuid4().hex,
            "transaction_id": uuid.uuid4().hex,
            "log_category": "business", "log_level": "INFO",
            "extra_data": "", "parent_object_type": "role",
            "parent_object_id": str(TEST_ROLE_ID),
        })
    # 1 条 OTHER_ROLE_ID 的日志 (验证不串扰)
    rows.append({
        "object_type": "role_menu", "object_id": str(_rand_id()),
        "action": "UPDATE", "field_name": "menu_codes",
        "old_value": "x", "new_value": "y",
        "user_id": "1", "user_name": test_user_name,
        "ip_address": "127.0.0.1", "user_agent": "test",
        "created_at": _now_str(), "trace_id": uuid.uuid4().hex,
        "transaction_id": uuid.uuid4().hex,
        "log_category": "business", "log_level": "INFO",
        "extra_data": "", "parent_object_type": "role",
        "parent_object_id": str(OTHER_ROLE_ID),
    })

    inserted_ids = []
    for r in rows:
        cur = ds.execute("""
            INSERT INTO audit_logs
            (object_type, object_id, action, field_name, old_value, new_value,
             user_id, user_name, ip_address, user_agent, created_at,
             trace_id, transaction_id, log_category, log_level,
             extra_data, parent_object_type, parent_object_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [
            r["object_type"], r["object_id"], r["action"], r["field_name"],
            r["old_value"], r["new_value"], r["user_id"], r["user_name"],
            r["ip_address"], r["user_agent"], r["created_at"], r["trace_id"],
            r["transaction_id"], r["log_category"], r["log_level"],
            r["extra_data"], r["parent_object_type"], r["parent_object_id"],
        ])
        inserted_ids.append(cur.lastrowid)
    ds.commit()

    yield {
        "TEST_ROLE_ID": TEST_ROLE_ID,
        "OTHER_ROLE_ID": OTHER_ROLE_ID,
        "inserted_ids": inserted_ids,
        "test_user_name": test_user_name,
        "test_sub_types": ["role_menu", "role_dimension_scope", "role_permissions",
                           "role_data_permission", "role_v2_menu_permissions", "permission_rule"],
    }

    # Cleanup
    try:
        placeholders = ",".join("?" for _ in inserted_ids)
        ds.execute(f"DELETE FROM audit_logs WHERE id IN ({placeholders})", inserted_ids)
        ds.commit()
    except Exception as e:
        print(f"[cleanup] 删除测试日志失败: {e}")


def _mk_tok():
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo
    u = UserInfo(
        user_id='1', username='poq_test', display_name='POQ Test',
        email='p@test.com', roles=['admin'], permissions=['*']
    )
    token, _ = TokenService.create_token(u)
    return token


@pytest.fixture(scope='class')
def admin_headers():
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {_mk_tok()}',
    }


# ============================================================
# T2  parent_object 查询
# ============================================================

class TestAuditParentObjectQuery:
    """[FIX 2026-06-12] 角色详情"操作日志" tab 归集: parent_object 查询"""

    def test_pure_parent_object_query(self, inserted_audit_logs, admin_headers):
        """?parent_object_type=role&parent_object_id=TEST_ROLE_ID
        → 6 条 (不含 role 自身, 不含 OTHER_ROLE_ID 的 1 条)"""
        from meta.tests.conftest import get_shared_app
        _, client = get_shared_app()
        role_id = inserted_audit_logs["TEST_ROLE_ID"]
        other_id = inserted_audit_logs["OTHER_ROLE_ID"]

        resp = client.get(
            f'/api/v1/audit/logs?parent_object_type=role&parent_object_id={role_id}'
            f'&page=1&page_size=200',
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.data
        body = resp.get_json()
        assert body.get("success") is True
        assert body.get("total") == 6, (
            f"pure parent_object 应返回 total=6, 实际 {body.get('total')}"
        )
        data = body.get("data") or []
        assert len(data) == 6
        # DB 返 int, 比较时统一转 str
        role_id_s = str(role_id)
        other_id_s = str(other_id)
        for item in data:
            assert item.get("parent_object_type") == "role", f"parent_object_type 错: {item}"
            assert str(item.get("parent_object_id")) == role_id_s, f"parent_object_id 错: {item}"
            assert str(item.get("parent_object_id")) != other_id_s, "串扰到 OTHER_ROLE"
            # 6 条都是子对象, 不是 role 自身
            assert item.get("object_type") != "role", f"混入 role 自身: {item}"
        # 6 条的 object_type 应是 6 个子类型
        actual_types = sorted(item.get("object_type") for item in data)
        expected_types = sorted(inserted_audit_logs["test_sub_types"])
        assert actual_types == expected_types, (
            f"object_type 不匹配: 期望 {expected_types}, 实际 {actual_types}"
        )

    def test_or_combined_query(self, inserted_audit_logs, admin_headers):
        """?object_type=role&object_id=TEST_ROLE_ID&parent_object_type=role&parent_object_id=TEST_ROLE_ID
        → OR 联合, 应返回 7 条 (role 自身 + 6 个子对象)"""
        from meta.tests.conftest import get_shared_app
        _, client = get_shared_app()
        role_id = inserted_audit_logs["TEST_ROLE_ID"]
        other_id = inserted_audit_logs["OTHER_ROLE_ID"]
        role_id_s = str(role_id)
        other_id_s = str(other_id)

        resp = client.get(
            f'/api/v1/audit/logs'
            f'?object_type=role&object_id={role_id}'
            f'&parent_object_type=role&parent_object_id={role_id}'
            f'&page=1&page_size=200',
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.data
        body = resp.get_json()
        assert body.get("total") == 7, (
            f"OR 联合应返回 total=7 (role 自身 + 6 个子对象), 实际 {body.get('total')}"
        )
        data = body.get("data") or []
        # 1 条 role 自身
        own = [item for item in data
               if item.get("object_type") == "role"
               and str(item.get("object_id")) == role_id_s]
        # 6 条子对象
        children = [item for item in data
                    if item.get("parent_object_type") == "role"
                    and str(item.get("parent_object_id")) == role_id_s
                    and item.get("object_type") != "role"]
        assert len(own) == 1, f"应有 1 条 role 自身, 实际 {len(own)}"
        assert len(children) == 6, f"应有 6 条子对象, 实际 {len(children)}"
        # 不应包含 OTHER_ROLE_ID
        for item in data:
            assert str(item.get("parent_object_id")) != other_id_s, (
                f"串扰 OTHER_ROLE: {item}"
            )

    def test_parent_object_type_only_no_id_should_not_500(
        self, inserted_audit_logs, admin_headers
    ):
        """T11: 只传 parent_object_type 不传 parent_object_id, 不应抛 500"""
        from meta.tests.conftest import get_shared_app
        _, client = get_shared_app()

        resp = client.get(
            '/api/v1/audit/logs?parent_object_type=role&page=1&page_size=10',
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.data
        body = resp.get_json()
        assert body.get("success") is True

    def test_parent_object_id_only_no_type_should_not_500(
        self, inserted_audit_logs, admin_headers
    ):
        """T11: 只传 parent_object_id 不传 parent_object_type, 不应抛 500"""
        from meta.tests.conftest import get_shared_app
        _, client = get_shared_app()
        role_id = inserted_audit_logs["TEST_ROLE_ID"]
        other_id = inserted_audit_logs["OTHER_ROLE_ID"]
        role_id_s = str(role_id)
        other_id_s = str(other_id)

        resp = client.get(
            f'/api/v1/audit/logs?parent_object_id={role_id}&page=1&page_size=200',
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.data
        body = resp.get_json()
        data = body.get("data") or []
        my_logs = [
            item for item in data
            if str(item.get("parent_object_id")) == role_id_s
        ]
        assert len(my_logs) == 6, (
            f"parent_object_id 单独应返回 6 条子对象日志, 实际 {len(my_logs)}"
        )
        for item in my_logs:
            assert str(item.get("parent_object_id")) == role_id_s
            assert str(item.get("parent_object_id")) != other_id_s

    def test_parent_object_no_match(self, admin_headers):
        """parent_object 查询无匹配 → 返回空, 不抛 500"""
        from meta.tests.conftest import get_shared_app
        _, client = get_shared_app()
        fake_id = 999999999

        resp = client.get(
            f'/api/v1/audit/logs?parent_object_type=role&parent_object_id={fake_id}&page=1&page_size=10',
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get("total") == 0

    def test_parent_object_does_not_leak_other_role(
        self, inserted_audit_logs, admin_headers
    ):
        """防串扰: 查询 TEST_ROLE_ID 不应返回 OTHER_ROLE_ID 的日志"""
        from meta.tests.conftest import get_shared_app
        _, client = get_shared_app()
        role_id = inserted_audit_logs["TEST_ROLE_ID"]
        other_id = inserted_audit_logs["OTHER_ROLE_ID"]
        other_id_s = str(other_id)

        resp = client.get(
            f'/api/v1/audit/logs?parent_object_type=role&parent_object_id={role_id}'
            f'&page=1&page_size=200',
            headers=admin_headers,
        )
        body = resp.get_json()
        data = body.get("data") or []
        for item in data:
            assert str(item.get("parent_object_id")) != other_id_s, (
                f"查询 parent_object_id={role_id} 串扰到 other_role={other_id}: {item}"
            )


# ============================================================
# T10  _extract_deleted_data 边界 (纯函数测试, 无 DB 依赖)
# ============================================================

class TestExtractDeletedData:
    """[FIX 2026-06-11] _extract_deleted_data 6 种输入边界"""

    def test_empty_string_returns_empty_dict(self):
        from meta.api.audit_api import _extract_deleted_data
        assert _extract_deleted_data("") == {}
        assert _extract_deleted_data(None) == {}

    def test_valid_json_with_deleted_data(self):
        from meta.api.audit_api import _extract_deleted_data
        raw = json.dumps({
            "deleted_data": {"id": 1, "name": "deleted_group"},
            "object_display": "Group A",
        })
        result = _extract_deleted_data(raw)
        assert result["deleted_data"]["id"] == 1
        assert result["deleted_data"]["name"] == "deleted_group"
        assert result["object_display"] == "Group A"

    def test_valid_json_without_deleted_data(self):
        """合法 JSON 但无 deleted_data 字段, 也应正常解析"""
        from meta.api.audit_api import _extract_deleted_data
        raw = json.dumps({"other": "field", "count": 5})
        result = _extract_deleted_data(raw)
        assert result == {"other": "field", "count": 5}
        assert "deleted_data" not in result

    def test_invalid_json_returns_empty_dict(self):
        from meta.api.audit_api import _extract_deleted_data
        # 非法 JSON
        assert _extract_deleted_data("not json") == {}
        assert _extract_deleted_data("{incomplete") == {}
        assert _extract_deleted_data("null") == {}
        assert _extract_deleted_data("123") == {}  # JSON 合法但不是 dict

    def test_dict_input_returns_as_is(self):
        """已经解析过的 dict, 直接返回"""
        from meta.api.audit_api import _extract_deleted_data
        d = {"deleted_data": {"id": 1}}
        assert _extract_deleted_data(d) == d

    def test_bytes_input_decoded(self):
        from meta.api.audit_api import _extract_deleted_data
        raw = json.dumps({"deleted_data": {"id": 99}}).encode("utf-8")
        result = _extract_deleted_data(raw)
        assert result["deleted_data"]["id"] == 99

    def test_nested_list_value_at_root_returns_empty(self):
        """JSON 是 list 而不是 dict, 应返回空 dict (业务要求顶层是 dict)"""
        from meta.api.audit_api import _extract_deleted_data
        assert _extract_deleted_data("[1,2,3]") == {}
        assert _extract_deleted_data('"just a string"') == {}

    def test_extra_data_for_blocked_delete(self):
        """DELETE_BLOCKED 场景: extra_data 应含 blocked_reason 字段"""
        from meta.api.audit_api import _extract_deleted_data
        raw = json.dumps({
            "blocked_reason": "Has associated users",
            "deleted_data": {"id": 1, "name": "attempted_to_delete"},
        })
        result = _extract_deleted_data(raw)
        assert result["blocked_reason"] == "Has associated users"
        assert result["deleted_data"]["id"] == 1
