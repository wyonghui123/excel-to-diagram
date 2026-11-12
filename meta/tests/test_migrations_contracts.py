# -*- coding: utf-8 -*-
"""迁移脚本契约测试（MigrationRunner 返回值 / v189 employees / v125 客户销售组织 / 规则段退役）。

[TEST-EFF P2-1] 由四个同域（tmp SQLite 上重放 migration）的 <=5 用例小文件合并而来：
- test_migration_runner_verify.py     (verify_migration 返回值归一化)
- test_employee_tbd_p4_migration.py   (v189 员工 TBD 收口)
- test_rule_validations_migration.py  (废弃顶层 validations: 段)
- test_customer_sales_org_migration.py (v125 客户销售组织唯一索引)
合并时修复了跨文件同名用例（rerun_is_idempotent）。
"""

import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.rule_executor import RuleEngine  # noqa: E402
from meta.core.yaml_loader import (  # noqa: E402
    load_yaml_file, DeprecatedSchemaSectionError,
)
from meta.core.metadata_driven_validator import MetadataDrivenValidator  # noqa: E402

from meta.migrations.v189__employee_tbd_p4 import (  # noqa: E402
    EMPLOYEES_TABLE,
    NEW_COLUMN,
    NEW_INDEX,
    OLD_INDEX,
    OLD_INDEX_SQL,
    migrate,
    rollback,
    verify,
)
from meta.migrations.v125__customer_sales_org import (  # noqa: E402
    TABLE,
    UNIQUE_INDEX,
    migrate as migrate_cso,
    rollback as rollback_cso,
    verify as verify_cso,
)
from meta.tests.factories._customer_sales_org_helpers import seed_override  # noqa: E402
from meta.tests.factories._pricing_p2_helpers import seed_row  # noqa: E402
from meta.tests.factories._pricing_w1_helpers import clone_schema  # noqa: E402

SCHEMA_DIR = os.path.join(PROJECT_ROOT, "meta", "schemas")
REAL_DB = Path(__file__).resolve().parents[1] / 'architecture.db'


# ---------------------------------------------------------------------------
# test_migration_runner_verify.py
# ---------------------------------------------------------------------------
# 背景: v224 的 verify() 返回 {'ok': bool, ...}; dict 非空恒为真，
# 原实现直接 bool(dict) 会把 verify 失败误报成 OK。


class TestVerifyResultNormalization:
    def _runner(self, tmp_path, return_expr):
        migration = tmp_path / 'v999_verify_shape.py'
        migration.write_text(
            'def verify(db_path):\n    return %s\n' % return_expr,
            encoding='utf-8')
        ds = MagicMock()
        ds.in_transaction = False
        ds._db_path = str(tmp_path / 'architecture.db')
        from meta.core.migration_runner import MigrationRunner
        return MigrationRunner(ds, migrations_dir=str(tmp_path))

    def test_dict_ok_false_reported_as_failure(self, tmp_path):
        runner = self._runner(tmp_path, "{'ok': False, 'checks': {'column': False}}")
        ran, ok, _ = runner.verify_migration('v999_verify_shape.py')
        assert ran is True
        assert ok is False

    def test_dict_ok_true_reported_as_success(self, tmp_path):
        runner = self._runner(tmp_path, "{'ok': True, 'checks': {}}")
        ran, ok, _ = runner.verify_migration('v999_verify_shape.py')
        assert ran is True
        assert ok is True

    def test_bool_result_unchanged(self, tmp_path):
        runner = self._runner(tmp_path, "False")
        ran, ok, _ = runner.verify_migration('v999_verify_shape.py')
        assert ran is True
        assert ok is False


# ---------------------------------------------------------------------------
# test_employee_tbd_p4_migration.py
# ---------------------------------------------------------------------------
# 依据: docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md §FR-015 / §10
# 口径:
#   ① `employees.supplier_party_id` 增列（可空，TBD-10 派遣供应商）；
#   ② 工号唯一索引从 `(employee_no) WHERE active` 换成
#      `(org_id, employee_no) WHERE active`（TBD-12 法人雇主语义）；
#   ③ 复跑只 SKIP；回滚恢复旧索引、保留列 stub。

# v185 时期（v189 之前）的 employees 结构：无 supplier_party_id
EMPLOYEE_DDL = """
CREATE TABLE employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_no TEXT NOT NULL,
    name TEXT NOT NULL,
    person_profile_id INTEGER NOT NULL,
    user_id INTEGER,
    org_id INTEGER NOT NULL,
    location_id INTEGER,
    position TEXT,
    job_grade TEXT,
    employment_type TEXT NOT NULL DEFAULT 'full_time',
    status TEXT NOT NULL DEFAULT 'active',
    hire_date TEXT NOT NULL,
    termination_date TEXT,
    manager_employee_id INTEGER,
    created_at TEXT,
    updated_at TEXT
)
"""


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    path = tmp_path / 'employee_tbd_p4.db'
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(EMPLOYEE_DDL)
        conn.execute(OLD_INDEX_SQL)
        conn.commit()
    finally:
        conn.close()
    return path


