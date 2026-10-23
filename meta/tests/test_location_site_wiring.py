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
    """临时库: locations + 父表 address / calendar（aspects 按平台路径解析）

    [FK 2026-10-07] locations 新增三条真外键（parent_id 自引用 /
    address_id→addresses / calendar_id→calendars），单表库须补父表。
    """
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    objs = [load_yaml_file(os.path.join(_SCHEMA_DIR, fn), aspects_defs=aspects)
            for fn in ('region.yaml', 'address.yaml', 'calendar.yaml',
                       'location.yaml')]
    assert all(o is not None for o in objs), 'location 相关 YAML 加载失败'

    ds = get_data_source('sqlite', database=str(tmp_path / 'location.db'))
    sync_schema_from_meta(ds, objs)
    # 父行：site 用例硬编码 address_id=101 / calendar_id=201
    # addresses.country_id 也是真外键 → regions，故先落 region 父行
    ds.insert('regions', {'id': 1, 'code': 'CN', 'name': '中国',
                          'level': 'country', 'status': 'active'})
    ds.insert('addresses', {'id': 101, 'code': 'ADDR-101',
                            'country_id': 1, 'formatted_address': '测试地址'})
    ds.insert('calendars', {'id': 201, 'code': 'CAL-201', 'name': '测试日历'})
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

    def test_list_column_calendar_renders_as_association(self):
        """[FIX 2026-10-23] 日历列必须在列表中按关联列渲染

        只落字段定义（semantics.display / value_help）不足以让列表显示可读值，
        ui_view_config.list.columns 必须显式声明该列，否则列表看不到「日历」列。
        写法对齐同文件 parent_id 与 calendar.yaml parent_calendar_id。

        注: address_id 未进列表列（列已足够宽, 地址走详情查看）, 不在本用例范围。
        """
        target, display = _SITE_REFS['calendar_id']
        data = _load_raw('location')
        cols = {
            c['field']: c
            for c in data['ui_view_config']['list']['columns']
        }
        assert 'calendar_id' in cols, 'calendar_id 未进列表列'
        col = cols['calendar_id']
        assert col.get('render_as') == 'association'
        assert col.get('target_type') == target
        assert col.get('display_field') == display
        assert col.get('filterable') is True
        assert col.get('filter_type') == 'value_help'


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
        # [FK 2026-10-07] parent_id 自引用外键：先落父行（原依赖上一用例的 id=1，
        # 但夹具 function-scoped，用例间不共享）
        loc_ds.insert('locations', {
            'id': 1, 'code': 'SITE01', 'name': '华东园区',
            'location_type': 'site', 'status': 'active',
            'address_id': 101, 'calendar_id': 201,
        })
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