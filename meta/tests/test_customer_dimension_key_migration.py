# -*- coding: utf-8 -*-
"""v130 客户维度匹配键迁移测试

依据: docs/superpowers/specs/2026-10-25-sales-order-wave2-detailed-plan.md
      §8.2（客户维度）/ §8.4（R-KEY-1~3）/ §9.1（v130 幂等判据）

口径:
  在临时库上用开发库的**表结构**（不含数据）重放 migrate：
  验证「空库能点亮客户维配置」「复跑只 SKIP」「回滚清干净」。
  不写真实开发库。
"""
import json
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from meta.core.sql_adapters import SQLiteAdapter
from meta.migrations.v123__pricing_chain_seed import migrate as migrate_wave1
from meta.migrations.v130__customer_dimension_key import (
    BASE_KEY_SCHEMA_CODE,
    BASE_SEQUENCE_CODE,
    DETERMINATION_CODE,
    FACTOR,
    KEY_SCHEMA_CODE,
    KEY_SCHEMA_FIELDS,
    RATE_TABLE_CODE,
    RECORD_CODE,
    SAMPLE_CUSTOMER_ID,
    SAMPLE_ITEM_ID,
    SAMPLE_RATE,
    SEQUENCE_CODE,
    migrate,
    rollback,
    verify,
)
from meta.services.pricing_determination_service import PricingDeterminationService
from meta.tests.factories._pricing_w1_helpers import (
    clone_schema,
    delete_row,
    seed_row,
)

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
    'customer_accounts',
)


def _clone(tmp_path: Path, with_item: bool = True) -> Path:
    if not REAL_DB.exists():
        pytest.skip('开发库不存在, 跳过种子迁移测试')
    dst = tmp_path / 'v130.db'
    missing = clone_schema(
        REAL_DB, dst, _SEED_TABLES,
        item_ids=(SAMPLE_ITEM_ID,) if with_item else ())
    if missing:
        pytest.skip(f'开发库缺表 {missing}, 跳过种子迁移测试')
    # W2-F 依赖波次 1 的 KS_ITEM，临时库先点亮波次 1 再验 v130
    assert migrate_wave1(dst) is True
    return dst


def _add_sample_customer(db: Path) -> None:
    seed_row(db, 'customer_accounts', id=SAMPLE_CUSTOMER_ID,
             relation_id=SAMPLE_CUSTOMER_ID, name='测试客户')


def _code_id(conn, table, code):
    row = conn.execute(f'SELECT id FROM {table} WHERE code = ?', (code,)).fetchone()
    return row[0] if row else None


def _count(conn, table):
    return conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]


