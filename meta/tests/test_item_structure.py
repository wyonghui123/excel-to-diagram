# -*- coding: utf-8 -*-
"""物料结构模型测试（schema 接线 + 守卫 R1/R3–R8/S1 + 展开口径 + 拦截器接线）

依据: meta/schemas/item_structure.yaml / item_structure_line.yaml 头注释
      meta/services/item_structure_guard_service.py
      meta/services/item_structure_explode_service.py
"""

import os

# 本文件只用 :memory: sqlite 造最小表，不碰真实库；按项目惯例解除 raw-SQL 守卫跳过
# （同 test_allocation_by_rule / test_bo_status_interceptor 的口径）。
os.environ.setdefault('ALLOW_RAW_SQL', '1')

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

pytestmark = pytest.mark.unit

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.item_structure_guard_interceptor import (
    ItemStructureGuardInterceptor,
)
from meta.services.item_structure_explode_service import (
    ItemStructureExplodeError,
    ItemStructureExplodeService,
)
from meta.services.item_structure_guard_service import (
    ItemStructureGuardError,
    ItemStructureGuardService,
)
from meta.services.item_structure_select_service import (
    ItemStructureSelectError,
    ItemStructureSelectService,
)

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / 'schemas'


# ─────────────────────────────────────────────────────────────────────────────
# 内存库（守卫与展开共用同一套三张表的最小形态）
# ─────────────────────────────────────────────────────────────────────────────

class _SqliteDS:
    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _new_db():
    conn = sqlite3.connect(':memory:')
    conn.execute(
        'CREATE TABLE items (id INTEGER PRIMARY KEY, structure_role TEXT, '
        'item_type TEXT, status TEXT)')
    conn.execute(
        'CREATE TABLE item_structures (id INTEGER PRIMARY KEY, item_id INTEGER, '
        'usage TEXT, alternative_no INTEGER, revision TEXT, status TEXT, '
        'base_qty REAL, valid_from TEXT, valid_to TEXT, '
        'min_select INTEGER, max_select INTEGER)')
    conn.execute(
        'CREATE TABLE item_structure_attributes (id INTEGER PRIMARY KEY, '
        'structure_id INTEGER, attribute_code TEXT, required_flag INTEGER, '
        'default_value_text TEXT, seq INTEGER, ui_widget TEXT)')
    conn.execute(
        'CREATE TABLE item_structure_lines (id INTEGER PRIMARY KEY, structure_id INTEGER, '
        'line_no INTEGER, component_item_id INTEGER, qty_per REAL, fixed_qty REAL, '
        'optional_flag INTEGER, default_flag INTEGER, phantom_flag INTEGER, '
        'min_qty REAL, max_qty REAL, default_qty REAL, substitute_group_code TEXT, '
        'included_in_base_price INTEGER, valid_from TEXT, valid_to TEXT, '
        'operation_seq INTEGER)')
    conn.execute(
        'CREATE TABLE attribute_definitions (id INTEGER PRIMARY KEY, tenant_id INTEGER, '
        'code TEXT, data_type TEXT, is_configurable INTEGER, status TEXT, '
        'value_domain_type TEXT, value_domain_ref TEXT)')
    conn.execute(
        'CREATE TABLE enum_values (id INTEGER PRIMARY KEY, enum_type_id TEXT, '
        'code TEXT, is_active INTEGER)')
    return conn


def _add_item(conn, item_id, role='none', item_type='goods', status='active'):
    conn.execute('INSERT INTO items VALUES (?, ?, ?, ?)',
                 (item_id, role, item_type, status))


def _add_structure(conn, sid, item_id, status='draft', usage='production',
                   alternative_no=1, valid_from='2026-01-01', valid_to=None,
                   base_qty=1, min_select=None, max_select=None):
    conn.execute(
        'INSERT INTO item_structures (id, item_id, usage, alternative_no, '
        'revision, status, base_qty, valid_from, valid_to, '
        'min_select, max_select) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (sid, item_id, usage, alternative_no, 'A', status, base_qty,
         valid_from, valid_to, min_select, max_select))


def _add_line(conn, line_id, structure_id, line_no, component_item_id,
              qty_per=None, fixed_qty=None, optional_flag=0, default_flag=0,
              phantom_flag=0, substitute_group_code=None, valid_from=None,
              valid_to=None, min_qty=None, max_qty=None, default_qty=None):
    conn.execute(
        'INSERT INTO item_structure_lines (id, structure_id, line_no, '
        'component_item_id, qty_per, fixed_qty, optional_flag, default_flag, '
        'phantom_flag, substitute_group_code, valid_from, valid_to, '
        'min_qty, max_qty, default_qty, included_in_base_price) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)',
        (line_id, structure_id, line_no, component_item_id, qty_per, fixed_qty,
         optional_flag, default_flag, phantom_flag, substitute_group_code,
         valid_from, valid_to, min_qty, max_qty, default_qty))


