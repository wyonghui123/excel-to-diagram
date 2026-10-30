# -*- coding: utf-8 -*-
"""变式物料化：声明默认值 + 未调用物化时不写 + off 时明确拒绝

背景:
  `meta/migrations/v117__configuration_price_and_materialize_fields.py` 加了
  - items.config_materialize_policy（off / manual / auto，默认 off）
  - configurations.variant_item_id（可空）
  Phase 1（manual 物化）落地后（spec: 2026-10-30-variant-item-materialization），
  本文件按 spec §6.3 改写为三条正向事实：
  1. 默认值 off 来自 schema（按 meta/schemas/items.yaml 真建表验证）；
  2. **未调用物化服务**的解算/复用链路（ConfigurationMatchService）不写
     configurations.variant_item_id；
  3. config_materialize_policy='off' 时调用物化服务被明确拒绝
     （MATERIALIZE_DISABLED），且 items 与 configurations 均无写入。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import io
import logging
import sqlite3
from contextlib import contextmanager, redirect_stdout

import pytest

pytestmark = pytest.mark.unit

from meta.core.models import registry
from meta.core.schema_generator import SchemaGenerator
from meta.services.configuration_match_service import ConfigurationMatchService
from meta.services.variant_item_materialize_service import (
    MaterializeError,
    VariantItemMaterializeService,
)
from meta.tests.factories._raw_sql_bridge import insert

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_META_DIR = os.path.join(_REPO, 'meta')

MODEL_ITEM = 1
ROOT_STRUCTURE = 10
HASH = 'H-VARIANT'
FROZEN_SOURCE = 100
SOLVED = 200


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
def items_conn():
    """按 meta/schemas/items.yaml 真建 items 表（registry + SQLite 方言）。"""
    level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with redirect_stdout(io.StringIO()):
            registry.reload(os.path.join(_META_DIR, 'schemas'))
        meta_object = registry.get('item')
        assert meta_object is not None, 'schema item 未注册'
        conn = sqlite3.connect(':memory:')
        gen = SchemaGenerator('sqlite')
        conn.execute(gen.generate_create_table(meta_object))
        for index_sql in gen.generate_create_index(meta_object):
            conn.execute(index_sql)
    finally:
        logging.disable(level)
    yield conn
    conn.close()


@pytest.fixture()
def config_env():
    """求解/复用消费链最小表集（口径同 test_configuration_match.py）。"""
    level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
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
    ds = _SqliteDS(conn)
    _seed(ds)
    try:
        yield ds
    finally:
        logging.disable(level)
        conn.close()


def _seed(ds):
    """模型物料（物化策略 manual）+ 两条同 hash 的已求解/冻结实例。"""
    now = '2026-10-25 00:00:00'
    insert(ds, 'items', id=MODEL_ITEM, code='MODEL-A', name='模型A',
           structure_role='model', item_type='goods', status='active',
           base_uom=1, config_match_policy='one_time_standard',
           config_materialize_policy='manual')
    insert(ds, 'item_structures', id=ROOT_STRUCTURE, item_id=MODEL_ITEM,
           usage='production', alternative_no=1, revision='A', status='active',
           base_qty=1, base_uom_code='EA', min_select=None, max_select=None,
           valid_from='2026-01-01', valid_to=None)
    _add_config(ds, FROZEN_SOURCE, status='frozen', revision=1)
    _add_config(ds, SOLVED, status='solved', revision=1, solved_at=now)


def _add_config(ds, config_id, *, status, revision, solved_at=None):
    insert(ds, 'configurations', id=config_id, model_item_id=MODEL_ITEM,
           structure_id=ROOT_STRUCTURE, status=status, config_hash=HASH,
           revision=revision, reused_from_id=None, match_policy_used='no',
           source_level='L2', context_json=None, validation_result_json=None,
           solved_at=solved_at, frozen_at=None, variant_item_id=None)
    insert(ds, 'configuration_values', configuration_id=config_id,
           attribute_code='color', seq=1, value_text='red',
           value_number=None, value_boolean=None, source='user',
           source_rule_id=None)
    insert(ds, 'configuration_components', configuration_id=config_id,
           component_key='L0001', structure_line_id=1,
           component_item_id=MODEL_ITEM, qty=1, uom_code='EA',
           parent_component_key=None, selection_source='user',
           source_rule_id=None, substitute_for_key=None,
           child_configuration_id=None, seq=1)


def _fetch(ds, config_id):
    rows = ds.query('SELECT * FROM configurations WHERE id = ?', [config_id])
    return rows[0] if rows else None


# ─────────────────────────────────────────────────────────────────────────────
# 1. schema 默认值
# ─────────────────────────────────────────────────────────────────────────────

def test_policy_defaults_to_off(items_conn):
    """插入时显式省略 config_materialize_policy，读回应为 schema 默认值 off。"""
    # 只给必填列（code / name / item_group_id / base_uom），刻意不写物化策略列
    items_conn.execute(
        "INSERT INTO items (code, name, item_group_id, base_uom)"
        " VALUES ('ITEM-MAT-1', '物化策略默认值件', 1, 1)")
    row = items_conn.execute(
        'SELECT config_materialize_policy FROM items').fetchone()
    assert row[0] == 'off'


# ─────────────────────────────────────────────────────────────────────────────
# 2. 未调用物化服务的解算/复用链路不写 variant_item_id
# ─────────────────────────────────────────────────────────────────────────────

def test_manual_policy_does_not_write_variant_item_id(config_env):
    """物化策略 manual + 已求解实例走 ConfigurationMatchService：

    该服务是 configurations 的真实写入方（复用命中会新建实例），
    但**不调用物化服务**时只写复用审计字段，不写 variant_item_id。
    """
    result = ConfigurationMatchService(config_env).match(SOLVED)
    assert result['reused'] is True
    new = _fetch(config_env, result['configuration_id'])
    assert new is not None and new['reused_from_id'] == FROZEN_SOURCE

    rows = config_env.query('SELECT * FROM configurations ORDER BY id')
    assert len(rows) == 3
    assert [row['variant_item_id'] for row in rows] == [None, None, None]
    assert config_env.query(
        'SELECT COUNT(*) AS n FROM configurations'
        ' WHERE variant_item_id IS NOT NULL')[0]['n'] == 0

    # 物化策略本身也不被消费链改写
    item = config_env.query(
        'SELECT config_materialize_policy FROM items WHERE id = ?',
        [MODEL_ITEM])[0]
    assert item['config_materialize_policy'] == 'manual'


# ─────────────────────────────────────────────────────────────────────────────
# 3. policy=off 时调用物化服务被明确拒绝且不写
# ─────────────────────────────────────────────────────────────────────────────

def test_off_policy_rejects_materialize_and_writes_nothing(config_env):
    """config_materialize_policy='off' → MATERIALIZE_DISABLED（不再静默）。

    拒绝发生在写库之前：items 不新增，所有 configurations.variant_item_id 仍为空。
    """
    config_env.update('items', MODEL_ITEM, {'config_materialize_policy': 'off'})
    items_before = config_env.query('SELECT COUNT(*) AS n FROM items')[0]['n']

    with pytest.raises(MaterializeError) as exc_info:
        VariantItemMaterializeService(config_env).materialize(SOLVED)
    assert exc_info.value.code == 'MATERIALIZE_DISABLED'

    assert config_env.query('SELECT COUNT(*) AS n FROM items')[0]['n'] == items_before
    assert config_env.query(
        'SELECT COUNT(*) AS n FROM configurations'
        ' WHERE variant_item_id IS NOT NULL')[0]['n'] == 0
