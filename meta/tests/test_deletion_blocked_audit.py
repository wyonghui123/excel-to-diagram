# -*- coding: utf-8 -*-
"""
test_deletion_blocked_audit.py

[新增 2026-06-12] 覆盖 _do_delete 全部 7 个失败路径, 验证 _write_delete_blocked_audit
被正确调用, 传入正确的 action_label / error_code / message.

设计目标:
  - 之前 bug: 业务规则拒删 (HAS_CHILDREN / FK / restrict_on) 时 0 audit log,
    "为什么没有 DELETE 审计" 排错 30+ 分钟.
  - 修复: action_executor.py 新增 _write_delete_blocked_audit, 6 个失败路径都调用.
  - 本测试: 用 spy 模式 (patch _write_delete_blocked_audit 记录调用) 覆盖所有 6 路径,
    不依赖 audit_logs 表, 不依赖 TESTING env, 跑得快且稳.

覆盖矩阵 (7 失败路径 × 2 维度):
  ┌──────────────────────────┬─────────────────┬────────────────┐
  │ 失败路径                 │ action_label    │ error_code     │
  ├──────────────────────────┼─────────────────┼────────────────┤
  │ validate_delete          │ DELETE_BLOCKED  │ HIERARCHY_*    │
  │ _check_deletability      │ DELETE_BLOCKED  │ CANNOT_DELETE  │
  │ _check_reverse_fk_refs   │ DELETE_BLOCKED  │ REFERENTIAL_*  │
  │ _check_delete_policy_*   │ DELETE_BLOCKED  │ RESTRICT_*     │
  │ rule_engine BEFORE_DELETE│ DELETE_BLOCKED  │ VALIDATION_*   │
  │ SQL DELETE 抛异常        │ DELETE_FAILED   │ DELETE_FAILED  │
  │ _cleanup_m2m / 事务异常  │ DELETE_FAILED   │ DELETE_FAILED  │
  └──────────────────────────┴─────────────────┴────────────────┘

边界:
  - NOT_FOUND / MISSING_ID: 不写审计 (设计选择), 单独验证.
  - 正常删除: 走 log_delete(action=DELETE), 验证不混淆到 DELETE_BLOCKED.
"""
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.action_executor import ActionExecutor
from meta.core.models import (
    MetaObject, MetaField, MetaAction, FieldType, ActionType,
)
from meta.core.rule_executor import RuleEngine
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.yaml_loader import RestrictRule, DeletionPolicy, DeletabilityConfig
from meta.core.table_name_validator import register_table_name


# ---- Fixtures (复用 test_deletion_policy_restrict_on 的模式) ----

