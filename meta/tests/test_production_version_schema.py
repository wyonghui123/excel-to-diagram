# -*- coding: utf-8 -*-
"""统一资源模型 P4a（生产版本）：YAML 声明 / 真建表 / 真外键 / 迁移 v188

依据: docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md §TBD-16

【本文件守什么】
  1. production_version 已注册，table_name 正确，skip_auto_menu + 三态 UI 配置
  2. 字段口径：物料=item、工厂=org、BOM=item_structure、路线=work_definition
  3. 唯一约束只在 code；(item_id, org_id) 允许一物料多版本（按优先级/批量/有效期选路）
  4. 状态枚举与 production_version_status 字典一致；locked / lot_min / priority 默认值
  5. v188 迁移：建两表 + 工序 sequence_id + 枚举 + 8 权限 + 1 菜单，幂等、可回滚

建表隔离同 `test_work_definition_sequence_schema.py`；播种经 factories，无裸 SQL DML。
"""
import logging
import os
import sqlite3
import sys
from pathlib import Path

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.core.models import registry  # noqa: E402
from meta.migrations.v188__routing_p4a import (  # noqa: E402
    MENUS,
    PARENT_MENU,
    PERMISSIONS,
    ENUM_SEEDS,
    migrate,
    rollback,
    verify,
)
from meta.tests.factories._pricing_p2_helpers import create_tables, seed_row  # noqa: E402

SCHEMA_DIR = os.path.join(ROOT, "meta", "schemas")

TABLES = ["org", "item_group", "uom_group", "uom", "item", "item_structure",
          "work_definition", "production_version"]

EXPECTED_FKS = {
    ("item_id", "items", "id"),
    ("org_id", "orgs", "id"),
    ("bom_id", "item_structures", "id"),
    ("work_definition_id", "work_definitions", "id"),
}

NOT_NULL_COLUMNS = ("code", "item_id", "org_id", "work_definition_id",
                    "valid_from", "lot_min", "priority", "locked", "status")

NULLABLE_COLUMNS = ("bom_id", "valid_to", "lot_max", "description")

pytestmark = pytest.mark.unit