# ─────────────────────────────────────────────────────────────────────────────
# schema 接线
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaWiring:
    def _load(self, name):
        with open(_SCHEMA_DIR / f'{name}.yaml', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def test_item_two_new_fields(self):
        item = self._load('items')
        fields = {f['id']: f for f in item['fields']}
        assert fields['structure_role']['default'] == 'none'
        assert [e['value'] for e in fields['structure_role']['enum_values']] == [
            'none', 'model', 'option_class']
        # YAML 1.1 下 no 会变布尔，必须以字符串落库
        policy = fields['config_match_policy']
        assert policy['default'] == 'no'
        assert all(isinstance(e['value'], str) for e in policy['enum_values'])

    def test_structure_header(self):
        obj = self._load('item_structure')
        assert obj['table_name'] == 'item_structures'
        assert obj['ui_view_config']['skip_auto_menu'] is True
        keys = [i['fields'] for i in obj['indexes'] if i.get('unique')]
        assert ['item_id', 'usage', 'alternative_no', 'revision'] in keys
        relations = {r['source_field']: r['target'] for r in obj['relations']}
        assert relations['item_id'] == 'item'
        assert relations['base_uom_id'] == 'uom'

    def test_structure_header_child_section(self):
        # 结构行、模型特征与配置规则都必须能挂在结构详情页内联维护，不另成菜单
        obj = self._load('item_structure')
        children = obj['ui_view_config'].get('child_sections') or []
        assert [c['child_object'] for c in children] == [
            'item_structure_line', 'item_structure_attribute', 'config_rule']
        assert all(c['enableAutoCrud'] is True for c in children)

    def test_structure_attribute(self):
        obj = self._load('item_structure_attribute')
        assert obj['table_name'] == 'item_structure_attributes'
        assert obj['parent_object'] == 'item_structure'
        assert obj['hierarchy']['parent_field'] == 'structure_id'
        assert obj['deletion_policy']['mode'] == 'cascade'
        assert obj['ui_view_config']['skip_auto_menu'] is True
        keys = [i['fields'] for i in obj['indexes'] if i.get('unique')]
        assert ['structure_id', 'attribute_code'] in keys
        relations = {r['source_field']: r['target'] for r in obj['relations']}
        assert relations['structure_id'] == 'item_structure'

    def test_structure_line(self):
        obj = self._load('item_structure_line')
        assert obj['table_name'] == 'item_structure_lines'
        assert obj['parent_object'] == 'item_structure'
        assert obj['hierarchy']['parent_field'] == 'structure_id'
        assert obj['ui_view_config']['skip_auto_menu'] is True
        keys = [i['fields'] for i in obj['indexes'] if i.get('unique')]
        assert ['structure_id', 'line_no'] in keys


# ─────────────────────────────────────────────────────────────────────────────
# 守卫
# ─────────────────────────────────────────────────────────────────────────────

class TestStructureGuard:
    def setup_method(self):
        self.conn = _new_db()
        for iid, role in ((1, 'none'), (2, 'none'), (3, 'model'),
                          (4, 'option_class'), (5, 'model'), (6, 'none')):
            _add_item(self.conn, iid, role)
        _add_structure(self.conn, 10, 1)   # 父项 1
        _add_structure(self.conn, 12, 2)   # 父项 2（用于成环）
        _add_structure(self.conn, 30, 3)   # 父项 3（模型）
        _add_line(self.conn, 1, 10, 1, 2, qty_per=1)
        self.svc = ItemStructureGuardService(_SqliteDS(self.conn))
        self.base = {'structure_id': 12, 'component_item_id': 6,
                     'line_no': 1, 'qty_per': 1}

    def _rule(self, data, header=False):
        with pytest.raises(ItemStructureGuardError) as e:
            if header:
                self.svc.validate_structure_write(data)
            else:
                self.svc.validate_line_write(data)
        return e.value.rule, e.value.field_name

    def test_r3_qty_exclusive(self):
        assert self._rule(dict(self.base, qty_per=None))[0] \
            == 'item_structure_line_qty_exclusive'
        assert self._rule(dict(self.base, fixed_qty=2))[0] \
            == 'item_structure_line_qty_exclusive'
        # 都不填时定位到 qty_per（提示先填哪个）
        assert self._rule(dict(self.base, qty_per=None))[1] == 'qty_per'

    def test_r3_single_qty_passes(self):
        self.svc.validate_line_write(dict(self.base, qty_per=None, fixed_qty=2))

    def test_r1_self_reference(self):
        rule, field = self._rule(dict(self.base, structure_id=10, component_item_id=1))
        assert (rule, field) == ('item_structure_self_reference', 'component_item_id')

    def test_r1_cycle(self):
        # 结构 10（父项 1）已含组件 2；再给父项 2 挂组件 1 即成环
        assert self._rule(dict(self.base, component_item_id=1))[0] \
            == 'item_structure_cycle'

    def test_r1_update_excludes_self(self):
        # 更新结构 10 的第 1 行本身不构成环
        self.svc.validate_line_write(
            {'id': 1, 'structure_id': 10, 'component_item_id': 2, 'qty_per': 1},
            exclude_id=1)

    def test_r7_role_matrix(self):
        # 标准结构只装标准件：模型 / 选项类都拒
        assert self._rule(dict(self.base, component_item_id=3))[0] \
            == 'item_structure_role_combination_invalid'
        assert self._rule(dict(self.base, component_item_id=4))[0] \
            == 'item_structure_role_combination_invalid'
        self.svc.validate_line_write(dict(self.base, component_item_id=6))
        # 模型父项（结构 30 / 物料 3）：标准件、选项类、子模型都放行
        for cid in (6, 4, 5):
            self.svc.validate_line_write(
                dict(self.base, structure_id=30, component_item_id=cid))
        # 选项类父项（结构 50 / 物料 4）：标准件、选项类、子模型都放行
        _add_item(self.conn, 8, 'option_class')
        _add_structure(self.conn, 50, 4)
        for cid in (6, 8, 5):
            self.svc.validate_line_write(
                dict(self.base, structure_id=50, component_item_id=cid))

    def test_r11_service_component_rejected(self):
        _add_item(self.conn, 7, item_type='service')
        assert self._rule(dict(self.base, component_item_id=7))[0] \
            == 'item_structure_component_service_item'

    def test_r11_service_component_allowed_in_sales_usage(self):
        _add_item(self.conn, 7, item_type='service')
        _add_structure(self.conn, 60, 1, usage='sales')
        self.svc.validate_line_write(
            dict(self.base, structure_id=60, component_item_id=7,
                 qty_per=None, fixed_qty=1))

    def test_r16_service_line_rejects_material_semantics(self):
        _add_item(self.conn, 7, item_type='service')
        _add_structure(self.conn, 60, 1, usage='sales')
        base = dict(self.base, structure_id=60, component_item_id=7,
                    qty_per=None, fixed_qty=1)
        cases = (
            (dict(base, scrap_rate=0.02),
             'item_structure_service_line_scrap_rate'),
            (dict(base, substitute_group_code='G1'),
             'item_structure_service_line_substitute'),
            (dict(base, phantom_flag=True),
             'item_structure_service_line_phantom'),
            (dict(base, operation_seq=10),
             'item_structure_service_line_operation_seq'),
            (dict(base, qty_per=1, fixed_qty=None),
             'item_structure_service_line_qty_per'),
        )
        for data, rule in cases:
            assert self._rule(data)[0] == rule

    def test_r12_service_parent_rejected(self):
        _add_item(self.conn, 9, item_type='service')
        assert self._rule(
            {'item_id': 9, 'usage': 'sales', 'alternative_no': 1,
             'status': 'draft', 'valid_from': '2026-01-01'},
            header=True) == ('item_structure_parent_requires_goods', 'item_id')
        # 实物物料作父项放行
        self.svc.validate_structure_write(
            {'item_id': 1, 'usage': 'sales', 'alternative_no': 1,
             'status': 'draft', 'valid_from': '2026-01-01'})

    def test_m1_service_item_cannot_hold_role(self):
        with pytest.raises(ItemStructureGuardError) as e:
            self.svc.validate_item_write(
                {'item_type': 'service', 'structure_role': 'model'})
        assert (e.value.rule, e.value.field_name) == (
            'item_structure_role_requires_goods', 'structure_role')
        # 服务物料不给结构角色、实物物料给角色都放行
        self.svc.validate_item_write(
            {'item_type': 'service', 'structure_role': 'none'})
        self.svc.validate_item_write(
            {'item_type': 'goods', 'structure_role': 'model'})

    def test_r6_default_requires_optional(self):
        assert self._rule(dict(self.base, default_flag=True))[0] \
            == 'item_structure_line_default_requires_optional'

    def test_r5_qty_range(self):
        assert self._rule(dict(self.base, optional_flag=True,
                               min_qty=5, max_qty=2))[0] \
            == 'item_structure_line_qty_range'
        assert self._rule(dict(self.base, optional_flag=True, min_qty=5,
                               max_qty=9, default_qty=2))[0] \
            == 'item_structure_line_qty_range'
        assert self._rule(dict(self.base, optional_flag=True, min_qty=5,
                               max_qty=9, default_qty=10))[0] \
            == 'item_structure_line_qty_range'
        self.svc.validate_line_write(
            dict(self.base, optional_flag=True, min_qty=5, max_qty=9, default_qty=6))

    def test_r5_skipped_for_required_line(self):
        # R4：必选行忽略 min/max，不因区间反了就拒
        self.svc.validate_line_write(dict(self.base, min_qty=9, max_qty=2))

    def test_r8_substitute_anchor(self):
        self.conn.execute(
            "UPDATE item_structure_lines SET substitute_group_code='G1' WHERE id=1")
        assert self._rule(dict(self.base, structure_id=10, component_item_id=6,
                               substitute_group_code='G1'))[0] \
            == 'item_structure_substitute_anchor_duplicate'
        self.svc.validate_line_write(
            dict(self.base, structure_id=10, component_item_id=6,
                 substitute_group_code='G1', optional_flag=True))

    def test_s1_active_version_overlap(self):
        _add_structure(self.conn, 20, 1, status='active',
                       valid_from='2025-01-01', valid_to='2025-12-31')
        data = {'item_id': 1, 'usage': 'production', 'alternative_no': 1,
                'status': 'active', 'valid_from': '2025-06-01'}
        assert self._rule(data, header=True)[0] == 'item_structure_version_overlap'
        # 新版本从旧版本失效次日起 → 不重叠
        self.svc.validate_structure_write(
            {**data, 'valid_from': '2026-01-01'})
        # 草稿不占用生效窗口
        self.svc.validate_structure_write({**data, 'status': 'draft'})

    def test_s2_validity_inverted(self):
        data = {'item_id': 1, 'usage': 'production', 'alternative_no': 1,
                'status': 'draft', 'valid_from': '2026-06-01',
                'valid_to': '2026-05-31'}
        assert self._rule(data, header=True) == (
            'item_structure_validity_inverted', 'valid_to')
        # 同日、留空都表示不早于生效起
        self.svc.validate_structure_write({**data, 'valid_to': '2026-06-01'})
        self.svc.validate_structure_write({**data, 'valid_to': None})

    def test_s3_select_only_for_option_class(self):
        data = {'item_id': 1, 'usage': 'production', 'alternative_no': 1,
                'status': 'draft', 'valid_from': '2026-06-01'}
        # 标准件填选择数 → 拒
        assert self._rule({**data, 'min_select': 1}, header=True) == (
            'item_structure_select_requires_option_class', 'min_select')
        assert self._rule({**data, 'max_select': 2}, header=True) == (
            'item_structure_select_requires_option_class', 'max_select')
        # 选项类（物料 4）：区间自洽放行，min > max 拒
        opt = {**data, 'item_id': 4, 'min_select': 1, 'max_select': 2}
        self.svc.validate_structure_write(opt)
        assert self._rule({**opt, 'min_select': 3}, header=True) == (
            'item_structure_select_range', 'max_select')
        # 最多选择数不得超过现有结构行数
        _add_structure(self.conn, 60, 4)
        _add_line(self.conn, 90, 60, 1, 6, qty_per=1)
        assert self._rule({**opt, 'id': 60, 'max_select': 3}, header=True) == (
            'item_structure_select_exceeds_children', 'max_select')

    def test_d1_delete_guard(self):
        # 结构 10 仍有结构行 → 禁止删除
        with pytest.raises(ItemStructureGuardError) as e:
            self.svc.validate_structure_delete(10)
        assert e.value.rule == 'item_structure_in_use'
        # 结构 12 无行且为草稿 → 可删
        self.svc.validate_structure_delete(12)
        # 生效中的结构版本即使无行也不允许物理删除
        _add_structure(self.conn, 40, 1, status='active')
        with pytest.raises(ItemStructureGuardError) as e:
            self.svc.validate_structure_delete(40)
        assert e.value.rule == 'item_structure_in_use'

    def test_s1_update_excludes_self(self):
        _add_structure(self.conn, 20, 1, status='active',
                       valid_from='2025-01-01', valid_to='2025-12-31')
        self.svc.validate_structure_write(
            {'item_id': 1, 'usage': 'production', 'alternative_no': 1,
             'status': 'active', 'valid_from': '2025-01-01',
             'valid_to': '2025-12-31'}, exclude_id=20)

    def test_query_failure_fails_open(self):
        class _Broken:
            def query(self, sql, params=None):
                raise RuntimeError('db down')

        svc = ItemStructureGuardService(_Broken())
        svc.validate_line_write(dict(self.base, component_item_id=6))
        svc.validate_structure_write(
            {'item_id': 1, 'usage': 'production', 'alternative_no': 1,
             'status': 'active', 'valid_from': '2026-01-01'})
        svc.validate_structure_delete(10)
        svc.validate_item_write({'item_type': 'service', 'structure_role': 'none'})


# ─────────────────────────────────────────────────────────────────────────────
# 模型特征守卫（A1–A4）
# ─────────────────────────────────────────────────────────────────────────────

class TestAttributeGuard:
    def setup_method(self):
        self.conn = _new_db()
        _add_item(self.conn, 1, 'none')
        _add_item(self.conn, 3, 'model')
        _add_structure(self.conn, 10, 1)   # 标准件结构
        _add_structure(self.conn, 30, 3)   # 模型结构
        self._add_definition('paint_color', 'string', 1, 'active',
                             'list', 'color_enum')
        self._add_definition('shelf_life_days', 'integer', 1, 'active',
                             'range', '[0, 99999]')
        self._add_definition('is_fragile', 'boolean', 1, 'active')
        self._add_definition('legacy_note', 'string', 0, 'active')
        self._add_definition('inactive_attr', 'string', 1, 'inactive')
        self._add_definition('ship_date', 'date', 1, 'active')
        self._add_definition('tenant_only', 'string', 1, 'active', tenant_id=1)
        self.conn.execute(
            "INSERT INTO enum_values VALUES (1, 'color_enum', 'red', 1)")
        self.conn.execute(
            "INSERT INTO enum_values VALUES (2, 'color_enum', 'green', 0)")
        self.svc = ItemStructureGuardService(_SqliteDS(self.conn))

    def _add_definition(self, code, data_type, configurable, status,
                        domain_type=None, domain_ref=None, tenant_id=0):
        self.conn.execute(
            'INSERT INTO attribute_definitions (tenant_id, code, data_type, '
            'is_configurable, status, value_domain_type, value_domain_ref) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (tenant_id, code, data_type, configurable, status,
             domain_type, domain_ref))

    def _rule(self, data):
        with pytest.raises(ItemStructureGuardError) as e:
            self.svc.validate_attribute_write(data)
        return e.value.rule, e.value.field_name

    def test_a1_requires_model(self):
        assert self._rule({'structure_id': 10, 'attribute_code': 'paint_color'}) \
            == ('item_structure_attribute_requires_model', 'structure_id')
        self.svc.validate_attribute_write(
            {'structure_id': 30, 'attribute_code': 'paint_color'})

    def test_a2_code_must_exist_in_platform_layer(self):
        assert self._rule({'structure_id': 30, 'attribute_code': 'missing'}) \
            == ('item_structure_attribute_code_not_found', 'attribute_code')
        # 租户层定义不得进结构版本
        assert self._rule({'structure_id': 30, 'attribute_code': 'tenant_only'}) \
            == ('item_structure_attribute_code_not_found', 'attribute_code')

    def test_a2_must_be_configurable_and_active(self):
        assert self._rule({'structure_id': 30, 'attribute_code': 'legacy_note'}) \
            == ('item_structure_attribute_not_configurable', 'attribute_code')
        assert self._rule({'structure_id': 30, 'attribute_code': 'inactive_attr'}) \
            == ('item_structure_attribute_not_configurable', 'attribute_code')

    def test_a3_type_must_be_configurable(self):
        assert self._rule({'structure_id': 30, 'attribute_code': 'ship_date'}) \
            == ('item_structure_attribute_type_unsupported', 'attribute_code')

    def test_a4_list_domain_default(self):
        self.svc.validate_attribute_write(
            {'structure_id': 30, 'attribute_code': 'paint_color',
             'default_value_text': 'red'})
        assert self._rule({'structure_id': 30, 'attribute_code': 'paint_color',
                           'default_value_text': 'blue'}) \
            == ('item_structure_attribute_default_invalid', 'default_value_text')
        # 停用的枚举值不算有效默认值
        assert self._rule({'structure_id': 30, 'attribute_code': 'paint_color',
                           'default_value_text': 'green'}) \
            == ('item_structure_attribute_default_invalid', 'default_value_text')

    def test_a4_range_and_type_parsing(self):
        self.svc.validate_attribute_write(
            {'structure_id': 30, 'attribute_code': 'shelf_life_days',
             'default_value_text': '30'})
        for bad in ('100000', '1.5', 'abc'):
            assert self._rule({'structure_id': 30,
                               'attribute_code': 'shelf_life_days',
                               'default_value_text': bad}) \
                == ('item_structure_attribute_default_invalid',
                    'default_value_text')
        self.svc.validate_attribute_write(
            {'structure_id': 30, 'attribute_code': 'is_fragile',
             'default_value_text': 'yes'})
        assert self._rule({'structure_id': 30, 'attribute_code': 'is_fragile',
                           'default_value_text': 'maybe'}) \
            == ('item_structure_attribute_default_invalid', 'default_value_text')

    def test_blank_default_passes(self):
        self.svc.validate_attribute_write(
            {'structure_id': 30, 'attribute_code': 'shelf_life_days',
             'default_value_text': None})

    def test_query_failure_fails_open(self):
        class _Broken:
            def query(self, sql, params=None):
                raise RuntimeError('db down')

        ItemStructureGuardService(_Broken()).validate_attribute_write(
            {'structure_id': 30, 'attribute_code': 'paint_color'})


