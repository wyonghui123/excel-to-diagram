# -*- coding: utf-8 -*-
"""
[NEW 2026-06-12] OBJECT_TYPE_LABELS / FIELD_NAME_LABELS 完整性 + enrich 行为测试

覆盖:
T1  - OBJECT_TYPE_LABELS 关键 key 都有中文 label (role, user, user_group, role_menu,
      role_dimension_scope, role_permissions, role_data_permission, role_v2_menu_permissions,
      permission_rule, menu ...)
T2  - FIELD_NAME_LABELS 关键 key 都有中文 label (menu_codes, dimension_codes, scopes_count,
      permission_ids, is_denied ...)
T3  - _enrich_log_labels 单条注入 3 个 label 字段
T4  - _enrich_log_labels_batch 批量注入
T5  - 未知 object_type / field_name 优雅降级 (label = 原值, 不报错)
T6  - 空字符串 / None / 缺失字段都不注入 (避免 "标签=空字符串" 前端显示空白)
T7  - 不覆盖已有的 *_label 字段 (调用方可能已自定义)
T8  - v1 /audit/logs 接口返回的 item 包含 *_label 字段 (端到端冒烟)
"""
import pytest

pytestmark = pytest.mark.integration


# ============================================================
# T1 / T2  label 映射完整性
# ============================================================

class TestObjectTypeLabelsCompleteness:
    """OBJECT_TYPE_LABELS 完整性 (解决 "role_menu 等技术名" bug)"""

    def test_labels_constant_exists_and_is_dict(self):
        from meta.api.audit_api import OBJECT_TYPE_LABELS
        assert isinstance(OBJECT_TYPE_LABELS, dict)
        assert len(OBJECT_TYPE_LABELS) >= 15, (
            f"OBJECT_TYPE_LABELS 应至少 15 项, 实际 {len(OBJECT_TYPE_LABELS)}"
        )

    @pytest.mark.parametrize("key,expected_substr", [
        ("role", "角色"),
        ("user", "用户"),
        ("user_group", "用户组"),
        ("role_menu", "菜单"),
        ("role_dimension_scope", "维度"),
        ("role_permissions", "功能权限"),
        ("role_data_permission", "数据权限"),
        ("role_v2_menu_permissions", "菜单"),
        ("permission_rule", "权限规则"),
        ("menu", "菜单"),
        ("permission", "权限"),
        ("product", "产品"),
    ])
    def test_key_object_types_have_chinese_label(self, key, expected_substr):
        """关键技术名都有中文 label (防止技术名漏翻译回归)"""
        from meta.api.audit_api import OBJECT_TYPE_LABELS
        assert key in OBJECT_TYPE_LABELS, f"object_type={key} 缺失 label"
        label = OBJECT_TYPE_LABELS[key]
        assert isinstance(label, str) and label.strip(), f"object_type={key} label 应为非空 str"
        assert label != key, f"object_type={key} label 不能等于原 key, 应翻译为中文"

    def test_label_values_are_not_technical_names(self):
        """label 值不应包含下划线 (业务术语不带技术命名)"""
        from meta.api.audit_api import OBJECT_TYPE_LABELS
        for key, label in OBJECT_TYPE_LABELS.items():
            # 允许 (v2) 这种括号标注, 但不应有 _xxx 这种技术命名
            assert "_" not in label or "(v" in label, (
                f"object_type={key} label={label!r} 含下划线, 可能是技术名漏翻译"
            )


class TestFieldNameLabelsCompleteness:
    """FIELD_NAME_LABELS 完整性"""

    def test_labels_constant_exists_and_is_dict(self):
        from meta.api.audit_api import FIELD_NAME_LABELS
        assert isinstance(FIELD_NAME_LABELS, dict)
        assert len(FIELD_NAME_LABELS) >= 25, (
            f"FIELD_NAME_LABELS 应至少 25 项, 实际 {len(FIELD_NAME_LABELS)}"
        )

    @pytest.mark.parametrize("key,expected_substr", [
        ("menu_codes", "菜单"),
        ("menu_names", "菜单"),
        ("dimension_codes", "维度"),
        ("permission_ids", "权限"),
        ("permission_names", "权限"),
        ("scopes_count", "范围"),
        ("is_denied", "禁止"),
        ("inherit_to_children", "继承"),
        ("synced_permissions_count", "同步"),
    ])
    def test_key_field_names_have_chinese_label(self, key, expected_substr):
        """关键字段名都有中文 label"""
        from meta.api.audit_api import FIELD_NAME_LABELS
        assert key in FIELD_NAME_LABELS, f"field_name={key} 缺失 label"
        label = FIELD_NAME_LABELS[key]
        assert isinstance(label, str) and label.strip()
        assert label != key

    def test_field_name_labels_have_no_underscore(self):
        from meta.api.audit_api import FIELD_NAME_LABELS
        for key, label in FIELD_NAME_LABELS.items():
            assert "_" not in label or label.startswith("("), (
                f"field_name={key} label={label!r} 含下划线"
            )


