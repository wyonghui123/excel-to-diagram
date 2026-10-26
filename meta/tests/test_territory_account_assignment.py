# -*- coding: utf-8 -*-
"""客户区域分配（M2）：YAML 声明 / 真建表 / 唯一约束 / 迁移 v133

依据: docs/superpowers/specs/2026-10-26-sales-territory-design.md
      §4.4（对象）/ §5（R-TER-6 / R-TER-7）/ §3.3（菜单中文名）

【本文件守什么】
  1. 对象已注册，table_name / parent_object 正确，skip_auto_menu 生效
  2. 字段必填 / 可空与 assignment_source 枚举符合设计
  3. 按 yaml 真建表，两条真外键（客户 / 区域）
  4. 唯一约束：三元组、客户同日第二主区域（部分唯一）、NULL 生效日不互斥
  5. 客户详情已挂「客户区域分配」子表；两侧删除保护就位
  6. v133：索引补齐 / 菜单改名 / 复跑 SKIP / 缺表终止 / 回滚

测试隔离同 `test_territory_schema.py`：内存 SQLite + registry 重载 + 真建表；
迁移部分用开发库表结构克隆到临时库，不写真实开发库。
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
from meta.migrations.v133__territory_account_assignment import (  # noqa: E402
    ASSIGNMENT_TABLE,
    MENU_CODE,
    MENU_NAME_NEW,
    _INDEX_DDL,
    migrate,
    rollback,
    verify,
)
from meta.tests.factories._pricing_p2_helpers import create_tables, seed_row  # noqa: E402
from meta.tests.factories._pricing_w1_helpers import clone_schema  # noqa: E402

SCHEMA_DIR = os.path.join(ROOT, "meta", "schemas")
REAL_DB = Path(__file__).resolve().parents[1] / "architecture.db"

# customer_account 的两条真外键（tax_classification / payment_term）在开 FK 的
# 用例里必须先有目标表，否则插客户行时会报 "no such table"。
TABLES = ["party", "user", "org", "tax_classification", "payment_term",
          "customer_account", "territory", "territory_account_assignment"]

ASSIGNMENT_FKS = [
    ("customer_account_id", "customer_accounts", "id"),
    ("territory_id", "territories", "id"),
]

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


def _index_sql(conn, name):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone()
    return row[0] if row else None


# ─────────────────────────────────────────────────────────────────────────────
# 声明层
# ─────────────────────────────────────────────────────────────────────────────

class TestDeclaration:

    def test_object_registered(self):
        _reload_quietly()
        obj = registry.get("territory_account_assignment")
        assert obj is not None
        assert obj.table_name == "territory_account_assignments"

    def test_parent_and_menu(self):
        schema = _load_raw("territory_account_assignment")
        assert schema["parent_object"] == "customer_account"
        assert schema["ui_view_config"]["skip_auto_menu"] is True

    def test_required_and_optional_fields(self):
        schema = _load_raw("territory_account_assignment")
        for field_id in ("customer_account_id", "territory_id", "is_primary",
                         "assignment_source"):
            assert _field(schema, field_id)["required"] is True
        for field_id in ("effective_from", "effective_to", "priority"):
            assert _field(schema, field_id).get("nullable") is True

    def test_assignment_source_enum(self):
        src = _field(_load_raw("territory_account_assignment"), "assignment_source")
        assert src["default"] == "manual"
        assert [v["value"] for v in src["enum_values"]] == [
            "manual", "rule", "import"]

    def test_indexes_declared(self):
        idx = {i["name"]: i for i in
               _load_raw("territory_account_assignment")["indexes"]}
        assert idx["uq_taa_triple"]["fields"] == [
            "customer_account_id", "territory_id", "effective_from"]
        assert idx["uq_taa_triple"]["unique"] is True
        primary = idx["uq_taa_primary"]
        assert primary["unique"] is True and primary["type"] == "partial"
        assert "is_primary = 1" in primary["condition"]
        assert idx["idx_taa_territory"]["fields"] == ["territory_id"]
        assert idx["idx_taa_customer"]["fields"] == ["customer_account_id"]

    def test_customer_child_section(self):
        children = (_load_raw("customer_account").get("ui_view_config") or {}) \
            .get("child_sections") or []
        match = [c for c in children
                 if c.get("child_object") == "territory_account_assignment"]
        assert match, "客户档案详情未挂载 territory_account_assignment"
        assert match[0]["display"] == "tab"

    def test_deletion_protection_both_sides(self):
        customer = {(r["table"], r["foreign_key"])
                    for r in _load_raw("customer_account")["deletion_policy"]["restrict_on"]}
        assert ("territory_account_assignments", "customer_account_id") in customer

        territory = {(r["table"], r["foreign_key"])
                     for r in _load_raw("territory")["deletion_policy"]["restrict_on"]}
        assert ("territory_account_assignments", "territory_id") in territory


# ─────────────────────────────────────────────────────────────────────────────
# 建表层
# ─────────────────────────────────────────────────────────────────────────────

class TestTable:

    def test_table_created(self, conn):
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert ASSIGNMENT_TABLE in names

    def test_foreign_keys(self, conn):
        fks = {(row[3], row[2], row[4]) for row in conn.execute(
            "PRAGMA foreign_key_list(%s)" % ASSIGNMENT_TABLE)}
        assert fks == set(ASSIGNMENT_FKS)

    def test_indexes_created(self, conn):
        triple = _index_sql(conn, "uq_taa_triple") or ""
        assert "UNIQUE" in triple.upper()
        primary = _index_sql(conn, "uq_taa_primary") or ""
        assert "UNIQUE" in primary.upper()
        assert "WHERE" in primary.upper() and "IS_PRIMARY" in primary.upper()

    def test_not_null_and_nullable(self, conn):
        cols = {r[1]: r for r in conn.execute(
            "PRAGMA table_info(%s)" % ASSIGNMENT_TABLE)}
        for column in ("customer_account_id", "territory_id", "is_primary",
                       "assignment_source"):
            assert cols[column][3] == 1
        for column in ("effective_from", "effective_to", "priority"):
            assert cols[column][3] == 0

    def test_dangling_customer_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, ASSIGNMENT_TABLE,
                     customer_account_id=999, territory_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_dangling_territory_rejected(self, fk_conn):
        seed_row(fk_conn, "customer_accounts", id=71, relation_id=1, name="客户甲")
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, ASSIGNMENT_TABLE,
                     customer_account_id=71, territory_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_duplicate_triple_rejected(self, conn):
        seed_row(conn, "customer_accounts", id=72, relation_id=2, name="客户乙")
        seed_row(conn, "territories", id=72, code="TAA72", name="七十二区")
        seed_row(conn, ASSIGNMENT_TABLE, customer_account_id=72, territory_id=72,
                 effective_from="2026-10-01", is_primary=0)
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, ASSIGNMENT_TABLE, customer_account_id=72, territory_id=72,
                     effective_from="2026-10-01", is_primary=0)

    def test_second_primary_rejected(self, conn):
        seed_row(conn, "customer_accounts", id=73, relation_id=3, name="客户丙")
        seed_row(conn, "territories", id=73, code="TAA73", name="七十三区")
        seed_row(conn, "territories", id=74, code="TAA74", name="七十四区")
        seed_row(conn, ASSIGNMENT_TABLE, customer_account_id=73, territory_id=73,
                 effective_from="2026-10-01", is_primary=1)
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, ASSIGNMENT_TABLE, customer_account_id=73, territory_id=74,
                     effective_from="2026-10-01", is_primary=1)

    def test_two_non_primary_allowed(self, conn):
        seed_row(conn, "customer_accounts", id=75, relation_id=4, name="客户丁")
        seed_row(conn, "territories", id=75, code="TAA75", name="七十五区")
        seed_row(conn, "territories", id=76, code="TAA76", name="七十六区")
        seed_row(conn, ASSIGNMENT_TABLE, customer_account_id=75, territory_id=75,
                 effective_from="2026-10-01", is_primary=0)
        seed_row(conn, ASSIGNMENT_TABLE, customer_account_id=75, territory_id=76,
                 effective_from="2026-10-01", is_primary=0)


# ─────────────────────────────────────────────────────────────────────────────
# 迁移 v133
# ─────────────────────────────────────────────────────────────────────────────

def _clone(tmp_path: Path) -> Path:
    if not REAL_DB.exists():
        pytest.skip('开发库不存在, 跳过迁移测试')
    dst = tmp_path / 'territory_account.db'
    missing = clone_schema(REAL_DB, dst, (ASSIGNMENT_TABLE, 'territories', 'menus'))
    if missing:
        pytest.skip(f'开发库缺表 {missing}, 跳过迁移测试')
    return dst


def _seed(db: Path, table: str, **values):
    """按路径插一行（复用 p2 的「NOT NULL 无默认列自动补占位」能力）。"""
    c = sqlite3.connect(str(db))
    try:
        seed_row(c, table, **values)
        c.commit()
    finally:
        c.close()


def _index_names(path: Path) -> set:
    c = sqlite3.connect(str(path))
    try:
        return {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        c.close()


def _scalar(path: Path, sql: str, params=()):
    c = sqlite3.connect(str(path))
    try:
        return c.execute(sql, params).fetchone()
    finally:
        c.close()


class TestMigration:

    def test_creates_indexes_and_renames_menu(self, tmp_path):
        db = _clone(tmp_path)
        _seed(db, 'menus', menu_code=MENU_CODE, menu_name='区域')
        assert not (_index_names(db) & {name for name, _ddl in _INDEX_DDL})
        assert _scalar(db, "SELECT menu_name FROM menus WHERE menu_code = ?",
                       (MENU_CODE,))[0] == '区域'

        assert migrate(db) is True
        names = _index_names(db)
        for name, _ddl in _INDEX_DDL:
            assert name in names
        assert _scalar(db, "SELECT menu_name FROM menus WHERE menu_code = ?",
                       (MENU_CODE,))[0] == MENU_NAME_NEW
        assert verify(db) is True

    def test_rerun_is_idempotent(self, tmp_path):
        db = _clone(tmp_path)
        _seed(db, 'menus', menu_code=MENU_CODE, menu_name=MENU_NAME_NEW)
        assert migrate(db) is True
        before = _index_names(db)
        assert migrate(db) is True
        assert _index_names(db) == before
        assert verify(db) is True

    def test_missing_table_terminates(self, tmp_path):
        db = tmp_path / 'empty.db'
        sqlite3.connect(str(db)).close()
        assert migrate(db) is False
        assert verify(db) is False

    def test_duplicate_triple_blocks_unique_index(self, tmp_path):
        db = _clone(tmp_path)
        _seed(db, 'menus', menu_code=MENU_CODE, menu_name='区域')
        _seed(db, 'territories', id=81, code="TAA81", name="八十一区")
        _seed(db, ASSIGNMENT_TABLE, customer_account_id=1, territory_id=81,
                 effective_from="2026-10-01", is_primary=0)
        _seed(db, ASSIGNMENT_TABLE, customer_account_id=1, territory_id=81,
                 effective_from="2026-10-01", is_primary=0)
        assert migrate(db) is False
        assert 'uq_taa_triple' not in _index_names(db)

    def test_rollback_drops_indexes_and_reverts_menu(self, tmp_path):
        db = _clone(tmp_path)
        _seed(db, 'menus', menu_code=MENU_CODE, menu_name='区域')
        assert migrate(db) is True
        assert rollback(db) is True
        assert _index_names(db).isdisjoint({name for name, _ddl in _INDEX_DDL})
        assert _scalar(db, "SELECT menu_name FROM menus WHERE menu_code = ?",
                       (MENU_CODE,))[0] == '区域'
        assert verify(db) is False
