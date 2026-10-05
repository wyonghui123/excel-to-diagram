# -*- coding: utf-8 -*-
"""F4 · 行政区划字典（region）落地测试 (2026-10-05)

依据: docs/superpowers/specs/2026-10-05-region-dictionary-design.md
      （§3 region 对象设计 / §6 测试计划；上游蓝图 v2.5 §3.8 / §5.4 / §7 步 7）

覆盖（设计 §6.1 六组）:
1. 结构     : 字段集合 / level 枚举 4 值 / indexes / restrict_on / 无 key_template
2. 树语义   : parent_id 语义（parent_key / self_reference）+ 树形 value_help
3. 建表端到端: sync_schema_from_meta 建表 + 四级链（含直辖市伪节点链）
4. 接线     : address 四 FK parameter_bindings + cascade_select 三链
5. 级联语义 : BoValueHelpProvider.search 父级+层级过滤只返回子集
6. 种子幂等 : 跑两次行数不变、重复 code 走 UPDATE、父链闭合

测试隔离: temp DB（get_data_source）+ sync_schema_from_meta; 不触碰 architecture.db;
         DML 走 ds.insert API（本文件无裸写语句 —— conftest raw-SQL 守卫）
"""
import os
import sys

import pytest

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
def _load_yaml(filename='region.yaml'):
    import yaml
    with open(os.path.join(_SCHEMA_DIR, filename), 'r',
              encoding='utf-8') as f:
        return yaml.safe_load(f)


def _fields(filename='region.yaml'):
    return {f['id']: f for f in _load_yaml(filename)['fields']}


def _get_id(ds, code):
    rows = ds.query("SELECT id FROM regions WHERE code = ?", (code,))
    assert rows, '区划不存在: %s' % code
    return rows[0]['id']


def _insert(ds, code, name, parent_code=None, level='province'):
    parent_id = None
    if parent_code is not None:
        parent_id = _get_id(ds, parent_code)
    ds.insert('regions', {
        'code': code,
        'name': name,
        'parent_id': parent_id,
        'level': level,
    })


def _level_counts(ds):
    rows = ds.query(
        "SELECT level, COUNT(*) AS n FROM regions GROUP BY level")
    return {r['level']: r['n'] for r in rows}


# ────────────────────────────────────────
# 1a. 命名三面（界面词 / 技术标识 / 物理表）
# ────────────────────────────────────────
class TestNaming:
    def test_interface_word(self):
        assert _load_yaml()['name'] == '行政区划'

    def test_technical_id_and_table(self):
        data = _load_yaml()
        assert data['id'] == 'region'
        assert data['table_name'] == 'regions'


# ────────────────────────────────────────
# 1b. 结构（设计 §3.1 / §3.2）
# ────────────────────────────────────────
class TestStructure:
    def test_core_fields(self):
        fields = _fields()
        for fid in ('id', 'code', 'name', 'parent_id', 'level', 'status'):
            assert fid in fields, '结构字段缺失: %s' % fid

    def test_code_required_unique(self):
        f = _fields()['code']
        assert f['required'] is True
        assert f['unique'] is True
        assert f['max_length'] == 20
        assert f['semantics'].get('business_key') is True

    def test_no_key_template(self):
        """业务键=国标代码 ⇒ 不启用 key_template（设计 §3.1）"""
        kt = _load_yaml().get('key_template') or {}
        assert not kt.get('enabled')

    def test_level_enum_four_values(self):
        f = _fields()['level']
        assert f['required'] is True
        assert {e['value'] for e in f['enum_values']} == {
            'country', 'province', 'city', 'district'}
        assert f['ui']['widget'] == 'select'

    def test_status_default_active(self):
        f = _fields()['status']
        assert f['default'] == 'active'
        assert f['required'] is True
        assert {e['value'] for e in f['enum_values']} == {'active', 'inactive'}

    def test_audit_and_semantics(self):
        data = _load_yaml()
        assert 'audit_aspect' in (data.get('aspects') or [])
        assert (data.get('audit') or {}).get('enabled') is True
        assert data['semantics']['business_key'] == ['code']
        assert data['semantics']['category'] == 'core_entity'
        assert data['display_name_field'] == 'name'

    def test_indexes(self):
        by_fields = {tuple(i['fields']): i for i in _load_yaml()['indexes']}
        assert by_fields[('code',)].get('unique') is True
        assert ('parent_id',) in by_fields
        assert ('level',) in by_fields
        assert ('status',) in by_fields

    def test_deletion_policy_restrict_on(self):
        """子区划 + address 四 FK 引用时禁删（机制: deletion_service 消费 restrict_on）"""
        dp = _load_yaml().get('deletion_policy') or {}
        assert dp.get('mode') == 'restrict'
        entries = {(r['table'], r['foreign_key'])
                   for r in dp.get('restrict_on') or []}
        assert ('regions', 'parent_id') in entries
        for fk in ('country_id', 'province_id', 'city_id', 'district_id'):
            assert ('addresses', fk) in entries, '缺 restrict: addresses.%s' % fk


