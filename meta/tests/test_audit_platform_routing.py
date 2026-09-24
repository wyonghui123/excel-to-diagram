# -*- coding: utf-8 -*-
"""[多产品平台] §6.5.3 P0 — 审计恒落平台库（模型乙）测试

背景:
    `APP_DB_ROUTING=1` 时应用 BO 的 CRUD 数据落应用库，而应用库只建应用 BO 表
    （`SchemaMigrator.migrate()` 只建传入的 BO），**不含** `audit_logs` /
    `audit_logs_archive` / `v_audit_all` / `users`。审计写入点与业务数据共用
    同一个 ActionExecutor ⇒ 若审计跟随请求绑定写向应用库会**静默失败**
    （`_write_audit_log_v2` 只记 warning），同时 `updated_at` 等审计派生字段
    读不到而变空（用户可见）。

覆盖:
- `resolve_audit_data_source()` 的开关语义（关闭 → 业务库本身，零变化）
- `get_platform_data_source()` 忽略请求级绑定
- `AuditLogger.audit_ds` / `ManageService.audit_ds` 的接线
- 端到端：审计写入落平台库、应用库无审计表也不报错
- `enrich_audit_virtual_fields()` 的 audit_derived 分支走平台库
- `AssociationEngine._write_audit_log` / `fallback.query_audit_logs` 走平台库

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §6.5.3 P0
"""
import os
import sqlite3

import pytest

pytestmark = pytest.mark.unit