class TestMigrate:

    def test_fresh_db_lights_up_customer_dimension(self, tmp_path):
        db = _clone(tmp_path)

        assert migrate(db) is True
        assert verify(db) is True

        conn = sqlite3.connect(str(db))
        try:
            schema_id = _code_id(conn, 'key_schemas', KEY_SCHEMA_CODE)
            assert schema_id
            raw = conn.execute(
                'SELECT key_fields FROM key_schemas WHERE id = ?',
                (schema_id,)).fetchone()[0]
            assert json.loads(raw) == KEY_SCHEMA_FIELDS

            base_id = _code_id(conn, 'key_schemas', BASE_KEY_SCHEMA_CODE)
            seq_id = _code_id(conn, 'lookup_sequences', SEQUENCE_CODE)
            slots = json.loads(conn.execute(
                'SELECT steps FROM lookup_sequences WHERE id = ?',
                (seq_id,)).fetchone()[0])
            assert [s['key_schema_id'] for s in slots] == [schema_id, base_id]

            assert _code_id(conn, 'rate_tables', RATE_TABLE_CODE)
            # PD_STD 的查找序列改指两槽序列（价目表/过程不动）
            rule_sql = conn.execute(
                'SELECT lookup_sequence_id FROM pricing_determinations'
                ' WHERE code = ?', (DETERMINATION_CODE,)).fetchone()
            assert rule_sql and rule_sql[0] == seq_id
            # 临时库无客户行 → 示例客户价跳过，仅点亮配置链
            assert _code_id(conn, 'rate_records', RECORD_CODE) is None
        finally:
            conn.close()

    def test_sample_record_written_when_customer_and_item_exist(self, tmp_path):
        db = _clone(tmp_path)
        _add_sample_customer(db)

        assert migrate(db) is True
        assert verify(db) is True

        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                'SELECT keys, rate, status, rate_table_id, key_schema_id '
                'FROM rate_records WHERE code = ?',
                (RECORD_CODE,)).fetchone()
            table_id = _code_id(conn, 'rate_tables', RATE_TABLE_CODE)
            schema_id = _code_id(conn, 'key_schemas', KEY_SCHEMA_CODE)
        finally:
            conn.close()
        assert row is not None
        assert json.loads(row[0]) == {
            'customer_account_id': SAMPLE_CUSTOMER_ID,
            'item_id': SAMPLE_ITEM_ID,
        }
        assert float(row[1]) == SAMPLE_RATE
        assert row[2] == 'active'
        # 客户价与物料价同处标准价目表，靠 hit_policy=exclusive 实现客户价优先
        assert row[3] == table_id
        assert row[4] == schema_id

    def test_second_run_only_skips(self, tmp_path, capsys):
        db = _clone(tmp_path)
        _add_sample_customer(db)
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

    def test_missing_base_key_schema_aborts(self, tmp_path):
        db = _clone(tmp_path)
        delete_row(db, 'key_schemas', code=BASE_KEY_SCHEMA_CODE)

        assert migrate(db) is False

    def test_rollback_removes_seed(self, tmp_path):
        db = _clone(tmp_path)
        _add_sample_customer(db)
        assert migrate(db) is True

        assert rollback(db) is True

        conn = sqlite3.connect(str(db))
        try:
            assert _code_id(conn, 'key_schemas', KEY_SCHEMA_CODE) is None
            assert _code_id(conn, 'lookup_sequences', SEQUENCE_CODE) is None
            assert _code_id(conn, 'rate_records', RECORD_CODE) is None
            # 确定规则还原到波次 1 的单槽序列
            bound = conn.execute(
                'SELECT lookup_sequence_id FROM pricing_determinations'
                ' WHERE code = ?', (DETERMINATION_CODE,)).fetchone()
            base_seq_id = _code_id(conn, 'lookup_sequences', BASE_SEQUENCE_CODE)
            assert bound and bound[0] == base_seq_id
            factor = conn.execute(
                'SELECT id FROM factor_catalogs WHERE object_type = ? AND field_id = ?',
                (FACTOR[0], FACTOR[1])).fetchone()
            assert factor is None
        finally:
            conn.close()


class TestCustomerPriceEndToEnd:
    """W2-F 验收：客户价优先、换客户落回物料价、客户为空不报错。"""

    @pytest.fixture
    def ds(self, tmp_path):
        db = _clone(tmp_path)
        _add_sample_customer(db)
        seed_row(db, 'customer_accounts', id=5, relation_id=5, name='无协议客户')
        assert migrate(db) is True
        assert verify(db) is True
        adapter = SQLiteAdapter()
        assert adapter.connect(path=str(db))
        yield adapter
        adapter.disconnect()

    def _price(self, ds, customer_account_id):
        return PricingDeterminationService(ds).determine_line(
            item_id=SAMPLE_ITEM_ID, qty=1,
            customer_account_id=customer_account_id,
            currency='CNY', price_date=None)

    def test_customer_price_wins(self, ds):
        got = self._price(ds, SAMPLE_CUSTOMER_ID)
        assert got['pricing_status'] == 'determined'
        assert got['unit_price'] == SAMPLE_RATE
        trace = got['trace']
        assert trace['candidates'] == 2          # 客户价 + 物料价都在候选池
        assert len(trace['hit_ids']) == 1        # exclusive 命中即停，不叠加

    def test_other_customer_falls_back_to_item_price(self, ds):
        got = self._price(ds, 5)
        assert got['pricing_status'] == 'determined'
        assert got['unit_price'] == 12.50

    def test_no_customer_uses_item_price(self, ds):
        got = self._price(ds, None)
        assert got['pricing_status'] == 'determined'
        assert got['unit_price'] == 12.50