# ────────────────────────────────────────
# 1c. 树语义（设计 §3.3 / §3.4；对照 org.yaml L151-204 先例）
# ────────────────────────────────────────
class TestTreeSemantics:
    def test_parent_semantics(self):
        f = _fields()['parent_id']
        sem = f['semantics']
        assert sem.get('parent_key') is True
        assert sem.get('hierarchy_field') == 'parent'
        assert sem['hierarchy_level']['relation'] == 'self_reference'
        assert sem['display']['target_type'] == 'region'
        assert sem['display']['display_field'] == 'name'

    def test_parent_value_help_tree(self):
        vh = _fields()['parent_id']['value_help']
        assert vh['source']['type'] == 'bo'
        assert vh['source']['target_bo'] == 'region'
        assert vh['source']['hierarchy']['enabled'] is True
        assert vh['source']['hierarchy']['parent_field'] == 'parent_id'
        assert vh['behavior']['exclude_self'] is True
        assert vh['presentation']['display_mode'] == 'tree'
        assert vh['presentation']['result_type'] == 'dialog'

    def test_parent_ui_select(self):
        f = _fields()['parent_id']
        assert f['ui']['widget'] == 'select'
        assert f['ui']['clearable'] is True


# ────────────────────────────────────────
# 夹具（建表）
# ────────────────────────────────────────
@pytest.fixture()
def region_ds(tmp_path):
    """临时库: 仅建 regions 表 + 索引（aspects 按平台路径解析）"""
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'region.yaml'),
                         aspects_defs=aspects)
    assert obj is not None, 'region.yaml 加载失败'

    ds = get_data_source("sqlite", database=str(tmp_path / 'f4_region.db'))
    sync_schema_from_meta(ds, [obj])
    yield ds
    _clear_data_source_cache_for_testing()


