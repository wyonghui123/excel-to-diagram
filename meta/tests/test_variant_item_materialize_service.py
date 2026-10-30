# -*- coding: utf-8 -*-
"""变式物料化服务测试（Phase 1 manual 链路）

依据: docs/superpowers/specs/2026-10-30-variant-item-materialization-spec.md
      meta/services/variant_item_materialize_service.py

覆盖 spec §4.1 的 10 个用例：正常物化 / 幂等复用 / policy=off /
未 solved / 模型不可交易 / 无 hash / 序号递增 / draft 不可引用 /
审计 1+1 / 编码冲突不覆盖。
"""

import logging
import os
import sqlite3
import sys
from contextlib import contextmanager

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from meta.core.models import FieldType, MetaField, MetaObject, registry
from meta.core.value_help_accessor import validate_value_helps
from meta.core.yaml_loader import load_yaml_file
from meta.services.variant_item_materialize_service import (
    MaterializeError,
    VariantItemMaterializeService,
)
from meta.tests.factories._raw_sql_bridge import insert

_SCHEMA_DIR = os.path.join(PROJECT_ROOT, 'meta', 'schemas')

MODEL_ITEM = 1
MODEL_DRAFT = 2
MODEL_OFF = 3

SOLVED = 200
FROZEN = 201
SAME_HASH = 202
OTHER_HASH = 203
DRAFT_CFG = 204
INVALID_CFG = 205
NO_HASH = 206
OFF_CFG = 300
NOT_TRADABLE_CFG = 310


class _SqliteDS:
    """最小数据源：query / execute / insert / update / transaction / commit。"""

    def __init__(self, conn):
        self.conn = conn
        self._in_transaction = False

    @property
    def in_transaction(self):
        return self._in_transaction

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

    def commit(self):
        self.conn.commit()

    @contextmanager
    def transaction(self):
        if self._in_transaction:
            yield self
            return
        self._in_transaction = True
        try:
            yield self
        except Exception:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()
        finally:
            self._in_transaction = False


@pytest.fixture()
def ds():
    level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    conn = sqlite3.connect(':memory:')
    conn.executescript(
        """
        CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE, name TEXT, spec TEXT, structure_role TEXT,
            item_type TEXT, status TEXT, item_group_id INTEGER,
            base_uom INTEGER, sales_uom INTEGER, tax_classification_id INTEGER,
            config_match_policy TEXT, config_materialize_policy TEXT,
            variant_of_item_id INTEGER, variant_config_hash TEXT);
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
        CREATE TABLE audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT, object_id TEXT, action TEXT, field_name TEXT,
            old_value TEXT, new_value TEXT, user_id TEXT, user_name TEXT,
            ip_address TEXT, user_agent TEXT, created_at TEXT, trace_id TEXT,
            transaction_id TEXT, change_set_id TEXT, reason_code TEXT,
            agent_id TEXT, agent_session_id TEXT, tool_call_id TEXT,
            agent_reasoning TEXT, status TEXT, extra_data TEXT,
            parent_object_type TEXT, parent_object_id TEXT, log_category TEXT,
            log_level TEXT, outcome TEXT, retention_until TEXT,
            cascade_root_id TEXT, cascade_root_action TEXT);
        """
    )
    data_source = _SqliteDS(conn)
    _seed(data_source)
    data_source.commit()
    try:
        yield data_source
    finally:
        logging.disable(level)
        conn.close()


def _seed(data_source):
    now = '2026-10-30 00:00:00'
    insert(data_source, 'items', rows=[
        dict(id=MODEL_ITEM, code='MODEL-A', name='模型A', structure_role='model',
             item_type='goods', status='active', item_group_id=5, base_uom=1,
             sales_uom=2, tax_classification_id=3,
             config_match_policy='one_time_standard',
             config_materialize_policy='manual'),
        dict(id=MODEL_DRAFT, code='MODEL-B', name='模型B', structure_role='model',
             item_type='goods', status='draft', item_group_id=5, base_uom=1,
             sales_uom=2, tax_classification_id=3,
             config_match_policy='one_time_standard',
             config_materialize_policy='manual'),
        dict(id=MODEL_OFF, code='MODEL-C', name='模型C', structure_role='model',
             item_type='goods', status='active', item_group_id=5, base_uom=1,
             sales_uom=2, tax_classification_id=3,
             config_match_policy='one_time_standard',
             config_materialize_policy='off'),
    ])
    _add_config(data_source, SOLVED, MODEL_ITEM, 'solved', 'H-A', now)
    _add_config(data_source, FROZEN, MODEL_ITEM, 'frozen', 'H-FROZEN', now)
    _add_config(data_source, SAME_HASH, MODEL_ITEM, 'solved', 'H-A', now)
    _add_config(data_source, OTHER_HASH, MODEL_ITEM, 'solved', 'H-B', now)
    _add_config(data_source, DRAFT_CFG, MODEL_ITEM, 'draft', 'H-A', None)
    _add_config(data_source, INVALID_CFG, MODEL_ITEM, 'invalid', 'H-A', None)
    _add_config(data_source, NO_HASH, MODEL_ITEM, 'solved', None, now)
    _add_config(data_source, OFF_CFG, MODEL_OFF, 'solved', 'H-C', now)
    _add_config(data_source, NOT_TRADABLE_CFG, MODEL_DRAFT, 'solved', 'H-D', now)