# ─────────────────────────────────────────────────────────────────────────────
# 展开
# ─────────────────────────────────────────────────────────────────────────────

class TestExplode:
    def setup_method(self):
        self.conn = _new_db()
        for iid in (1, 2, 3, 4, 5):
            _add_item(self.conn, iid)
        # 100：父项 1，虚拟件 2 + 普通件 3 + 可选项 5
        _add_structure(self.conn, 100, 1, status='active')
        _add_line(self.conn, 11, 100, 10, 2, qty_per=2, phantom_flag=1)
        _add_line(self.conn, 12, 100, 20, 3, qty_per=3)
        _add_line(self.conn, 13, 100, 30, 5, qty_per=1, optional_flag=1)
        # 200：虚拟件 2 的结构，含组件 4
        _add_structure(self.conn, 200, 2, status='active')
        _add_line(self.conn, 21, 200, 1, 4, qty_per=4)
        self.svc = ItemStructureExplodeService(_SqliteDS(self.conn))

    def test_phantom_penetration_and_qty(self):
        result = self.svc.explode_structure(100, qty=2, as_of='2026-06-01')
        rows = {r['path']: r for r in result['lines']}
        assert set(rows) == {'10.1', '20'}
        assert rows['10.1']['component_item_id'] == 4
        assert rows['10.1']['total_qty'] == pytest.approx(16)  # 2 × 2 × 4
        assert rows['20']['total_qty'] == pytest.approx(6)     # 2 × 3
        assert result['skipped_optional'] == 1

    def test_include_optional(self):
        result = self.svc.explode_structure(
            100, qty=1, include_optional=True, as_of='2026-06-01')
        assert {r['component_item_id'] for r in result['lines']} == {3, 4, 5}
        assert result['skipped_optional'] == 0

    def test_fixed_qty_not_scaled(self):
        self.conn.execute("UPDATE item_structure_lines SET fixed_qty=5 WHERE id=12")
        result = self.svc.explode_structure(100, qty=3, as_of='2026-06-01')
        row = [r for r in result['lines'] if r['component_item_id'] == 3][0]
        assert row['total_qty'] == pytest.approx(5)

    def test_line_date_window(self):
        self.conn.execute(
            "UPDATE item_structure_lines SET valid_to='2025-12-31' WHERE id=12")
        result = self.svc.explode_structure(100, qty=1, as_of='2026-06-01')
        assert 3 not in [r['component_item_id'] for r in result['lines']]

    def test_cycle_detected(self):
        # 让 4 成为虚拟件，才会继续穿透到结构 300（其行指回父项 1）
        self.conn.execute(
            "UPDATE item_structure_lines SET phantom_flag=1 WHERE id=21")
        _add_structure(self.conn, 300, 4, status='active')
        _add_line(self.conn, 31, 300, 1, 1, qty_per=1)
        with pytest.raises(ItemStructureExplodeError) as e:
            self.svc.explode_structure(100, qty=1, as_of='2026-06-01')
        assert e.value.rule == 'item_structure_cycle'

    def test_phantom_without_structure_kept_as_leaf(self):
        self.conn.execute("UPDATE item_structure_lines SET phantom_flag=0 WHERE id=11")
        _add_line(self.conn, 14, 100, 40, 9, qty_per=1, phantom_flag=1)
        result = self.svc.explode_structure(100, qty=1, as_of='2026-06-01')
        assert any(w['rule'] == 'item_structure_phantom_without_structure'
                   for w in result['warnings'])
        assert 9 in [r['component_item_id'] for r in result['lines']]

    def test_explode_item_resolves_active_version(self):
        result = self.svc.explode_item(1, as_of='2026-06-01')
        assert result['structure_id'] == 100
        with pytest.raises(ItemStructureExplodeError) as e:
            self.svc.explode_item(5, as_of='2026-06-01')
        assert e.value.rule == 'item_structure_no_active_version'

    def test_missing_structure(self):
        with pytest.raises(ItemStructureExplodeError) as e:
            self.svc.explode_structure(999)
        assert e.value.rule == 'item_structure_not_found'

    def test_base_qty_scaling(self):
        # 结构头基准 2：原料 3 用量 → 需求 2 件时 2 × 3 / 2 = 3
        self.conn.execute("UPDATE item_structures SET base_qty=2 WHERE id=100")
        result = self.svc.explode_structure(100, qty=2, as_of='2026-06-01')
        rows = {r['path']: r for r in result['lines']}
        assert rows['20']['total_qty'] == pytest.approx(3)
        # 虚拟件穿透后的下层结构按自身 base_qty 再缩放
        assert rows['10.1']['total_qty'] == pytest.approx(8)

    def test_inactive_component_warns(self):
        self.conn.execute("UPDATE items SET status='inactive' WHERE id=3")
        result = self.svc.explode_structure(100, qty=1, as_of='2026-06-01')
        assert any(w['rule'] == 'item_structure_component_inactive'
                   and w['line_no'] == 20 for w in result['warnings'])
        assert 3 in [r['component_item_id'] for r in result['lines']]

    def test_missing_component_warns(self):
        self.conn.execute("DELETE FROM items WHERE id=3")
        result = self.svc.explode_structure(100, qty=1, as_of='2026-06-01')
        assert any(w['rule'] == 'item_structure_component_missing'
                   and w['component_item_id'] == 3 for w in result['warnings'])
        assert 3 in [r['component_item_id'] for r in result['lines']]

    def test_ambiguous_active_version(self):
        _add_structure(self.conn, 110, 1, status='active')
        with pytest.raises(ItemStructureExplodeError) as e:
            self.svc.explode_item(1, as_of='2026-06-01')
        assert e.value.rule == 'item_structure_version_ambiguous'

    def test_substitute_group_metadata(self):
        self.conn.execute(
            "UPDATE item_structure_lines SET substitute_group_code='G1' "
            "WHERE id IN (12, 13)")
        result = self.svc.explode_structure(100, qty=1, as_of='2026-06-01')
        # 可选替代行随锚点进 substitutes，不计入 skipped_optional
        assert result['skipped_optional'] == 0
        assert len(result['substitutes']) == 1
        sub = result['substitutes'][0]
        assert (sub['path'], sub['group_code']) == ('20', 'G1')
        assert [c['component_item_id'] for c in sub['components']] == [5]

    def test_non_production_usage_returns_empty(self):
        result = self.svc.explode_item(1, usage='sales', as_of='2026-06-01')
        assert result['structure_id'] is None
        assert result['lines'] == []
        assert any(w['rule'] == 'item_structure_usage_not_enabled'
                   for w in result['warnings'])


