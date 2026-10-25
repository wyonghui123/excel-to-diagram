# -*- coding: utf-8 -*-
"""v123 定价链种子迁移测试

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md
      §3.3（种子规格）/ §3.9（迁移）/ §5（测试矩阵）

口径:
  在临时库上用开发库的**表结构**（不含数据）重放 migrate，
  既验证「空库能点亮整条链」，也验证「复跑只 SKIP」。
  不写真实开发库，避免测试污染 meta/architecture.db。
"""
import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from meta.core.sql_adapters import SQLiteAdapter
from meta.migrations.v123__pricing_chain_seed import (
    DETERMINATION_CODE,
    KEY_SCHEMA_CODE,
    PROCEDURE_CODE,
    RATE_RECORDS,
    RATE_TABLE_CODE,
    RATE_TYPE_CODE,
    SEQUENCE_CODE,
    migrate,
    verify,
)
from meta.services.pricing_service import PricingService
from meta.tests.factories._pricing_w1_helpers import clone_schema

REAL_DB = Path(__file__).resolve().parents[1] / 'architecture.db'

_SEED_TABLES = (
    'factor_catalogs',
    'key_schemas',
    'lookup_sequences',
    'rate_types',
    'calc_procedures',
    'calc_procedure_steps',
    'rate_tables',
    'rate_records',
    'pricing_determinations',
    'items',
)

_ITEM_IDS = tuple(item_id for item_id, _rate in RATE_RECORDS)


def _clone(tmp_path: Path, tables=_SEED_TABLES, with_items: bool = True) -> Path:
    if not REAL_DB.exists():
        pytest.skip('开发库不存在, 跳过种子迁移测试')
    dst_path = tmp_path / 'seed.db'
    missing = clone_schema(
        REAL_DB, dst_path, tables, item_ids=_ITEM_IDS if with_items else ())
    if missing:
        pytest.skip(f'开发库缺表 {missing}, 跳过种子迁移测试')
    return dst_path


def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]


def _code_id(conn: sqlite3.Connection, table: str, code: str):
    row = conn.execute(
        f'SELECT id FROM {table} WHERE code = ?', (code,)).fetchone()
    return row[0] if row else None


def _present_item_ids(conn: sqlite3.Connection):
    """种子只给存在的物料建价目行；测试按实际存在的物料数断言。"""
    marks = ', '.join('?' * len(_ITEM_IDS))
    rows = conn.execute(
        f'SELECT id FROM items WHERE id IN ({marks})', _ITEM_IDS).fetchall()
    return {row[0] for row in rows}


class TestMigrate:

    def test_fresh_db_lights_up_whole_chain(self, tmp_path):
        db = _clone(tmp_path)

        assert migrate(db) is True
        assert verify(db) is True

        conn = sqlite3.connect(str(db))
        try:
            present = _present_item_ids(conn)
            assert present, '临时库应至少带一个示例物料'
            assert _count(conn, 'factor_catalogs') == 3
            assert _count(conn, 'key_schemas') == 1
            assert _count(conn, 'lookup_sequences') == 1
            assert _count(conn, 'rate_types') == 1
            assert _count(conn, 'calc_procedures') == 1
            assert _count(conn, 'calc_procedure_steps') == 2
            assert _count(conn, 'rate_tables') == 1
            assert _count(conn, 'rate_records') == len(present)
            assert _count(conn, 'pricing_determinations') == 1
        finally:
            conn.close()

    def test_second_run_only_skips(self, tmp_path, capsys):
        db = _clone(tmp_path)
        assert migrate(db) is True
        capsys.readouterr()

        conn = sqlite3.connect(str(db))
        try:
            before = {t: _count(conn, t) for t in _SEED_TABLES if t != 'items'}
        finally:
            conn.close()

        assert migrate(db) is True
        out = capsys.readouterr().out
        assert 'SKIP' in out
        assert '+ INSERT' not in out

        conn = sqlite3.connect(str(db))
        try:
            after = {t: _count(conn, t) for t in _SEED_TABLES if t != 'items'}
        finally:
            conn.close()
        assert after == before

    def test_missing_required_table_aborts(self, tmp_path):
        tables = tuple(t for t in _SEED_TABLES if t != 'factor_catalogs')
        db = _clone(tmp_path, tables=tables)

        assert migrate(db) is False

    def test_missing_items_skips_rate_records(self, tmp_path, capsys):
        db = _clone(tmp_path, with_items=False)

        assert migrate(db) is True
        out = capsys.readouterr().out
        assert '缺少物料' in out
        # 物料缺失不影响其余种子与 verify 结论
        assert verify(db) is True

        conn = sqlite3.connect(str(db))
        try:
            assert _count(conn, 'rate_records') == 0
        finally:
            conn.close()