def _add_config(data_source, config_id, model_item_id, status, config_hash,
                solved_at):
    insert(data_source, 'configurations', id=config_id,
           model_item_id=model_item_id, structure_id=9, status=status,
           config_hash=config_hash, revision=1, reused_from_id=None,
           match_policy_used='no', source_level='L2', context_json=None,
           validation_result_json=None, solved_at=solved_at, frozen_at=None,
           variant_item_id=None)
    insert(data_source, 'configuration_values', rows=[
        dict(configuration_id=config_id, attribute_code='color', seq=1,
             value_text='red', value_number=None, value_boolean=None,
             source='user', source_rule_id=None),
        dict(configuration_id=config_id, attribute_code='size', seq=1,
             value_text='L', value_number=None, value_boolean=None,
             source='user', source_rule_id=None),
    ])


def _config(data_source, config_id):
    rows = data_source.query(
        'SELECT * FROM configurations WHERE id = ?', [config_id])
    return rows[0] if rows else None


def _item(data_source, item_id):
    rows = data_source.query('SELECT * FROM items WHERE id = ?', [item_id])
    return rows[0] if rows else None


def _items_count(data_source):
    return data_source.query('SELECT COUNT(*) AS n FROM items')[0]['n']


def _assert_code(exc_info, code):
    assert exc_info.value.code == code, exc_info.value


# ─────────────────────────────────────────────────────────────────────────────
# 1. 正常物化
# ─────────────────────────────────────────────────────────────────────────────

def test_materialize_creates_draft_item(ds):
    result = VariantItemMaterializeService(ds).materialize(SOLVED)

    assert result['created'] is True
    assert result['item_code'] == 'MODEL-A-0001'

    row = _item(ds, result['item_id'])
    assert row['code'] == 'MODEL-A-0001'
    assert row['status'] == 'draft'
    assert row['structure_role'] == 'none'
    assert row['config_materialize_policy'] == 'off'
    assert row['config_match_policy'] == 'no'
    # 继承模型
    assert row['item_type'] == 'goods'
    assert row['item_group_id'] == 5
    assert row['base_uom'] == 1
    assert row['sales_uom'] == 2
    assert row['tax_classification_id'] == 3
    # name = 模型名 / 前 3 条配置值
    assert row['name'].startswith('模型A / ')
    assert len(row['name']) <= 60
    # 回写
    assert _config(ds, SOLVED)['variant_item_id'] == result['item_id']
    # provenance：幂等键物理落点
    assert row['variant_of_item_id'] == MODEL_ITEM
    assert row['variant_config_hash'] == 'H-A'


# ─────────────────────────────────────────────────────────────────────────────
# 2. 幂等复用
# ─────────────────────────────────────────────────────────────────────────────

def test_materialize_is_idempotent_per_model_and_hash(ds):
    service = VariantItemMaterializeService(ds)
    first = service.materialize(SOLVED)
    second = service.materialize(SAME_HASH)

    assert second['created'] is False
    assert second['item_id'] == first['item_id']
    assert _items_count(ds) == 4  # 3 个模型 + 1 个变式物料
    assert _config(ds, SOLVED)['variant_item_id'] == first['item_id']
    assert _config(ds, SAME_HASH)['variant_item_id'] == first['item_id']


# ─────────────────────────────────────────────────────────────────────────────
# 3. policy=off → 明确报错且不写
# ─────────────────────────────────────────────────────────────────────────────