# 平台库最小审计 schema（audit_logs + users 都是平台资源）
_PLATFORM_DDL = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type VARCHAR(200), object_id VARCHAR(200), action VARCHAR(200),
    field_name VARCHAR(200), old_value TEXT, new_value TEXT,
    user_id VARCHAR(200), user_name VARCHAR(200),
    ip_address VARCHAR(200), user_agent VARCHAR(500),
    created_at VARCHAR(200), trace_id VARCHAR(200), transaction_id VARCHAR(200),
    agent_id VARCHAR(200), agent_session_id VARCHAR(200),
    tool_call_id VARCHAR(200), agent_reasoning TEXT,
    status VARCHAR(100) DEFAULT 'written', extra_data TEXT,
    parent_object_type VARCHAR(200), parent_object_id VARCHAR(200),
    log_category VARCHAR(100), log_level VARCHAR(50), outcome VARCHAR(50),
    retention_until VARCHAR(200), cascade_root_id VARCHAR(200),
    cascade_root_action VARCHAR(200), error_message TEXT
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, username VARCHAR(200), display_name VARCHAR(200)
);
"""


def _make_ds(path, ddl=""):
    conn = sqlite3.connect(str(path))
    if ddl:
        conn.executescript(ddl)
    conn.commit()
    conn.close()
    from meta.core.datasource import get_data_source
    return get_data_source("sqlite", database=str(path))


@pytest.fixture(autouse=True)
def isolated_binding(monkeypatch):
    """隔离每个用例：清空应用绑定与数据源缓存。"""
    monkeypatch.delenv("APP_DB_ROUTING", raising=False)
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, unbind_app_data_source,
    )
    unbind_app_data_source()
    yield
    unbind_app_data_source()
    _clear_data_source_cache_for_testing()


@pytest.fixture
def platform_ds(tmp_path):
    """平台库：含 audit_logs + users。"""
    return _make_ds(tmp_path / "platform.db", _PLATFORM_DDL)


@pytest.fixture
def app_ds(tmp_path):
    """应用库：空库，**无**审计表（真实应用库的样子）。"""
    return _make_ds(tmp_path / "app.db")


@pytest.fixture
def platform_installed(monkeypatch, platform_ds):
    """把平台库装到全局 bo_framework 上（`get_platform_data_source()` 的权威来源）。"""
    from meta.core.bo_framework import bo_framework
    monkeypatch.setattr(bo_framework, "_data_source", platform_ds, raising=False)
    return platform_ds


class TestResolveAuditDataSource:
    """开关语义：关闭 ⇒ 返回业务库本身（存量零风险）。"""

    def test_routing_off_returns_business_ds(self, app_ds, platform_installed):
        from meta.core.datasource import resolve_audit_data_source
        assert resolve_audit_data_source(app_ds) is app_ds

    def test_routing_on_returns_platform_ds(self, app_ds, platform_installed, monkeypatch):
        monkeypatch.setenv("APP_DB_ROUTING", "1")
        from meta.core.datasource import resolve_audit_data_source
        resolved = resolve_audit_data_source(app_ds)
        assert resolved is platform_installed
        assert resolved is not app_ds

    def test_get_platform_data_source_ignores_binding(self, platform_installed, monkeypatch):
        monkeypatch.setenv("APP_DB_ROUTING", "1")
        from meta.core.datasource import (
            bind_app_data_source, get_bound_app_data_source, get_platform_data_source,
        )
        bind_app_data_source("hello_world")
        assert get_bound_app_data_source() is not platform_installed
        assert get_platform_data_source() is platform_installed

    def test_platform_ds_falls_back_to_meta_db_path(self, monkeypatch, tmp_path):
        """未初始化（或循环导入）时回落到 `get_meta_db_path()`。"""
        from meta.core.bo_framework import bo_framework
        monkeypatch.setattr(bo_framework, "_data_source", None, raising=False)
        target = tmp_path / "meta_fallback.db"
        import meta.core.db_path as db_path_mod
        monkeypatch.setattr(db_path_mod, "get_meta_db_path", lambda: str(target))

        from meta.core.datasource import get_platform_data_source
        ds = get_platform_data_source()
        assert os.path.normcase(ds._db_path) == os.path.normcase(str(target))


class TestAuditConsumerWiring:
    """审计取用点的接线：AuditLogger / ManageService。"""

    def test_audit_logger_uses_business_ds_when_routing_off(self, app_ds):
        from meta.core.action_executor import ActionExecutor
        assert ActionExecutor(app_ds).audit_logger.audit_ds is app_ds

    def test_audit_logger_uses_platform_ds_when_routing_on(
        self, app_ds, platform_installed, monkeypatch,
    ):
        monkeypatch.setenv("APP_DB_ROUTING", "1")
        from meta.core.action_executor import ActionExecutor
        assert ActionExecutor(app_ds).audit_logger.audit_ds is platform_installed

    def test_explicit_audit_data_source_wins(self, app_ds, platform_installed):
        from meta.core.action_executor import AuditLogger
        logger = AuditLogger(app_ds, audit_data_source=platform_installed)
        assert logger.audit_ds is platform_installed

    def test_manage_service_audit_ds_follows_platform(
        self, app_ds, platform_installed, monkeypatch,
    ):
        monkeypatch.setenv("APP_DB_ROUTING", "1")
        from meta.services.manage_service import ManageService
        assert ManageService(app_ds).audit_ds is platform_installed


class TestAuditWriteEndToEnd:
    """端到端：审计写入落平台库；应用库无审计表也不抛错。"""

    def test_audit_write_lands_in_platform_not_app(
        self, app_ds, platform_installed, monkeypatch,
    ):
        monkeypatch.setenv("APP_DB_ROUTING", "1")
        from meta.core.action_executor import ActionExecutor

        ok = ActionExecutor(app_ds).audit_logger.log(
            object_type="greeting", object_id=1, action="CREATE",
        )

        assert ok is True
        rows = platform_installed.find("audit_logs", filters={"object_type": "greeting"})
        assert len(rows) == 1, "审计未落到平台库"
        assert app_ds.table_exists("audit_logs") is False, "应用库不应有审计表"

    def test_routing_off_writes_into_business_db(
        self, platform_ds, monkeypatch,
    ):
        """关闭路由时应用 BO 本就建在平台库 ⇒ 审计仍写同一个库（改造前行为）。"""
        from meta.core.action_executor import ActionExecutor

        ok = ActionExecutor(platform_ds).audit_logger.log(
            object_type="greeting", object_id=2, action="CREATE",
        )

        assert ok is True
        assert len(platform_ds.find("audit_logs", filters={"object_type": "greeting"})) == 1


class _StubRegistry:
    """只用于把 updated_at 策略钉在 audit_derived 上（真实注册表可能物化）。"""

    def get_strategy(self, table_name):
        from meta.core.materialization_registry import STRATEGY_AUDIT_DERIVED
        return STRATEGY_AUDIT_DERIVED

    def is_materialized(self, table_name):
        return False


class TestAuditDerivedReadRouting:
    """`updated_at` 派生：路由开启时从平台库的 audit_logs 读取。"""

    @staticmethod
    def _seed_update_log(ds):
        ds.insert("audit_logs", {
            "object_type": "greeting",
            "object_id": "7",
            "action": "UPDATE",
            "created_at": "2026-09-24T10:00:00",
        })

    @pytest.fixture(autouse=True)
    def pin_audit_derived_strategy(self, monkeypatch):
        import meta.core.materialization_registry as mr
        monkeypatch.setattr(mr, "get_registry", lambda: _StubRegistry())

    def test_routing_on_reads_platform_db(self, app_ds, platform_installed, monkeypatch):
        monkeypatch.setenv("APP_DB_ROUTING", "1")
        self._seed_update_log(platform_installed)

        from meta.core.audit_derived_fields import enrich_audit_virtual_fields
        rows = enrich_audit_virtual_fields(
            app_ds, "greeting", [{"id": 7, "created_at": "2026-09-01T00:00:00"}],
        )

        assert rows[0]["updated_at"] == "2026-09-24T10:00:00"

    def test_routing_off_reads_business_db(self, platform_ds):
        self._seed_update_log(platform_ds)

        from meta.core.audit_derived_fields import enrich_audit_virtual_fields
        rows = enrich_audit_virtual_fields(
            platform_ds, "greeting", [{"id": 7, "created_at": "2026-09-01T00:00:00"}],
        )

        assert rows[0]["updated_at"] == "2026-09-24T10:00:00"

    def test_routing_on_without_audit_tables_falls_back_to_created_at(
        self, app_ds, platform_installed, monkeypatch,
    ):
        """平台库查不到 UPDATE 记录 ⇒ 回落 created_at，而不是抛错或变空。"""
        monkeypatch.setenv("APP_DB_ROUTING", "1")

        from meta.core.audit_derived_fields import enrich_audit_virtual_fields
        rows = enrich_audit_virtual_fields(
            app_ds, "greeting", [{"id": 9, "created_at": "2026-09-01T00:00:00"}],
        )

        assert rows[0]["updated_at"] == "2026-09-01T00:00:00"


class TestAssociationAuditRouting:

    def test_association_engine_audit_uses_platform_ds(
        self, app_ds, platform_installed, monkeypatch,
    ):
        monkeypatch.setenv("APP_DB_ROUTING", "1")
        import meta.core.association_engine as ae

        seen = []
        monkeypatch.setattr(
            ae, "write_association_audit",
            lambda **kwargs: seen.append(kwargs.get("data_source")),
        )

        from types import SimpleNamespace
        context = SimpleNamespace(
            params={"src_id": 1}, object_type="greeting", user_id=1, user_name="admin",
            data_source=app_ds,
        )
        ae.AssociationEngine()._write_audit_log(context, "ASSOCIATE", "role", 5, "members")

        assert seen == [platform_installed]

    def test_query_audit_logs_reads_platform_ds(
        self, app_ds, platform_installed, monkeypatch,
    ):
        monkeypatch.setenv("APP_DB_ROUTING", "1")
        import meta.core.association.fallback as fb

        seen = []
        monkeypatch.setattr(
            fb, "_execute_audit_query",
            lambda ds, where, params, order_by="created_at DESC": seen.append(ds) or [],
        )

        from types import SimpleNamespace
        context = SimpleNamespace(
            params={"src_id": 1}, object_type="unknown_type", data_source=app_ds,
        )
        fb.query_audit_logs(context)

        assert seen, "未触发审计查询"
        assert all(ds is platform_installed for ds in seen)
