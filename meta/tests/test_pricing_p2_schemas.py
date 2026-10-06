# -*- coding: utf-8 -*-
"""定价 P2 六对象 —— schema 落地 / 真外键约束 / 枚举逐值 回归 (2026-10-06)

依据: docs/superpowers/specs/2026-10-05-pricing-engine-spec.md
      §9.3.1 A 表 (`allocation_rule` / `usage_group` / `external_rate_source` / `pricing_period`)
      §9.3.1 B 表 (`cumulative_usage`)
      §9.3.1 C 表 (`adjustment`) · FR-013 / FR-014 / FR-015 / FR-016

【本文件守什么】
  1. 六个对象已注册 + `table_name` 正确
  2. 六个对象 + `calc_result` 的 DDL 可真建表
  3. 真外键子句**逐条**存在(含列名 —— 防 `source_field` 被忽略而推出错列)
  4. `calc_results.pricing_period_id` 已由 string 收紧为 INTEGER
  5. 枚举**逐值**与 Spec 一致(非"包含")
  6. DB 级 FK 是**真约束**: 悬空引用必须抛 IntegrityError, 可空列 NULL 放行

【测试隔离 / 为何不重蹈假绿】
  内存 SQLite + `registry.reload(meta/schemas)` + SchemaGenerator 真建表。
  本文件**不含任何裸写 DML**; 播种经 `meta/tests/factories/_pricing_p2_helpers.py`
  (factories/ 是 conftest raw-SQL 门控的唯一白名单目录)。
  教训: `test_pricing_service.py` 因内联 DML 常年 42 skipped 而 Success=True。
"""
import logging
import os
import sqlite3
import sys

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.core.models import registry  # noqa: E402
from meta.core.schema_generator import SchemaGenerator  # noqa: E402
from meta.tests.factories._pricing_p2_helpers import create_tables, seed_row  # noqa: E402

SCHEMA_DIR = os.path.join(ROOT, "meta", "schemas")

P2_OBJECTS = ["allocation_rule", "adjustment", "usage_group",
              "cumulative_usage", "external_rate_source", "pricing_period"]

# 建表清单: 六对象 + calc_result(被 adjustment 引用) + 三张 FK 目标表
TABLES = P2_OBJECTS + ["calc_result", "rate_record", "calendar"]

EXPECTED_TABLES = {
    "allocation_rule": "allocation_rules",
    "adjustment": "adjustments",
    "usage_group": "usage_groups",
    "cumulative_usage": "cumulative_usages",
    "external_rate_source": "external_rate_sources",
    "pricing_period": "pricing_periods",
}

# (源列, 目标表, 目标列) —— 逐条断言, 不是"有 FK 就行"
EXPECTED_FKS = {
    "calc_result": [
        ("allocation_rule_id", "allocation_rules", "id"),
        ("external_rate_source_id", "external_rate_sources", "id"),
        ("pricing_period_id", "pricing_periods", "id"),
    ],
    "adjustment": [
        ("original_result_id", "calc_results", "id"),
    ],
    "cumulative_usage": [
        ("rate_record_id", "rate_records", "id"),
        ("usage_group_id", "usage_groups", "id"),
    ],
    "external_rate_source": [
        ("calendar_id", "calendars", "id"),
    ],
}

# 枚举逐值(Spec §9.3.1 A/C 表)
EXPECTED_ENUMS = {
    ("allocation_rule", "basis"): ["equal", "value", "quantity",
                                   "weight", "volume", "manual"],
    ("allocation_rule", "target"): ["cost", "expense"],
    ("adjustment", "adjustment_type"): [
        "subsequent_debit", "subsequent_credit", "retro_price_change",
        "rebate_settlement", "delta_accrual", "provisional_settlement", "override",
    ],
    ("external_rate_source", "source"): ["platts", "lme", "ice", "index", "custom"],
    ("pricing_period", "period_type"): ["shipment_date", "receipt_date",
                                        "invoice_date", "fixed_range"],
    ("pricing_period", "average_basis"): ["close", "average", "first", "last"],
}

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
    """registry.reload 的 yaml_loader 会大量 print; 静音后还原。

    注: `logging.disable()` 返回 None, 不能用返回值还原 —— 用 NOTSET 复位。
    """
    logging.disable(logging.CRITICAL)
    try:
        registry.reload(SCHEMA_DIR)
    finally:
        logging.disable(logging.NOTSET)


