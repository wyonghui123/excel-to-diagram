# -*- coding: utf-8 -*-
"""配置定价门面测试（P4.1：门面五道校验 + none 来源 + 幂等缓存 + 只读）

依据: docs/superpowers/specs/2026-10-25-configuration-and-structure-spec.p4.tasks.md §2 / §3.1
      meta/services/configuration_price_service.py
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import logging
import sqlite3
from contextlib import contextmanager

import pytest

pytestmark = pytest.mark.unit

from meta.core.models import registry
from meta.core.schema_generator import SchemaGenerator
from meta.services.configuration_price_service import ConfigurationPriceService
from meta.services.item_structure_config_service import (
    ItemStructureConfigError,
    ItemStructureConfigService,
)
from meta.tests.factories._raw_sql_bridge import delete, insert, update

CONFIG_ID = 100
ROOT_STRUCTURE = 10
MODEL_ITEM = 1
PART_ITEM = 3
PART_ITEM_Y = 4
PART_ITEM_Z = 5
PART_ITEM_NEG = 6

# 定价域按 yaml 真建表；配置域三表用手写最小 DDL（P3 测试同口径）
PRICING_TABLES = [
    'key_schema', 'lookup_sequence', 'rate_type', 'rate_table', 'rate_record',
    'calc_procedure', 'calc_procedure_step', 'calc_result', 'calc_detail',
]


class _SqliteDS:
    """最小数据源：query / insert / update / transaction / execute。"""

    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, params or [])

    def insert(self, table, data):
        columns = list(data.keys())
        sql = (f"INSERT INTO {table} ({', '.join(columns)}) "
               f"VALUES ({', '.join('?' for _ in columns)})")
        cur = self.conn.execute(sql, [data[col] for col in columns])
        return cur.lastrowid

    def update(self, table, row_id, data):
        assignments = ', '.join(f'{key} = ?' for key in data)
        self.conn.execute(
            f"UPDATE {table} SET {assignments} WHERE id = ?",
            [*data.values(), row_id])

    @contextmanager
    def transaction(self):
        try:
            yield self
        except Exception:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()


@pytest.fixture()
def env():
    previous_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        registry.reload(os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), 'meta', 'schemas'))
    finally:
        logging.disable(previous_level)

    conn = sqlite3.connect(':memory:')
    conn.executescript(
        """
        CREATE TABLE items (id INTEGER PRIMARY KEY, code TEXT, name TEXT,
            structure_role TEXT, item_type TEXT, status TEXT, base_uom INTEGER,
            config_match_policy TEXT, config_materialize_policy TEXT);
        CREATE TABLE item_structures (id INTEGER PRIMARY KEY, item_id INTEGER,
            usage TEXT, alternative_no INTEGER, revision TEXT, status TEXT,
            base_qty REAL, base_uom_code TEXT, min_select INTEGER,
            max_select INTEGER, valid_from TEXT, valid_to TEXT);
        CREATE TABLE configurations (id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_item_id INTEGER, structure_id INTEGER, status TEXT,
            config_hash TEXT, revision INTEGER, reused_from_id INTEGER,
            match_policy_used TEXT, source_level TEXT, context_json TEXT,
            validation_result_json TEXT, solved_at TEXT, frozen_at TEXT,
            variant_item_id INTEGER);
        CREATE TABLE configuration_values (id INTEGER PRIMARY KEY AUTOINCREMENT,
            configuration_id INTEGER, attribute_code TEXT, seq INTEGER,
            value_text TEXT, value_number REAL, value_boolean INTEGER,
            source TEXT, source_rule_id INTEGER);
        CREATE TABLE configuration_components (id INTEGER PRIMARY KEY AUTOINCREMENT,
            configuration_id INTEGER, component_key TEXT, structure_line_id INTEGER,
            component_item_id INTEGER, qty REAL, uom_code TEXT,
            parent_component_key TEXT, selection_source TEXT, source_rule_id INTEGER,
            substitute_for_key TEXT, child_configuration_id INTEGER, seq INTEGER);
        """
    )
    gen = SchemaGenerator('sqlite')
    for name in PRICING_TABLES:
        mo = registry.get(name)
        assert mo is not None, f'{name} 未注册'
        conn.execute(gen.generate_create_table(mo))
        for index_sql in gen.generate_create_index(mo):
            conn.execute(index_sql)

    ds = _SqliteDS(conn)
    _seed(ds)
    yield ds
    conn.close()


def _seed(ds):
    """模型 MODEL-A + 一个已求解实例 + 一份可算的定价过程与价目表。"""
    now = '2026-10-25 00:00:00'
    insert(ds, 'items', rows=[
        dict(id=MODEL_ITEM, code='MODEL-A', name='模型A', structure_role='model',
             item_type='goods', status='active', base_uom=1,
             config_match_policy='no', config_materialize_policy='off'),
        dict(id=PART_ITEM, code='PART-X', name='部件X', structure_role='none',
             item_type='goods', status='active', base_uom=1,
             config_match_policy='no', config_materialize_policy='off'),
        dict(id=PART_ITEM_Y, code='PART-Y', name='部件Y', structure_role='none',
             item_type='goods', status='active', base_uom=1,
             config_match_policy='no', config_materialize_policy='off'),
        dict(id=PART_ITEM_Z, code='PART-Z', name='部件Z', structure_role='none',
             item_type='goods', status='active', base_uom=1,
             config_match_policy='no', config_materialize_policy='off'),
        dict(id=PART_ITEM_NEG, code='PART-NEG', name='折扣件', structure_role='none',
             item_type='goods', status='active', base_uom=1,
             config_match_policy='no', config_materialize_policy='off'),
    ])
    insert(ds, 'item_structures', id=ROOT_STRUCTURE, item_id=MODEL_ITEM,
           usage='production', alternative_no=1, revision='A', status='active',
           base_qty=1, base_uom_code='EA', min_select=None, max_select=None,
           valid_from='2026-01-01', valid_to=None)
    insert(ds, 'configurations', id=CONFIG_ID, model_item_id=MODEL_ITEM,
           structure_id=ROOT_STRUCTURE, status='solved', config_hash=None,
           revision=1, reused_from_id=None, match_policy_used='no',
           source_level='L3', context_json=None, validation_result_json=None,
           solved_at=now, frozen_at=None, variant_item_id=None)
    insert(ds, 'configuration_values', id=1, configuration_id=CONFIG_ID,
           attribute_code='color', seq=1, value_text='red',
           value_number=None, value_boolean=None, source='user',
           source_rule_id=None)
    insert(ds, 'configuration_values', id=2, configuration_id=CONFIG_ID,
           attribute_code='size', seq=1, value_text='L',
           value_number=None, value_boolean=None, source='user',
           source_rule_id=None)
    insert(ds, 'configuration_components', id=1, configuration_id=CONFIG_ID,
           component_key='L0001', structure_line_id=1,
           component_item_id=PART_ITEM, qty=1, uom_code='EA',
           parent_component_key=None, selection_source='user',
           source_rule_id=None, substitute_for_key=None,
           child_configuration_id=None, seq=1)

    # 定价主数据：已发布价目表 + 单步 list_price（rate=500，base=1 ⇒ net=500）
    insert(ds, 'rate_types', id=1, code='PRICE_BASE', name='基本价格',
           rate_class='price', calc_type='percent', rate_source='rate_record',
           sign='+', rounding=None, exclusion_group_id=None, manual_allowed=0,
           mandatory=0, statistical=0, lookup_sequence_id=None,
           created_at=now, updated_at=now)
    insert(ds, 'rate_tables', id=1, code='PL_STD', name='标准价目表',
           type='standard', currency='CNY', owner_org_id=None,
           status='approved', created_at=now, updated_at=now)
    insert(ds, 'calc_procedures', id=1, code='PROC_STD', name='标准过程',
           procedure_type='pricing', result_semantic='price', currency='CNY',
           subtotal_keys=None, created_at=now, updated_at=now)
    insert(ds, 'calc_procedure_steps', rows=[dict(
        id=1, calc_procedure_id=1, seq=1, element_type='list_price',
        rate_type_id=None, condition=None, params='{"rate": 500}', rolling=0,
        base_step=None, subtotal_key=None, created_at=now, updated_at=now)])

    # 组件价：物料单槽位 + 按物料命中费率（PART-X=300 / PART-Y=200）
    insert(ds, 'key_schemas', id=1, code='KEY_ITEM', name='物料键',
           key_fields='["item_code"]', created_at=now, updated_at=now)
    insert(ds, 'lookup_sequences', id=1, code='SEQ_ITEM', name='物料序列',
           steps='[{"seq":1,"key_schema_id":1}]', created_at=now, updated_at=now)
    insert(ds, 'calc_procedures', id=2, code='PROC_ITEM', name='组件过程',
           procedure_type='pricing', result_semantic='price', currency='CNY',
           subtotal_keys=None, created_at=now, updated_at=now)
    insert(ds, 'calc_procedure_steps', rows=[dict(
        id=2, calc_procedure_id=2, seq=1, element_type='formula',
        rate_type_id=None, condition=None,
        params='{"expr": "lookup_amount * base"}', rolling=0,
        base_step=None, subtotal_key=None, created_at=now, updated_at=now)])
    insert(ds, 'rate_records', rows=[
        dict(id=1, code='RC_PX', rate_table_id=1, key_schema_id=1,
             keys='{"item_code": "PART-X"}', rate_type_id=1, rate=300.0,
             hit_policy='exclusive', priority=1, status='active',
             created_at=now, updated_at=now),
        dict(id=2, code='RC_PY', rate_table_id=1, key_schema_id=1,
             keys='{"item_code": "PART-Y"}', rate_type_id=1, rate=200.0,
             hit_policy='exclusive', priority=1, status='active',
             created_at=now, updated_at=now),
        dict(id=3, code='RC_MODEL', rate_table_id=1, key_schema_id=1,
             keys='{"item_code": "MODEL-A"}', rate_type_id=1, rate=1000.0,
             hit_policy='exclusive', priority=1, status='active',
             created_at=now, updated_at=now),
        dict(id=4, code='RC_NEG', rate_table_id=1, key_schema_id=1,
             keys='{"item_code": "PART-NEG"}', rate_type_id=1, rate=-5000.0,
             hit_policy='exclusive', priority=1, status='active',
             created_at=now, updated_at=now),
    ])

    # 矩阵价：双维（颜色 × 尺寸）键模式 + 两条组合行
    insert(ds, 'key_schemas', id=2, code='KEY_MATRIX', name='颜色尺寸键',
           key_fields='["color", "size"]', created_at=now, updated_at=now)
    insert(ds, 'lookup_sequences', id=2, code='SEQ_MATRIX', name='矩阵序列',
           steps='[{"seq":1,"key_schema_id":2}]', created_at=now, updated_at=now)
    insert(ds, 'rate_records', rows=[
        dict(id=11, code='RC_MATRIX_RL', rate_table_id=1, key_schema_id=2,
             keys='{"color": "red", "size": "L"}', rate_type_id=1, rate=5000.0,
             hit_policy='exclusive', priority=1, status='active',
             created_at=now, updated_at=now),
        dict(id=12, code='RC_MATRIX_BL', rate_table_id=1, key_schema_id=2,
             keys='{"color": "blue", "size": "L"}', rate_type_id=1, rate=4500.0,
             hit_policy='exclusive', priority=1, status='active',
             created_at=now, updated_at=now),
    ])

    _refresh_hash(ds)


def _refresh_hash(ds):
    """按库内三表算出与 verify_hash 同口径的 config_hash。"""
    service = ItemStructureConfigService(ds)
    values = service._fetch_values(CONFIG_ID)
    components = service._fetch_components(CONFIG_ID)
    digest = service._compute_hash('MODEL-A', 'A', values, components)
    update(ds, 'configurations', {'id': CONFIG_ID}, config_hash=digest)
    return digest


def _context(**over):
    context = {
        'pricing_procedure_code': 'PROC_STD',
        'rate_table_id': 1,
        'currency_code': 'CNY',
        'order_date': '2026-10-25',
    }
    context.update(over)
    return context


def _service(ds):
    return ConfigurationPriceService(ds)


def _component_context(**over):
    context = _context(
        pricing_procedure_code='PROC_ITEM',
        sequence_code='SEQ_ITEM',
        slot_keys=[{'item_code': None}])
    context.update(over)
    return context


def _matrix_context(**over):
    context = _context(
        pricing_procedure_code='PROC_ITEM',
        sequence_code='SEQ_MATRIX')
    context.update(over)
    return context


def _add_component(ds, row_id, key, item_id, qty, seq):
    insert(ds, 'configuration_components', id=row_id, configuration_id=CONFIG_ID,
           component_key=key, structure_line_id=seq,
           component_item_id=item_id, qty=qty, uom_code='EA',
           parent_component_key=None, selection_source='user',
           source_rule_id=None, substitute_for_key=None,
           child_configuration_id=None, seq=seq)
    _refresh_hash(ds)


def _active_rows(ds):
    return ds.query(
        "SELECT * FROM calc_results WHERE document_type = 'configuration'"
        " AND document_id = ? AND status = 'active'"
        " ORDER BY document_line_id", [CONFIG_ID])


def _result_rows(ds):
    return ds.query(
        "SELECT * FROM calc_results WHERE document_type = 'configuration'"
        " AND document_id = ?", [CONFIG_ID])


# ─────────────────────────────────────────────────────────────────────────────
# 门面校验
# ─────────────────────────────────────────────────────────────────────────────

class TestPriceGuards:

    def test_unknown_source_rejected(self, env):
        with pytest.raises(ItemStructureConfigError) as info:
            _service(env).price(CONFIG_ID, 'magic', _context())
        assert info.value.code == 'CONFIG_INVALID_VALUE'
        assert info.value.rule == 'price_source_invalid'

    def test_draft_instance_rejected(self, env):
        update(env, 'configurations', {'id': CONFIG_ID}, status='draft')
        with pytest.raises(ItemStructureConfigError) as info:
            _service(env).price(CONFIG_ID, 'none', _context())
        assert info.value.code == 'CONFIG_VERSION_MISMATCH'
        assert info.value.rule == 'configuration_status_not_priceable'

    def test_tampered_component_rejected(self, env):
        update(env, 'configuration_components', {'id': 1}, qty=9)
        with pytest.raises(ItemStructureConfigError) as info:
            _service(env).price(CONFIG_ID, 'none', _context())
        assert info.value.code == 'CONFIG_INVALID_VALUE'
        assert info.value.rule == 'configuration_hash_mismatch'

    def test_missing_context_rejected(self, env):
        with pytest.raises(ItemStructureConfigError) as info:
            _service(env).price(CONFIG_ID, 'none', {})
        assert info.value.code == 'CONFIG_INCOMPLETE'
        assert info.value.rule == 'pricing_context_incomplete'

    def test_currency_mismatch_rejected(self, env):
        with pytest.raises(ItemStructureConfigError) as info:
            _service(env).price(
                CONFIG_ID, 'none', _context(currency_code='USD'))
        assert info.value.code == 'CONFIG_INVALID_VALUE'
        assert info.value.rule == 'currency_mismatch'

    def test_pricing_mode_mismatch_rejected(self, env):
        with pytest.raises(ItemStructureConfigError) as info:
            _service(env).price(CONFIG_ID, 'component_price',
                                _context(pricing_mode='parent_priced'))
        assert info.value.code == 'CONFIG_CONFLICT'
        assert info.value.rule == 'pricing_mode_mismatch'

    def test_resolved_mismatch_rejected(self, env):
        with pytest.raises(ItemStructureConfigError) as info:
            _service(env).price(
                CONFIG_ID, 'none', _context(),
                resolved=[{'component_key': 'L9999', 'qty': 1}])
        assert info.value.code == 'CONFIG_INVALID_VALUE'
        assert info.value.rule == 'resolved_mismatch'

    def test_resolved_match_accepted(self, env):
        result = _service(env).price(
            CONFIG_ID, 'none', _context(),
            resolved=[{'component_key': 'L0001', 'qty': 1}])
        assert result['total'] == 500.0

    def test_calculated_not_enabled(self, env):
        with pytest.raises(ItemStructureConfigError) as info:
            _service(env).price(CONFIG_ID, 'calculated', _context())
        assert info.value.code == 'CONFIG_PRICE_MISSING'
        assert info.value.rule == 'price_source_not_enabled'

    def test_unapproved_rate_table_is_price_missing(self, env):
        update(env, 'rate_tables', {'id': 1}, status='draft')
        with pytest.raises(ItemStructureConfigError) as info:
            _service(env).price(CONFIG_ID, 'none', _context())
        assert info.value.code == 'CONFIG_PRICE_MISSING'
        assert info.value.rule == 'price_not_found'


# ─────────────────────────────────────────────────────────────────────────────
# none 来源
# ─────────────────────────────────────────────────────────────────────────────

class TestPriceNone:

    def test_root_line_and_total(self, env):
        result = _service(env).price(CONFIG_ID, 'none', _context())
        assert result['price_source'] == 'none'
        assert result['currency_code'] == 'CNY'
        assert result['total'] == 500.0
        assert result['cached'] is False
        line = result['lines'][0]
        assert line['component_no'] == 'root'
        assert line['net_amount'] == 500.0
        assert line['unit_price'] == 500.0
        assert len(result['lines']) == 1

    def test_default_source_is_none(self, env):
        result = _service(env).price(CONFIG_ID, None, _context())
        assert result['price_source'] == 'none'
        assert result['total'] == 500.0

    def test_component_selection_does_not_change_price(self, env):
        first = _service(env).price(CONFIG_ID, 'none', _context())
        insert(env, 'configuration_components', id=2, configuration_id=CONFIG_ID,
               component_key='L0002', structure_line_id=2,
               component_item_id=PART_ITEM, qty=2, uom_code='EA',
               parent_component_key=None, selection_source='user',
               source_rule_id=None, substitute_for_key=None,
               child_configuration_id=None, seq=2)
        _refresh_hash(env)
        second = _service(env).price(CONFIG_ID, 'none', _context())
        assert second['total'] == first['total']


# ─────────────────────────────────────────────────────────────────────────────
# 幂等 / 只读
# ─────────────────────────────────────────────────────────────────────────────

class TestIdempotency:

    def test_repeat_call_reuses_single_result(self, env):
        service = _service(env)
        first = service.price(CONFIG_ID, 'none', _context())
        second = service.price(CONFIG_ID, 'none', _context())
        assert second['total'] == first['total']
        assert second['cached'] is True
        assert len(_result_rows(env)) == 1
        assert _result_rows(env)[0]['status'] == 'active'

    def test_context_digest_is_order_insensitive(self, env):
        service = _service(env)
        service.price(CONFIG_ID, 'none', _context())
        reordered = {
            'order_date': '2026-10-25',
            'currency_code': 'CNY',
            'rate_table_id': 1,
            'pricing_procedure_code': 'PROC_STD',
        }
        second = service.price(CONFIG_ID, 'none', reordered)
        assert second['cached'] is True
        assert len(_result_rows(env)) == 1

    def test_different_source_gives_separate_result(self, env):
        service = _service(env)
        service.price(CONFIG_ID, 'none', _context())
        with pytest.raises(ItemStructureConfigError):
            service.price(CONFIG_ID, 'attribute_matrix', _context())
        assert len(_result_rows(env)) == 1

    def test_concurrent_duplicate_falls_back_to_cached(self, env):
        """并发第二次落库撞唯一键 → 回读已有结果，不向调用方报错（§2.3）。"""
        service = _service(env)
        first = service.price(CONFIG_ID, 'none', _context())
        assert first['cached'] is False

        original_find = service._find_cached
        calls = {'n': 0}

        def miss_once(code):
            calls['n'] += 1
            return None if calls['n'] == 1 else original_find(code)

        class _RacingPricing:
            def get_procedure(self, code):
                return {'currency': 'CNY'}

            def price_line(self, *args, **kwargs):
                raise sqlite3.IntegrityError(
                    'UNIQUE constraint failed: calc_results.code')

        service._find_cached = miss_once
        service.pricing = _RacingPricing()
        second = service.price(CONFIG_ID, 'none', _context())
        assert second['cached'] is True
        assert second['total'] == first['total']
        assert len(_result_rows(env)) == 1

    def test_price_does_not_write_configuration_tables(self, env):
        def snapshot():
            return {
                'configurations': env.query('SELECT * FROM configurations'),
                'values': env.query('SELECT * FROM configuration_values'),
                'components': env.query('SELECT * FROM configuration_components'),
            }

        before = snapshot()
        _service(env).price(CONFIG_ID, 'none', _context())
        after = snapshot()
        assert before == after
        assert len(env.query('SELECT * FROM calc_details')) > 0


# ─────────────────────────────────────────────────────────────────────────────
# component_price 来源
# ─────────────────────────────────────────────────────────────────────────────

class TestPriceComponents:

    def test_total_is_sum_of_component_prices(self, env):
        _add_component(env, 21, 'L0002', PART_ITEM_Y, qty=2, seq=2)
        result = _service(env).price(
            CONFIG_ID, 'component_price', _component_context())

        assert result['price_source'] == 'component_price'
        assert result['currency_code'] == 'CNY'
        assert result['cached'] is False
        assert result['total'] == 700.0           # 300×1 + 200×2

        root, first, second = result['lines']
        assert (root['component_no'], root['unit_price'], root['net_amount']) \
            == ('root', 0.0, 0.0)
        assert first['component_no'] == 'L0001'
        assert (first['unit_price'], first['net_amount']) == (300.0, 300.0)
        assert second['component_no'] == 'L0002'
        assert (second['unit_price'], second['net_amount']) == (200.0, 400.0)

        rows = _active_rows(env)
        assert len(rows) == 2
        assert {row['level'] for row in rows} == {'line'}
        assert {row['document_line_id'] for row in rows} == {1, 21}

    def test_component_qty_is_base(self, env):
        update(env, 'configuration_components', {'id': 1}, qty=4)
        _refresh_hash(env)
        result = _service(env).price(
            CONFIG_ID, 'component_price', _component_context())
        line = result['lines'][1]
        assert line['net_amount'] == 1200.0
        assert line['unit_price'] == 300.0
        assert result['total'] == 1200.0

    def test_same_item_two_keys_priced_separately(self, env):
        """同物料不同 component_key 逐键计价、不按物料合并（R14）。"""
        _add_component(env, 22, 'L0002', PART_ITEM, qty=1, seq=2)
        result = _service(env).price(
            CONFIG_ID, 'component_price', _component_context())

        nets = [line['net_amount'] for line in result['lines'][1:]]
        assert nets == [300.0, 300.0]
        assert result['total'] == 600.0
        assert len(_active_rows(env)) == 2

    def test_component_without_price_blocks(self, env):
        """缺任一组件价即阻断；不得用其余组件补齐，也不留 0 价 active 行。"""
        _add_component(env, 23, 'L0003', PART_ITEM_Z, qty=1, seq=2)
        with pytest.raises(ItemStructureConfigError) as info:
            _service(env).price(
                CONFIG_ID, 'component_price', _component_context())
        assert info.value.code == 'CONFIG_PRICE_MISSING'
        assert info.value.rule == 'price_not_found'

        active = _active_rows(env)
        assert [row['document_line_id'] for row in active] == [1]

    def test_repeat_call_reuses_component_cache(self, env):
        _add_component(env, 21, 'L0002', PART_ITEM_Y, qty=2, seq=2)
        service = _service(env)
        first = service.price(CONFIG_ID, 'component_price', _component_context())
        second = service.price(CONFIG_ID, 'component_price', _component_context())

        assert first['cached'] is False
        assert second['cached'] is True
        assert second['total'] == first['total']
        assert len(_active_rows(env)) == 2
        for row in _active_rows(env):
            assert row['code'].startswith('cfg:100:component_price:')

    def test_qty_change_reprices_instead_of_reusing_cache(self, env):
        """`config_hash` 入缓存键：改量后必须重算，不得命中旧价（§2.3）。"""
        service = _service(env)
        assert service.price(
            CONFIG_ID, 'component_price', _component_context())['total'] == 300.0

        update(env, 'configuration_components', {'id': 1}, qty=4)
        _refresh_hash(env)
        second = service.price(
            CONFIG_ID, 'component_price', _component_context())

        assert second['cached'] is False
        assert second['total'] == 1200.0
        assert len(_active_rows(env)) == 1

    def test_removing_component_lowers_total_and_invalidates_stale(self, env):
        _add_component(env, 21, 'L0002', PART_ITEM_Y, qty=2, seq=2)
        service = _service(env)
        assert service.price(
            CONFIG_ID, 'component_price', _component_context())['total'] == 700.0

        delete(env, 'configuration_components', id=21)
        _refresh_hash(env)
        result = service.price(CONFIG_ID, 'component_price', _component_context())

        assert result['total'] == 300.0
        active = _active_rows(env)
        assert len(active) == 1
        assert active[0]['document_line_id'] == 1

    def test_price_does_not_write_configuration_tables(self, env):
        def snapshot():
            return {
                'configurations': env.query('SELECT * FROM configurations'),
                'values': env.query('SELECT * FROM configuration_values'),
                'components': env.query('SELECT * FROM configuration_components'),
            }

        before = snapshot()
        _service(env).price(CONFIG_ID, 'component_price', _component_context())
        assert before == snapshot()


# ─────────────────────────────────────────────────────────────────────────────
# base_plus_option 来源（P4.3）
# ─────────────────────────────────────────────────────────────────────────────

class TestPriceBaseOption:

    def test_total_is_base_plus_option(self, env):
        result = _service(env).price(
            CONFIG_ID, 'base_plus_option', _component_context())

        assert result['price_source'] == 'base_plus_option'
        assert result['cached'] is False
        assert result['total'] == 1300.0          # 基准 1000 + 选项 300
        assert result['warnings'] == []

        base, option = result['lines']
        assert (base['component_no'], base['net_amount']) == ('root', 1000.0)
        assert (option['component_no'], option['net_amount']) == ('L0001', 300.0)

        rows = _active_rows(env)
        assert len(rows) == 2
        base_row = [r for r in rows if r['level'] == 'header'][0]
        option_row = [r for r in rows if r['level'] == 'line'][0]
        assert base_row['document_line_id'] is None
        assert option_row['document_line_id'] == 1

    def test_all_options_are_added(self, env):
        _add_component(env, 21, 'L0002', PART_ITEM_Y, qty=2, seq=2)
        result = _service(env).price(
            CONFIG_ID, 'base_plus_option', _component_context())

        assert result['total'] == 1700.0          # 1000 + 300 + 200×2
        assert [line['net_amount'] for line in result['lines']] \
            == [1000.0, 300.0, 400.0]
        assert len(_active_rows(env)) == 3

    def test_option_without_price_counts_zero_and_warns(self, env):
        _add_component(env, 23, 'L0003', PART_ITEM_Z, qty=1, seq=2)
        result = _service(env).price(
            CONFIG_ID, 'base_plus_option', _component_context())

        assert result['total'] == 1300.0          # 未配价的选项按 0 计，不阻断
        assert len(result['warnings']) == 1
        assert 'L0003' in result['warnings'][0]
        assert len(_active_rows(env)) == 3

    def test_negative_option_lowers_total(self, env):
        update(env, 'rate_records', {'id': 4}, rate=-100.0)
        _add_component(env, 24, 'L0004', PART_ITEM_NEG, qty=1, seq=2)
        result = _service(env).price(
            CONFIG_ID, 'base_plus_option', _component_context())

        assert result['total'] == 1200.0          # 1000 + 300 - 100
        assert result['lines'][2]['unit_price'] == -100.0

    def test_negative_total_blocks(self, env):
        _add_component(env, 24, 'L0004', PART_ITEM_NEG, qty=1, seq=2)
        with pytest.raises(ItemStructureConfigError) as info:
            _service(env).price(
                CONFIG_ID, 'base_plus_option', _component_context())
        assert info.value.code == 'CONFIG_INVALID_VALUE'
        assert info.value.rule == 'price_total_negative'

    def test_base_without_price_blocks(self, env):
        """无基准价时加价无意义，直接阻断且不留 0 价 active 行。"""
        delete(env, 'rate_records', id=3)
        with pytest.raises(ItemStructureConfigError) as info:
            _service(env).price(
                CONFIG_ID, 'base_plus_option', _component_context())
        assert info.value.code == 'CONFIG_PRICE_MISSING'
        assert info.value.rule == 'price_not_found'
        assert _active_rows(env) == []

    def test_repeat_call_reuses_base_option_cache(self, env):
        service = _service(env)
        first = service.price(CONFIG_ID, 'base_plus_option', _component_context())
        second = service.price(CONFIG_ID, 'base_plus_option', _component_context())

        assert first['cached'] is False
        assert second['cached'] is True
        assert second['total'] == first['total']
        assert len(_active_rows(env)) == 2
        for row in _active_rows(env):
            assert row['code'].startswith('cfg:100:base_plus_option:')

    def test_removing_option_invalidates_stale_and_keeps_base(self, env):
        _add_component(env, 21, 'L0002', PART_ITEM_Y, qty=2, seq=2)
        service = _service(env)
        assert service.price(
            CONFIG_ID, 'base_plus_option', _component_context())['total'] == 1700.0

        delete(env, 'configuration_components', id=21)
        _refresh_hash(env)
        result = service.price(
            CONFIG_ID, 'base_plus_option', _component_context())

        assert result['total'] == 1300.0
        rows = _active_rows(env)
        assert len(rows) == 2
        assert {row['level'] for row in rows} == {'header', 'line'}
        assert [row['document_line_id'] for row in rows
                if row['level'] == 'line'] == [1]


# ─────────────────────────────────────────────────────────────────────────────
# attribute_matrix 来源（P4.4）
# ─────────────────────────────────────────────────────────────────────────────

class TestPriceMatrix:

    def test_combination_hits_unique_price(self, env):
        result = _service(env).price(
            CONFIG_ID, 'attribute_matrix', _matrix_context())

        assert result['price_source'] == 'attribute_matrix'
        assert result['cached'] is False
        assert result['total'] == 5000.0
        line = result['lines'][0]
        assert (line['component_no'], line['unit_price'], line['net_amount']) \
            == ('root', 5000.0, 5000.0)

        rows = _active_rows(env)
        assert len(rows) == 1
        assert rows[0]['level'] == 'header'
        assert rows[0]['document_line_id'] is None

    def test_change_one_dimension_reprices(self, env):
        service = _service(env)
        assert service.price(
            CONFIG_ID, 'attribute_matrix', _matrix_context())['total'] == 5000.0

        update(env, 'configuration_values', {'id': 1}, value_text='blue')
        _refresh_hash(env)
        second = service.price(
            CONFIG_ID, 'attribute_matrix', _matrix_context())

        assert second['cached'] is False
        assert second['total'] == 4500.0
        assert len(_active_rows(env)) == 1

    def test_missing_dimension_rejected(self, env):
        delete(env, 'configuration_values', id=2)
        _refresh_hash(env)
        with pytest.raises(ItemStructureConfigError) as info:
            _service(env).price(
                CONFIG_ID, 'attribute_matrix', _matrix_context())
        assert info.value.code == 'CONFIG_INCOMPLETE'
        assert info.value.rule == 'matrix_dimension_missing'
        assert info.value.field_name == 'size'

    def test_unmatched_combination_missing_price(self, env):
        update(env, 'configuration_values', {'id': 1}, value_text='green')
        _refresh_hash(env)
        with pytest.raises(ItemStructureConfigError) as info:
            _service(env).price(
                CONFIG_ID, 'attribute_matrix', _matrix_context())
        assert info.value.code == 'CONFIG_PRICE_MISSING'
        assert info.value.rule == 'price_not_found'
        assert _active_rows(env) == []

    def test_requires_sequence(self, env):
        context = _matrix_context()
        context.pop('sequence_code')
        with pytest.raises(ItemStructureConfigError) as info:
            _service(env).price(CONFIG_ID, 'attribute_matrix', context)
        assert info.value.code == 'CONFIG_INCOMPLETE'
        assert info.value.rule == 'pricing_context_incomplete'

    def test_repeat_call_reuses_cache(self, env):
        service = _service(env)
        first = service.price(CONFIG_ID, 'attribute_matrix', _matrix_context())
        second = service.price(CONFIG_ID, 'attribute_matrix', _matrix_context())

        assert first['cached'] is False
        assert second['cached'] is True
        assert second['total'] == first['total']
        assert len(_active_rows(env)) == 1


# ─────────────────────────────────────────────────────────────────────────────
# M2 字段落库（P4 只留位置）
# ─────────────────────────────────────────────────────────────────────────────

class TestMaterializeFields:

    def test_defaults_and_nullable(self, env):
        item = env.query('SELECT * FROM items WHERE id = ?', [MODEL_ITEM])[0]
        assert item['config_materialize_policy'] == 'off'
        config = env.query(
            'SELECT * FROM configurations WHERE id = ?', [CONFIG_ID])[0]
        assert config['variant_item_id'] is None