# ────────────────────────────────────────
# 3. 建表端到端（含直辖市伪节点链）
# ────────────────────────────────────────
class TestBuildAndTree:
    def test_table_created(self, region_ds):
        names = {r[0] for r in region_ds.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert 'regions' in names

    def test_code_unique_index_created(self, region_ds):
        names = {r[1] for r in region_ds.execute(
            "PRAGMA index_list('regions')").fetchall()}
        assert 'idx_region_code' in names

    def test_duplicate_code_rejected(self, region_ds):
        _insert(region_ds, 'CN', '中国', level='country')
        with pytest.raises(Exception):
            _insert(region_ds, 'CN', '中国（重复）', level='country')

    def test_four_level_chain(self, region_ds):
        """CN → 110000 → 110100（市辖区伪节点）→ 110101"""
        _insert(region_ds, 'CN', '中国', level='country')
        _insert(region_ds, '110000', '北京市', 'CN', level='province')
        _insert(region_ds, '110100', '市辖区', '110000', level='city')
        _insert(region_ds, '110101', '东城区', '110100', level='district')

        row = region_ds.query(
            "SELECT p.code AS pcode FROM regions r "
            "LEFT JOIN regions p ON r.parent_id = p.id "
            "WHERE r.code = ?", ('110101',))[0]
        assert row['pcode'] == '110100'

        children = region_ds.query(
            "SELECT code FROM regions WHERE parent_id = ? AND level = 'city'",
            (_get_id(region_ds, '110000'),))
        assert {r['code'] for r in children} == {'110100'}


# ────────────────────────────────────────
# 6. 种子幂等（设计 §5 / §6.1）
# ────────────────────────────────────────
class TestSeedIdempotent:
    def test_seed_counts(self, region_ds):
        from meta.scripts.init_region_seed import init_region_seed_data
        inserted, updated = init_region_seed_data(region_ds)
        assert (inserted, updated) == (282, 0)
        counts = _level_counts(region_ds)
        assert counts['country'] == 4
        assert counts['province'] == 34
        assert counts['city'] == 31
        assert counts['district'] >= 175
        total = region_ds.query(
            "SELECT COUNT(*) AS n FROM regions")[0]['n']
        assert total == 282

    def test_seed_parent_chain_closed(self, region_ds):
        from meta.scripts.init_region_seed import init_region_seed_data
        init_region_seed_data(region_ds)
        sql = (
            "SELECT c.code AS ccode, p.code AS pcode "
            "FROM regions c JOIN regions p ON c.parent_id = p.id "
            "WHERE c.code IN ('110000', '110100', '110101')")
        parents = {r['ccode']: r['pcode'] for r in region_ds.query(sql)}
        assert parents == {'110000': 'CN', '110100': '110000',
                           '110101': '110100'}

    def test_seed_municipality_min_samples(self, region_ds):
        from meta.scripts.init_region_seed import init_region_seed_data
        init_region_seed_data(region_ds)
        for city_code, lower in (('110100', 16), ('120100', 16),
                                 ('310100', 16), ('500100', 38),
                                 ('440100', 11), ('540100', 3)):
            n = region_ds.query(
                "SELECT COUNT(*) AS n FROM regions WHERE parent_id = ?",
                (_get_id(region_ds, city_code),))[0]['n']
            assert n >= lower, '%s 子区县样本不足: %d' % (city_code, n)

    def test_seed_idempotent_second_run(self, region_ds):
        from meta.scripts.init_region_seed import init_region_seed_data
        init_region_seed_data(region_ds)
        inserted, updated = init_region_seed_data(region_ds)
        assert inserted == 0 and updated == 282
        total = region_ds.query(
            "SELECT COUNT(*) AS n FROM regions")[0]['n']
        assert total == 282

    def test_seed_codes_unique(self, region_ds):
        from meta.scripts.init_region_seed import init_region_seed_data
        init_region_seed_data(region_ds)
        row = region_ds.query(
            "SELECT COUNT(*) AS total, COUNT(DISTINCT code) AS uniq "
            "FROM regions")[0]
        assert row['total'] == row['uniq']


# ────────────────────────────────────────
# 夹具（双表 + 注册 + 数据源注入）
# ────────────────────────────────────────
@pytest.fixture()
def cascade_ds(tmp_path):
    """临时库: regions + addresses 双表 + 区划样本; 注入 query_service 数据源

    注意: MetaRegistry 单例无 unregister ⇒ 幂等覆盖注册（同 YAML 等价对象）;
    _data_source_instance 为模块级全局 ⇒ teardown 必须复位 None。
    """
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.models import MetaRegistry
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml
    from meta.services import query_service

    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    region_obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'region.yaml'),
                                aspects_defs=aspects)
    addr_obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'address.yaml'),
                              aspects_defs=aspects)
    ds = get_data_source("sqlite", database=str(tmp_path / 'f4_cascade.db'))
    sync_schema_from_meta(ds, [region_obj, addr_obj])

    MetaRegistry().register(region_obj)

    _insert(ds, 'CN', '中国', level='country')
    _insert(ds, '110000', '北京市', 'CN', level='province')
    _insert(ds, '110100', '市辖区', '110000', level='city')
    _insert(ds, '110101', '东城区', '110100', level='district')
    _insert(ds, '330000', '浙江省', 'CN', level='province')
    _insert(ds, '330100', '杭州市', '330000', level='city')
    _insert(ds, '330102', '上城区', '330100', level='district')

    query_service._data_source_instance = ds
    yield ds
    query_service._data_source_instance = None
    _clear_data_source_cache_for_testing()


