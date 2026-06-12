# -*- coding: utf-8 -*-
"""
TestDeletionPolicyRestrictOnFormats — 单元测试

[FIX 2026-06-12] 回归测试，验证 _check_deletion_policy_restrict
正确处理两种 rule 格式:
1. dict 格式（{target_object, fk_field, message}）
2. RestrictRule dataclass（{table, foreign_key, message}）— yaml_loader.parse_deletion_policy 解析的格式

之前 bug：YAML 里的 restrict_on 规则被解析为 RestrictRule dataclass，
但 _check_deletion_policy_restrict 只识别 dict 格式，导致规则被静默跳过。
"""

import sys
import os

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.action_executor import ActionExecutor
from meta.core.models import (
    MetaObject, MetaField, MetaAction, FieldType, ActionType,
)
from meta.core.rule_executor import RuleEngine
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.yaml_loader import RestrictRule, DeletionPolicy
from meta.core.table_name_validator import register_table_name


# ---- Fixtures (module-scoped: connection pool + table 共享，避免跨连接 schema 不可见) ----

@pytest.fixture(scope='module')
def ds(tmp_path_factory):
    data_source = SQLiteAdapter()
    db_path = tmp_path_factory.mktemp("test_restrict_policy") / "test.db"
    data_source.connect(path=str(db_path))

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

    data_source.execute("""
        CREATE TABLE IF NOT EXISTS policy_target (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)
    data_source.execute("DELETE FROM policy_target")
    data_source.execute("INSERT INTO policy_target (id, name) VALUES (42, 'Target-42')")

    data_source.execute("""
        CREATE TABLE IF NOT EXISTS policy_dep (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id INTEGER NOT NULL
        )
    """)
    data_source.execute("DELETE FROM policy_dep")
    data_source.execute("INSERT INTO policy_dep (target_id) VALUES (42)")

    register_table_name("policy_target")
    register_table_name("policy_dep")

    yield data_source
    data_source.disconnect()


@pytest.fixture(scope='module')
def executor(ds):
    rule_engine = RuleEngine(ds)
    return ActionExecutor(ds, rule_engine, audit_enabled=False)


def _make_target_obj(deletion_policy):
    obj = MetaObject(
        id="policy_target",
        name="policy_target",
        table_name="policy_target",
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name", required=True),
        ],
        actions=[
            MetaAction(id="crud_create", name="创建", action_type=ActionType.CRUD, method="POST", path=""),
            MetaAction(id="crud_delete", name="删除", action_type=ActionType.CRUD, method="DELETE", path=""),
        ],
    )
    obj.deletion_policy = deletion_policy
    return obj


# ---- Tests ----

class TestDeletionPolicyRestrictOnFormats:
    """_check_deletion_policy_restrict 兼容 RestrictRule dataclass 格式"""

    def test_restrict_rule_dataclass_format_with_dependents(self, executor):
        """RestrictRule dataclass 格式 + 存在依赖行 → 应返回错误信息"""
        deletion_policy = DeletionPolicy(
            restrict_on=[RestrictRule(
                table="policy_dep",
                foreign_key="target_id",
                message="policy_target 存在依赖记录，禁止删除",
            )],
            cascade_delete=[],
        )
        obj = _make_target_obj(deletion_policy)

        errors = executor._check_deletion_policy_restrict(obj, 42)

        assert len(errors) == 1, (
            f"BUG: RestrictRule dataclass 应被识别，实际 errors={errors}"
        )
        assert "policy_target" in errors[0] and "依赖" in errors[0], (
            f"应使用 rule 自定义 message，实际: {errors[0]}"
        )

    def test_restrict_rule_dataclass_format_no_dependents(self, executor, ds):
        """RestrictRule dataclass 格式 + 无依赖行 → 不应返回错误"""
        # 清空依赖表，模拟无依赖场景
        ds.execute("DELETE FROM policy_dep")

        deletion_policy = DeletionPolicy(
            restrict_on=[RestrictRule(
                table="policy_dep",
                foreign_key="target_id",
                message="policy_target 存在依赖记录",
            )],
        )
        obj = _make_target_obj(deletion_policy)

        errors = executor._check_deletion_policy_restrict(obj, 42)

        assert errors == [], f"无依赖时不应报错，实际 errors={errors}"

    def test_dict_format_still_works_for_backward_compat(self, executor):
        """旧 dict 格式（target_object/fk_field）仍然兼容"""
        # 重新插一条依赖
        # （注：上一测试清空了 policy_dep）
        # 这里通过外层 fixture 已经在测试开始时插过 42，但因为测试间共享 ds，需要重新插
        # 实际上 pytest 会按声明顺序跑，但可能 not，所以我们也尝试 insert ignore
        try:
            executor.ds.execute("INSERT INTO policy_dep (target_id) VALUES (42)")
        except Exception:
            pass

        deletion_policy = {
            'restrict_on': [
                {
                    'table': 'policy_dep',
                    'fk_field': 'target_id',
                    'message': '旧 dict 格式：存在依赖',
                }
            ]
        }
        obj = _make_target_obj(deletion_policy)

        errors = executor._check_deletion_policy_restrict(obj, 42)

        assert len(errors) == 1, f"旧 dict 格式应继续工作，实际 errors={errors}"
        assert "旧 dict 格式" in errors[0], f"应使用 dict 自定义 message，实际: {errors[0]}"


class TestDoDeleteSilentlyFailsBug:
    """[FIX 2026-06-12] _do_delete 之前 bug：SQL DELETE 失败时 except 只 log warning
    不冒泡，导致函数继续走 AFTER_DELETE + 审计 + 返回 success，
    前端看到"删除成功"但实际记录没删（"没有成功，也没有报错"）。

    修复：except 内 return ActionResult.fail，让前端能看到真实错误。
    """

    def _make_obj_no_restrict(self, table_name="policy_target"):
        obj = MetaObject(
            id="policy_target",
            name="policy_target",
            table_name=table_name,
            fields=[
                MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True),
                MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name", required=True),
            ],
            actions=[
                MetaAction(id="crud_create", name="创建", action_type=ActionType.CRUD, method="POST", path=""),
                MetaAction(id="crud_delete", name="删除", action_type=ActionType.CRUD, method="DELETE", path=""),
            ],
        )
        # 不设 deletion_policy / deletability → 跳过前置校验
        return obj

    def test_delete_with_fk_violation_returns_fail(self, ds, executor):
        """SQL DELETE 抛异常时（典型：FK 违反），必须返回 fail（不能吞错）

        通过 monkey-patch executor.ds.execute 抛 RuntimeError 模拟 DELETE 失败，
        验证 _do_delete 不再 silently 吞错。
        """
        # 准备：插入一条 parent 记录（不插 child，让真实 FK 也能跑通）
        ds.execute("""
            CREATE TABLE IF NOT EXISTS fk_parent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
        """)
        ds.execute("DELETE FROM fk_parent")
        ds.execute("INSERT INTO fk_parent (id, name) VALUES (99, 'P')")

        # [FIX 2026-06-12] register_table_name 必须，否则 find_by_id 的
        # validate_table_name 会抛 ValueError 被 except 吞掉，导致 original_data=None
        # → _do_delete 提前返回 NOT_FOUND，永远到不了 DELETE 阶段。
        register_table_name("fk_parent")

        # 替换 executor 用的 obj：指向 fk_parent 表（设 deletion_policy 为空绕过 restrict_on）
        obj = self._make_obj_no_restrict(table_name="fk_parent")
        obj.deletion_policy = None
        obj.deletability = None

        # Monkey-patch ds.execute：所有 DELETE 抛 RuntimeError 模拟 FK 违反
        original_execute = ds.execute

        def fake_execute(sql, params=None):
            sql_stripped = sql.strip().upper() if isinstance(sql, str) else ""
            if sql_stripped.startswith("DELETE FROM FK_PARENT"):
                raise RuntimeError("FOREIGN KEY constraint failed (simulated)")
            return original_execute(sql, params)

        ds.execute = fake_execute
        try:
            result = executor._do_delete(obj, {"id": 99})
        finally:
            ds.execute = original_execute

        # 关键断言：必须返回 fail，不能是 success
        assert not result.success, (
            f"BUG: SQL DELETE 抛异常时必须返回 fail，实际 success=True, "
            f"message={result.message}, error={getattr(result, 'error', None)}"
        )
        assert result.error == "DELETE_FAILED", (
            f"应返回 DELETE_FAILED 错误码，实际 {getattr(result, 'error', None)}"
        )
        assert "数据库约束" in (result.message or ""), (
            f"错误信息应说明是数据库约束失败，实际: {result.message}"
        )

        # 父记录应该还在（因为 DELETE 失败）
        ds2_execute = original_execute  # 用原 execute 查
        row = ds2_execute("SELECT id FROM fk_parent WHERE id = 99").fetchone()
        assert row is not None, "BUG: 失败时不应误删父记录"


class TestUserGroupAndProductRestrictOnYaml:
    """[FIX 2026-06-12] 验证 YAML 里的 restrict_on 规则能实际阻止删除
    （这是用户报的两个核心 bug）：
    1. 删除有成员的用户组 → 应该被拒
    2. 删除有 versions 的 product → 应该被拒
    3. 删除有 sub_domains 的 version → 应该被拒

    之前 bug：YAML 配置的 restrict_on 是 RestrictRule dataclass 格式，
    旧 _check_deletion_policy_restrict 只识别 dict 格式，导致规则被静默跳过。
    """

    def _build_meta_with_deletion_policy(self, table_name, deletion_policy):
        """构造一个最简 MetaObject，指向指定表，带 deletion_policy"""
        obj = MetaObject(
            id=table_name,
            name=table_name,
            table_name=table_name,
            fields=[
                MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True),
                MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name", required=True),
            ],
            actions=[
                MetaAction(id="crud_create", name="创建", action_type=ActionType.CRUD, method="POST", path=""),
                MetaAction(id="crud_delete", name="删除", action_type=ActionType.CRUD, method="DELETE", path=""),
            ],
        )
        obj.deletion_policy = deletion_policy
        return obj

    def test_user_group_yaml_blocks_delete_with_members(self, ds, executor):
        """user_group.yaml 的 restrict_on 规则能正确拒绝有成员的删除"""
        # 1) 准备 user_groups + user_group_members 表
        ds.execute("""
            CREATE TABLE IF NOT EXISTS ug_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                parent_id INTEGER
            )
        """)
        ds.execute("""
            CREATE TABLE IF NOT EXISTS ug_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                user_id INTEGER
            )
        """)
        ds.execute("DELETE FROM ug_groups")
        ds.execute("DELETE FROM ug_members")
        ds.execute("INSERT INTO ug_groups (id, name) VALUES (100, 'dev-team')")
        ds.execute("INSERT INTO ug_members (group_id, user_id) VALUES (100, 1)")
        register_table_name("ug_groups")
        register_table_name("ug_members")

        # 2) 模拟 user_group.yaml 的 restrict_on 规则
        deletion_policy = DeletionPolicy(
            restrict_on=[
                RestrictRule(
                    table="ug_members",
                    foreign_key="group_id",
                    message="用户组下还有成员，请先移除所有成员后再删除",
                ),
            ],
        )
        obj = self._build_meta_with_deletion_policy("ug_groups", deletion_policy)

        # 3) 调用 _check_deletion_policy_restrict
        errors = executor._check_deletion_policy_restrict(obj, 100)

        # 4) 必须返回 1 条错误
        assert len(errors) == 1, f"应有 1 条错误，实际 errors={errors}"
        assert "成员" in errors[0], f"应包含'成员'关键字，实际: {errors[0]}"
        print(f"[PASS] user_group 含成员时被拒绝: {errors[0]}")

    def test_user_group_yaml_allows_delete_when_empty(self, ds, executor):
        """user_group.yaml 的 restrict_on：无成员时不应报错"""
        ds.execute("""
            CREATE TABLE IF NOT EXISTS ug_groups2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                parent_id INTEGER
            )
        """)
        ds.execute("""
            CREATE TABLE IF NOT EXISTS ug_members2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                user_id INTEGER
            )
        """)
        ds.execute("DELETE FROM ug_groups2")
        ds.execute("DELETE FROM ug_members2")
        ds.execute("INSERT INTO ug_groups2 (id, name) VALUES (200, 'empty-team')")
        register_table_name("ug_groups2")
        register_table_name("ug_members2")

        deletion_policy = DeletionPolicy(
            restrict_on=[
                RestrictRule(
                    table="ug_members2",
                    foreign_key="group_id",
                    message="有成员不可删",
                ),
            ],
        )
        obj = self._build_meta_with_deletion_policy("ug_groups2", deletion_policy)

        errors = executor._check_deletion_policy_restrict(obj, 200)
        assert errors == [], f"无成员时不应报错，实际 errors={errors}"
        print("[PASS] user_group 无成员时不被拒绝")

    def test_product_yaml_blocks_delete_with_versions(self, ds, executor):
        """product.yaml 的 restrict_on 规则能正确拒绝有 versions 的删除"""
        ds.execute("""
            CREATE TABLE IF NOT EXISTS prod_table (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
        """)
        ds.execute("""
            CREATE TABLE IF NOT EXISTS prod_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL
            )
        """)
        ds.execute("DELETE FROM prod_table")
        ds.execute("DELETE FROM prod_versions")
        ds.execute("INSERT INTO prod_table (id, name) VALUES (300, 'test-prod')")
        ds.execute("INSERT INTO prod_versions (product_id) VALUES (300)")
        register_table_name("prod_table")
        register_table_name("prod_versions")

        # 模拟 product.yaml 的 restrict_on
        deletion_policy = DeletionPolicy(
            restrict_on=[
                RestrictRule(
                    table="prod_versions",
                    foreign_key="product_id",
                    message="产品下还有版本，请先删除或迁移版本后再删除",
                ),
            ],
        )
        obj = self._build_meta_with_deletion_policy("prod_table", deletion_policy)

        errors = executor._check_deletion_policy_restrict(obj, 300)

        assert len(errors) == 1, f"应有 1 条错误，实际 errors={errors}"
        assert "版本" in errors[0], f"应包含'版本'关键字，实际: {errors[0]}"
        print(f"[PASS] product 含 versions 时被拒绝: {errors[0]}")

    def test_version_yaml_blocks_delete_with_subdomains(self, ds, executor):
        """version.yaml 的 restrict_on 规则能正确拒绝有 sub_domains 的删除"""
        ds.execute("""
            CREATE TABLE IF NOT EXISTS ver_table (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
        """)
        ds.execute("""
            CREATE TABLE IF NOT EXISTS ver_subdomains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_id INTEGER NOT NULL
            )
        """)
        ds.execute("DELETE FROM ver_table")
        ds.execute("DELETE FROM ver_subdomains")
        ds.execute("INSERT INTO ver_table (id, name) VALUES (400, 'v1.0')")
        ds.execute("INSERT INTO ver_subdomains (version_id) VALUES (400)")
        register_table_name("ver_table")
        register_table_name("ver_subdomains")

        # 模拟 version.yaml 的 restrict_on
        deletion_policy = DeletionPolicy(
            restrict_on=[
                RestrictRule(
                    table="ver_subdomains",
                    foreign_key="version_id",
                    message="版本下还有子领域，请先删除或迁移子领域后再删除",
                ),
            ],
        )
        obj = self._build_meta_with_deletion_policy("ver_table", deletion_policy)

        errors = executor._check_deletion_policy_restrict(obj, 400)

        assert len(errors) == 1, f"应有 1 条错误，实际 errors={errors}"
        assert "子领域" in errors[0], f"应包含'子领域'关键字，实际: {errors[0]}"
        print(f"[PASS] version 含 sub_domains 时被拒绝: {errors[0]}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
