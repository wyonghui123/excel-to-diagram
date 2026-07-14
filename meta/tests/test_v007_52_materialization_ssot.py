"""Tests for V007.52 MaterializationRegistry SSOT (2026-07-14)

覆盖场景：
1. SSOT 文件加载 + 单例
2. strategy 分类（business_trigger / audit_callback / application_explicit / audit_derived / none）
3. is_materialized() 判断
4. get_audit_callback_tables() 返回正确目标表
5. get_updated_at() 统一入口（materialized / audit_derived / none）
6. v007_51 从 SSOT 读取目标表
7. virtual_sort 从 SSOT 判断物化列
"""
import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


class TestV00752MaterializationSSOT:
    """V007.52 SSOT 注册表测试"""

    def setup_method(self):
        """每个测试前重置单例（保证干净状态）"""
        from meta.core.materialization_registry import MaterializationRegistry
        MaterializationRegistry.reset()

    def test_registry_loads_default_ssot(self):
        """场景 1：单例加载默认 SSOT 文件"""
        from meta.core.materialization_registry import get_registry
        registry = get_registry()

        assert registry._loaded, "SSOT 应已加载"
        entries = registry.get_all_entries()
        assert len(entries) > 10, f"应有 >10 个 entry，实际 {len(entries)}"

    def test_strategy_classification(self):
        """场景 2：各策略分类正确"""
        from meta.core.materialization_registry import (
            get_registry,
            STRATEGY_BUSINESS_TRIGGER,
            STRATEGY_AUDIT_CALLBACK,
            STRATEGY_APPLICATION_EXPLICIT,
            STRATEGY_AUDIT_DERIVED,
            STRATEGY_NONE,
        )
        registry = get_registry()

        # business_trigger
        assert registry.get_strategy("roles") == STRATEGY_BUSINESS_TRIGGER
        assert registry.get_strategy("user_groups") == STRATEGY_BUSINESS_TRIGGER

        # audit_callback (V007.51)
        assert registry.get_strategy("enum_types") == STRATEGY_AUDIT_CALLBACK
        assert registry.get_strategy("enum_values") == STRATEGY_AUDIT_CALLBACK
        assert registry.get_strategy("users") == STRATEGY_AUDIT_CALLBACK

        # application_explicit
        assert registry.get_strategy("ai_async_tasks") == STRATEGY_APPLICATION_EXPLICIT
        assert registry.get_strategy("filter_variants") == STRATEGY_APPLICATION_EXPLICIT

        # audit_derived
        assert registry.get_strategy("products") == STRATEGY_AUDIT_DERIVED
        assert registry.get_strategy("versions") == STRATEGY_AUDIT_DERIVED

        # none
        assert registry.get_strategy("group_data_permissions") == STRATEGY_NONE

    def test_is_materialized(self):
        """场景 3：is_materialized 判断正确"""
        from meta.core.materialization_registry import get_registry
        registry = get_registry()

        # True: business_trigger / audit_callback / application_explicit
        assert registry.is_materialized("enum_types") is True
        assert registry.is_materialized("users") is True
        assert registry.is_materialized("roles") is True
        assert registry.is_materialized("ai_async_tasks") is True

        # False: audit_derived / none / 未注册
        assert registry.is_materialized("products") is False
        assert registry.is_materialized("group_data_permissions") is False
        assert registry.is_materialized("unknown_table_xyz") is False

    def test_get_audit_callback_tables(self):
        """场景 4：audit_callback 目标表清单"""
        from meta.core.materialization_registry import get_registry
        registry = get_registry()
        targets = registry.get_audit_callback_tables()
        target_dict = dict(targets)

        assert "enum_types" in target_dict
        assert "enum_values" in target_dict
        assert "users" in target_dict
        assert target_dict["enum_types"] == "enum_type"
        assert target_dict["users"] == "user"

    def test_needs_audit_derived(self):
        """场景 5：needs_audit_derived 正确识别"""
        from meta.core.materialization_registry import get_registry
        registry = get_registry()

        assert registry.needs_audit_derived("products") is True
        assert registry.needs_audit_derived("versions") is True
        assert registry.needs_audit_derived("enum_types") is False  # 物化
        assert registry.needs_audit_derived("unknown_xyz") is False

    def test_get_by_object_type(self):
        """场景 6：按 object_type 反查"""
        from meta.core.materialization_registry import get_registry
        registry = get_registry()

        entry = registry.get_by_object_type("enum_type")
        assert entry is not None
        assert entry["name"] == "enum_types"
        assert entry["strategy"] == "audit_callback"

        entry = registry.get_by_object_type("role")
        assert entry is not None
        assert entry["name"] == "roles"

        assert registry.get_by_object_type("unknown_xyz") is None

    def test_get_updated_at_materialized(self, tmp_path):
        """场景 7a：get_updated_at - 物化列路径"""
        from meta.core.materialization_registry import get_updated_at

        # 创建临时 DB
        db = str(tmp_path / "test.db")
        conn = sqlite3.connect(db)
        conn.execute("""
            CREATE TABLE enum_types (
                id INTEGER PRIMARY KEY, name TEXT, updated_at TEXT
            )
        """)
        conn.execute("INSERT INTO enum_types VALUES (1, 'Status', '2026-07-14T12:00:00')")
        conn.commit()

        class MockDS:
            def execute(self, sql, params):
                return conn.execute(sql, params)

        result = get_updated_at(MockDS(), "enum_types", 1, object_type="enum_type")
        assert result == "2026-07-14T12:00:00"
        conn.close()

    def test_get_updated_at_materialized_null(self, tmp_path):
        """场景 7b：物化列路径返回 NULL（无数据）"""
        from meta.core.materialization_registry import get_updated_at

        db = str(tmp_path / "test.db")
        conn = sqlite3.connect(db)
        conn.execute("""
            CREATE TABLE enum_types (
                id INTEGER PRIMARY KEY, name TEXT, updated_at TEXT
            )
        """)
        conn.commit()

        class MockDS:
            def execute(self, sql, params):
                return conn.execute(sql, params)

        result = get_updated_at(MockDS(), "enum_types", 999, fallback="FALLBACK_VAL")
        assert result == "FALLBACK_VAL"
        conn.close()

    def test_get_updated_at_audit_derived(self, tmp_path):
        """场景 7c：audit_derived 路径（products）"""
        from meta.core.materialization_registry import get_updated_at

        db = str(tmp_path / "test.db")
        conn = sqlite3.connect(db)
        conn.execute("""
            CREATE TABLE v_audit_all AS
            SELECT 'product' AS object_type, '1' AS object_id, 'UPDATE' AS action, '2026-07-14T10:00:00' AS created_at
        """)
        conn.commit()

        class MockDS:
            def execute(self, sql, params):
                return conn.execute(sql, params)

        result = get_updated_at(MockDS(), "products", 1, object_type="product")
        assert result == "2026-07-14T10:00:00"
        conn.close()

    def test_get_updated_at_none_strategy(self):
        """场景 7d：none 策略（中间表）→ 直接返回 fallback"""
        from meta.core.materialization_registry import get_updated_at

        class MockDS:
            def execute(self, sql, params):
                raise AssertionError("none 策略不应执行 SQL")

        result = get_updated_at(MockDS(), "group_data_permissions", 1, fallback=None)
        assert result is None

        result = get_updated_at(MockDS(), "group_data_permissions", 1, fallback="DEFAULT")
        assert result == "DEFAULT"

    def test_get_updated_at_strategy_none_returns_fallback(self):
        """场景 7e：未注册表 / none 策略 → 返回 fallback

        注：validate_table_name 拒绝未注册的表名，所以这里测试
        已注册但 strategy=none 的中间表（group_data_permissions）
        """
        from meta.core.materialization_registry import get_updated_at

        class MockDS:
            def execute(self, sql, params):
                raise AssertionError("none 策略不应执行 SQL")

        # group_data_permissions 已注册但 strategy=none
        result = get_updated_at(MockDS(), "group_data_permissions", 1, fallback=None)
        assert result is None
        result = get_updated_at(MockDS(), "group_data_permissions", 1, fallback="X")
        assert result == "X"

    def test_v007_51_uses_ssot(self, tmp_path):
        """场景 8：v007_51 从 SSOT 读取目标表"""
        from meta.migrations.v007_51_add_updated_at_materialized import _get_target_tables

        targets = _get_target_tables()
        assert len(targets) == 3, f"应有 3 个 audit_callback 表，实际 {len(targets)}"

        target_dict = dict(targets)
        assert "enum_types" in target_dict
        assert "enum_values" in target_dict
        assert "users" in target_dict

    def test_virtual_sort_uses_ssot(self):
        """场景 9：virtual_sort 从 SSOT 判断物化列"""
        from meta.services.query.virtual_sort import _build_audit_derived_order_join

        # enum_types (audit_callback) → 物化路径（零 JOIN）
        result = _build_audit_derived_order_join(
            table_name="enum_types", obj_type="enum_type",
            sort_field="updated_at", sort_direction="desc",
        )
        assert result is not None
        join_clause, order_alias, sort_dir = result
        assert join_clause == "", "物化列路径 join_clause 应为空"
        assert "enum_types.updated_at" in order_alias

        # roles (business_trigger) → 物化路径
        result = _build_audit_derived_order_join(
            table_name="roles", obj_type="role",
            sort_field="updated_at", sort_direction="asc",
        )
        assert result is not None
        join_clause, order_alias, sort_dir = result
        assert join_clause == ""

        # products (audit_derived) → LEFT JOIN
        result = _build_audit_derived_order_join(
            table_name="products", obj_type="product",
            sort_field="updated_at", sort_direction="asc",
        )
        assert result is not None
        join_clause, _, _ = result
        assert "LEFT JOIN" in join_clause
        assert "v_audit_all" in join_clause

    def test_new_table_via_ssot_only(self, tmp_path):
        """场景 10：新增表只需修改 SSOT，代码不动

        模拟：用户在 _audit_materialization.yaml 加一行
        new_strategy_table: audit_callback
        → v007_51 自动覆盖
        → virtual_sort 自动用物化路径
        """
        from meta.core.materialization_registry import (
            MaterializationRegistry,
        )

        # 创建新的隔离单例（不重置全局，避免污染后续测试）
        registry = MaterializationRegistry()
        # 直接给私有属性赋值（测试用）
        registry._by_table = {}
        registry._by_object_type = {}

        ssot_content = """
audit_materialization:
  - name: my_new_table
    strategy: audit_callback
    object_type: my_new_type
  - name: my_derived_table
    strategy: audit_derived
    object_type: my_derived_type
"""
        ssot_file = tmp_path / "test_ssot.yaml"
        ssot_file.write_text(ssot_content, encoding="utf-8")

        # 加载临时 SSOT
        registry.load_from_file(str(ssot_file))

        # 验证新表被识别
        assert registry.is_materialized("my_new_table") is True
        assert registry.get_strategy("my_new_table") == "audit_callback"
        assert registry.get_audit_callback_tables() == [("my_new_table", "my_new_type")]

        assert registry.needs_audit_derived("my_derived_table") is True
        assert registry.is_materialized("my_derived_table") is False

    def test_singleton_thread_safety(self):
        """场景 11：单例线程安全（基本验证）"""
        import threading
        from meta.core.materialization_registry import MaterializationRegistry

        results = []

        def get_inst():
            results.append(MaterializationRegistry.instance())

        threads = [threading.Thread(target=get_inst) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有线程应返回同一个实例
        assert all(r is results[0] for r in results), "单例不一致"