def test_policy_off_rejects_with_explicit_code(ds):
    before = _items_count(ds)
    with pytest.raises(MaterializeError) as exc_info:
        VariantItemMaterializeService(ds).materialize(OFF_CFG)
    _assert_code(exc_info, 'MATERIALIZE_DISABLED')

    assert _items_count(ds) == before
    assert _config(ds, OFF_CFG)['variant_item_id'] is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. 配置未 solved
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('config_id', [DRAFT_CFG, INVALID_CFG])
def test_configuration_not_solved_rejected(ds, config_id):
    with pytest.raises(MaterializeError) as exc_info:
        VariantItemMaterializeService(ds).materialize(config_id)
    _assert_code(exc_info, 'CONFIG_NOT_SOLVED')
    assert _config(ds, config_id)['variant_item_id'] is None


# ─────────────────────────────────────────────────────────────────────────────
# 5. 模型不可交易（draft / inactive）
# ─────────────────────────────────────────────────────────────────────────────

def test_model_not_tradable_rejected(ds):
    service = VariantItemMaterializeService(ds)

    with pytest.raises(MaterializeError) as exc_info:
        service.materialize(NOT_TRADABLE_CFG)
    _assert_code(exc_info, 'MODEL_NOT_TRADABLE')

    ds.update('items', MODEL_DRAFT, {'status': 'inactive'})
    with pytest.raises(MaterializeError) as exc_info:
        service.materialize(NOT_TRADABLE_CFG)
    _assert_code(exc_info, 'MODEL_NOT_TRADABLE')

    assert _config(ds, NOT_TRADABLE_CFG)['variant_item_id'] is None


# ─────────────────────────────────────────────────────────────────────────────
# 6. 无 config_hash
# ─────────────────────────────────────────────────────────────────────────────

def test_config_hash_missing_rejected(ds):
    with pytest.raises(MaterializeError) as exc_info:
        VariantItemMaterializeService(ds).materialize(NO_HASH)
    _assert_code(exc_info, 'CONFIG_HASH_MISSING')
    assert _config(ds, NO_HASH)['variant_item_id'] is None


# ─────────────────────────────────────────────────────────────────────────────
# 7. 序号递增
# ─────────────────────────────────────────────────────────────────────────────

def test_sequence_increments_per_model(ds):
    service = VariantItemMaterializeService(ds)
    first = service.materialize(SOLVED)
    second = service.materialize(OTHER_HASH)

    assert first['item_code'] == 'MODEL-A-0001'
    assert second['item_code'] == 'MODEL-A-0002'
    assert second['created'] is True
    assert second['item_id'] != first['item_id']


def test_sequence_does_not_skip_when_configs_share_variant(ds):
    """D3 复用不得让序号跳号：两个配置共用一个物料后，下一个新物料仍是 0002。"""
    service = VariantItemMaterializeService(ds)
    first = service.materialize(SOLVED)
    reused = service.materialize(SAME_HASH)
    third = service.materialize(OTHER_HASH)

    assert reused['created'] is False
    assert reused['item_id'] == first['item_id']
    assert third['item_code'] == 'MODEL-A-0002'


# ─────────────────────────────────────────────────────────────────────────────
# 8. 联动不变量：draft 不可被单据行引用，签发后放行
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def item_registered():
    """`sales_order_line.item_id` 的 target_bo=item 需要可解析的最小对象。"""
    previous = registry.get('item')
    registry.register(MetaObject(
        id='item', name='物料', table_name='items',
        fields=[
            MetaField(id='id', name='ID', field_type=FieldType.INTEGER,
                      db_column='id'),
            MetaField(id='status', name='状态', field_type=FieldType.STRING,
                      db_column='status'),
        ],
    ))
    yield
    if previous is not None:
        registry.register(previous)
    else:
        registry.unregister('item')


def test_draft_variant_item_invisible_to_document_line_until_active(
        ds, item_registered):
    """value_filter.status='active' 生效：draft 拒 / active 放行（真表查询）。"""
    result = VariantItemMaterializeService(ds).materialize(SOLVED)
    item_id = result['item_id']
    assert _item(ds, item_id)['status'] == 'draft'

    line_meta = load_yaml_file(os.path.join(_SCHEMA_DIR, 'sales_order_line.yaml'))

    errors_draft = validate_value_helps(ds, line_meta, {'item_id': item_id})
    assert len(errors_draft) >= 1 and str(item_id) in errors_draft[0]

    ds.update('items', item_id, {'status': 'active'})
    errors_active = validate_value_helps(ds, line_meta, {'item_id': item_id})
    assert errors_active == []


# ─────────────────────────────────────────────────────────────────────────────
# 9. 审计：items 新增 1 条 + configuration 更新 1 条
# ─────────────────────────────────────────────────────────────────────────────

