# -*- coding: utf-8 -*-
"""party_group · 分类对象接线（party_relations.group_id → party_groups）(2026-10-07)

依据: docs/superpowers/specs/2026-10-04-classification-objects-as-rule-factor-research.md（G2）
      + 2026-10-07 拍板：统一分组（不拆客户组/供应商组）、role_scope 适用范围、挂关系层

覆盖:
1. YAML 结构: party_group 字段（code / name / role_scope / parent_id）+ role_scope 必填无默认 + 枚举三类
2. YAML 接线: party_relation.group_id（value_help strict / display / ui / 可空）
3. 建表落地: party_groups + party_relations 建表; group_id 正向引用 / NULL 放行 / 孤儿拦截;
   party_groups.parent_id 自引用（正向 + 孤儿拦截）; role_scope NOT NULL 强制
4. deletion 反补: party_group.restrict_on → party_relations.group_id 与 party_groups.parent_id

测试隔离: temp DB（get_data_source）+ sync_schema_from_meta; 不触碰 architecture.db;
         DML 走 ds.insert API（本文件无裸写语句 —— conftest raw-SQL 守卫）
"""
import os
import sys

import pytest
import yaml

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

_META_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_DIR = os.path.join(_META_DIR, 'schemas')

pytestmark = pytest.mark.unit


# ────────────────────────────────────────
# 辅助
# ────────────────────────────────────────
def _load_raw(bo_id):
    with open(os.path.join(_SCHEMA_DIR, bo_id + '.yaml'), 'r',
              encoding='utf-8') as f:
        return yaml.safe_load(f)


def _field(schema, field_id):
    for f in schema.get('fields') or []:
        if f.get('id') == field_id:
            return f
    return None


# ────────────────────────────────────────
# 夹具
# ────────────────────────────────────────
@pytest.fixture()
def pg_ds(tmp_path):
    """临时库: party_groups + party_relations + 父表 parties / orgs"""
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml
    from meta import registry

    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    pg = load_yaml_file(os.path.join(_SCHEMA_DIR, 'party_group.yaml'),
                        aspects_defs=aspects)
    pr = load_yaml_file(os.path.join(_SCHEMA_DIR, 'party_relation.yaml'))
    assert pg is not None and pr is not None, 'party_group / party_relation YAML 加载失败'
    # FK 目标解析（party_relation.group_id → party_groups 物理表）
    registry.register(pg)

    ds = get_data_source('sqlite', database=str(tmp_path / 'party_group.db'))
    sync_schema_from_meta(ds, [pg, pr])
    ds.execute("CREATE TABLE IF NOT EXISTS parties "
               "(id INTEGER PRIMARY KEY AUTOINCREMENT)")
    ds.execute("CREATE TABLE IF NOT EXISTS orgs "
               "(id INTEGER PRIMARY KEY AUTOINCREMENT)")
    ds.insert('parties', {'id': 1})
    ds.insert('parties', {'id': 2})
    yield ds
    _clear_data_source_cache_for_testing()


def _relation(ds, rid, group_id):
    ds.insert('party_relations', {
        'id': rid, 'party1_id': 1, 'party2_id': 2,
        'role': 'customer', 'internal_mark': 'external',
        'group_id': group_id,
    })


# ────────────────────────────────────────
# 1. YAML 结构
# ────────────────────────────────────────
class TestPartyGroupStructure:
    def test_naming(self):
        data = _load_raw('party_group')
        assert data['id'] == 'party_group'
        assert data['table_name'] == 'party_groups'

    def test_business_key_and_fields(self):
        data = _load_raw('party_group')
        assert data['semantics']['business_key'] == ['code']
        for fid in ('code', 'name', 'role_scope', 'parent_id', 'description'):
            assert _field(data, fid) is not None, '字段缺失: %s' % fid

    def test_code_unique_immutable(self):
        f = _field(_load_raw('party_group'), 'code')
        assert f['unique'] is True
        assert f.get('max_length') == 50
        assert f['semantics'].get('immutable') is True

    def test_role_scope_required_no_default(self):
        """必填无默认：防静默误挂（默认 both 会让字段空转）"""
        f = _field(_load_raw('party_group'), 'role_scope')
        assert f['required'] is True
        assert 'default' not in f or f.get('default') is None
        vals = {e['value'] for e in f['enum_values']}
        assert vals == {'customer', 'vendor', 'both'}

    def test_parent_depth_10(self):
        f = _field(_load_raw('party_group'), 'parent_id')
        assert f['semantics']['hierarchy_level']['max_depth'] == 10
        assert f.get('nullable') is True

    def test_audit_aspect(self):
        assert 'audit_aspect' in (_load_raw('party_group').get('aspects') or [])