@pytest.fixture(scope="module")
def conn():
    """内存 SQLite + 按 yaml 声明真建表(不播种)。"""
    _reload_quietly()
    c = sqlite3.connect(":memory:")
    create_tables(c, TABLES)
    yield c
    c.close()


@pytest.fixture()
def fk_conn():
    """FK 强制连接: 每例新建(避免用例间数据串味)。"""
    _reload_quietly()
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1, "FK 未开启, 用例无意义"
    create_tables(c, TABLES)
    yield c
    c.close()


def _ddl(name):
    return SchemaGenerator("sqlite").generate_create_table(registry.get(name))


# ────────────────────────────────────────
# 1. 注册与表名
# ────────────────────────────────────────
class TestRegistration:
    @pytest.mark.parametrize("name", P2_OBJECTS)
    def test_registered_with_expected_table(self, name):
        mo = registry.get(name)
        assert mo is not None, "{0} 未注册".format(name)
        assert mo.table_name == EXPECTED_TABLES[name]

    @pytest.mark.parametrize("name", P2_OBJECTS)
    def test_display_name_field_declared(self, name):
        """平台约定: 每个对象必须有展示字段(否则 UI/详情无标题)"""
        mo = registry.get(name)
        assert mo.display_name_field, "{0} 缺 display_name_field".format(name)

    @pytest.mark.parametrize("name", P2_OBJECTS)
    def test_yaml_id_matches_filename(self, name):
        assert _load_raw(name)["id"] == name


# ────────────────────────────────────────
# 2. DDL 真建表
# ────────────────────────────────────────
class TestDdlLands:
    @pytest.mark.parametrize("name", TABLES)
    def test_create_table_sql_non_empty(self, name):
        assert _ddl(name).strip(), "{0} DDL 为空".format(name)

    @pytest.mark.parametrize("name", P2_OBJECTS)
    def test_table_exists_in_sqlite(self, conn, name):
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (EXPECTED_TABLES[name],),
        ).fetchall()
        assert rows == [(EXPECTED_TABLES[name],)], \
            "{0} 未真建表".format(EXPECTED_TABLES[name])


# ────────────────────────────────────────
# 3. 真外键子句逐条
# ────────────────────────────────────────
class TestForeignKeys:
    @pytest.mark.parametrize("name", sorted(EXPECTED_FKS))
    def test_each_fk_clause_present(self, name):
        ddl = _ddl(name)
        for src_col, ref_table, ref_col in EXPECTED_FKS[name]:
            clause = "FOREIGN KEY ({0}) REFERENCES {1}({2})".format(
                src_col, ref_table, ref_col
            )
            assert clause in ddl, "{0} 缺 FK: {1}".format(name, clause)

    def test_adjustment_does_not_use_wrong_column(self):
        """防回归: source_field 被忽略时 FK 列会被推成 calc_result_id(表内不存在)"""
        ddl = _ddl("adjustment")
        assert "FOREIGN KEY (calc_result_id)" not in ddl
        assert "FOREIGN KEY (original_result_id)" in ddl

    @pytest.mark.parametrize("name", sorted(EXPECTED_FKS))
    def test_fk_target_tables_all_created(self, conn, name):
        """FK 指向的表必须真实存在(否则 DML 期才炸)"""
        for _src, ref_table, _ref in EXPECTED_FKS[name]:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (ref_table,),
            ).fetchall()
            assert rows, "FK 目标表 {0} 未创建".format(ref_table)


# ────────────────────────────────────────
# 4. pricing_period_id 类型收紧
# ────────────────────────────────────────
class TestPricingPeriodIdType:
    def test_column_type_is_integer(self, conn):
        """原为 string 存 pricing_periods.code; 收紧为整型引用 id"""
        info = conn.execute("PRAGMA table_info(calc_results)").fetchall()
        types = {r[1]: (r[2] or "").upper() for r in info}
        assert "pricing_period_id" in types, "calc_results.pricing_period_id 不存在"
        assert types["pricing_period_id"] == "INTEGER", \
            "pricing_period_id 仍非整型: {0}".format(types["pricing_period_id"])

    def test_no_max_length_leftover(self):
        f = _field(_load_raw("calc_result"), "pricing_period_id")
        assert f is not None
        assert f.get("max_length") is None, "整型列不应残留 max_length"
        assert (f.get("ui") or {}).get("widget") == "reference"