def _columns(path: Path) -> dict:
    conn = sqlite3.connect(str(path))
    try:
        return {row[1]: row for row in conn.execute(
            'PRAGMA table_info({0})'.format(EMPLOYEES_TABLE))}
    finally:
        conn.close()


def _index_names(path: Path) -> set:
    conn = sqlite3.connect(str(path))
    try:
        return {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        conn.close()


def _index_sql(path: Path, name: str):
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            (name,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_migrate_adds_nullable_column_and_swaps_index(db):
    assert migrate(db) is True

    column = NEW_COLUMN[0]
    info = _columns(db)
    assert column in info, '缺列 {0}'.format(column)
    assert info[column][3] == 0, '{0} 应可空'.format(column)

    names = _index_names(db)
    assert OLD_INDEX not in names
    assert NEW_INDEX in names
    sql = (_index_sql(db, NEW_INDEX) or '').lower()
    assert 'unique' in sql and 'where' in sql
    assert 'org_id' in sql and 'employee_no' in sql
    assert "'active'" in sql
    assert verify(db) is True


def test_index_enforced_per_legal_employer(db):
    assert migrate(db) is True
    conn = sqlite3.connect(str(db))
    try:
        seed_row(conn, EMPLOYEES_TABLE, employee_no='E1', name='甲',
                 person_profile_id=1, org_id=1, status='active',
                 hire_date='2026-01-01')
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, EMPLOYEES_TABLE, employee_no='E1', name='乙',
                     person_profile_id=2, org_id=1, status='active',
                     hire_date='2026-02-01')
        conn.rollback()
        # 跨法人可复用同一工号
        seed_row(conn, EMPLOYEES_TABLE, employee_no='E1', name='丙',
                 person_profile_id=3, org_id=2, status='active',
                 hire_date='2026-03-01')
        conn.commit()
    finally:
        conn.close()
    assert verify(db) is True


def test_employee_tbd_rerun_is_idempotent(db):
    assert migrate(db) is True
    before = (len(_columns(db)), _index_names(db))
    assert migrate(db) is True
    assert (len(_columns(db)), _index_names(db)) == before
    assert verify(db) is True


def test_rollback_restores_old_index_and_keeps_column_stub(db):
    assert migrate(db) is True
    assert rollback(db) is True

    names = _index_names(db)
    assert NEW_INDEX not in names
    assert OLD_INDEX in names
    # 列保留为 stub（不 DROP COLUMN）
    assert NEW_COLUMN[0] in _columns(db)
    assert verify(db) is False


# ---------------------------------------------------------------------------
# test_rule_validations_migration.py
# ---------------------------------------------------------------------------
# 规则模型 P2/P3 迁移测试（废弃顶层 validations: 段）
#
# 覆盖：
# 1. G 类迁移：relationship.source_not_equal_target 经 rules: 在保存链路真阻断
# 2. 字段属性路径：enum_type.id（business_key）不再被 _skip_field 跳过；普通对象 id 仍跳过
# 3. 残留顶层 validations: 段被加载器拒绝
# 4. MetaObject 不再持有 validations 容器 / get_validations


def test_relationship_source_not_equal_target_blocks():
    """G 类规则迁入 rules: 后必须真阻断（首次启用 type: validation）。"""
    meta = load_yaml_file(os.path.join(SCHEMA_DIR, "relationship.yaml"))
    assert meta is not None

    rule = meta.get_rule("source_not_equal_target")
    assert rule is not None, "relationship.rules: 缺少 source_not_equal_target"
    assert rule.rule_type.value == "validation"

    engine = RuleEngine()
    bad = engine.validate(meta, {"source_bo_id": 1, "target_bo_id": 1})
    assert bad.success is False, "source_bo_id == target_bo_id 应被阻断"
    assert bad.failed >= 1

    ok = engine.validate(meta, {"source_bo_id": 1, "target_bo_id": 2})
    assert ok.success is True, "source_bo_id != target_bo_id 不应阻断"


def test_enum_type_id_business_key_not_skipped():
    """enum_type.id 声明 business_key，字段属性路径不得再跳过它。"""
    dv = MetadataDrivenValidator(None)
    enum_meta = load_yaml_file(os.path.join(SCHEMA_DIR, "enum_type.yaml"))
    id_field = next(f for f in enum_meta.fields if f.id == "id")
    assert getattr(id_field.semantics, "business_key", False) is True
    assert dv._skip_field(id_field, "create") is False

    annotation_meta = load_yaml_file(os.path.join(SCHEMA_DIR, "annotation.yaml"))
    plain_id = next(f for f in annotation_meta.fields if f.id == "id")
    assert dv._skip_field(plain_id, "create") is True, "普通 id 应保持跳过"


def test_residual_validations_section_rejected(tmp_path):
    """残留顶层 validations: 段必须在加载期被拒绝（防回流）。"""
    bad_schema = tmp_path / "legacy_validations.yaml"
    bad_schema.write_text(
        "id: legacy\nname: 遗留\nvalidations:\n- id: x_required\n  type: field\n  rule: x is not None\n",
        encoding="utf-8",
    )
    with pytest.raises(DeprecatedSchemaSectionError):
        load_yaml_file(str(bad_schema))


def test_meta_object_no_validations_container():
    from meta.core.models import MetaObject

    assert "validations" not in MetaObject.__dataclass_fields__
    assert not hasattr(MetaObject, "get_validations")


def test_parse_aspects_yaml_has_no_validations_key(tmp_path):
    """[B12 2026-10-05] parse_aspects_yaml 不再产出死键 "validations"。

    _resolve_aspects 只消费 fields / rules；保留 "validations" 只会误导后续维护者。
    覆盖三种产出分支：dict 形 aspect、list 形 aspect、shared_properties 组。
    """
    from meta.core.yaml_loader import parse_aspects_yaml

    (tmp_path / "aspects.yaml").write_text(
        "audit_fields:\n"
        "  fields:\n"
        "  - id: created_at\n"
        "    name: 创建时间\n"
        "    type: datetime\n"
        "simple_group:\n"
        "- id: note\n"
        "  name: 备注\n"
        "  type: string\n",
        encoding="utf-8",
    )
    (tmp_path / "shared_properties.yaml").write_text(
        "shared_group:\n"
        "- id: tag\n"
        "  name: 标签\n"
        "  type: string\n",
        encoding="utf-8",
    )

    aspects = parse_aspects_yaml(str(tmp_path))
    for name in ("audit_fields", "simple_group", "shared_group"):
        assert name in aspects, "缺少产出分支: {0}".format(name)
        assert "validations" not in aspects[name], \
            "{0} 不应再产出 validations 键".format(name)
        assert "fields" in aspects[name] and "rules" in aspects[name]


# ---------------------------------------------------------------------------
# test_customer_sales_org_migration.py
# ---------------------------------------------------------------------------
# 依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md §4.6
# 口径:
#   用开发库的表结构（不含数据、不含索引）在临时库重放 migrate，既验证
#   「表已由 sync_schema 建好时能补唯一索引」，也验证复跑只 SKIP、有重复
#   组合时拒绝建索引。不写真实开发库。


def _clone_cso(tmp_path: Path) -> Path:
    if not REAL_DB.exists():
        pytest.skip('开发库不存在, 跳过迁移测试')
    dst = tmp_path / 'cso.db'
    missing = clone_schema(REAL_DB, dst, (TABLE,))
    if missing:
        pytest.skip(f'开发库缺表 {missing}, 跳过迁移测试')
    return dst


def _cso_index_sql(path: Path):
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            (UNIQUE_INDEX,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_customer_sales_org_fresh_creates_unique_index(tmp_path):
    db = _clone_cso(tmp_path)
    assert _cso_index_sql(db) is None

    assert migrate_cso(db) is True
    sql = _cso_index_sql(db)
    assert sql and 'UNIQUE' in sql.upper()
    assert 'CUSTOMER_ACCOUNT_ID' in sql.upper()
    assert 'SALES_ORG_ID' in sql.upper()
    assert verify_cso(db) is True


def test_customer_sales_org_rerun_is_idempotent(tmp_path):
    db = _clone_cso(tmp_path)
    assert migrate_cso(db) is True
    before = _cso_index_sql(db)

    assert migrate_cso(db) is True
    assert _cso_index_sql(db) == before


def test_customer_sales_org_missing_table_fails(tmp_path):
    db = tmp_path / 'empty.db'
    sqlite3.connect(str(db)).close()
    assert migrate_cso(db) is False
    assert verify_cso(db) is False


def test_duplicates_block_index(tmp_path):
    db = _clone_cso(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        seed_override(conn, customer_account_id=1, sales_org_id=318)
        seed_override(conn, customer_account_id=1, sales_org_id=318)
    finally:
        conn.close()

    assert migrate_cso(db) is False
    assert _cso_index_sql(db) is None


def test_rollback_drops_index_only(tmp_path):
    db = _clone_cso(tmp_path)
    assert migrate_cso(db) is True

    assert rollback_cso(db) is True
    assert _cso_index_sql(db) is None

    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE,)).fetchone()
    finally:
        conn.close()