# ─────────────────────────────────────────────────────────────────────────────
# 手工选择（P2 验收：四选一选项类与必选件混排）
# ─────────────────────────────────────────────────────────────────────────────

class TestManualSelect:
    def setup_method(self):
        self.conn = _new_db()
        _add_item(self.conn, 1, 'model')            # 模型（根）
        _add_item(self.conn, 10)                    # 必选标准件
        _add_item(self.conn, 20, 'option_class')    # 四选一选项类
        for iid in (21, 22, 23, 24):
            _add_item(self.conn, iid)
        # 100：模型 = 必选标准件 + 必选选项类容器
        _add_structure(self.conn, 100, 1)
        _add_line(self.conn, 1, 100, 1, 10, qty_per=1)
        _add_line(self.conn, 2, 100, 2, 20, qty_per=1)
        # 200：选项类 四选一
        _add_structure(self.conn, 200, 20, status='active',
                       min_select=1, max_select=1)
        _add_line(self.conn, 11, 200, 1, 21, qty_per=1, optional_flag=1)
        _add_line(self.conn, 12, 200, 2, 22, qty_per=1, optional_flag=1)
        _add_line(self.conn, 13, 200, 3, 23, qty_per=1, optional_flag=1)
        _add_line(self.conn, 14, 200, 4, 24, qty_per=1, optional_flag=1)
        self.svc = ItemStructureSelectService(_SqliteDS(self.conn))

    def _rule(self, *args, **kwargs):
        with pytest.raises(ItemStructureSelectError) as e:
            self.svc.select(*args, **kwargs)
        return e.value.rule, e.value.field_name

    def test_four_choose_one_acceptance(self):
        # 必选标准件 + 选中子项；选项类物料本身不出组件，容器路径作前缀
        result = self.svc.select(100, selections={11})
        assert [(c['component_key'], c['component_item_id'])
                for c in result['components']] == [
                    ('L0001', 10), ('L0002.L0001', 21)]
        assert all(c['parent_component_key'] is None
                   for c in result['components'])
        sources = {c['component_item_id']: c['selection_source']
                   for c in result['components']}
        assert sources == {10: 'auto', 21: 'user'}
        assert result['skipped_optional'] == 3
        assert 20 not in {c['component_item_id'] for c in result['components']}

    def test_selection_as_list(self):
        result = self.svc.select(100, selections=[12])
        assert [c['component_item_id'] for c in result['components']] == [10, 22]

    def test_cardinality_too_few(self):
        assert self._rule(100, selections=[]) == (
            'item_structure_select_too_few', 'selections')

    def test_cardinality_too_many(self):
        assert self._rule(100, selections={11, 12}) == (
            'item_structure_select_too_many', 'selections')

    def test_default_child_counts_toward_cardinality(self):
        self.conn.execute(
            "UPDATE item_structure_lines SET default_flag=1 WHERE id=13")
        result = self.svc.select(100)
        assert [(c['component_item_id'], c['selection_source'])
                for c in result['components']] == [(10, 'auto'), (23, 'auto')]

    def test_required_child_always_chosen(self):
        # 选项类内的必选子项恒被选中，显式取消无效；基数按 1 计
        self.conn.execute(
            "UPDATE item_structure_lines SET optional_flag=0 WHERE id=12")
        self.conn.execute(
            "UPDATE item_structures SET max_select=2 WHERE id=200")
        result = self.svc.select(100, selections={12: False})
        assert [c['component_item_id'] for c in result['components']] == [10, 22]

    def test_required_standard_line_not_deselectable(self):
        result = self.svc.select(100, selections={1: False, 11: True})
        assert 10 in [c['component_item_id'] for c in result['components']]

    def test_explicit_qty_must_be_in_range(self):
        self.conn.execute(
            "UPDATE item_structure_lines SET min_qty=2, max_qty=5 WHERE id=11")
        assert self._rule(100, selections={11}, quantities={11: 6}) == (
            'item_structure_select_qty_range', 'quantities')
        assert self._rule(100, selections={11}, quantities={11: 1}) == (
            'item_structure_select_qty_range', 'quantities')
        result = self.svc.select(100, selections={11}, quantities={11: 3})
        row = [c for c in result['components'] if c['component_item_id'] == 21][0]
        assert row['qty'] == pytest.approx(3)

    def test_default_qty_used(self):
        self.conn.execute(
            "UPDATE item_structure_lines SET default_qty=2 WHERE id=11")
        result = self.svc.select(100, selections={11})
        row = [c for c in result['components'] if c['component_item_id'] == 21][0]
        assert row['qty'] == pytest.approx(2)

    def test_qty_scaling(self):
        result = self.svc.select(100, selections={11}, qty=2)
        qty = {c['component_item_id']: c['qty'] for c in result['components']}
        assert qty[10] == pytest.approx(2)
        assert qty[21] == pytest.approx(2)

    def test_fixed_qty_not_scaled(self):
        self.conn.execute(
            "UPDATE item_structure_lines SET fixed_qty=5, qty_per=NULL WHERE id=1")
        result = self.svc.select(100, selections={11}, qty=3)
        row = [c for c in result['components'] if c['component_item_id'] == 10][0]
        assert row['qty'] == pytest.approx(5)

    def test_unknown_selection_line(self):
        # 基数满足后才暴露「行不在本次可选集」的入参错误
        assert self._rule(100, selections={11, 99}) == (
            'item_structure_select_line_unknown', 'selections')

    def test_child_of_unselected_container_rejected(self):
        # 未选中选项类时，其子项不在可选集内
        _add_item(self.conn, 30, 'option_class')
        _add_item(self.conn, 31)
        _add_structure(self.conn, 300, 30, status='active',
                       min_select=1, max_select=1)
        _add_line(self.conn, 31, 300, 1, 31, qty_per=1, optional_flag=1)
        _add_line(self.conn, 3, 100, 3, 30, qty_per=1, optional_flag=1)
        assert self._rule(100, selections={11, 31}) == (
            'item_structure_select_line_unknown', 'selections')

    def test_missing_component_warns(self):
        self.conn.execute("DELETE FROM items WHERE id=10")
        result = self.svc.select(100, selections={11})
        assert any(w['rule'] == 'item_structure_component_missing'
                   and w['component_item_id'] == 10 for w in result['warnings'])
        assert 10 in [c['component_item_id'] for c in result['components']]

    def test_inactive_component_warns(self):
        self.conn.execute("UPDATE items SET status='inactive' WHERE id=10")
        result = self.svc.select(100, selections={11})
        assert any(w['rule'] == 'item_structure_component_inactive'
                   and w['component_item_id'] == 10 for w in result['warnings'])

    def test_cycle_detected(self):
        # 选项类 20 内再挂 20 自身（必选行使之必被遍历）
        _add_line(self.conn, 15, 200, 5, 20, qty_per=1)
        self.conn.execute(
            "UPDATE item_structures SET max_select=2 WHERE id=200")
        assert self._rule(100, selections={11}) == (
            'item_structure_cycle', 'component_item_id')

    def test_option_class_missing_structure(self):
        _add_item(self.conn, 25, 'option_class')
        _add_structure(self.conn, 101, 1)
        _add_line(self.conn, 20, 101, 1, 25, qty_per=1)
        assert self._rule(101) == (
            'item_structure_option_class_missing_structure', 'component_item_id')

    def test_ambiguous_option_class_version(self):
        _add_structure(self.conn, 201, 20, status='active',
                       min_select=1, max_select=1)
        assert self._rule(100, selections={11}) == (
            'item_structure_version_ambiguous', 'structure_id')

    def test_max_depth(self):
        assert self._rule(100, selections={11}, max_depth=1) == (
            'item_structure_max_depth_exceeded', 'structure_id')

    def test_structure_not_found(self):
        assert self._rule(999) == (
            'item_structure_not_found', 'structure_id')

    def test_attribute_required(self):
        self.conn.execute(
            'INSERT INTO item_structure_attributes (structure_id, attribute_code, '
            'required_flag, seq) VALUES (100, ?, 1, 1)', ('paint_color',))
        assert self._rule(100, selections={11}) == (
            'item_structure_attribute_required', 'attribute_values')

    def test_attribute_default_and_override(self):
        self.conn.execute(
            'INSERT INTO item_structure_attributes (structure_id, attribute_code, '
            'required_flag, default_value_text, seq) '
            'VALUES (100, ?, 1, ?, 1)', ('paint_color', 'red'))
        result = self.svc.select(100, selections={11})
        assert result['values'] == [{'attribute_code': 'paint_color',
                                     'value_text': 'red', 'source': 'default'}]
        result = self.svc.select(100, selections={11},
                                 attribute_values={'paint_color': 'blue'})
        assert result['values'] == [{'attribute_code': 'paint_color',
                                     'value_text': 'blue', 'source': 'user'}]

    def test_attribute_only_for_model(self):
        # 选项类结构不声明特征：即使表中有行也忽略
        self.conn.execute(
            'INSERT INTO item_structure_attributes (structure_id, attribute_code, '
            'required_flag, seq) VALUES (200, ?, 1, 1)', ('paint_color',))
        result = self.svc.select(100, selections={11})
        assert result['values'] == []