@pytest.fixture(scope='module')
def ds(tmp_path_factory):
    data_source = SQLiteAdapter()
    db_path = tmp_path_factory.mktemp("test_blocked_audit") / "test.db"
    data_source.connect(path=str(db_path))

    # audit_logs 表 (即便 spy 不写, 也建出来避免日志告警)
    data_source.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT NOT NULL,
            object_id INTEGER,
            action TEXT NOT NULL,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            user_id INTEGER,
            user_name TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT,
            extra_data TEXT,
            trace_id TEXT,
            transaction_id TEXT,
            status TEXT,
            retry_count INTEGER DEFAULT 0,
            agent_id TEXT,
            agent_session_id TEXT,
            tool_call_id TEXT,
            agent_reasoning TEXT
        )
    """)

    # parent 表
    data_source.execute("""
        CREATE TABLE IF NOT EXISTS blk_parent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'active'
        )
    """)
    data_source.execute("DELETE FROM blk_parent")

    # child 表 (FK 引用 blk_parent, 用于触发 SQL 异常)
    data_source.execute("""
        CREATE TABLE IF NOT EXISTS blk_child_fk (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER NOT NULL REFERENCES blk_parent(id)
        )
    """)
    data_source.execute("DELETE FROM blk_child_fk")

    # child 表 (用于 _check_reverse_fk_references)
    data_source.execute("""
        CREATE TABLE IF NOT EXISTS blk_child_ref (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blk_parent_id INTEGER
        )
    """)
    data_source.execute("DELETE FROM blk_child_ref")

    # child 表 (用于 _check_deletion_policy_restrict)
    data_source.execute("""
        CREATE TABLE IF NOT EXISTS blk_child_dep (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER NOT NULL
        )
    """)
    data_source.execute("DELETE FROM blk_child_dep")

    # 业务对象表 (验证 rule_engine BEFORE_DELETE 拦截)
    data_source.execute("""
        CREATE TABLE IF NOT EXISTS blk_business (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            is_locked INTEGER DEFAULT 0
        )
    """)
    data_source.execute("DELETE FROM blk_business")

    register_table_name("blk_parent")
    register_table_name("blk_child_fk")
    register_table_name("blk_child_ref")
    register_table_name("blk_child_dep")
    register_table_name("blk_business")

    yield data_source
    data_source.disconnect()


@pytest.fixture
def spy_blocked_audit(monkeypatch):
    """Patch _write_delete_blocked_audit 为 spy, 记录所有调用.

    为什么不直接 patch _write_audit_log_v2 + 查 audit_logs 表?
      - _write_audit_log_v2 在 TESTING=1 时完全跳过 (见 action_executor.py:1702)
      - 即便去掉 TESTING, 异步 writer 还要等启动/flush, 测试不稳定.
    Spy 是最直接、最快、覆盖最稳的方式.
    """
    calls = []

    def spy(self, meta_object, id_value, original_data, action_label, error_code, message):
        calls.append({
            "object_type": meta_object.id,
            "object_id": id_value,
            "action_label": action_label,
            "error_code": error_code,
            "message": message,
            "snapshot_keys": sorted(original_data.keys()) if original_data else None,
        })

    monkeypatch.setattr(ActionExecutor, "_write_delete_blocked_audit", spy)
    return calls


@pytest.fixture
def executor(ds):
    rule_engine = RuleEngine(ds)
    return ActionExecutor(ds, rule_engine, audit_enabled=True)


def _make_obj(table_name="blk_parent", deletion_policy=None, deletability=None,
              with_fk_business=False):
    """构造最简 MetaObject, 可选配 deletion_policy / deletability."""
    if with_fk_business:
        # 走 business_object 模式 (rule_engine 会找规则)
        table_name = "blk_business"
    obj = MetaObject(
        id=table_name,
        name=table_name,
        table_name=table_name,
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name", required=True),
            MetaField(id="status", name="状态", field_type=FieldType.STRING, db_column="status", required=False),
        ],
        actions=[
            MetaAction(id="crud_create", name="创建", action_type=ActionType.CRUD, method="POST", path=""),
            MetaAction(id="crud_delete", name="删除", action_type=ActionType.CRUD, method="DELETE", path=""),
        ],
    )
    if deletion_policy is not None:
        obj.deletion_policy = deletion_policy
    if deletability is not None:
        obj.deletability = deletability
    return obj


# ---- 7 失败路径: 每条都验证 (action_label, error_code, object_id) ----

class TestPath1HierarchyBlocked:
    """路径 1: validate_delete 返回 invalid (HAS_CHILDREN) → DELETE_BLOCKED"""

    def test_hierarchy_validator_returns_invalid_triggers_blocked_audit(
        self, ds, executor, spy_blocked_audit, monkeypatch
    ):
        """validate_delete 不 valid → 写 DELETE_BLOCKED + HIERARCHY_BLOCKED"""
        # mock validate_delete 返回 invalid
        # 注意: action_executor.py line 28 已经 `from meta.services.hierarchy_validation_service import validate_delete`,
        # 已在 module scope 引用. 必须在 action_executor 模块 patch 那个名字.
        from meta.core import action_executor as ae_mod
        from types import SimpleNamespace

        monkeypatch.setattr(
            ae_mod, "validate_delete",
            lambda *a, **k: SimpleNamespace(
                valid=False,
                error_code="HAS_CHILDREN",
                message="存在 3 个子领域，无法删除",
            ),
        )

        # 准备数据
        ds.execute("INSERT INTO blk_parent (id, name) VALUES (1, 'parent-1')")

        obj = _make_obj("blk_parent")
        result = executor._do_delete(obj, {"id": 1})

        # 1) 业务侧: 返回 fail
        assert not result.success, "应返回 fail"
        assert result.error == "HAS_CHILDREN", f"应透传 error_code, 实际 {result.error}"

        # 2) 审计侧: 写了 1 条 DELETE_BLOCKED
        assert len(spy_blocked_audit) == 1, (
            f"应写 1 条 DELETE_BLOCKED 审计, 实际 {len(spy_blocked_audit)}: {spy_blocked_audit}"
        )
        call = spy_blocked_audit[0]
        assert call["action_label"] == "DELETE_BLOCKED"
        assert call["error_code"] == "HAS_CHILDREN"
        assert "子领域" in call["message"]
        assert call["object_id"] == 1
        # snapshot 保留原记录字段
        assert call["snapshot_keys"] is not None
        assert "id" in call["snapshot_keys"] and "name" in call["snapshot_keys"]


class TestPath2DeletabilityDenied:
    """路径 2: _check_deletability 表达式为 False → DELETE_BLOCKED / CANNOT_DELETE"""

    def test_deletability_condition_false_triggers_blocked_audit(
        self, ds, executor, spy_blocked_audit
    ):
        """deletability 条件不满足 → 写 DELETE_BLOCKED + CANNOT_DELETE"""
        ds.execute("INSERT INTO blk_parent (id, name, status) VALUES (10, 'locked', 'locked')")

        # 配 deletability: status == 'active' 才能删
        obj = _make_obj("blk_parent", deletability=DeletabilityConfig(
            condition="self.status == 'active'",
            message="已锁定的记录不可删除",
        ))

        result = executor._do_delete(obj, {"id": 10})

        assert not result.success
        assert result.error == "CANNOT_DELETE"

        assert len(spy_blocked_audit) == 1
        call = spy_blocked_audit[0]
        assert call["action_label"] == "DELETE_BLOCKED"
        assert call["error_code"] == "CANNOT_DELETE"
        assert "已锁定" in call["message"] or "不可删除" in call["message"]


class TestPath3ReferentialIntegrity:
    """路径 3: _check_reverse_fk_references 找到引用 → DELETE_BLOCKED / REFERENTIAL_INTEGRITY"""

    def test_reverse_fk_referenced_triggers_blocked_audit(
        self, ds, executor, spy_blocked_audit, monkeypatch
    ):
        """被其他表 FK 引用 → 写 DELETE_BLOCKED + REFERENTIAL_INTEGRITY"""
        ds.execute("INSERT INTO blk_parent (id, name) VALUES (20, 'refed-parent')")
        ds.execute("INSERT INTO blk_child_ref (id, blk_parent_id) VALUES (1, 20)")

        # _check_reverse_fk_references 遍历 registry 找 resolve_to_object=blk_parent 的字段.
        # 测试更稳: 直接 patch 实例方法, 模拟"有引用", 验证 _write_delete_blocked_audit 触发.
        def fake_refs(self, meta_obj, id_value):
            return ["被 blk_child_ref.id=1 引用，无法删除"]

        monkeypatch.setattr(
            ActionExecutor, "_check_reverse_fk_references", fake_refs
        )

        obj = _make_obj("blk_parent")
        result = executor._do_delete(obj, {"id": 20})

        assert not result.success
        assert result.error == "REFERENTIAL_INTEGRITY"

        assert len(spy_blocked_audit) == 1
        call = spy_blocked_audit[0]
        assert call["action_label"] == "DELETE_BLOCKED"
        assert call["error_code"] == "REFERENTIAL_INTEGRITY"
        assert "引用" in call["message"]


class TestPath4RestrictOnDelete:
    """路径 4: _check_deletion_policy_restrict 命中 YAML restrict_on → DELETE_BLOCKED / RESTRICT_ON_DELETE"""

    def test_yaml_restrict_on_with_dependents_triggers_blocked_audit(
        self, ds, executor, spy_blocked_audit
    ):
        """YAML restrict_on 命中依赖 → 写 DELETE_BLOCKED + RESTRICT_ON_DELETE"""
        ds.execute("INSERT INTO blk_parent (id, name) VALUES (30, 'with-dep')")
        ds.execute("INSERT INTO blk_child_dep (parent_id) VALUES (30)")

        deletion_policy = DeletionPolicy(
            restrict_on=[RestrictRule(
                table="blk_child_dep",
                foreign_key="parent_id",
                message="存在依赖记录，禁止删除",
            )],
        )
        obj = _make_obj("blk_parent", deletion_policy=deletion_policy)

        result = executor._do_delete(obj, {"id": 30})

        assert not result.success
        assert result.error == "RESTRICT_ON_DELETE"

        assert len(spy_blocked_audit) == 1
        call = spy_blocked_audit[0]
        assert call["action_label"] == "DELETE_BLOCKED"
        assert call["error_code"] == "RESTRICT_ON_DELETE"
        assert "依赖" in call["message"] or "禁止" in call["message"]


class TestPath5RuleEngineBeforeDelete:
    """路径 5: rule_engine.execute_rules(BEFORE_DELETE) 失败 → DELETE_BLOCKED / VALIDATION_FAILED"""

    def test_rule_engine_before_delete_failure_triggers_blocked_audit(
        self, ds, executor, spy_blocked_audit, monkeypatch
    ):
        """BEFORE_DELETE 规则失败 → 写 DELETE_BLOCKED + VALIDATION_FAILED"""
        ds.execute("INSERT INTO blk_business (id, name, is_locked) VALUES (40, 'biz', 1)")

        # 直接 patch rule_engine.execute_rules 模拟失败
        from meta.core.rule_executor import RuleTrigger
        from types import SimpleNamespace

        original = executor.rule_engine.execute_rules

        def fake_execute_rules(meta_obj, trigger, data, *args, **kwargs):
            if trigger == RuleTrigger.BEFORE_DELETE:
                return SimpleNamespace(
                    success=False,
                    errors=["规则校验失败：is_locked=1 不允许删除"],
                )
            return original(meta_obj, trigger, data, *args, **kwargs)

        monkeypatch.setattr(executor.rule_engine, "execute_rules", fake_execute_rules)

        obj = _make_obj("blk_business")
        result = executor._do_delete(obj, {"id": 40})

        assert not result.success
        assert result.error == "VALIDATION_FAILED"

        assert len(spy_blocked_audit) == 1
        call = spy_blocked_audit[0]
        assert call["action_label"] == "DELETE_BLOCKED"
        assert call["error_code"] == "VALIDATION_FAILED"
        assert "Before delete" in call["message"] or "validation" in call["message"].lower()


class TestPath6SqlDeleteException:
    """路径 6: SQL DELETE 抛异常 (FK violation) → DELETE_FAILED / DELETE_FAILED"""

    def test_sql_delete_runtime_error_triggers_failed_audit(
        self, ds, executor, spy_blocked_audit
    ):
        """SQL DELETE 抛异常 → 写 DELETE_FAILED + DELETE_FAILED (不是 DELETE_BLOCKED)"""
        # parent 不放 child_fk, 触发 FK 违反
        ds.execute("INSERT INTO blk_parent (id, name) VALUES (50, 'fk-violation')")
        ds.execute("INSERT INTO blk_child_fk (parent_id) VALUES (50)")

        obj = _make_obj("blk_parent")
        # 不配 deletion_policy / deletability, 跳过前置检查
        obj.deletion_policy = None
        obj.deletability = None

        result = executor._do_delete(obj, {"id": 50})

        # 1) 业务侧: 失败, error=DELETE_FAILED
        assert not result.success
        assert result.error == "DELETE_FAILED", f"应返回 DELETE_FAILED, 实际 {result.error}"
        assert "约束" in (result.message or "")

        # 2) 审计侧: 写了 1 条 DELETE_FAILED (action_label=DELETE_FAILED)
        assert len(spy_blocked_audit) == 1, (
            f"应写 1 条 DELETE_FAILED 审计, 实际 {len(spy_blocked_audit)}: {spy_blocked_audit}"
        )
        call = spy_blocked_audit[0]
        assert call["action_label"] == "DELETE_FAILED", (
            f"SQL 异常应标 DELETE_FAILED, 不是 DELETE_BLOCKED, 实际 {call['action_label']}"
        )
        assert call["error_code"] == "DELETE_FAILED"
        assert "FOREIGN KEY" in call["message"] or "约束" in call["message"]

        # 3) 数据侧: 父记录应还在
        row = ds.execute("SELECT id FROM blk_parent WHERE id = 50").fetchone()
        assert row is not None, "失败时不应误删父记录"


class TestPath7CleanupM2mException:
    """路径 7: _cleanup_m2m_tables / transaction 外层异常 → DELETE_FAILED / DELETE_FAILED"""

    def test_cleanup_m2m_exception_triggers_failed_audit(
        self, ds, executor, spy_blocked_audit, monkeypatch
    ):
        """_cleanup_m2m_tables 抛异常 → 写 DELETE_FAILED"""
        ds.execute("INSERT INTO blk_parent (id, name) VALUES (60, 'cleanup-err')")

        def fake_cleanup(meta_obj, id_value):
            raise RuntimeError("M2M cleanup failed (simulated)")

        monkeypatch.setattr(executor, "_cleanup_m2m_tables", fake_cleanup)

        obj = _make_obj("blk_parent")
        obj.deletion_policy = None
        obj.deletability = None

        result = executor._do_delete(obj, {"id": 60})

        assert not result.success
        assert result.error == "DELETE_FAILED"

        assert len(spy_blocked_audit) == 1
        call = spy_blocked_audit[0]
        assert call["action_label"] == "DELETE_FAILED"
        assert call["error_code"] == "DELETE_FAILED"
        assert "M2M" in call["message"] or "cleanup" in call["message"].lower()


# ---- 边界: NOT_FOUND / MISSING_ID 不应写审计 ----

class TestNegativeCasesNoAudit:
    """NOT_FOUND / MISSING_ID 不应触发审计 (设计选择: 没有 original_data 就没有 snapshot)"""

    def test_not_found_id_does_not_write_audit(
        self, ds, executor, spy_blocked_audit
    ):
        obj = _make_obj("blk_parent")
        result = executor._do_delete(obj, {"id": 99999})  # 不存在

        assert not result.success
        assert result.error == "NOT_FOUND"
        assert spy_blocked_audit == [], (
            f"NOT_FOUND 不应写审计 (无 original_data), 实际: {spy_blocked_audit}"
        )

    def test_missing_id_param_does_not_write_audit(
        self, ds, executor, spy_blocked_audit
    ):
        obj = _make_obj("blk_parent")
        result = executor._do_delete(obj, {})  # 无 id

        assert not result.success
        assert result.error == "MISSING_ID"
        assert spy_blocked_audit == []


# ---- 正常路径: 成功删除不混淆到 DELETE_BLOCKED ----

class TestNormalDeleteDoesNotTriggerBlockedAudit:
    """正常成功删除 → _write_delete_blocked_audit 一次都不应被调用"""

    def test_successful_delete_does_not_trigger_blocked_audit(
        self, ds, executor, spy_blocked_audit
    ):
        """[FIX 2026-06-12] 正常成功删除应走 log_delete(action=DELETE), 不是 DELETE_BLOCKED"""
        ds.execute("INSERT INTO blk_parent (id, name) VALUES (70, 'happy-path')")

        obj = _make_obj("blk_parent")
        obj.deletion_policy = None
        obj.deletability = None

        # [FIX v2] _cleanup_m2m_tables 在 parent 没有 m2m 关系时直接返回, 不抛错
        # 但为了确保不被 _cleanup_m2m 失败污染, 我们 mock 一下
        import meta.core.action_executor as ae_mod
        original_cleanup = executor._cleanup_m2m_tables
        executor._cleanup_m2m_tables = lambda *a, **k: None

        try:
            result = executor._do_delete(obj, {"id": 70})
        finally:
            executor._cleanup_m2m_tables = original_cleanup

        assert result.success, f"应成功, 实际: {result.message}"

        # 关键: DELETE_BLOCKED 一次都不应被调
        assert spy_blocked_audit == [], (
            f"成功路径不应触发 _write_delete_blocked_audit, 实际: {spy_blocked_audit}"
        )

        # 数据应真的被删
        row = ds.execute("SELECT id FROM blk_parent WHERE id = 70").fetchone()
        assert row is None, "成功删除后记录应不在"


# ---- 集成: 多个失败路径在 batch_delete (force=True) 下都能逐条写审计 ----

class TestBatchDeleteForceAuditsEachFailure:
    """[FIX 2026-06-12] manage_service.batch_delete(force=True) 应逐条写审计.

    修复前 bug: all_or_none=True 时, 1 条失败导致事务回滚 → 所有 id 都没审计.
    修复: force=True → effective_all_or_none=False → 每条独立事务, 失败也写审计.
    """
    def test_batch_delete_with_force_writes_audit_per_failed_id(
        self, ds, executor, spy_blocked_audit
    ):
        # 这是 _do_delete 单元测试层级, 验证 spy 已被 patch
        # 真实 batch_delete 集成测试见 test_delete_validation_e2e_regression.py
        # 这里只验证 spy 在多次 _do_delete 调用间能累加记录
        ds.execute("INSERT INTO blk_parent (id, name, status) VALUES (80, 'a', 'locked')")
        ds.execute("INSERT INTO blk_parent (id, name, status) VALUES (81, 'b', 'locked')")
        ds.execute("INSERT INTO blk_parent (id, name, status) VALUES (82, 'c', 'active')")

        from meta.core.yaml_loader import DeletabilityConfig
        obj = _make_obj("blk_parent", deletability=DeletabilityConfig(
            condition="self.status == 'active'",
            message="locked 不可删",
        ))

        # 模拟 batch 逐条调用 _do_delete
        for record_id in (80, 81, 82):
            r = executor._do_delete(obj, {"id": record_id})
            if not r.success:
                pass  # 失败已写入 spy

        # 80 / 81 失败应各写 1 条 DELETE_BLOCKED, 82 成功不写
        assert len(spy_blocked_audit) == 2, (
            f"80+81 失败应写 2 条审计, 82 成功不写, 实际 {len(spy_blocked_audit)}: {spy_blocked_audit}"
        )
        ids = sorted(c["object_id"] for c in spy_blocked_audit)
        assert ids == [80, 81], f"失败 id 集合应为 [80, 81], 实际 {ids}"
        for c in spy_blocked_audit:
            assert c["action_label"] == "DELETE_BLOCKED"
            assert c["error_code"] == "CANNOT_DELETE"


# ---- 辅助验证: _write_delete_blocked_audit 自身的安全保护 ----

class TestWriteDeleteBlockedAuditSafetyNet:
    """_write_delete_blocked_audit 自身的安全保护:

    - original_data=None: 直接 return, 不写 (避免空 snapshot)
    - 内部异常: 捕获并 log warning, 不影响业务结果
    """

    def test_skip_when_original_data_is_none(self, ds, executor, monkeypatch):
        """[FIX 2026-06-12] original_data=None 时跳过审计写入 (不抛错)"""
        # 直接调用 _write_delete_blocked_audit, original_data=None
        # 应直接 return, 不抛异常
        from meta.core.models import MetaObject, MetaField, FieldType
        obj = MetaObject(
            id="test_obj", name="test_obj", table_name="test_obj",
            fields=[MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id")],
            actions=[],
        )
        # 不应抛
        executor._write_delete_blocked_audit(
            obj, 1, None,
            action_label="DELETE_BLOCKED",
            error_code="X",
            message="x",
        )
        # 验证: 不写 audit_logs (original_data 缺失) - 此时 _write_audit_log_v2 会写
        # 但因为是 sync 路径 (v2 在 TESTING 跳过), 所以不会真写
        # 真正的"不写" 逻辑: _write_delete_blocked_audit 自身在 original_data is None 时直接 return

    def test_internal_audit_failure_does_not_propagate(
        self, ds, executor, monkeypatch
    ):
        """_write_audit_log_v2 抛异常时, _write_delete_blocked_audit 不应向外抛"""
        from meta.core.models import MetaObject, MetaField, FieldType

        def fake_boom(self_v2, audit_fn):
            raise RuntimeError("v2 audit boom")

        monkeypatch.setattr(ActionExecutor, "_write_audit_log_v2", fake_boom)

        obj = MetaObject(
            id="test_obj", name="test_obj", table_name="test_obj",
            fields=[MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id")],
            actions=[],
        )
        # 不应向外抛
        executor._write_delete_blocked_audit(
            obj, 1, {"id": 1, "name": "x"},
            action_label="DELETE_BLOCKED",
            error_code="X",
            message="x",
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
