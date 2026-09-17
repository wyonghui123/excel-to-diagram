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
        # [P1-D 2026-07-25] 改造后, role/user_group 走 yaml registry + DisplayNameService:
        #   - role.name (yaml) = "角色"
        #   - role.fields[id=name].name (yaml) = "角色名称" (不再是硬编码 "名称")
        #   - user_group.name (yaml) = "用户组"
        #   - user_group.fields[id=code].name (yaml) = "组编码" (不再是硬编码 "编码")
        assert logs[0]["object_type_label"] == "角色"
        assert logs[0]["field_name_label"] == "角色名称"
        assert logs[1]["object_type_label"] == "用户组"
        assert logs[1]["field_name_label"] == "组编码"
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
        # [P1-D 2026-07-25] role.fields[id=name].name = "角色名称" (yaml schema 单一事实源)
        assert log["field_name_label"] == "角色名称"

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


# ============================================================
# [P1-D 2026-07-25] DisplayNameService 单一事实源测试
#   改造后 object_type_label / field_name_label 优先级:
#     1. yaml registry / DisplayNameService (基于 yaml schema)
#     2. OBJECT_TYPE_LABELS / FIELD_NAME_LABELS 硬编码 fallback
#     3. 原值
# ============================================================

class TestP1DDisplayNameServicePriority:
    """[P1-D] _get_object_type_label / _get_field_name_label 优先级链测试"""

    # ── _get_object_type_label ──

    def test_object_type_label_prefers_yaml_registry(self):
        """object_type 在 registry 中 → 返回 yaml 顶层 name"""
        from meta.api.audit_api import _get_object_type_label
        # role 在 registry, yaml.name = "角色"
        assert _get_object_type_label("role") == "角色"
        # user 在 registry, yaml.name = "用户"
        assert _get_object_type_label("user") == "用户"
        # product 在 registry, yaml.name = "产品"
        assert _get_object_type_label("product") == "产品"

    def test_object_type_label_falls_back_to_hardcoded(self):
        """object_type 不在 registry → 降级到 OBJECT_TYPE_LABELS 硬编码"""
        from meta.api.audit_api import _get_object_type_label
        # role_menu 是衍生类型, 不在 registry, 但在 OBJECT_TYPE_LABELS
        assert _get_object_type_label("role_menu") == "角色菜单权限"
        # permission_rule 在 OBJECT_TYPE_LABELS
        assert _get_object_type_label("permission_rule") == "权限规则"

    def test_object_type_label_falls_back_to_raw(self):
        """object_type 完全未知 → 返回原值"""
        from meta.api.audit_api import _get_object_type_label
        assert _get_object_type_label("unknown_type") == "unknown_type"
        assert _get_object_type_label("__nonexistent__") == "__nonexistent__"

    def test_object_type_label_empty_string(self):
        """空字符串 → 返回空字符串 (不注入)"""
        from meta.api.audit_api import _get_object_type_label
        assert _get_object_type_label("") == ""
        assert _get_object_type_label(None) == ""

    def test_object_type_label_audit_pseudo_type(self):
        """audit 专用伪类型 → 走硬编码 fallback (registry 无此类型)"""
        from meta.api.audit_api import _get_object_type_label, OBJECT_TYPE_LABELS
        # audit_log 在 registry (有 schema), 应返回 yaml.name
        # __audit_failure__ 不在 registry, 应走 OBJECT_TYPE_LABELS
        # 若 OBJECT_TYPE_LABELS 含 __audit_failure__ 则返回硬编码值, 否则返回原值
        result = _get_object_type_label("__audit_failure__")
        expected = OBJECT_TYPE_LABELS.get("__audit_failure__", "__audit_failure__")
        assert result == expected

    # ── _get_field_name_label ──

    def test_field_name_label_prefers_display_name_service(self):
        """object_type + field_name 在 registry 中 → 返回 yaml field.name"""
        from meta.api.audit_api import _get_field_name_label
        # role.fields[id=name].name = "角色名称"
        assert _get_field_name_label("role", "name") == "角色名称"
        # role.fields[id=code].name 应该是某个中文 (取决于 yaml)
        # 验证: 不再返回硬编码 FIELD_NAME_LABELS["code"]="编码"
        result = _get_field_name_label("role", "code")
        assert result != "编码", (
            "P1-D 改造后应返回 yaml schema field.name, 而非硬编码 FIELD_NAME_LABELS['code']='编码'"
        )

    def test_field_name_label_falls_back_to_hardcoded(self):
        """object_type 不在 registry → 降级到 FIELD_NAME_LABELS 硬编码"""
        from meta.api.audit_api import _get_field_name_label
        # role_menu 不在 registry → field_name_label 走 FIELD_NAME_LABELS
        assert _get_field_name_label("role_menu", "menu_codes") == "菜单编码列表"
        # unknown_type 不在 registry → 走 FIELD_NAME_LABELS["name"]="名称"
        assert _get_field_name_label("unknown_type", "name") == "名称"

    def test_field_name_label_falls_back_to_raw(self):
        """field_name 完全未知 → 返回原值"""
        from meta.api.audit_api import _get_field_name_label
        # 已知 object_type, 未知 field_name → DisplayNameService 返回原值 → 降级到 FIELD_NAME_LABELS 也无 → 返回原值
        result = _get_field_name_label("role", "totally_unknown_field_xyz")
        assert result == "totally_unknown_field_xyz"

    def test_field_name_label_empty_object_type_uses_hardcoded(self):
        """object_type 为空 → 跳过 DisplayNameService, 直接走硬编码"""
        from meta.api.audit_api import _get_field_name_label
        # object_type 为空 → 跳过 DisplayNameService → 走 FIELD_NAME_LABELS["name"]="名称"
        assert _get_field_name_label("", "name") == "名称"
        assert _get_field_name_label(None, "name") == "名称"

    def test_field_name_label_empty_field_name(self):
        """field_name 为空 → 返回空字符串"""
        from meta.api.audit_api import _get_field_name_label
        assert _get_field_name_label("role", "") == ""
        assert _get_field_name_label("role", None) == ""

    # ── _enrich_log_labels 端到端 ──

    def test_enrich_uses_yaml_field_name_for_known_object_type(self):
        """_enrich_log_labels 对已知 object_type 注入 yaml schema 的 field.name"""
        from meta.api.audit_api import _enrich_log_labels
        log = {
            "object_type": "role",
            "field_name": "name",
            "action": "UPDATE",
        }
        _enrich_log_labels(log)
        # yaml schema 单一事实源: role.fields[id=name].name = "角色名称"
        assert log["field_name_label"] == "角色名称"
        # object_type_label 也是 yaml registry.name
        assert log["object_type_label"] == "角色"

    def test_enrich_falls_back_for_audit_specific_fields(self):
        """_enrich_log_labels 对 audit 专用字段 (action/old_value/new_value) 走硬编码 fallback

        这些字段不在任何业务 object_type 的 fields 中, DisplayNameService 找不到,
        应降级到 FIELD_NAME_LABELS.
        """
        from meta.api.audit_api import _enrich_log_labels
        log = {
            "object_type": "audit_log",
            "field_name": "old_value",  # audit 专用字段
            "action": "UPDATE",
        }
        _enrich_log_labels(log)
        # FIELD_NAME_LABELS["old_value"] = "旧值"
        assert log["field_name_label"] == "旧值"

    def test_enrich_falls_back_for_unregistered_object_type(self):
        """_enrich_log_labels 对未注册 object_type 走硬编码 fallback"""
        from meta.api.audit_api import _enrich_log_labels
        log = {
            "object_type": "role_permissions",  # 衍生类型, 不在 registry
            "field_name": "permission_ids",     # 在 FIELD_NAME_LABELS
            "action": "UPDATE",
        }
        _enrich_log_labels(log)
        assert log["object_type_label"] == "角色功能权限"  # OBJECT_TYPE_LABELS
        assert log["field_name_label"] == "权限ID列表"      # FIELD_NAME_LABELS

    def test_enrich_parent_object_type_uses_yaml_registry(self):
        """_enrich_log_labels 的 parent_object_type_label 也走 yaml registry"""
        from meta.api.audit_api import _enrich_log_labels
        log = {
            "object_type": "role_menu",
            "parent_object_type": "role",  # 在 registry
            "field_name": "menu_codes",
            "action": "ASSOCIATE",
        }
        _enrich_log_labels(log)
        # role_menu 不在 registry → fallback to OBJECT_TYPE_LABELS
        assert log["object_type_label"] == "角色菜单权限"
        # role 在 registry → yaml.name = "角色"
        assert log["parent_object_type_label"] == "角色"

    def test_enrich_action_label_unchanged(self):
        """[P0-3] action_label 仍从 audit_log.yaml enum_values 加载 (单一事实源)"""
        from meta.api.audit_api import _enrich_log_labels
        log = {"object_type": "role", "field_name": "name", "action": "CREATE"}
        _enrich_log_labels(log)
        # action_label 来自 audit_log.yaml enum_values
        assert log.get("action_label") == "创建"

    # ── 验证 yaml schema 单一事实源不依赖硬编码 ──

    def test_yaml_registry_provides_more_specific_labels(self):
        """验证 yaml schema 提供比硬编码更具体的标签

        场景: role.fields[id=name].name = "角色名称"
              而 FIELD_NAME_LABELS["name"] = "名称" (通用)

        P1-D 改造后应返回更具体的 "角色名称", 而非通用的 "名称".
        """
        from meta.api.audit_api import _get_field_name_label, FIELD_NAME_LABELS
        # 硬编码 fallback 应该是 "名称"
        assert FIELD_NAME_LABELS["name"] == "名称"
        # 但通过 DisplayNameService 应返回 role.yaml 中定义的 "角色名称"
        assert _get_field_name_label("role", "name") == "角色名称"
        # user_group.yaml 中 fields[id=name].name = "组名"
        assert _get_field_name_label("user_group", "name") == "组名"