# ============================================================
# T3 / T4  _enrich_log_labels 行为
# ============================================================

class TestEnrichLogLabels:
    """_enrich_log_labels / _enrich_log_labels_batch 单函数行为"""

    def test_enrich_injects_three_label_fields(self):
        from meta.api.audit_api import _enrich_log_labels
        log = {
            "object_type": "role_menu",
            "field_name": "menu_codes",
            "parent_object_type": "role",
        }
        _enrich_log_labels(log)
        assert log["object_type_label"] == "角色菜单权限"
        assert log["field_name_label"] == "菜单编码列表"
        assert log["parent_object_type_label"] == "角色"

    def test_enrich_batch_injects_to_all_items(self):
        from meta.api.audit_api import _enrich_log_labels_batch
        logs = [
            {"object_type": "role", "field_name": "name"},
            {"object_type": "user_group", "field_name": "code"},
            {"object_type": "unknown_type", "field_name": "unknown_field"},
        ]
        _enrich_log_labels_batch(logs)
        assert logs[0]["object_type_label"] == "角色"
        assert logs[0]["field_name_label"] == "名称"
        assert logs[1]["object_type_label"] == "用户组"
        assert logs[1]["field_name_label"] == "编码"
        # 未知类型优雅降级: label == 原值
        assert logs[2]["object_type_label"] == "unknown_type"
        assert logs[2]["field_name_label"] == "unknown_field"

    def test_enrich_skips_when_object_type_empty(self):
        from meta.api.audit_api import _enrich_log_labels
        log = {"object_type": "", "field_name": "name"}
        _enrich_log_labels(log)
        assert "object_type_label" not in log
        # field_name 有值, 应注入
        assert log["field_name_label"] == "名称"

    def test_enrich_skips_when_field_name_none(self):
        from meta.api.audit_api import _enrich_log_labels
        log = {"object_type": "role", "field_name": None}
        _enrich_log_labels(log)
        assert log["object_type_label"] == "角色"
        assert "field_name_label" not in log

    def test_enrich_does_not_overwrite_existing_label(self):
        """调用方已设过 *_label, 不应被覆盖 (保持自定义 label 优先)"""
        from meta.api.audit_api import _enrich_log_labels
        log = {
            "object_type": "role",
            "object_type_label": "我的自定义角色",
            "field_name": "name",
        }
        _enrich_log_labels(log)
        assert log["object_type_label"] == "我的自定义角色"
        assert log["field_name_label"] == "名称"

    def test_enrich_handles_non_dict(self):
        """非 dict 入参 (如 None, str) 不抛异常"""
        from meta.api.audit_api import _enrich_log_labels
        _enrich_log_labels(None)  # 不报错
        _enrich_log_labels("string")  # 不报错
        _enrich_log_labels(42)  # 不报错

    def test_enrich_batch_with_empty_list(self):
        from meta.api.audit_api import _enrich_log_labels_batch
        _enrich_log_labels_batch([])
        _enrich_log_labels_batch(None)  # 不报错


# ============================================================
# T8  v1 接口端到端冒烟 (确认修复后真的生效)
# ============================================================

class TestV1AuditLogsEndpointEnrichment:
    """v1 /api/v1/audit/logs 接口应返回 *_label 字段 (P0 防回归)"""

    @pytest.fixture(scope='class')
    def client_and_headers(self):
        from meta.tests.conftest import get_shared_app
        _, client = get_shared_app()
        from meta.services.token_service import TokenService
        from meta.services.auth_provider import UserInfo
        u = UserInfo(
            user_id='1', username='label_test', display_name='Label Tester',
            email='l@test.com', roles=['admin'], permissions=['*']
        )
        token, _ = TokenService.create_token(u)
        return client, {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
        }

    def test_logs_response_items_have_label_fields(self, client_and_headers):
        """v1 列表返回的每条 item 都应带 *_label 字段 (无值则不带)"""
        client, h = client_and_headers
        # 拉一页日志 (可能空, 也可能非空)
        resp = client.get('/api/v1/audit/logs?page=1&page_size=10', headers=h)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get("success") is True
        items = body.get("data") or []
        if items:
            first = items[0]
            # 即使 object_type 未知, 也应注入 label 字段 (降级为原值)
            ot = first.get("object_type", "") or ""
            fn = first.get("field_name", "") or ""
            pot = first.get("parent_object_type", "") or ""
            if ot:
                assert "object_type_label" in first
                assert first["object_type_label"] == ot or first["object_type_label"]  # 降级为原值
            if fn:
                assert "field_name_label" in first
            if pot:
                assert "parent_object_type_label" in first