# ────────────────────────────────────────
# 5. 枚举逐值
# ────────────────────────────────────────
class TestEnumsValueByValue:
    @pytest.mark.parametrize("key", sorted(EXPECTED_ENUMS))
    def test_enum_values_exact(self, key):
        bo_id, field_id = key
        f = _field(_load_raw(bo_id), field_id)
        assert f is not None, "{0}.{1} 不存在".format(bo_id, field_id)
        got = [e.get("value") for e in (f.get("enum_values") or [])]
        assert got == EXPECTED_ENUMS[key], \
            "{0}.{1} 枚举不一致: {2}".format(bo_id, field_id, got)

    @pytest.mark.parametrize("key", sorted(EXPECTED_ENUMS))
    def test_enum_has_exactly_one_initial(self, key):
        bo_id, field_id = key
        f = _field(_load_raw(bo_id), field_id)
        initials = [e for e in (f.get("enum_values") or []) if e.get("is_initial")]
        assert len(initials) == 1, \
            "{0}.{1} 初始值个数应为 1, 实为 {2}".format(bo_id, field_id, len(initials))
        assert f.get("default") == initials[0]["value"], \
            "{0}.{1} default 与 is_initial 不一致".format(bo_id, field_id)


# ────────────────────────────────────────
# 6. DB 级 FK 是真约束
# ────────────────────────────────────────
class TestForeignKeyEnforcement:
    def test_dangling_reference_rejected(self, fk_conn):
        """calc_results 空 → adjustments 引用不存在的 id 必须被拒"""
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(fk_conn, "adjustments", id=1, original_result_id=999)

    def test_nullable_reference_allows_null(self, fk_conn):
        """original_result_id 可空 → NULL 放行"""
        seed_row(fk_conn, "adjustments", id=2, original_result_id=None)
        got = fk_conn.execute(
            "SELECT original_result_id FROM adjustments WHERE id=2"
        ).fetchone()
        assert got[0] is None

    def test_valid_reference_accepted(self, fk_conn):
        """日历存在 → external_rate_sources.calendar_id 指向它应放行"""
        seed_row(fk_conn, "calendars", id=7)
        seed_row(fk_conn, "external_rate_sources", id=3, calendar_id=7)
        got = fk_conn.execute(
            "SELECT calendar_id FROM external_rate_sources WHERE id=3"
        ).fetchone()
        assert got[0] == 7

    def test_dangling_calendar_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(fk_conn, "external_rate_sources", id=4, calendar_id=4242)

    def test_cumulative_usage_rate_record_fk_enforced(self, fk_conn):
        """rate_records 空 → 必填的 rate_record_id 引用不存在必须被拒"""
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(fk_conn, "cumulative_usages", id=5, rate_record_id=888)


# ────────────────────────────────────────
# 7. 删除保护与真外键对齐
# ────────────────────────────────────────
class TestDeletionGuardBackfill:
    """新外键的**反向**登记: 被引用方须声明 restrict_on(服务层友好提示)。

    口径与 address/calendar 一致 —— FK 兜底在 DB, restrict_on 让服务层给出可读原因。
    """

    @pytest.mark.parametrize("bo_id,ref_table,ref_col", [
        ("allocation_rule", "calc_results", "allocation_rule_id"),
        ("external_rate_source", "calc_results", "external_rate_source_id"),
        ("pricing_period", "calc_results", "pricing_period_id"),
        ("usage_group", "cumulative_usages", "usage_group_id"),
        ("calc_result", "adjustments", "original_result_id"),
    ])
    def test_restrict_on_declared(self, bo_id, ref_table, ref_col):
        dp = _load_raw(bo_id)["deletion_policy"]
        assert dp["mode"] == "restrict"
        pairs = {(r["table"], r["foreign_key"]) for r in dp["restrict_on"]}
        assert (ref_table, ref_col) in pairs, \
            "{0} 缺删除保护 {1}.{2}".format(bo_id, ref_table, ref_col)

    @pytest.mark.parametrize("bo_id,ref_table,ref_col", [
        ("allocation_rule", "calc_results", "allocation_rule_id"),
        ("external_rate_source", "calc_results", "external_rate_source_id"),
        ("pricing_period", "calc_results", "pricing_period_id"),
    ])
    def test_restrict_entry_has_message(self, bo_id, ref_table, ref_col):
        dp = _load_raw(bo_id)["deletion_policy"]
        for r in dp["restrict_on"]:
            if (r["table"], r["foreign_key"]) == (ref_table, ref_col):
                assert r.get("message"), "{0} 的保护条目缺 message".format(bo_id)
                return
        pytest.fail("{0} 未登记 {1}.{2}".format(bo_id, ref_table, ref_col))