# ─────────────────────────────────────────────────────────────────────────────
# 拦截器接线
# ─────────────────────────────────────────────────────────────────────────────

class TestInterceptor:
    def _ctx(self, object_id, action='crud_create', params=None, old=None, oid=None):
        return SimpleNamespace(
            meta_object=SimpleNamespace(id=object_id),
            action=action,
            params=params or {},
            old_data=old or {},
            object_id=oid,
            data_source=None,
        )

    def test_priority_and_short_circuit(self):
        ic = ItemStructureGuardInterceptor()
        assert ic.priority == 46
        assert ic.should_execute(
            self._ctx('item_structure_line', 'crud_create')) is True
        assert ic.should_execute(self._ctx('item', 'crud_create')) is True
        assert ic.should_execute(
            self._ctx('item_structure', 'crud_delete')) is True
        assert ic.should_execute(
            self._ctx('item_structure_line', 'crud_delete')) is True
        assert ic.should_execute(
            self._ctx('item_structure_attribute', 'crud_create')) is True
        assert ic.should_execute(
            self._ctx('item_structure_attribute', 'crud_update')) is True
        assert ic.should_execute(
            self._ctx('item_structure_attribute', 'crud_delete')) is False
        assert ic.should_execute(self._ctx('item', 'crud_delete')) is False
        assert ic.should_execute(self._ctx('item_structure_line', 'crud_list')) is False

    def _wire(self):
        conn = _new_db()
        _add_item(conn, 1)
        _add_item(conn, 2)
        _add_structure(conn, 10, 1)
        return conn

    def test_update_merges_old_data(self):
        conn = self._wire()
        ic = ItemStructureGuardInterceptor()
        ctx = self._ctx('item_structure_line', 'crud_update',
                        params={'qty_per': 2},
                        old={'id': 1, 'structure_id': 10,
                             'component_item_id': 2, 'fixed_qty': None},
                        oid=1)
        ctx.data_source = _SqliteDS(conn)
        ic.before_action(ctx)  # 合并后 qty_per=2、fixed_qty=None → 放行

    def test_rejection_maps_to_validation_error(self):
        conn = self._wire()
        ic = ItemStructureGuardInterceptor()
        ctx = self._ctx('item_structure_line', 'crud_create',
                        params={'structure_id': 10, 'component_item_id': 2,
                                'line_no': 1})
        ctx.data_source = _SqliteDS(conn)
        with pytest.raises(ValidationFailedError):
            ic.before_action(ctx)

    def test_item_write_maps_to_validation_error(self):
        ic = ItemStructureGuardInterceptor()
        ctx = self._ctx('item', 'crud_create',
                        params={'item_type': 'service',
                                'structure_role': 'model'})
        ctx.data_source = _SqliteDS(_new_db())
        with pytest.raises(ValidationFailedError):
            ic.before_action(ctx)

    def test_delete_guard_via_interceptor(self):
        conn = self._wire()
        ic = ItemStructureGuardInterceptor()
        ctx = self._ctx('item_structure', 'crud_delete', oid=10)
        ctx.data_source = _SqliteDS(conn)
        ic.before_action(ctx)  # 草稿且无行 → 放行
        _add_line(conn, 1, 10, 1, 2, qty_per=1)
        with pytest.raises(ValidationFailedError):
            ic.before_action(ctx)

    def test_attribute_write_maps_to_validation_error(self):
        conn = self._wire()
        ic = ItemStructureGuardInterceptor()
        # 结构 10 的父项角色是 none：不允许声明模型特征
        ctx = self._ctx('item_structure_attribute', 'crud_create',
                        params={'structure_id': 10,
                                'attribute_code': 'paint_color'})
        ctx.data_source = _SqliteDS(conn)
        with pytest.raises(ValidationFailedError) as e:
            ic.before_action(ctx)
        assert e.value.details[0]['rule'] == \
            'item_structure_attribute_requires_model'