# ────────────────────────────────────────
# 4. 接线（设计 §4.2 / §4.3 / §6.1）: address 四 FK
# ────────────────────────────────────────
class TestAddressWiring:
    def test_country_id_constant_binding(self):
        """country_id: 无父字段, 仅靠 constant 锁定 level=country"""
        f = _fields('address.yaml')['country_id']
        pbs = f['value_help']['behavior']['parameter_bindings']
        assert {'target_field': 'level', 'constant': 'country'} in pbs

    def test_province_id_bindings(self):
        f = _fields('address.yaml')['province_id']
        pbs = f['value_help']['behavior']['parameter_bindings']
        assert {'local_field': 'country_id', 'target_field': 'parent_id',
                'required': True} in pbs
        assert {'target_field': 'level', 'constant': 'province'} in pbs

    def test_city_id_bindings(self):
        f = _fields('address.yaml')['city_id']
        pbs = f['value_help']['behavior']['parameter_bindings']
        assert {'local_field': 'province_id', 'target_field': 'parent_id',
                'required': True} in pbs
        assert {'target_field': 'level', 'constant': 'city'} in pbs

    def test_district_id_bindings(self):
        f = _fields('address.yaml')['district_id']
        pbs = f['value_help']['behavior']['parameter_bindings']
        assert {'local_field': 'city_id', 'target_field': 'parent_id',
                'required': True} in pbs
        assert {'target_field': 'level', 'constant': 'district'} in pbs

    def test_cascade_select_chains(self):
        """BO 顶层三链: 父字段变更清下游（设计 §4.3）"""
        chains = {c['field']: (c['parent_object'], c['filter_by'])
                  for c in _load_yaml('address.yaml')['cascade_select']}
        assert chains == {
            'province_id': ('region', 'country_id'),
            'city_id': ('region', 'province_id'),
            'district_id': ('region', 'city_id'),
        }


# ────────────────────────────────────────
# 5. 级联语义（设计 §6.1）: provider 过滤只返回子集
# ────────────────────────────────────────
class TestCascadeSemantics:
    @staticmethod
    def _provider():
        from meta.core.models_value_help import ValueHelpSource
        from meta.core.value_help_providers import BoValueHelpProvider
        return BoValueHelpProvider(ValueHelpSource(
            type='bo', target_bo='region', value_field='id',
            display_field='name', code_field='code',
            apply_target_permissions=False))

    def test_region_registered(self, cascade_ds):
        from meta.core.yaml_loader import get_meta_object
        assert get_meta_object('region') is not None

    def test_filter_by_parent_and_level(self, cascade_ds):
        result = self._provider().search(
            '', [],
            {'parent_id': _get_id(cascade_ds, '110000'), 'level': 'city'},
            page=1, page_size=50, sort=[])
        codes = {item['code'] for item in result['data']}
        assert codes == {'110100'}

    def test_filter_isolates_subtree(self, cascade_ds):
        result = self._provider().search(
            '', [],
            {'parent_id': _get_id(cascade_ds, 'CN'), 'level': 'province'},
            page=1, page_size=50, sort=[])
        codes = {item['code'] for item in result['data']}
        assert codes == {'110000', '330000'}

    def test_level_constant_only(self, cascade_ds):
        """country_id 场景: 仅 level=country 常量"""
        result = self._provider().search(
            '', [], {'level': 'country'},
            page=1, page_size=50, sort=[])
        codes = {item['code'] for item in result['data']}
        assert codes == {'CN'}