def _load_raw(bo_id):
    with open(os.path.join(SCHEMA_DIR, bo_id + ".yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _field(schema, field_id):
    for f in schema.get("fields") or []:
        if f.get("id") == field_id:
            return f
    return None


def _reload_quietly():
    logging.disable(logging.CRITICAL)
    try:
        registry.reload(SCHEMA_DIR)
    finally:
        logging.disable(logging.NOTSET)


@pytest.fixture(scope="module")
def conn():
    _reload_quietly()
    c = sqlite3.connect(":memory:")
    create_tables(c, TABLES)
    yield c
    c.close()


@pytest.fixture()
def fk_conn():
    _reload_quietly()
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    create_tables(c, TABLES)
    yield c
    c.close()


def _fk_set(conn, table):
    return {(row[3], row[2], row[4]) for row in conn.execute(
        "PRAGMA foreign_key_list({0})".format(table))}


class TestDeclaration:

    def test_object_registered(self):
        _reload_quietly()
        mo = registry.get("production_version")
        assert mo is not None, "production_version 未注册"
        assert mo.table_name == "production_versions"
        assert mo.aspects and "audit_aspect" in mo.aspects

    def test_skip_auto_menu_and_three_state_ui(self):
        schema = _load_raw("production_version")
        assert schema["ui_view_config"]["skip_auto_menu"] is True
        for key in ("list", "form", "detail"):
            assert key in schema["ui_view_config"]

    def test_code_required_and_unique(self):
        code = _field(_load_raw("production_version"), "code")
        assert code["required"] is True
        assert code["unique"] is True
        assert code["semantics"]["business_key"] is True

    def test_reference_fields(self):
        expected = {
            "item_id": ("item", False),
            "org_id": ("org", False),
            "bom_id": ("item_structure", True),
            "work_definition_id": ("work_definition", False),
        }
        schema = _load_raw("production_version")
        for field_id, (target_bo, nullable) in expected.items():
            field = _field(schema, field_id)
            assert field is not None, "production_version.{0} 缺失".format(field_id)
            assert field["value_help"]["source"]["type"] == "bo"
            assert field["value_help"]["source"]["target_bo"] == target_bo
            assert field["value_help"]["source"]["apply_target_permissions"] is True
            assert field["value_help"]["behavior"]["binding_strength"] == "strict"
            assert bool(field.get("nullable")) is nullable

    def test_validity_and_lot_fields(self):
        schema = _load_raw("production_version")
        valid_from = _field(schema, "valid_from")
        assert valid_from["type"] == "date"
        assert valid_from["required"] is True
        valid_to = _field(schema, "valid_to")
        assert valid_to["type"] == "date"
        assert valid_to.get("nullable") is True
        lot_min = _field(schema, "lot_min")
        assert lot_min["default"] == 0
        assert lot_min["required"] is True
        assert lot_min["constraints"][0]["gte"] == 0
        lot_max = _field(schema, "lot_max")
        assert lot_max.get("nullable") is True

    def test_priority_and_locked(self):
        schema = _load_raw("production_version")
        priority = _field(schema, "priority")
        assert priority["default"] == 1
        assert priority["required"] is True
        assert priority["constraints"][0]["gte"] == 1
        locked = _field(schema, "locked")
        assert locked["type"] == "boolean"
        assert locked["default"] is False
        assert locked["required"] is True

    def test_status_enum(self):
        field = _field(_load_raw("production_version"), "status")
        assert [v["value"] for v in field["enum_values"]] == [
            "draft", "active", "obsolete"]
        assert all("label" in v for v in field["enum_values"])
        assert field["default"] == "draft"
        assert field["value_help"]["source"]["enum_type_id"] == \
            "production_version_status"

    def test_indexes_declared(self):
        indexes = {i.get("name"): i for i in
                   _load_raw("production_version")["indexes"]}
        assert indexes["uq_production_version_code"]["unique"] is True
        assert indexes["uq_production_version_code"]["fields"] == ["code"]
        assert indexes["idx_production_version_item_org"]["fields"] == [
            "item_id", "org_id"]
        assert indexes["idx_production_version_work_definition"]["fields"] == [
            "work_definition_id"]
        assert indexes["idx_production_version_status"]["fields"] == ["status"]

    def test_relations_are_four_real_fks(self):
        relations = {r["source_field"] for r in
                     _load_raw("production_version")["relations"]}
        assert relations == {"item_id", "org_id", "bom_id", "work_definition_id"}

    def test_deletion_policy(self):
        policy = _load_raw("production_version")["deletion_policy"]
        assert policy["mode"] == "restrict"
        assert policy["restrict_on"] == []
        assert policy["cascade_delete"] == []


class TestTable:

    def test_table_created(self, conn):
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "production_versions" in names

    def test_foreign_keys(self, conn):
        assert _fk_set(conn, "production_versions") == EXPECTED_FKS

    def test_not_null_columns(self, conn):
        info = {r[1]: r for r in conn.execute(
            "PRAGMA table_info(production_versions)")}
        for col in NOT_NULL_COLUMNS:
            assert info[col][3] == 1, "{0} 应 NOT NULL".format(col)

    def test_nullable_columns(self, conn):
        info = {r[1]: r for r in conn.execute(
            "PRAGMA table_info(production_versions)")}
        for col in NULLABLE_COLUMNS:
            assert info[col][3] == 0, "{0} 应可空".format(col)

    def test_indexes_created(self, conn):
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        for name in ("uq_production_version_code",
                     "idx_production_version_item_org",
                     "idx_production_version_work_definition",
                     "idx_production_version_bom",
                     "idx_production_version_status"):
            assert name in names, "缺索引 {0}".format(name)

    def test_duplicate_code_rejected(self, conn):
        seed_row(conn, "production_versions", code="PV-001", item_id=1, org_id=1,
                 work_definition_id=1, valid_from="2026-01-01")
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "production_versions", code="PV-001", item_id=1, org_id=1,
                     work_definition_id=1, valid_from="2026-02-01")

    def test_same_item_org_can_have_multiple_versions(self, conn):
        """同一物料同一工厂允许多条生产版本（按优先级/批量/有效期选路）。"""
        seed_row(conn, "production_versions", code="PV-A", item_id=7, org_id=2,
                 work_definition_id=1, valid_from="2026-01-01", priority=1)
        seed_row(conn, "production_versions", code="PV-B", item_id=7, org_id=2,
                 work_definition_id=2, valid_from="2026-01-01", priority=2)

    def test_dangling_item_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "production_versions", code="PV-ORPHAN", item_id=999,
                     org_id=999, work_definition_id=999, valid_from="2026-01-01")
        assert "FOREIGN KEY" in str(exc.value).upper()