# ────────────────────────────────────────
# 2. party_relation.group_id 接线
# ────────────────────────────────────────
class TestGroupRefWiring:
    def test_value_help_strict_wiring(self):
        field = _field(_load_raw('party_relation'), 'group_id')
        assert field is not None, 'party_relation.group_id 未接线'
        source = (field.get('value_help') or {}).get('source') or {}
        assert source.get('type') == 'bo'
        assert source.get('target_bo') == 'party_group'
        assert source.get('value_field') == 'id'
        assert source.get('display_field') == 'name'
        assert source.get('code_field') == 'code'
        assert source.get('apply_target_permissions') is True
        behavior = (field.get('value_help') or {}).get('behavior') or {}
        assert behavior.get('binding_strength') == 'strict'
        assert behavior.get('validation') is True
        assert behavior.get('multiple') is False

    def test_display_and_ui_wired(self):
        field = _field(_load_raw('party_relation'), 'group_id')
        display_cfg = (field.get('semantics') or {}).get('display') or {}
        assert display_cfg.get('type') == 'association'
        assert display_cfg.get('target_type') == 'party_group'
        assert display_cfg.get('display_field') == 'name'
        ui = field.get('ui') or {}
        assert ui.get('widget') == 'select'
        assert ui.get('relation') == 'party_group'
        assert ui.get('multiple') is False

    def test_nullable_optional(self):
        """分类可选挂（未归类 = NULL），不设 required"""
        field = _field(_load_raw('party_relation'), 'group_id')
        assert field.get('nullable') is True
        assert not field.get('required')

    def test_target_display_fields_exist(self):
        cols = {f.get('id') for f in _load_raw('party_group')['fields']}
        assert 'name' in cols and 'code' in cols

    def test_relation_cardinality_is_string(self):
        """防 YAML 1.1 六十进制坑：cardinality 必须是字符串 'N:1'"""
        rels = {r['id']: r for r in _load_raw('party_relation').get('relations') or []}
        rel = rels.get('party_relation_to_party_group')
        assert rel is not None, 'party_relation_to_party_group 关系缺失'
        assert rel['cardinality'] == 'N:1'
        assert rel['source_field'] == 'group_id'
        assert rel['target'] == 'party_group'


# ────────────────────────────────────────
# 3. 建表落地（FK 强制）
# ────────────────────────────────────────
class TestSchemaLands:
    def test_tables_created(self, pg_ds):
        names = {r[0] for r in pg_ds.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert 'party_groups' in names
        assert 'party_relations' in names

    def test_group_ref_ok(self, pg_ds):
        pg_ds.insert('party_groups', {'id': 1, 'code': 'C_KA',
                                      'name': '重点客户', 'role_scope': 'customer'})
        _relation(pg_ds, 1, 1)
        row = pg_ds.execute(
            'SELECT group_id FROM party_relations WHERE id = ?', (1,)).fetchone()
        assert row[0] == 1

    def test_group_ref_null_ok(self, pg_ds):
        _relation(pg_ds, 1, None)
        row = pg_ds.execute(
            'SELECT group_id FROM party_relations WHERE id = ?', (1,)).fetchone()
        assert row[0] is None

    def test_orphan_group_rejected(self, pg_ds):
        with pytest.raises(Exception):
            _relation(pg_ds, 1, 999)

    def test_parent_self_fk(self, pg_ds):
        pg_ds.insert('party_groups', {'id': 1, 'code': 'P_ROOT',
                                      'name': '根', 'role_scope': 'both'})
        pg_ds.insert('party_groups', {'id': 2, 'code': 'P_CHILD',
                                      'name': '子', 'role_scope': 'both',
                                      'parent_id': 1})
        with pytest.raises(Exception):
            pg_ds.insert('party_groups', {'id': 3, 'code': 'P_BAD',
                                          'name': '孤儿', 'role_scope': 'both',
                                          'parent_id': 999})

    def test_role_scope_not_null(self, pg_ds):
        """role_scope 必填 ⇒ 建表为 NOT NULL（无默认）"""
        with pytest.raises(Exception):
            pg_ds.insert('party_groups', {'id': 4, 'code': 'P_NOSCOPE',
                                          'name': '缺范围'})


# ────────────────────────────────────────
# 4. deletion 反补
# ────────────────────────────────────────
class TestDeletionBackfill:
    def test_restrict_on_relations_and_parent(self):
        dp = _load_raw('party_group')['deletion_policy']
        assert dp['mode'] == 'restrict'
        pairs = {(r['table'], r['foreign_key']) for r in dp['restrict_on']}
        assert ('party_relations', 'group_id') in pairs
        assert ('party_groups', 'parent_id') in pairs