class TestSeedShape:

    @pytest.fixture(scope='class')
    def db(self, tmp_path_factory):
        db = _clone(tmp_path_factory.mktemp('seed_shape'))
        assert migrate(db) is True
        return db

    def test_factors_are_static_and_price_relevant(self, db):
        conn = sqlite3.connect(str(db))
        try:
            rows = conn.execute(
                'SELECT object_type, field_id, source_type, is_price_relevant '
                'FROM factor_catalogs').fetchall()
        finally:
            conn.close()
        assert sorted(rows) == sorted([
            ('sales_order', 'customer_account_id', 'static', 1),
            ('sales_order', 'sales_org_id', 'static', 1),
            ('sales_order_line', 'item_id', 'static', 1),
        ])

    def test_key_schema_points_to_item_id(self, db):
        conn = sqlite3.connect(str(db))
        try:
            raw = conn.execute(
                'SELECT key_fields FROM key_schemas WHERE code = ?',
                (KEY_SCHEMA_CODE,)).fetchone()[0]
        finally:
            conn.close()
        assert json.loads(raw) == ['item_id']

    def test_sequence_slot_points_to_key_schema(self, db):
        conn = sqlite3.connect(str(db))
        try:
            ks_id = _code_id(conn, 'key_schemas', KEY_SCHEMA_CODE)
            raw = conn.execute(
                'SELECT steps FROM lookup_sequences WHERE code = ?',
                (SEQUENCE_CODE,)).fetchone()[0]
        finally:
            conn.close()
        slots = json.loads(raw)
        assert slots and slots[0]['key_schema_id'] == ks_id

    def test_rate_type_binds_sequence_and_numeric_field(self, db):
        conn = sqlite3.connect(str(db))
        try:
            seq_id = _code_id(conn, 'lookup_sequences', SEQUENCE_CODE)
            row = conn.execute(
                'SELECT rate_source, numeric_field, lookup_sequence_id, sign '
                'FROM rate_types WHERE code = ?', (RATE_TYPE_CODE,)).fetchone()
        finally:
            conn.close()
        assert row == ('rate_record', 'unit_price', seq_id, '+')

    def test_procedure_steps_formula_then_round(self, db):
        conn = sqlite3.connect(str(db))
        try:
            procedure_id = _code_id(conn, 'calc_procedures', PROCEDURE_CODE)
            rate_type_id = _code_id(conn, 'rate_types', RATE_TYPE_CODE)
            rows = conn.execute(
                'SELECT seq, element_type, rate_type_id, params '
                'FROM calc_procedure_steps WHERE calc_procedure_id = ? '
                'ORDER BY seq', (procedure_id,)).fetchall()
        finally:
            conn.close()

        assert [(seq, kind) for seq, kind, _rt, _p in rows] == [
            (10, 'formula'), (20, 'round')]
        assert json.loads(rows[0][3]) == {'expr': 'lookup_amount * base'}
        assert rows[0][2] == rate_type_id
        assert rows[1][2] is None
        assert json.loads(rows[1][3])['digits'] == 2

    def test_rate_table_is_approved_global_cny(self, db):
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                'SELECT status, currency, owner_org_id, type FROM rate_tables '
                'WHERE code = ?', (RATE_TABLE_CODE,)).fetchone()
        finally:
            conn.close()
        assert row == ('approved', 'CNY', None, 'standard')

    def test_rate_records_carry_item_keys(self, db):
        conn = sqlite3.connect(str(db))
        try:
            table_id = _code_id(conn, 'rate_tables', RATE_TABLE_CODE)
            ks_id = _code_id(conn, 'key_schemas', KEY_SCHEMA_CODE)
            rate_type_id = _code_id(conn, 'rate_types', RATE_TYPE_CODE)
            rows = conn.execute(
                'SELECT code, keys, rate, key_schema_id, rate_type_id, status '
                'FROM rate_records WHERE rate_table_id = ? ORDER BY code',
                (table_id,)).fetchall()
            present = _present_item_ids(conn)
        finally:
            conn.close()

        assert len(rows) == len(present)
        expected = {
            'PT_ITEM_%s' % item_id: rate
            for item_id, rate in RATE_RECORDS if item_id in present}
        for code, keys, rate, key_schema_id, rate_type_id_row, status in rows:
            # 开发库 rate 列是 VARCHAR(200)（历史建表口径），故按数值比较
            assert float(rate) == pytest.approx(expected[code])
            assert json.loads(keys) == {'item_id': int(code.rsplit('_', 1)[1])}
            assert key_schema_id == ks_id
            assert rate_type_id_row == rate_type_id
            assert status == 'active'

    def test_determination_is_wildcard_active(self, db):
        conn = sqlite3.connect(str(db))
        try:
            table_id = _code_id(conn, 'rate_tables', RATE_TABLE_CODE)
            procedure_id = _code_id(conn, 'calc_procedures', PROCEDURE_CODE)
            seq_id = _code_id(conn, 'lookup_sequences', SEQUENCE_CODE)
            row = conn.execute(
                'SELECT sales_org_id, order_type_id, rate_table_id, '
                'calc_procedure_id, lookup_sequence_id, currency, seq, status '
                'FROM pricing_determinations WHERE code = ?',
                (DETERMINATION_CODE,)).fetchone()
        finally:
            conn.close()
        assert row == (None, None, table_id, procedure_id, seq_id, None, 100, 'active')

    def test_load_candidates_hits_seeded_records(self, db):
        conn = sqlite3.connect(str(db))
        try:
            table_id = _code_id(conn, 'rate_tables', RATE_TABLE_CODE)
            present = _present_item_ids(conn)
        finally:
            conn.close()

        ds = SQLiteAdapter()
        try:
            ds.connect(path=str(db))
            cands = PricingService(ds).load_candidates(
                table_id, valid_on=date.today().isoformat())
        finally:
            ds.disconnect()
        assert len(cands) == len(present)
        assert {c.keys.get('item_id') for c in cands} == present