INFRA_DDL = (
    """
CREATE TABLE menus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_code VARCHAR(200) UNIQUE NOT NULL,
    menu_name VARCHAR(200) NOT NULL,
    menu_path VARCHAR(200),
    page_type VARCHAR(200) NOT NULL DEFAULT 'object_list',
    object_types TEXT,
    primary_object_type VARCHAR(200),
    bo_bindings TEXT,
    required_permissions TEXT,
    required_any_permission INTEGER DEFAULT 0,
    data_permission_hint TEXT,
    page_config TEXT,
    parent_menu VARCHAR(200),
    icon VARCHAR(200),
    color VARCHAR(200),
    description VARCHAR(200),
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    show_in_sidebar INTEGER DEFAULT 1,
    auto_generated INTEGER DEFAULT 0
)
""",
    """
CREATE TABLE menu_permissions (
    menu_code VARCHAR(200) UNIQUE NOT NULL,
    menu_name VARCHAR(200) NOT NULL,
    menu_path VARCHAR(200) NOT NULL,
    required_permissions TEXT,
    required_any_permission INTEGER DEFAULT 0,
    parent_menu VARCHAR(200),
    icon VARCHAR(200),
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    data_permission_hint TEXT,
    created_at DATETIME,
    updated_at DATETIME
)
""",
    """
CREATE TABLE permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    resource_type VARCHAR(200),
    action VARCHAR(200)
)
""",
    """
CREATE TABLE permission_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    is_active INTEGER DEFAULT 1,
    is_system INTEGER DEFAULT 0
)
""",
    """
CREATE TABLE permission_set_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    permission_set_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    granted INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME
)
""",
    """
CREATE TABLE enum_types (
    id VARCHAR(200) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(200) NOT NULL,
    mutability VARCHAR(200) NOT NULL,
    dimension_schema TEXT,
    description TEXT,
    created_at DATETIME
)
""",
    """
CREATE TABLE enum_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enum_type_id VARCHAR(200) NOT NULL,
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    name_en VARCHAR(200),
    dimensions TEXT,
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    is_system INTEGER DEFAULT 0,
    parent_code VARCHAR(200),
    metadata TEXT,
    created_at DATETIME
)
""",
    "CREATE TABLE work_definitions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "code VARCHAR(200))",
    "CREATE TABLE work_definition_operations (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "operation_name VARCHAR(200))",
)


def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / "routing_p4a.db"
    conn = sqlite3.connect(str(db))
    try:
        for ddl in INFRA_DDL:
            conn.execute(ddl)
        seed_row(conn, "menus", menu_code=PARENT_MENU, menu_name="主数据",
                 menu_path="", page_type="multi_object_hub", is_active=1,
                 show_in_sidebar=1)
        seed_row(conn, "permission_sets", code="admin", name="管理员", is_active=1)
        seed_row(conn, "permission_sets", code="default", name="默认权限集",
                 is_active=1)
        conn.commit()
    finally:
        conn.close()
    return db


def _scalar(path: Path, sql: str, params=()):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def _tables(path: Path) -> set:
    conn = sqlite3.connect(str(path))
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


class TestMigration:

    def test_migrate_and_verify(self, tmp_path):
        db = _make_db(tmp_path)
        assert migrate(db)
        assert verify(db) is True

        tables = _tables(db)
        assert "production_versions" in tables
        assert "work_definition_sequences" in tables

        cols = {r[1] for r in _scalar_cols(db, "work_definition_operations")}
        assert "sequence_id" in cols

        assert _scalar(db, "SELECT COUNT(*) FROM menus WHERE menu_code=?",
                       (MENUS[0]["menu_code"],))[0] == 1
        assert _scalar(db, "SELECT COUNT(*) FROM menu_permissions "
                           "WHERE menu_code=?", (MENUS[0]["menu_code"],))[0] == 1
        assert _scalar(db, "SELECT COUNT(*) FROM permissions WHERE code IN (%s)"
                       % ",".join("?" * len(PERMISSIONS)),
                       tuple(code for code, _n, _r, _a in PERMISSIONS))[0] == 8
        for type_id, _name, _desc, values in ENUM_SEEDS:
            got = _scalar(db, "SELECT COUNT(*) FROM enum_values "
                              "WHERE enum_type_id=?", (type_id,))[0]
            assert got == len(values), "枚举 {0} 取值数不符".format(type_id)

    def test_migrate_is_idempotent(self, tmp_path):
        db = _make_db(tmp_path)
        assert migrate(db)
        assert migrate(db)
        assert _scalar(db, "SELECT COUNT(*) FROM menus WHERE menu_code=?",
                       (MENUS[0]["menu_code"],))[0] == 1
        assert _scalar(db, "SELECT COUNT(*) FROM permissions WHERE code IN (%s)"
                       % ",".join("?" * len(PERMISSIONS)),
                       tuple(code for code, _n, _r, _a in PERMISSIONS))[0] == 8

    def test_rollback(self, tmp_path):
        db = _make_db(tmp_path)
        assert migrate(db)
        assert rollback(db)
        tables = _tables(db)
        assert "production_versions" not in tables
        assert "work_definition_sequences" not in tables
        assert _scalar(db, "SELECT COUNT(*) FROM menus WHERE menu_code=?",
                       (MENUS[0]["menu_code"],))[0] == 0
        assert _scalar(db, "SELECT COUNT(*) FROM permissions WHERE code IN (%s)"
                       % ",".join("?" * len(PERMISSIONS)),
                       tuple(code for code, _n, _r, _a in PERMISSIONS))[0] == 0


def _scalar_cols(db: Path, table: str):
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute("PRAGMA table_info({0})".format(table)).fetchall()
    finally:
        conn.close()