def test_materialize_writes_audit_for_item_create_and_config_update(ds):
    result = VariantItemMaterializeService(ds).materialize(SOLVED)

    created = ds.query(
        "SELECT * FROM audit_logs WHERE object_type = 'item'"
        " AND action = 'CREATE'")
    assert len(created) == 1
    assert created[0]['object_id'] == str(result['item_id'])
    assert created[0]['new_value'] == result['item_code']

    updated = ds.query(
        "SELECT * FROM audit_logs WHERE object_type = 'configuration'"
        " AND action = 'UPDATE'")
    assert len(updated) == 1
    assert updated[0]['object_id'] == str(SOLVED)
    assert updated[0]['field_name'] == 'variant_item_id'
    assert updated[0]['new_value'] == str(result['item_id'])


# ─────────────────────────────────────────────────────────────────────────────
# 10. 编码冲突：重算序号、不静默覆盖
# ─────────────────────────────────────────────────────────────────────────────

def test_code_conflict_recomputes_sequence_without_overwrite(ds):
    insert(ds, 'items', id=900, code='MODEL-A-0001', name='占位变式',
           structure_role='none', item_type='goods', status='active',
           item_group_id=5, base_uom=1, config_match_policy='no',
           config_materialize_policy='off')
    ds.commit()

    service = VariantItemMaterializeService(ds)
    try:
        result = service.materialize(SOLVED)
    except MaterializeError as exc:
        assert exc.code == 'CODE_CONFLICT'
    else:
        assert result['created'] is True
        assert result['item_code'] == 'MODEL-A-0002'

    # 预置行未被覆盖
    existing = _item(ds, 900)
    assert existing['code'] == 'MODEL-A-0001'
    assert existing['name'] == '占位变式'


# ─────────────────────────────────────────────────────────────────────────────
# 11. auto（§12）：配置冻结后按模型策略自动物化，产物直接 active
# ─────────────────────────────────────────────────────────────────────────────

def _set_policy(data_source, model_item_id, policy):
    data_source.update('items', model_item_id,
                       {'config_materialize_policy': policy})
    data_source.commit()


def _freeze(data_source, config_id):
    data_source.update('configurations', config_id, {'status': 'frozen'})
    data_source.commit()


def test_auto_policy_materializes_on_freeze_as_active(ds):
    _set_policy(ds, MODEL_ITEM, 'auto')

    result = VariantItemMaterializeService(ds).materialize_on_freeze(FROZEN)

    assert result is not None
    assert result['created'] is True
    assert result['item_code'] == 'MODEL-A-0001'
    assert _item(ds, result['item_id'])['status'] == 'active'
    assert _config(ds, FROZEN)['variant_item_id'] == result['item_id']


def test_auto_policy_ignores_solved_configuration(ds):
    """承诺点语义：solved（未冻结）不触发，避免售前试配产生主数据。"""
    _set_policy(ds, MODEL_ITEM, 'auto')
    before = _items_count(ds)

    result = VariantItemMaterializeService(ds).materialize_on_freeze(SOLVED)

    assert result is None
    assert _items_count(ds) == before
    assert _config(ds, SOLVED)['variant_item_id'] is None


def test_auto_policy_skips_when_model_policy_not_auto(ds):
    before = _items_count(ds)

    result = VariantItemMaterializeService(ds).materialize_on_freeze(FROZEN)

    assert result is None
    assert _items_count(ds) == before
    assert _config(ds, FROZEN)['variant_item_id'] is None


def test_auto_policy_swallows_failure_without_raising(ds):
    _set_policy(ds, MODEL_DRAFT, 'auto')
    _freeze(ds, NOT_TRADABLE_CFG)
    before = _items_count(ds)

    # MODEL_DRAFT 状态 draft → MODEL_NOT_TRADABLE，属于可预期拒绝
    result = VariantItemMaterializeService(ds).materialize_on_freeze(
        NOT_TRADABLE_CFG)

    assert result is None
    assert _items_count(ds) == before
    assert _config(ds, NOT_TRADABLE_CFG)['variant_item_id'] is None


def test_auto_policy_reuses_variant_for_same_hash(ds):
    _set_policy(ds, MODEL_ITEM, 'auto')
    _freeze(ds, SOLVED)
    _freeze(ds, SAME_HASH)
    service = VariantItemMaterializeService(ds)

    first = service.materialize_on_freeze(SOLVED)
    second = service.materialize_on_freeze(SAME_HASH)

    assert first is not None and first['created'] is True
    assert second is not None and second['created'] is False
    assert second['item_id'] == first['item_id']
    assert _items_count(ds) == 4  # 3 模型 + 1 变式物料
