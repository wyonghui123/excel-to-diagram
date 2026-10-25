# -*- coding: utf-8 -*-
"""配置复用匹配测试（P4 T6：one_time_standard）

依据: docs/superpowers/specs/2026-10-25-configuration-and-structure-spec.p4.tasks.md §4
      meta/services/configuration_match_service.py
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import logging
import sqlite3
from contextlib import contextmanager

import pytest

pytestmark = pytest.mark.unit

from meta.services.configuration_match_service import ConfigurationMatchService
from meta.services.item_structure_config_service import ItemStructureConfigError
from meta.tests.factories._raw_sql_bridge import insert

MODEL_ITEM = 1
ROOT_STRUCTURE = 10
OTHER_STRUCTURE = 11
HASH = 'H-AAA'

SOURCE = 100
OTHER_SOURCE = 101
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
def env():
    level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
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
        yield ds
        conn.close()
    finally:
        logging.disable(level)


def _seed(ds):
    now = '2026-10-25 00:00:00'
    insert(ds, 'items', rows=[dict(
        id=MODEL_ITEM, code='MODEL-A', name='模型A', structure_role='model',
        item_type='goods', status='active', base_uom=1,
        config_match_policy='one_time_standard', config_materialize_policy='off')])
    insert(ds, 'item_structures', rows=[
        dict(id=ROOT_STRUCTURE, item_id=MODEL_ITEM, usage='production',
             alternative_no=1, revision='A', status='active', base_qty=1,
             base_uom_code='EA', min_select=None, max_select=None,
             valid_from='2026-01-01', valid_to=None),
        dict(id=OTHER_STRUCTURE, item_id=MODEL_ITEM, usage='production',
             alternative_no=2, revision='B', status='active', base_qty=1,
             base_uom_code='EA', min_select=None, max_select=None,
             valid_from='2026-01-01', valid_to=None),
    ])


def _add_config(ds, config_id, *, status, structure_id=ROOT_STRUCTURE,
                config_hash=HASH, revision=1, reused_from_id=None,
                policy_used='no', values=2, components=1):
    now = '2026-10-25 00:00:00'
    insert(ds, 'configurations', id=config_id, model_item_id=MODEL_ITEM,
           structure_id=structure_id, status=status, config_hash=config_hash,
           revision=revision, reused_from_id=reused_from_id,
           match_policy_used=policy_used, source_level='L2',
           context_json=None, validation_result_json=None,
           solved_at=now, frozen_at=now if status == 'frozen' else None,
           variant_item_id=None)
    for offset in range(values):
        insert(ds, 'configuration_values', configuration_id=config_id,
               attribute_code=f'color{offset}', seq=1,
               value_text='red', value_number=None, value_boolean=None,
               source='user', source_rule_id=None)
    for offset in range(components):
        insert(ds, 'configuration_components', configuration_id=config_id,
               component_key=f'L{offset + 1:04d}', structure_line_id=offset + 1,
               component_item_id=None, qty=1, uom_code='EA',
               parent_component_key=None, selection_source='user',
               source_rule_id=None, substitute_for_key=None,
               child_configuration_id=None, seq=offset + 1)


def _fetch(ds, config_id):
    return ds.query('SELECT * FROM configurations WHERE id = ?', [config_id])[0]


def _count(ds, table, config_id):
    return ds.query(f'SELECT COUNT(*) AS n FROM {table}'
                    ' WHERE configuration_id = ?', [config_id])[0]['n']


def _match(ds, config_id):
    return ConfigurationMatchService(ds).match(config_id)


class TestReuseHit:

    def test_frozen_source_yields_new_instance(self, env):
        _add_config(env, SOURCE, status='frozen', revision=1)
        _add_config(env, SOLVED, status='solved', revision=1)

        result = _match(env, SOLVED)

        assert result['reused'] is True
        assert result['source_id'] == SOURCE
        assert result['revision'] == 2
        assert result['config_hash'] == HASH
        assert result['status'] == 'frozen'

        new_id = result['configuration_id']
        assert new_id not in (SOLVED, SOURCE)
        new = _fetch(env, new_id)
        assert (new['revision'], new['reused_from_id']) == (2, SOURCE)
        assert (new['config_hash'], new['match_policy_used']) \
            == (HASH, 'one_time_standard')
        assert (new['status'], new['structure_id']) == ('frozen', ROOT_STRUCTURE)

        # 内容照抄：特征值与组件同数
        for table in ('configuration_values', 'configuration_components'):
            assert _count(env, table, new_id) == _count(env, table, SOLVED)

        # 源实例只读：状态与 revision 不变，不被指向自己
        source = _fetch(env, SOURCE)
        assert (source['status'], source['revision'], source['reused_from_id']) \
            == ('frozen', 1, None)

        # 刚求解出的实例被替代
        assert _fetch(env, SOLVED)['status'] == 'superseded'

    def test_newest_frozen_source_wins(self, env):
        _add_config(env, SOURCE, status='frozen', revision=1)
        _add_config(env, OTHER_SOURCE, status='frozen', revision=2)
        _add_config(env, SOLVED, status='solved', revision=1)

        result = _match(env, SOLVED)

        assert result['source_id'] == OTHER_SOURCE
        assert result['revision'] == 3

    def test_sequential_reuse_chains_revision(self, env):
        _add_config(env, SOURCE, status='frozen', revision=1)
        _add_config(env, SOLVED, status='solved', revision=1)
        first = _match(env, SOLVED)

        _add_config(env, 301, status='solved', revision=1)
        second = _match(env, 301)

        assert second['reused'] is True
        assert second['source_id'] == first['configuration_id']
        assert second['revision'] == 3
        assert _fetch(env, 301)['status'] == 'superseded'


class TestReuseMiss:

    def test_no_frozen_source_not_reused(self, env):
        _add_config(env, SOLVED, status='solved')

        result = _match(env, SOLVED)

        assert result['reused'] is False
        assert result['configuration_id'] == SOLVED
        assert _fetch(env, SOLVED)['status'] == 'solved'
        assert len(env.query('SELECT id FROM configurations')) == 1

    def test_different_hash_not_reused(self, env):
        _add_config(env, SOURCE, status='frozen', config_hash='H-OTHER')
        _add_config(env, SOLVED, status='solved')

        result = _match(env, SOLVED)

        assert result['reused'] is False
        assert _fetch(env, SOLVED)['status'] == 'solved'

    def test_model_version_upgrade_not_reused(self, env):
        """结构版本已升级（structure_id 变）→ 同 hash 也不复用（§6.4）。"""
        _add_config(env, SOURCE, status='frozen', structure_id=OTHER_STRUCTURE)
        _add_config(env, SOLVED, status='solved')

        assert _match(env, SOLVED)['reused'] is False

    def test_policy_no_not_reused(self, env):
        _add_config(env, SOURCE, status='frozen')
        _add_config(env, SOLVED, status='solved')
        env.update('items', MODEL_ITEM, {'config_match_policy': 'no'})

        assert _match(env, SOLVED)['reused'] is False

    def test_policy_one_time_user_defined_not_reused(self, env):
        _add_config(env, SOURCE, status='frozen')
        _add_config(env, SOLVED, status='solved')
        env.update('items', MODEL_ITEM,
                   {'config_match_policy': 'one_time_user_defined'})

        assert _match(env, SOLVED)['reused'] is False

    def test_unsolved_instance_not_reused(self, env):
        _add_config(env, SOURCE, status='frozen')
        _add_config(env, SOLVED, status='draft')

        result = _match(env, SOLVED)

        assert result['reused'] is False
        assert _fetch(env, SOLVED)['status'] == 'draft'

    def test_frozen_instance_not_reused(self, env):
        _add_config(env, SOURCE, status='frozen')
        _add_config(env, SOLVED, status='frozen')

        result = _match(env, SOLVED)

        assert result['reused'] is False
        assert _fetch(env, SOLVED)['status'] == 'frozen'

    def test_missing_instance_rejected(self, env):
        with pytest.raises(ItemStructureConfigError) as info:
            _match(env, 9999)
        assert info.value.code == 'CONFIG_VERSION_MISMATCH'
        assert info.value.rule == 'configuration_not_found'
