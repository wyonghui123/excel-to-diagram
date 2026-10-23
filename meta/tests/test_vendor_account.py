# -*- coding: utf-8 -*-
"""vendor_account 供应商档案测试（角色层 C2 供应商侧 · 第二步）

依据: docs/superpowers/specs/2026-10-06-customer-account-profile-design.md §12
      （PM 2026-10-06 拍板「供应商先先先先第二步做」）

与 test_customer_account.py **严格对称**，并额外锁定「供应商特有字段不得越界」。

覆盖：
  ① 结构（字段集 / 类型 / 必填 / 唯一 / 命名 / 表名）
  ② relation_id 1:1 唯一约束（含 DB 层真 DDL）
  ③ 5 动作码齐备 + path 正确 + skip_auto_menu
  ④ 删除保护 restrict
  ⑤ **与 customer_account 的对称性**（本文件核心）
  ⑥ 负向：无 SAP LFM1 / Oracle POZ 采购财务字段
  ⑦ 负向：无 site 级字段（Oracle supplier_site 粒度含 PRC_BU）
  ⑧ 负向：无生效期 / 无 status / 无生命周期 rules
  ⑨ 索引口径
  ⑩ party_relation.role 值域含 vendor（前置依赖断言）
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
_YAML_PATH = os.path.join(_SCHEMA_DIR, 'vendor_account.yaml')
_CUSTOMER_YAML_PATH = os.path.join(_SCHEMA_DIR, 'customer_account.yaml')
_RELATION_YAML_PATH = os.path.join(_SCHEMA_DIR, 'party_relation.yaml')

pytestmark = pytest.mark.unit


def _raw(path=_YAML_PATH):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _fields():
    return {f['id']: f for f in (_raw().get('fields') or [])}


def _field_ids():
    return set(_fields().keys())


def _load_loaded_fields():
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml
    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    obj = load_yaml_file(_YAML_PATH, aspects_defs=aspects)
    return {f.id: f for f in obj.fields}


# ────────────────────────────────────────
# ① 结构
# ────────────────────────────────────────
class TestStructure:
    def test_object_identity(self):
        d = _raw()
        assert d['id'] == 'vendor_account'
        assert d['name'] == '供应商档案'
        assert d['table_name'] == 'vendor_accounts'
        assert d['aspects'] == ['audit_aspect']

    def test_display_name_field_exists(self):
        d = _raw()
        assert d['display_name_field'] == 'name'
        assert 'name' in _field_ids()

    def test_field_set_exactly_symmetric(self):
        """字段集 = id / relation_id / name / description / created_at
        [2026-10-23] vendor_type 已删（对称口径，见 test_vendor_type_removed）。"""
        assert _field_ids() == {
            'id', 'relation_id', 'name', 'description', 'created_at',
        }

    def test_id_field(self):
        f = _fields()['id']
        assert f['type'] == 'integer'
        assert f['required'] is True
        assert f['unique'] is True

    def test_relation_id_required_unique(self):
        f = _fields()['relation_id']
        assert f['type'] == 'integer'
        assert f['required'] is True
        assert f['unique'] is True
        assert f['db_column'] == 'relation_id'

    def test_name_required(self):
        f = _fields()['name']
        assert f['type'] == 'string'
        assert f['required'] is True
        assert f['max_length'] == 200

    def test_vendor_type_removed(self):
        """[删除回归锁 2026-10-23] vendor_type 已删，不得复活（与客户侧 customer_type 同理由）。"""
        assert 'vendor_type' not in _fields()
        v = _raw()['ui_view_config']
        assert 'vendor_type' not in {x['field'] for x in v['list']['columns']}
        assert 'vendor_type' not in {
            fid for s in v['form']['sections']
            for c in (s.get('columns') or []) for fid in c.get('fields', [])}
        assert 'vendor_type' not in {
            f for facet in v['detail']['facets'] for f in facet.get('fields', [])}

    def test_description_nullable_text(self):
        f = _fields()['description']
        assert f['type'] == 'text'
        assert f['nullable'] is True

    def test_created_at_is_audit_field(self):
        f = _fields()['created_at']
        assert f['type'] == 'datetime'
        assert f['semantics']['audit_field'] is True


# ────────────────────────────────────────
# ② relation_id 唯一约束
# ────────────────────────────────────────
class TestRelationUniqueEnforced:
    def test_schema_declares_unique(self):
        assert _fields()['relation_id']['unique'] is True

    def test_named_unique_index(self):
        idx = _raw().get('indexes') or []
        hits = [i for i in idx
                if i.get('name') == 'idx_vendor_account_relation_unique']
        assert len(hits) == 1
        assert hits[0]['unique'] is True
        assert hits[0]['fields'] == ['relation_id']

    def test_unique_enforced_at_db_level(self, tmp_path):
        from meta.core.datasource import get_data_source
        from meta.core.schema_generator import sync_schema_from_meta
        from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

        aspects = parse_aspects_yaml(_SCHEMA_DIR)
        obj = load_yaml_file(_YAML_PATH, aspects_defs=aspects)
        ds = get_data_source('sqlite', database=str(tmp_path / 'va_uniq.db'))
        sync_schema_from_meta(ds, [obj])

        ds.insert('vendor_accounts', {
            'relation_id': 1, 'name': 'A',
        })
        with pytest.raises(Exception):
            ds.insert('vendor_accounts', {
                'relation_id': 1, 'name': 'B',
            })

    def test_different_relation_id_allowed(self, tmp_path):
        from meta.core.datasource import get_data_source
        from meta.core.schema_generator import sync_schema_from_meta
        from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

        aspects = parse_aspects_yaml(_SCHEMA_DIR)
        obj = load_yaml_file(_YAML_PATH, aspects_defs=aspects)
        ds = get_data_source('sqlite', database=str(tmp_path / 'va_multi.db'))
        sync_schema_from_meta(ds, [obj])

        for rid in (1, 2, 3):
            ds.insert('vendor_accounts', {'relation_id': rid, 'name': f'V{rid}'})
        assert len(ds.query('SELECT relation_id FROM vendor_accounts')) == 3


# ────────────────────────────────────────
# ③ 动作码
# ────────────────────────────────────────
class TestActionCodes:
    def test_five_explicit_actions(self):
        assert len(_raw().get('actions') or []) == 5

    def test_action_ids(self):
        ids = {a['id'] for a in (_raw().get('actions') or [])}
        assert ids == {
            'vendor_account_create', 'vendor_account_read',
            'vendor_account_update', 'vendor_account_delete',
            'vendor_account_list',
        }

    def test_action_types(self):
        types = {a['id']: a['type'] for a in (_raw().get('actions') or [])}
        assert types['vendor_account_create'] == 'create'
        assert types['vendor_account_read'] == 'read'
        assert types['vendor_account_update'] == 'update'
        assert types['vendor_account_delete'] == 'delete'
        assert types['vendor_account_list'] == 'list'

    def test_action_paths(self):
        by_id = {a['id']: a for a in (_raw().get('actions') or [])}
        assert by_id['vendor_account_create']['path'] == '/api/v1/vendor_accounts'
        assert by_id['vendor_account_list']['path'] == '/api/v1/vendor_accounts'
        for rid in ('vendor_account_read', 'vendor_account_update',
                    'vendor_account_delete'):
            assert by_id[rid]['path'] == '/api/v1/vendor_accounts/{id}'

    def test_permissions_isolated_from_customer(self):
        """权限码与客户侧完全隔离（独立权限域，D-V1 核心）"""
        perms = {a['permission'] for a in (_raw().get('actions') or [])}
        assert all(p.startswith('vendor_account:') for p in perms)
        assert not any(p.startswith('customer_account:') for p in perms)

    def test_skip_auto_menu(self):
        assert _raw()['ui_view_config']['skip_auto_menu'] is True

    def test_import_export_auto_crud_disabled(self):
        assert _raw()['import_export']['auto_crud'] is False


# ────────────────────────────────────────
# ④ 删除保护
# ────────────────────────────────────────
class TestDeletionPolicy:
    def test_restrict_mode(self):
        assert _raw()['deletion_policy']['mode'] == 'restrict'

    def test_restrict_on_empty_but_present(self):
        dp = _raw()['deletion_policy']
        assert dp['restrict_on'] == []
        assert 'restrict_on' in dp

    def test_audit_exclude_only_machinery(self):
        audit = _raw()['audit']
        assert 'exclude' not in audit['create']
        assert set(audit['update']['exclude']) == {'id', 'created_at', 'updated_at'}
        assert set(audit['delete']['exclude']) == {'id', 'created_at', 'updated_at'}


# ────────────────────────────────────────
# ⑤ 与 customer_account 的对称性（本文件核心）
# ────────────────────────────────────────
class TestSymmetryWithCustomerAccount:
    """供应商侧必须与客户侧严格对称（除字段名 vendor_/customer_ 前缀差异）"""

    def test_field_id_mapping(self):
        """字段集按「去掉 vendor/customer 前缀」后应完全一致"""
        v = {fid.replace('vendor_', '') for fid in _field_ids()}
        c = {fid.replace('customer_', '')
             for fid in _raw(_CUSTOMER_YAML_PATH) and
             {f['id'] for f in (_raw(_CUSTOMER_YAML_PATH).get('fields') or [])}}
        assert v == c, f'两侧字段集不对称：vendor={v} customer={c}'

    def test_same_field_count(self):
        vc = _raw(_CUSTOMER_YAML_PATH)
        assert len(_raw()['fields']) == len(vc['fields'])

    def test_same_index_count_and_uniqueness(self):
        vc = _raw(_CUSTOMER_YAML_PATH)
        vi = _raw()['indexes']
        ci = vc['indexes']
        assert len(vi) == len(ci) == 1
        assert vi[0]['fields'] == ci[0]['fields'] == ['relation_id']
        assert vi[0]['unique'] is True and ci[0]['unique'] is True

    def test_same_deletion_policy_shape(self):
        v = _raw()['deletion_policy']
        c = _raw(_CUSTOMER_YAML_PATH)['deletion_policy']
        assert v['mode'] == c['mode'] == 'restrict'
        assert v['restrict_on'] == c['restrict_on'] == []

    def test_same_action_shape(self):
        va = {a['type'] for a in (_raw().get('actions') or [])}
        ca = {a['type'] for a in
              (_raw(_CUSTOMER_YAML_PATH).get('actions') or [])}
        assert va == ca
        assert len(va) == 5

    def test_both_skip_auto_menu(self):
        assert _raw()['ui_view_config']['skip_auto_menu'] is True
        assert _raw(_CUSTOMER_YAML_PATH)['ui_view_config']['skip_auto_menu'] is True

    def test_same_ui_view_config_shape(self):
        """[分区落点 2026-10-22] 两侧 UI 配置对称（独立菜单下架后仍须有完整配置）"""
        v = _raw()['ui_view_config']
        c = _raw(_CUSTOMER_YAML_PATH)['ui_view_config']
        assert set(v) == set(c) == {
            'skip_auto_menu', 'list', 'form', 'detail'}
        # 列集合对称：供应侧对客户侧做前缀替换后比对（两侧同为name/description/created_at）
        assert [x['field'].replace('vendor_', 'customer_')
                for x in v['list']['columns']] == \
            [x['field'] for x in c['list']['columns']]

    def test_list_columns_exclude_technical_id_and_relation_id(self):
        """裸 ID 缺陷 + relation_id 冗余列的回归锁（两侧同时）"""
        for path in (_YAML_PATH, _CUSTOMER_YAML_PATH):
            fields = [x['field']
                      for x in _raw(path)['ui_view_config']['list']['columns']]
            assert 'id' not in fields, path
            assert 'relation_id' not in fields, path

    def test_form_and_detail_declared_both_sides(self):
        """编辑态空白缺陷的回归锁（两侧同时）"""
        for path in (_YAML_PATH, _CUSTOMER_YAML_PATH):
            cfg = _raw(path)['ui_view_config']
            form_ids = [fid for s in cfg['form']['sections']
                        for c in (s.get('columns') or [])
                        for fid in c.get('fields', [])]
            detail_ids = [fid for fc in cfg['detail']['facets']
                          for fid in fc.get('fields', [])]
            assert 'name' in form_ids, path
            assert 'name' in detail_ids, path
            assert 'relation_id' not in form_ids, path

    def test_neither_side_in_init_menu_declarations(self):
        """两条独立菜单均已从 init_menu_permissions.py 移除"""
        init_path = os.path.join(_META_DIR, 'scripts', 'init_menu_permissions.py')
        with open(init_path, 'r', encoding='utf-8') as f:
            src = f.read()
        assert "'menu_code': 'vendor-account-management'" not in src
        assert "'menu_code': 'customer-account-management'" not in src

    def test_customer_side_has_no_vendor_fields(self):
        """反向锁定：客户侧不得被本次改动污染"""
        cf = {f['id'] for f in (_raw(_CUSTOMER_YAML_PATH).get('fields') or [])}
        for bad in ('vendor_id', 'vendor_relation_id', 'supplier_id'):
            assert bad not in cf

    def test_loaded_field_count_symmetric(self):
        """目录级加载：两侧都是 5 显式 + 3 aspect 净增 = 8
        （[2026-10-23] 删 customer_type / vendor_type 后由 9 降为 8）"""
        from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml
        aspects = parse_aspects_yaml(_SCHEMA_DIR)
        vo = load_yaml_file(_YAML_PATH, aspects_defs=aspects)
        co = load_yaml_file(_CUSTOMER_YAML_PATH, aspects_defs=aspects)
        assert len(vo.fields) == len(co.fields) == 8


# ────────────────────────────────────────
# ⑥⑦ 负向：采购/财务字段不得越界
# ────────────────────────────────────────
class TestNoProcurementFinancialFields:
    """SAP LFM1 / LFB1 / LFBK + Oracle POZ 的采购与财务字段本期全不做"""

    SAP_LFM1_FIELDS = {
        'waers', 'ekorg', 'ekgrp', 'lfabc', 'sperm', 'loevm', 'verkf',
        'incoterms', 'lgpro', 'gr_we', 'rekl', 'zterm', 'wafs', 'nettx',
    }

    ORACLE_POZ_FIELDS = {
        'terms_id', 'tolerance_id', 'services_tolerance_id', 'retainage_rate',
        'bank_charge_bearer', 'pay_site_flag', 'purchasing_site_flag',
        'primary_pay_site_flag', 'rfq_only_site_flag', 'pcard_site_flag',
        'exempt_cert_flag', 'pay_on_code', 'match_option', 'allow_unordered_receipts_flag',
        'allow_substitute_receipts_flag', 'country_of_origin_code',
    }

    FIN_FIELDS = {
        'bank_account', 'bank_name', 'iban', 'swift', 'payment_terms',
        'cash_discount_terms', 'reconciliation_account', 'posted_payment_block',
        'withholding_tax', 'gst_number', 'tax_number', 'pan_number',
    }

    def test_no_sap_lfm1_fields(self):
        fids = {f.lower() for f in _field_ids()}
        assert not (fids & self.SAP_LFM1_FIELDS)

    def test_no_oracle_poz_fields(self):
        fids = {f.lower() for f in _field_ids()}
        assert not (fids & self.ORACLE_POZ_FIELDS)

    def test_no_financial_fields(self):
        fids = {f.lower() for f in _field_ids()}
        assert not (fids & self.FIN_FIELDS)

    def test_no_purchasing_org_grouping_axis(self):
        """SAP LFM1.EKORG(采购组织) / EKGRP(采购组) / KFKOR(采购组织范围) 不做"""
        fids = _field_ids()
        for bad in ('ekorg', 'ekgrp', 'purchasing_org', 'purchasing_group',
                    'bu_id', 'procurement_bu'):
            assert bad not in fids

    def test_no_po_currency_field(self):
        """SAP LFM1.WAERS（采购订单币种）不做 —— 需币种+汇率前置（TBD-1）"""
        assert 'currency' not in _field_ids()
        assert 'order_currency' not in _field_ids()
        assert 'waers' not in _field_ids()

    def test_no_bank_fields(self):
        """SAP LFBK 银行数据独立表 —— 本期不做"""
        fids = _field_ids()
        for bad in ('bank_details', 'bank_account', 'bank_name', 'iban', 'swift_code'):
            assert bad not in fids

    def test_no_retainage_or_tolerance(self):
        """Oracle RETAINAGE_RATE / TOLERANCE_ID 不做"""
        fids = _field_ids()
        for bad in ('retainage_rate', 'tolerance_id', 'services_tolerance_id'):
            assert bad not in fids


class TestNoSiteLevelFields:
    """Oracle supplier_site 粒度 = VENDOR_ID + PARTY_SITE_ID + PRC_BU_ID ⇒ 本期不做 site 级"""

    def test_no_site_id_fields(self):
        fids = _field_ids()
        for bad in ('party_site_id', 'site_id', 'vendor_site_id',
                    'site_use_id', 'vendor_site_code', 'prc_bu_id'):
            assert bad not in fids

    def test_no_site_purpose_flags(self):
        """Oracle site purposes = Purchasing / Pay / Procurement Card / Primary Pay / Sourcing Only"""
        fids = _field_ids()
        for bad in ('purchasing_site_flag', 'pay_site_flag',
                    'primary_pay_site_flag', 'rfq_only_site_flag', 'pcard_site_flag'):
            assert bad not in fids

    def test_no_site_assignments(self):
        """Oracle site assignments（client BU 分配）不做"""
        assert 'site_assignments' not in _field_ids()
        assert 'client_bu_id' not in _field_ids()

    def test_no_relations_declared(self):
        assert (_raw().get('relations') or []) == []

    def test_no_le_org_id_field(self):
        """法人粒度由 party_relation.le_org_id 承载，不重复落列"""
        assert 'le_org_id' not in _field_ids()


class TestNoEffectiveDatesAndStatus:
    def test_no_effective_date_fields(self):
        fids = _field_ids()
        for bad in ('effective_start_date', 'effective_end_date',
                    'effective_sequence', 'effective_from', 'effective_to',
                    'valid_from', 'valid_to', 'inactive_date'):
            assert bad not in fids, f'不得含生效期字段：{bad}'

    def test_no_status_field(self):
        assert 'status' not in _field_ids()

    def test_no_lifecycle_rules(self):
        assert not (_raw().get('rules') or [])

    def test_no_qualification_fields(self):
        """Oracle site 有 Qualifications 页（资质评估）—— 不做"""
        fids = _field_ids()
        for bad in ('qualification', 'qualifications', 'assessment_id'):
            assert bad not in fids


# ────────────────────────────────────────
# ⑨ 索引
# ────────────────────────────────────────
class TestIndexes:
    def test_only_relation_id_index(self):
        idx = _raw().get('indexes') or []
        assert len(idx) == 1
        assert idx[0]['fields'] == ['relation_id']

    def test_no_secondary_index(self):
        names = {i.get('name') for i in (_raw().get('indexes') or [])}
        assert names == {'idx_vendor_account_relation_unique'}


# ────────────────────────────────────────
# ⑩ 前置依赖 + 加载
# ────────────────────────────────────────
class TestPrerequisites:
    def test_party_relation_role_has_vendor(self):
        """前置：party_relation.role 值域必须已含 vendor（否则本对象锚点无意义）"""
        rel = _raw(_RELATION_YAML_PATH)
        role = {f['id']: f for f in (rel.get('fields') or [])}['role']
        assert 'vendor' in {e['value'] for e in role['enum_values']}

    def test_party_relation_unique_key_includes_le_org_id(self):
        """前置：relation 唯一键含 le_org_id ⇒ 一法人一 relation ⇒ 一法人一档案"""
        rel = _raw(_RELATION_YAML_PATH)
        rel_ids = {f['id'] for f in (rel.get('fields') or [])}
        assert 'le_org_id' in rel_ids

    def test_loaded_updated_at_is_virtual(self):
        """audit_aspect 展开的 updated_at 为 VIRTUAL（不落物理列）"""
        loaded = _load_loaded_fields()
        assert 'updated_at' in loaded
        assert str(loaded['updated_at'].storage).endswith('VIRTUAL')

    def test_loaded_has_no_site_fields(self):
        """加载后（aspect 展开完）仍无 site 级字段"""
        loaded = set(_load_loaded_fields().keys())
        for bad in ('party_site_id', 'vendor_site_id', 'prc_bu_id'):
            assert bad not in loaded

    def test_insert_works_and_created_at_autofill(self, tmp_path):
        from meta.core.datasource import get_data_source
        from meta.core.schema_generator import sync_schema_from_meta
        from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

        aspects = parse_aspects_yaml(_SCHEMA_DIR)
        obj = load_yaml_file(_YAML_PATH, aspects_defs=aspects)
        ds = get_data_source('sqlite', database=str(tmp_path / 'va_ins.db'))
        sync_schema_from_meta(ds, [obj])

        raw = ds.get_table_columns('vendor_accounts')
        cols = set(raw.keys()) if isinstance(raw, dict) else {str(c) for c in raw}
        assert 'updated_at' not in cols, 'updated_at 为 virtual，不应落列'
        assert 'created_at' in cols

        ds.insert('vendor_accounts', {
            'relation_id': 1, 'name': '供应商甲',
        })
        rows = ds.query('SELECT relation_id, name, created_at FROM vendor_accounts')
        assert len(rows) == 1
