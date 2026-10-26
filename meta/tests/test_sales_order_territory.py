# -*- coding: utf-8 -*-
"""销售订单区域快照（M3）：字段声明 / 区域带出判定 / R-TER-8 冻结 / 迁移 v134

依据: docs/superpowers/specs/2026-10-26-sales-territory-design.md
      §4.5（抬头快照）/ §5 R-TER-8 / §6.1（客户主区域判定）

【本文件守什么】
  1. `sales_order.territory_id` 可空、候选限 active、有真外键关系与过滤索引
  2. 列表列 / 表单字段已声明（未分配显示「未分配」）
  3. §6.1 判定顺序：当日有效 → 主区域优先 → priority 升序 → effective_from 最新
  4. fail-open：无分配 / 缺客户 / 读侧异常 一律返回空，不阻断下单
  5. R-TER-8：confirmed / closed 后不可改，draft / submitted 可改
  6. v134：补列 + 建索引 / 复跑幂等 / 缺表终止 / 回滚只扔索引

判定用例用真实 SQLite（临时文件 + yaml 真建表），让 ORDER BY 语义被真正执行，
而非用假数据源替用户验证排序。
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

from meta.core.datasource import get_data_source  # noqa: E402
from meta.core.models import registry  # noqa: E402
from meta.core.schema_generator import SchemaGenerator  # noqa: E402
from meta.migrations.v134__sales_order_territory import (  # noqa: E402
    COLUMN,
    IDX_ORDER_TERRITORY,
    ORDER_TABLE,
    migrate,
    rollback,
    verify,
)
from meta.services.sales_order_guard_service import (  # noqa: E402
    SalesOrderGuardError,
    SalesOrderGuardService,
)
from meta.tests.factories._pricing_p2_helpers import create_tables, seed_row  # noqa: E402

SCHEMA_DIR = os.path.join(ROOT, "meta", "schemas")
TODAY = '2026-06-30'

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


class _BrokenDS:
    """读侧异常：守卫必须 fail-open。"""

    def query(self, sql, params=None):
        raise RuntimeError('boom')


def _service(ds):
    svc = SalesOrderGuardService(ds)
    svc._today = lambda: TODAY
    return svc


@pytest.fixture()
def make_service(tmp_path):
    """按给定的客户分配行造库并返回守卫服务。

    `rows` 每项是分配行，第 i 行自动配 territory_id = 100 + i，返回值用于断言。
    """
    opened = []

    def _factory(rows=(), customer_id=1):
        path = tmp_path / ('territory_default_%d.db' % len(opened))
        conn = sqlite3.connect(str(path))
        create_tables(conn, ['territory', 'territory_account_assignment'])
        for i, row in enumerate(rows):
            territory_id = 100 + i
            seed_row(conn, 'territories', id=territory_id,
                     code='T%d' % territory_id, name='区域%d' % territory_id)
            seed_row(conn, 'territory_account_assignments',
                     customer_account_id=customer_id,
                     territory_id=territory_id, **row)
        conn.commit()
        conn.close()
        ds = get_data_source('sqlite', database=str(path))
        opened.append(ds)
        return _service(ds)

    yield _factory
    for ds in opened:
        ds.disconnect()


# ─────────────────────────────────────────────────────────────────────────────
# 声明层
# ─────────────────────────────────────────────────────────────────────────────

class TestDeclaration:

    def test_field_nullable_and_active_candidates(self):
        _reload_quietly()
        raw = _load_raw("sales_order")
        field = _field(raw, "territory_id")
        assert field is not None
        assert field.get("nullable") is True
        assert field["value_help"]["source"]["target_bo"] == "territory"
        assert field["value_help"]["source"]["value_filter"] == {"status": "active"}
        assert field["ui"]["relation"] == "territory"

    def test_relation_and_index_declared(self):
        raw = _load_raw("sales_order")
        relations = {r["id"]: r for r in raw["relations"]}
        assert relations["sales_order_to_territory"]["source_field"] == "territory_id"
        assert relations["sales_order_to_territory"]["target"] == "territory"
        indexes = {i["name"]: i for i in raw["indexes"]}
        assert indexes[IDX_ORDER_TERRITORY]["fields"] == ["territory_id"]

    def test_list_and_form_expose_territory(self):
        ui = _load_raw("sales_order")["ui_view_config"]
        columns = [c["field"] for c in ui["list"]["columns"]]
        assert "territory_id" in columns
        form_fields = [
            f for section in ui["form"]["sections"]
            for column in section["columns"]
            for f in column["fields"]
        ]
        assert "territory_id" in form_fields

    def test_generated_ddl_has_column(self):
        _reload_quietly()
        sql = SchemaGenerator("sqlite").generate_create_table(
            registry.get("sales_order"))
        assert "territory_id" in sql
        assert "FOREIGN KEY (territory_id) REFERENCES territories(id)" in sql


# ─────────────────────────────────────────────────────────────────────────────
# §6.1 客户主区域判定
# ─────────────────────────────────────────────────────────────────────────────

class TestTerritoryDefault:

    def test_primary_wins_over_priority(self, make_service):
        svc = make_service([
            {"is_primary": 0, "priority": 1},
            {"is_primary": 1, "priority": 99},
        ])
        assert svc.territory_default({"customer_account_id": 1}) == {
            "territory_id": 101}

    def test_priority_ascending_when_no_primary(self, make_service):
        svc = make_service([
            {"is_primary": 0, "priority": 5},
            {"is_primary": 0, "priority": 2},
        ])
        assert svc.territory_default({"customer_account_id": 1}) == {
            "territory_id": 101}

    def test_priority_null_ranks_last(self, make_service):
        svc = make_service([
            {"is_primary": 0, "priority": None},
            {"is_primary": 0, "priority": 9},
        ])
        assert svc.territory_default({"customer_account_id": 1}) == {
            "territory_id": 101}

    def test_latest_effective_from_breaks_tie(self, make_service):
        svc = make_service([
            {"is_primary": 0, "priority": 2, "effective_from": "2026-01-01"},
            {"is_primary": 0, "priority": 2, "effective_from": "2026-05-01"},
        ])
        assert svc.territory_default({"customer_account_id": 1}) == {
            "territory_id": 101}

    def test_expired_assignment_ignored(self, make_service):
        svc = make_service([
            {"is_primary": 0, "effective_to": "2026-06-29"},
        ])
        assert svc.territory_default({"customer_account_id": 1}) == {}

    def test_future_assignment_ignored(self, make_service):
        svc = make_service([
            {"is_primary": 0, "effective_from": "2026-07-01"},
        ])
        assert svc.territory_default({"customer_account_id": 1}) == {}

    def test_boundary_days_inclusive(self, make_service):
        svc = make_service([
            {"is_primary": 0, "effective_from": TODAY, "effective_to": TODAY},
        ])
        assert svc.territory_default({"customer_account_id": 1}) == {
            "territory_id": 100}

    def test_blank_effective_from_means_immediate(self, make_service):
        svc = make_service([{"is_primary": 0, "effective_from": None}])
        assert svc.territory_default({"customer_account_id": 1}) == {
            "territory_id": 100}

    def test_no_assignment_returns_empty(self, make_service):
        svc = make_service([])
        assert svc.territory_default({"customer_account_id": 1}) == {}

    def test_missing_customer_returns_empty(self, make_service):
        svc = make_service([{"is_primary": 1}])
        assert svc.territory_default({"customer_account_id": None}) == {}

    def test_manual_value_not_overwritten(self, make_service):
        svc = make_service([{"is_primary": 1}])
        assert svc.territory_default({
            "customer_account_id": 1, "territory_id": 999}) == {}

    def test_read_failure_fails_open(self):
        svc = _service(_BrokenDS())
        assert svc.territory_default({"customer_account_id": 1}) == {}


# ─────────────────────────────────────────────────────────────────────────────
# R-TER-8 确认后冻结
# ─────────────────────────────────────────────────────────────────────────────

class TestTerritoryLocked:

    def _validate(self, data, old):
        SalesOrderGuardService(_BrokenDS()).validate_order_write(
            data, old_data=old, is_create=False)

    def test_confirmed_rejects_change(self):
        with pytest.raises(SalesOrderGuardError) as exc:
            self._validate({"territory_id": 2},
                           {"status": "confirmed", "territory_id": 1})
        assert exc.value.rule == 'order_territory_locked'
        assert exc.value.field_name == 'territory_id'

    def test_closed_rejects_change(self):
        with pytest.raises(SalesOrderGuardError) as exc:
            self._validate({"territory_id": 2},
                           {"status": "closed", "territory_id": 1})
        assert exc.value.rule == 'order_territory_locked'

    def test_confirmed_allows_same_value(self):
        self._validate({"territory_id": 1},
                       {"status": "confirmed", "territory_id": 1})

    def test_draft_allows_change(self):
        self._validate({"territory_id": 2},
                       {"status": "draft", "territory_id": 1})

    def test_submitted_allows_change(self):
        self._validate({"territory_id": 2},
                       {"status": "submitted", "territory_id": 1})


# ─────────────────────────────────────────────────────────────────────────────
# 迁移 v134
# ─────────────────────────────────────────────────────────────────────────────

def _stub_db(tmp_path: Path) -> Path:
    db = tmp_path / 'sales_order_territory.db'
    conn = sqlite3.connect(str(db))
    conn.execute('CREATE TABLE sales_orders (id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()
    return db


def _columns(path: Path, table: str):
    conn = sqlite3.connect(str(path))
    try:
        return [r[1] for r in conn.execute(
            'PRAGMA table_info({0})'.format(table))]
    finally:
        conn.close()


def _index_names(path: Path) -> set:
    conn = sqlite3.connect(str(path))
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        conn.close()


class TestMigration:

    def test_adds_column_and_index(self, tmp_path):
        db = _stub_db(tmp_path)
        assert COLUMN not in _columns(db, ORDER_TABLE)
        assert migrate(db) is True
        assert COLUMN in _columns(db, ORDER_TABLE)
        assert IDX_ORDER_TERRITORY in _index_names(db)
        assert verify(db) is True

    def test_rerun_is_idempotent(self, tmp_path):
        db = _stub_db(tmp_path)
        assert migrate(db) is True
        assert migrate(db) is True
        assert verify(db) is True

    def test_missing_table_terminates(self, tmp_path):
        db = tmp_path / 'empty.db'
        sqlite3.connect(str(db)).close()
        assert migrate(db) is False
        assert verify(db) is False

    def test_rollback_drops_index_keeps_column(self, tmp_path):
        db = _stub_db(tmp_path)
        assert migrate(db) is True
        assert rollback(db) is True
        assert IDX_ORDER_TERRITORY not in _index_names(db)
        assert COLUMN in _columns(db, ORDER_TABLE)
