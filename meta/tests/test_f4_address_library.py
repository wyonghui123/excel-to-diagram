# -*- coding: utf-8 -*-
"""F4 · 地址库（address）落地测试 (2026-10-05)

依据: 蓝图 v2.5 §3.8（F4 两库判定 / v2.3 定性校正：用途 / 角色归关系侧）
      §4.3 键与编码（key_template）/ §5.4 生命周期；foundation 步 7 支持对象首案

覆盖:
1. 命名三面 : 界面词「地址」/ 技术标识 address / 物理表 addresses
2. 两库分治 : 不是 location 泛化；不反向挂引用方（无 site_id / party_id 等）
3. 结构     : id / code / 四 FK（country_id … district_id → region）/ 三文本
              （street / street_number / postal_code）/ formatted_address / status
4. 编码     : code required + unique；key_template = ADDR-{SEQ:8}；无 parent_field 段
5. 定性校正 : 不承载用途 / 角色（无 use / purpose / role 字段）
6. 建表/强制: sync_schema_from_meta 建表（regions + addresses 双表）+ code 唯一；
              重复 code 被拒；status 默认 active；country_id 必填；其余 FK/文本可空
（级联接线/级联语义断言见 test_f4_region_dictionary.py —— 设计 §6.1）

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

_STRUCTURED_FK = ('country_id', 'province_id', 'city_id', 'district_id')
_STRUCTURED_TEXT = ('street', 'street_number', 'postal_code')

_FORBIDDEN_NAMES = ('location', 'locations', 'product', 'relationship')

# 不承载的语义（v2.3：用途 / 角色归关系侧；两库分治：不反向挂引用方）
_FORBIDDEN_FIELDS = (
    'use', 'usage', 'purpose', 'role',
    'address_type', 'address_role',
    'site_id', 'location_id', 'party_id', 'owner_party_id',
)

pytestmark = pytest.mark.unit


# ────────────────────────────────────────
# 辅助
# ────────────────────────────────────────
def _load_yaml():
    import yaml
    with open(os.path.join(_SCHEMA_DIR, 'address.yaml'), 'r',
              encoding='utf-8') as f:
        return yaml.safe_load(f)


def _fields():
    return {f['id']: f for f in _load_yaml()['fields']}


# ────────────────────────────────────────
# 夹具
# ────────────────────────────────────────
@pytest.fixture()
def addr_ds(tmp_path):
    """临时库: regions + addresses 双表（aspects 按平台路径解析）"""
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    region_obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'region.yaml'),
                                aspects_defs=aspects)
    obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'address.yaml'),
                         aspects_defs=aspects)
    assert obj is not None, 'address.yaml 加载失败'

    ds = get_data_source("sqlite", database=str(tmp_path / 'f4_address.db'))
    sync_schema_from_meta(ds, [region_obj, obj])
    ds.insert('regions', {
        'id': 1, 'code': 'CN', 'name': '中国',
        'level': 'country', 'status': 'active',
    })
    yield ds
    _clear_data_source_cache_for_testing()


_counter = {'n': 0}


def _next_row(ds, code, formatted='上海市浦东新区世纪大道1号', country_id=1):
    _counter['n'] += 1
    ds.insert('addresses', {
        'id': _counter['n'],
        'code': code,
        'country_id': country_id,
        'formatted_address': formatted,
    })


# ────────────────────────────────────────
# 1. 命名三面（界面词 / 技术标识 / 物理表）
# ────────────────────────────────────────
class TestNaming:
    def test_interface_word(self):
        assert _load_yaml()['name'] == '地址'

    def test_technical_id_and_table(self):
        data = _load_yaml()
        assert data['id'] == 'address'
        assert data['table_name'] == 'addresses'

    def test_not_location_tree(self):
        """F4 两库分治: 地址库不是设施树（site 不泛化为地理点）"""
        data = _load_yaml()
        assert data['id'] != 'location'
        assert data['table_name'] != 'locations'

    def test_no_forbidden_names(self):
        data = _load_yaml()
        assert data['id'] not in _FORBIDDEN_NAMES
        assert data['table_name'] not in _FORBIDDEN_NAMES


# ────────────────────────────────────────
# 2. 结构（§3.8.2）
# ────────────────────────────────────────
class TestStructure:
    def test_identity_and_anchor_fields(self):
        fields = _fields()
        for fid in ('id', 'code', 'formatted_address', 'status'):
            assert fid in fields, '结构字段缺失: %s' % fid

    def test_fk_fields_integer(self):
        """四 FK 引用 region 字典（设计 §4.1）"""
        fields = _fields()
        for fid in _STRUCTURED_FK:
            assert fid in fields, 'FK 字段缺失: %s' % fid
            assert fields[fid]['type'] == 'integer'
            assert fields[fid]['db_column'] == fid

    def test_fk_display_association(self):
        fields = _fields()
        for fid in _STRUCTURED_FK:
            disp = fields[fid]['semantics']['display']
            assert disp['type'] == 'association'
            assert disp['target_type'] == 'region'
            assert disp['display_field'] == 'name'

    def test_country_id_required_others_nullable(self):
        fields = _fields()
        assert fields['country_id']['required'] is True
        for fid in _STRUCTURED_FK[1:]:
            assert not fields[fid].get('required'), '%s 一期应为可空' % fid

    def test_text_fields_kept(self):
        """街道 / 门牌 / 邮编仍为文本列（不经字典）"""
        fields = _fields()
        for fid in _STRUCTURED_TEXT:
            assert fid in fields
            assert fields[fid]['type'] == 'string'

    def test_formatted_address_required(self):
        """格式化全文 = 展示字段（进单据走快照 S20）"""
        f = _fields()['formatted_address']
        assert f['type'] == 'text'
        assert f['required'] is True

    def test_display_name_is_formatted_address(self):
        assert _load_yaml()['display_name_field'] == 'formatted_address'

    def test_status_enum_and_default(self):
        f = _fields()['status']
        vals = {e['value'] for e in f['enum_values']}
        assert vals == {'active', 'inactive'}
        assert f['default'] == 'active'
        assert f['required'] is True

    def test_no_lat_lng_columns_phase1(self):
        """经纬度一期留扩展点（不落列；随地理能力专题以可空列追加）"""
        fields = _fields()
        assert 'latitude' not in fields
        assert 'longitude' not in fields

    def test_audit_kept(self):
        """地址变更留痕（§3.8.4）"""
        data = _load_yaml()
        assert 'audit_aspect' in (data.get('aspects') or [])
        assert (data.get('audit') or {}).get('enabled') is True

    def test_deletion_policy_restrict(self):
        """停用 ≠ 删除（§5.4）: 生命周期走 status；一期不落级联"""
        dp = _load_yaml().get('deletion_policy') or {}
        assert dp.get('mode') == 'restrict'
        assert not dp.get('cascade_delete')


# ────────────────────────────────────────
# 3. 定性校正（v2.3）：只存"地"
# ────────────────────────────────────────
class TestNoPurposeOrRole:
    def test_no_purpose_role_fields(self):
        """用途 / 角色归关系侧（关联边），不得落为地址字段"""
        fields = _fields()
        for bad in _FORBIDDEN_FIELDS:
            assert bad not in fields, '地址库不得承载: %s' % bad


# ────────────────────────────────────────
# 4. 编码（§4.3）：code + key_template
# ────────────────────────────────────────
class TestCodeAndKeyTemplate:
    def test_code_required_unique(self):
        f = _fields()['code']
        assert f['required'] is True
        assert f['unique'] is True

    def test_key_template_form(self):
        kt = _load_yaml().get('key_template') or {}
        assert kt.get('enabled') is True
        assert kt.get('pattern') == 'ADDR-{SEQ:8}'
        assert kt.get('preview') == 'ADDR-00000001'
        assert kt.get('user_editable') == 'auto_or_manual'

    def test_pattern_admits_generated_code(self):
        """编码 pattern 必须放行 key_template 生成值（含连字符）"""
        import re
        f = _fields()['code']
        assert re.match(f['pattern'], _load_yaml()['key_template']['preview'])
        assert len(_load_yaml()['key_template']['preview']) <= f['max_length']

    def test_no_parent_field_segment(self):
        """address 无父对象 ⇒ segments 不得含 parent_field（引擎强制非空校验）"""
        segs = (_load_yaml().get('key_template') or {}).get('segments') or []
        assert segs, 'key_template 应有 sequence 段'
        assert all(s.get('type') != 'parent_field' for s in segs)
        seq = [s for s in segs if s.get('type') == 'sequence']
        assert len(seq) == 1 and seq[0].get('padding') == 8


# ────────────────────────────────────────
# 5. 建表与约束强制（端到端）
# ────────────────────────────────────────
class TestBuildAndConstraints:
    def test_table_created(self, addr_ds):
        names = {r[0] for r in addr_ds.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert 'addresses' in names

    def test_code_unique_index_created(self, addr_ds):
        names = {r[1] for r in addr_ds.execute(
            "PRAGMA index_list('addresses')").fetchall()}
        assert 'idx_address_code' in names

    def test_duplicate_code_rejected(self, addr_ds):
        _next_row(addr_ds, 'ADDR-00000001')
        with pytest.raises(Exception):
            _next_row(addr_ds, 'ADDR-00000001', formatted='北京市朝阳区某路2号')

    def test_status_default_active(self, addr_ds):
        _next_row(addr_ds, 'ADDR-00000002')
        row = addr_ds.execute(
            "SELECT status FROM addresses WHERE code = 'ADDR-00000002'"
        ).fetchone()
        assert row is not None and row[0] == 'active'

    def test_country_required_enforced(self, addr_ds):
        with pytest.raises(Exception):
            addr_ds.insert('addresses', {
                'id': 900,
                'code': 'ADDR-00000090',
                'formatted_address': '无国家地址',
            })

    def test_structured_fields_optional(self, addr_ds):
        """除国家外 FK / 文本字段一期可空（不预烧约束）"""
        _next_row(addr_ds, 'ADDR-00000003')
        row = addr_ds.execute(
            "SELECT city_id, postal_code, street FROM addresses "
            "WHERE code = 'ADDR-00000003'"
        ).fetchone()
        assert row == (None, None, None)

    def test_country_fk_joins_region(self, addr_ds):
        """country_id → regions.id 联查（字典引用端到端）"""
        _next_row(addr_ds, 'ADDR-00000004')
        row = addr_ds.execute(
            "SELECT r.code, r.name FROM addresses a "
            "JOIN regions r ON a.country_id = r.id "
            "WHERE a.code = 'ADDR-00000004'"
        ).fetchone()
        assert row == ('CN', '中国')


# ────────────────────────────────────────
# 6. 地址全文派生（2026-10-23）
#    formatted_address 由 省/市/区/街道/门牌/邮编 拼接，不人工录入；
#    required 约束保留（它同时是 display_name_field）。
# ────────────────────────────────────────
class TestFormattedAddressDerived:
    def test_not_in_create_form(self):
        sections = _load_yaml()['ui_view_config']['form']['sections']
        ids = [fid for s in sections
               for c in (s.get('columns') or []) for fid in c.get('fields', [])]
        assert 'formatted_address' not in ids

    def test_readonly_display_kept(self):
        """只读展示保留在详情、且不进表单（口径同 party_relation.internal_mark）"""
        detail = _load_yaml()['ui_view_config']['detail']
        ids = [fid for t in detail['tabs'] for fid in t.get('fields', [])]
        assert 'formatted_address' in ids
        ui = _fields()['formatted_address']['ui']
        assert ui['editable'] is False
        assert ui['readonly'] is True

    def test_not_importable(self):
        assert _fields()['formatted_address']['semantics']['import_visible'] is False

    def test_still_required(self):
        """必填保留 —— 它是 display_name_field，为空会让列表出现空白行"""
        assert _fields()['formatted_address']['required'] is True

    def test_derive_concatenates_in_order(self, addr_ds):
        """区划层级链 + 街道 + 门牌 + 邮编，按序拼接"""
        from meta.services.address_derive_service import AddressDeriveService
        addr_ds.insert('regions', {
            'id': 2, 'code': 'SH', 'name': '上海市', 'level': 'province',
            'parent_id': 1, 'status': 'active'})
        addr_ds.insert('regions', {
            'id': 3, 'code': 'PD', 'name': '浦东新区', 'level': 'district',
            'parent_id': 2, 'status': 'active'})
        data = AddressDeriveService(addr_ds).derive_formatted_address({
            'country_id': 1, 'province_id': 2, 'district_id': 3,
            'street': '世纪大道', 'street_number': '1号',
            'postal_code': '200120',
        })
        assert data['formatted_address'] == '中国上海市浦东新区世纪大道1号200120'

    def test_duplicate_region_ids_not_repeated(self, addr_ds):
        """同一 id 传多次不重复拼接（层级链只走一遍）"""
        from meta.services.address_derive_service import AddressDeriveService
        addr_ds.insert('regions', {
            'id': 2, 'code': 'SH', 'name': '上海市', 'level': 'province',
            'parent_id': 1, 'status': 'active'})
        data = AddressDeriveService(addr_ds).derive_formatted_address({
            'country_id': 1, 'province_id': 2, 'city_id': 2, 'district_id': 2,
            'street': '世纪大道',
        })
        assert data['formatted_address'] == '中国上海市世纪大道'

    def test_municipality_no_duplicate_province(self, addr_ds):
        """直辖市：省与市同一个「北京市」，不得拼成「北京市北京市」"""
        from meta.services.address_derive_service import AddressDeriveService
        addr_ds.insert('regions', {
            'id': 10, 'code': '110000', 'name': '北京市', 'level': 'province',
            'parent_id': 1, 'status': 'active'})
        addr_ds.insert('regions', {
            'id': 11, 'code': '110100', 'name': '北京市', 'level': 'city',
            'parent_id': 10, 'status': 'active'})
        data = AddressDeriveService(addr_ds).derive_formatted_address({
            'country_id': 1, 'province_id': 10, 'city_id': 11,
            'street': '东长安街', 'street_number': '1号',
        })
        assert data['formatted_address'] == '中国北京市北京市东长安街1号'

    def test_empty_segments_skipped(self, addr_ds):
        """缺失的中间级不产生连续空格"""
        from meta.services.address_derive_service import AddressDeriveService
        addr_ds.insert('regions', {
            'id': 2, 'code': 'SH', 'name': '上海市', 'level': 'province',
            'parent_id': 1, 'status': 'active'})
        data = AddressDeriveService(addr_ds).derive_formatted_address({
            'province_id': 2, 'street': '世纪大道', 'street_number': None,
        })
        assert data['formatted_address'] == '中国上海市世纪大道'

    def test_client_value_discarded(self, addr_ds):
        """客户端自带值一律丢弃，避免绕过派生口径"""
        from meta.services.address_derive_service import AddressDeriveService
        addr_ds.insert('regions', {
            'id': 2, 'code': 'SH', 'name': '上海市', 'level': 'province',
            'parent_id': 1, 'status': 'active'})
        data = AddressDeriveService(addr_ds).derive_formatted_address({
            'province_id': 2, 'street': '世纪大道',
            'formatted_address': '手工乱填的地址',
        })
        assert data['formatted_address'] == '中国上海市世纪大道'

    def test_all_blank_drops_field(self, addr_ds):
        """结构化字段全空时不写空串 —— 交给 required 校验给标准错误"""
        from meta.services.address_derive_service import AddressDeriveService
        data = AddressDeriveService(addr_ds).derive_formatted_address(
            {'formatted_address': '手工乱填的地址'})
        assert 'formatted_address' not in data

    def test_update_merges_existing_fields(self, addr_ds):
        """只改街道时，未改的省/市须从库中原值补齐（否则全文丢前缀）"""
        from meta.services.address_derive_service import AddressDeriveService
        addr_ds.insert('regions', {
            'id': 2, 'code': 'SH', 'name': '上海市', 'level': 'province',
            'parent_id': 1, 'status': 'active'})
        addr_ds.insert('addresses', {
            'id': 700, 'code': 'ADDR-00000700', 'country_id': 1,
            'province_id': 2, 'street': '旧路', 'street_number': '1号',
            'formatted_address': '中国上海市旧路1号',
        })
        data = AddressDeriveService(addr_ds).derive_formatted_address(
            {'id': 700, 'street': '新路'})
        assert data['formatted_address'] == '中国上海市新路1号'
    def test_hook_applied_only_to_registered_object(self, addr_ds):
        from meta.core.consistency_guard import ComputedFieldHandler
        from meta.services.address_derive_service import (
            derive_formatted_address_hook,
        )
        ComputedFieldHandler.register_hook('address', derive_formatted_address_hook)
        try:
            out = ComputedFieldHandler(addr_ds).on_before_save(
                'address', {'street': '世纪大道'})
            assert out['formatted_address'] == '世纪大道'
            other = ComputedFieldHandler(addr_ds).on_before_save(
                'party', {'street': '世纪大道'})
            assert 'formatted_address' not in other
        finally:
            ComputedFieldHandler.clear_hooks()