# -*- coding: utf-8 -*-
"""位置锚 · site 支持对象接线（address_id / calendar_id）(2026-10-06)

依据: docs/superpowers/specs/2026-10-04-foundation-object-model-and-architecture.md
      §3.5.2（site: address_id→address / timezone / calendar_id→calendar）
      §7 步 1（位置锚）+ 步 7（支持对象 address / calendar 已落地 ⇒ 接线前置解除）

口径（W12 载体核对结论, 2026-10-06）:
  - 平台 aspects = 静态字段切面（无条件合并）; 条件机制仅 conditional_required（校验层）
    ⇒ 无字段级"按类型存在"表达力; site 引用以【可空公共列 + value_help(strict)】先行接线
    （非 site 类型恒空; 条件显示待平台机制）。
  - deletion 反补: address.yaml / calendar.yaml 的 restrict_on 指向 locations 列
    （locations.address_id / locations.calendar_id），列随建表落。

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

# 接线清单: field_id → (target_bo, display_field)
_SITE_REFS = {
    'address_id': ('address', 'formatted_address'),
    'calendar_id': ('calendar', 'name'),
}

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
def loc_ds(tmp_path):
    """临时库: locations 单表（aspects 按平台路径解析）"""
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'location.yaml'),
                         aspects_defs=aspects)
    assert obj is not None, 'location.yaml 加载失败'

    ds = get_data_source('sqlite', database=str(tmp_path / 'location.db'))
    sync_schema_from_meta(ds, [obj])
    yield ds
    _clear_data_source_cache_for_testing()


# ────────────────────────────────────────
# 1. YAML 接线（value_help / display / ui）
# ────────────────────────────────────────
class TestSiteRefWiring:
    @pytest.mark.parametrize('field_id', sorted(_SITE_REFS))
    def test_value_help_strict_wiring(self, field_id):
        """引用接线: source.target_bo + binding_strength=strict（照 items 先例）"""
        target, display = _SITE_REFS[field_id]
        field = _field(_load_raw('location'), field_id)
        assert field is not None, f'location.{field_id} 未接线'
        value_help = field.get('value_help') or {}
        source = value_help.get('source') or {}
        assert source.get('type') == 'bo'
        assert source.get('target_bo') == target
        assert source.get('value_field') == 'id'
        assert source.get('display_field') == display
        assert source.get('code_field') == 'code'
        assert source.get('apply_target_permissions') is True
        behavior = value_help.get('behavior') or {}
        assert behavior.get('binding_strength') == 'strict'
        assert behavior.get('validation') is True
        assert behavior.get('multiple') is False

    @pytest.mark.parametrize('field_id', sorted(_SITE_REFS))
    def test_display_and_ui_wired(self, field_id):
        """关联展示 + 选择控件已接线（不再是裸整数 input）"""
        target, display = _SITE_REFS[field_id]
        field = _field(_load_raw('location'), field_id)
        display_cfg = (field.get('semantics') or {}).get('display') or {}
        assert display_cfg.get('type') == 'association'
        assert display_cfg.get('target_type') == target
        assert display_cfg.get('display_field') == display
        ui = field.get('ui') or {}
        assert ui.get('widget') == 'select'
        assert ui.get('relation') == target
        assert ui.get('multiple') is False

    @pytest.mark.parametrize('field_id', sorted(_SITE_REFS))
    def test_nullable_site_semantics(self, field_id):
        """非 site 类型恒空 ⇒ 可空列（不设 required）"""
        field = _field(_load_raw('location'), field_id)
        assert field.get('nullable') is True
        assert not field.get('required')

    def test_target_display_fields_exist(self):
        """value_help 目标列必须在目标对象上真实存在（防静默漂移）"""
        for target, display in _SITE_REFS.values():
            cols = {f.get('id') for f in _load_raw(target)['fields']}
            assert display in cols, f'{target}.{display} 不存在（接线目标漂移）'
            assert 'code' in cols, f'{target}.code 不存在（code_field 漂移）'

    def test_form_and_detail_list_fields(self):
        """接线字段进表单（场地信息 section）与详情（否则用户不可维护）"""
        data = _load_raw('location')
        form_fields = set()
        for sec in data['ui_view_config']['form']['sections']:
            for col in sec.get('columns') or []:
                form_fields.update(col.get('fields') or [])
        detail_fields = set()
        for tab in data['ui_view_config']['detail']['tabs']:
            detail_fields.update(tab.get('fields') or [])
        for fid in _SITE_REFS:
            assert fid in form_fields, f'{fid} 未进表单'
            assert fid in detail_fields, f'{fid} 未进详情'


# ────────────────────────────────────────
# 2. 建表落地（可空引用列 + 非 site 恒空）
# ────────────────────────────────────────
class TestSchemaLands:
    def test_site_row_keeps_refs(self, loc_ds):
        loc_ds.insert('locations', {
            'id': 1, 'code': 'SITE01', 'name': '华东园区',
            'location_type': 'site', 'status': 'active',
            'address_id': 101, 'calendar_id': 201,
        })
        row = loc_ds.execute(
            'SELECT address_id, calendar_id FROM locations WHERE id = ?',
            (1,)).fetchone()
        assert row[0] == 101
        assert row[1] == 201

    def test_non_site_row_refs_null(self, loc_ds):
        loc_ds.insert('locations', {
            'id': 2, 'code': 'WH01', 'name': '原料仓',
            'location_type': 'warehouse', 'status': 'active', 'parent_id': 1,
        })
        row = loc_ds.execute(
            'SELECT address_id, calendar_id FROM locations WHERE id = ?',
            (2,)).fetchone()
        assert row[0] is None
        assert row[1] is None


# ────────────────────────────────────────
# 3. deletion 反补（restrict_on 指向已落列）
# ────────────────────────────────────────
class TestDeletionBackfill:
    def test_address_restrict_on_locations(self):
        dp = _load_raw('address')['deletion_policy']
        assert dp['mode'] == 'restrict'
        pairs = {(r['table'], r['foreign_key']) for r in dp['restrict_on']}
        assert ('locations', 'address_id') in pairs

    def test_calendar_restrict_on_locations(self):
        dp = _load_raw('calendar')['deletion_policy']
        pairs = {(r['table'], r['foreign_key']) for r in dp['restrict_on']}
        assert ('locations', 'calendar_id') in pairs

    def test_location_self_restrict_kept(self):
        """location 一期统一 restrict: 自引用 parent_id 条目保留"""
        dp = _load_raw('location')['deletion_policy']
        pairs = {(r['table'], r['foreign_key']) for r in dp['restrict_on']}
        assert ('locations', 'parent_id') in pairs