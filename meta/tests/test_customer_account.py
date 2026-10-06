# -*- coding: utf-8 -*-
"""customer_account 客户档案测试（C2 · foundation 步 3 角色层）

依据: docs/superpowers/specs/2026-10-06-customer-account-profile-design.md v1.2
      （PM 2026-10-06 拍板：建骨架 / 命名 customer_account / 供应商留第二步）

本对象是**结构占位** —— 无任何财务语义字段（随 D1 会计处置挂起）。
故测试重心在**负向锁定**：断言「不该有的字段确实没有」，防止后续误加。

覆盖：
  ① 结构（字段集 / 类型 / 必填 / 唯一 / 命名 / 表名）
  ② relation_id 1:1 唯一约束生效
  ③ 5 动作码齐备 + path 正确
  ④ 删除保护 restrict + restrict_on 空
  ⑤ 负向：无财务语义字段（D3 锁定）
  ⑥ 负向：无生效期字段（D2 / TBD-14 锁定）
  ⑦ 负向：无 status 字段（D4 锁定）
  ⑧ 负向：无 site_use / 用途字段（D3 锁定）
  ⑨ 索引口径
  ⑩ 命名裁定留痕（customer_account 而非 customer_profile）
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
_YAML_PATH = os.path.join(_SCHEMA_DIR, 'customer_account.yaml')

pytestmark = pytest.mark.unit


# ────────────────────────────────────────
# 辅助
# ────────────────────────────────────────
def _raw():
    with open(_YAML_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _fields():
    """字段 id -> 原始声明 dict"""
    return {f['id']: f for f in (_raw().get('fields') or [])}


def _field_ids():
    return set(_fields().keys())


# ────────────────────────────────────────
# ① 结构
# ────────────────────────────────────────
class TestStructure:
    def test_object_identity(self):
        d = _raw()
        assert d['id'] == 'customer_account'
        assert d['name'] == '客户档案'
        assert d['table_name'] == 'customer_accounts'
        assert d['aspects'] == ['audit_aspect']

    def test_display_name_field_exists(self):
        """display_name_field 指向的字段必须真实存在"""
        d = _raw()
        assert d['display_name_field'] == 'name'
        assert 'name' in _field_ids()

    def test_field_set_is_exactly_four_business_fields(self):
        """业务字段集 = id / relation_id / name / customer_type / description / created_at

        本期是结构占位，字段集刻意极小（spec §3.1.2）。
        """
        assert _field_ids() == {
            'id', 'relation_id', 'name', 'customer_type', 'description', 'created_at',
        }

    def test_id_field(self):
        f = _fields()['id']
        assert f['type'] == 'integer'
        assert f['required'] is True
        assert f['unique'] is True

    def test_relation_id_required_unique(self):
        """1:1 锚 —— required + unique（spec §3.1.2）"""
        f = _fields()['relation_id']
        assert f['type'] == 'integer'
        assert f['required'] is True
        assert f['unique'] is True
        assert f['db_column'] == 'relation_id'

    def test_name_required(self):
        f = _fields()['name']
        assert f['type'] == 'string'
        assert f['required'] is True

    def test_customer_type_enum(self):
        """客户类型 = internal / external（Oracle CUSTOMER_TYPE 值域）"""
        f = _fields()['customer_type']
        assert f['nullable'] is True
        assert f['max_length'] == 30
        values = {e['value'] for e in f['enum_values']}
        assert values == {'internal', 'external'}

    def test_description_nullable_text(self):
        f = _fields()['description']
        assert f['type'] == 'text'
        assert f['nullable'] is True

    def test_created_at_is_audit_aspect(self):
        f = _fields()['created_at']
        assert f['type'] == 'datetime'
        assert f['semantics']['audit_field'] is True


# ────────────────────────────────────────
# ② relation_id 唯一约束
# ────────────────────────────────────────
class TestRelationUniqueEnforced:
    def test_schema_declares_unique(self):
        """声明层：字段级 unique"""
        assert _fields()['relation_id']['unique'] is True

    def test_named_unique_index_exists(self):
        """命名唯一索引（双落惯例）"""
        idx = _raw().get('indexes') or []
        hits = [i for i in idx if i.get('name') == 'idx_customer_account_relation_unique']
        assert len(hits) == 1, '缺命名唯一索引 idx_customer_account_relation_unique'
        assert hits[0]['unique'] is True
        assert hits[0]['fields'] == ['relation_id']

    def test_unique_enforced_at_db_level(self, tmp_path):
        """落库后重复 relation_id 必须被拒（真 DDL 层面，非仅声明）"""
        from meta.core.datasource import get_data_source
        from meta.core.schema_generator import sync_schema_from_meta
        from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

        aspects = parse_aspects_yaml(_SCHEMA_DIR)
        obj = load_yaml_file(_YAML_PATH, aspects_defs=aspects)
        ds = get_data_source('sqlite',
                             database=str(tmp_path / 'ca_unique.db'))
        sync_schema_from_meta(ds, [obj])

        ds.insert('customer_accounts', {
            'relation_id': 1, 'name': 'A', 'customer_type': 'external',
        })
        with pytest.raises(Exception):
            ds.insert('customer_accounts', {
                'relation_id': 1, 'name': 'B', 'customer_type': 'internal',
            })

    def test_different_relation_id_allowed(self, tmp_path):
        """不同 relation_id 可并存（1:1 不等于全局唯一单行）"""
        from meta.core.datasource import get_data_source
        from meta.core.schema_generator import sync_schema_from_meta
        from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

        aspects = parse_aspects_yaml(_SCHEMA_DIR)
        obj = load_yaml_file(_YAML_PATH, aspects_defs=aspects)
        ds = get_data_source('sqlite',
                             database=str(tmp_path / 'ca_multi.db'))
        sync_schema_from_meta(ds, [obj])

        for rid in (1, 2, 3):
            ds.insert('customer_accounts', {
                'relation_id': rid, 'name': f'A{rid}',
            })
        rows = ds.query('SELECT relation_id FROM customer_accounts')
        assert len(rows) == 3


# ────────────────────────────────────────
# ③ 动作码
# ────────────────────────────────────────
class TestActionCodes:
    def test_five_explicit_actions(self):
        actions = _raw().get('actions') or []
        assert len(actions) == 5, f'应为 5 个显式动作，实际 {len(actions)}'

    def test_action_ids(self):
        ids = {a['id'] for a in (_raw().get('actions') or [])}
        assert ids == {
            'customer_account_create', 'customer_account_read',
            'customer_account_update', 'customer_account_delete',
            'customer_account_list',
        }

    def test_action_types(self):
        types = {a['id']: a['type'] for a in (_raw().get('actions') or [])}
        assert types['customer_account_create'] == 'create'
        assert types['customer_account_read'] == 'read'
        assert types['customer_account_update'] == 'update'
        assert types['customer_account_delete'] == 'delete'
        assert types['customer_account_list'] == 'list'

    def test_action_paths(self):
        by_id = {a['id']: a for a in (_raw().get('actions') or [])}
        assert by_id['customer_account_create']['path'] == '/api/v1/customer_accounts'
        assert by_id['customer_account_list']['path'] == '/api/v1/customer_accounts'
        for rid in ('customer_account_read', 'customer_account_update',
                    'customer_account_delete'):
            assert by_id[rid]['path'] == '/api/v1/customer_accounts/{id}'

    def test_skip_auto_menu(self):
        """角色层档案不自动挂菜单（照 person_profile 先例）"""
        assert _raw()['ui_view_config']['skip_auto_menu'] is True

    def test_import_export_auto_crud_disabled(self):
        assert _raw()['import_export']['auto_crud'] is False


# ────────────────────────────────────────
# ④ 删除保护
# ────────────────────────────────────────
class TestDeletionPolicy:
    def test_restrict_mode(self):
        dp = _raw()['deletion_policy']
        assert dp['mode'] == 'restrict'

    def test_restrict_on_empty_but_present(self):
        """restrict_on 留空但**保留结构**（零引用方，供未来补条目）"""
        dp = _raw()['deletion_policy']
        assert dp['restrict_on'] == []
        assert 'restrict_on' in dp


# ────────────────────────────────────────
# ⑤⑥⑦⑧ 负向锁定：不该有的字段确实没有
# ────────────────────────────────────────
class TestNoFinancialFields:
    """D3 锁定：商务条款字段随 D1「会计处置」挂起，本期全不建"""

    FORBIDDEN = {
        'credit_rating', 'risk_code', 'credit_limit', 'credit_checking',
        'tolerance', 'standard_terms', 'override_terms', 'payment_terms',
        'discount_terms', 'discount_grace_days', 'payment_grace_days',
        'interest_charges', 'interest_period_days', 'interest_rate',
        'dunning_letters', 'dunning_cycle', 'send_statements',
        'statement_cycle_id', 'percent_collectable', 'autocash_hierarchy_id',
        'account_status', 'profile_class_id', 'credit_balance_statements',
        'credit_hold', 'collector_id', 'tax_printing_option',
    }

    def test_no_credit_or_terms_fields(self):
        assert not (_field_ids() & self.FORBIDDEN), (
            f'不得含财务语义字段，实际多出：{_field_ids() & self.FORBIDDEN}')

    def test_no_amount_fields(self):
        """信用额度等金额须独立表（Oracle HZ_CUST_PROFILE_AMTS_F）⇒ 本对象不得有"""
        fids = _field_ids()
        for bad in ('credit_limit', 'overall_credit_limit', 'trx_credit_limit',
                    'min_dunning_amount', 'max_interest_charge'):
            assert bad not in fids


class TestNoEffectiveDates:
    """D2 锁定：不建生效期（平台零对象有该机制 ⇒ TBD-14）"""

    def test_no_effective_date_fields(self):
        fids = _field_ids()
        for bad in ('effective_start_date', 'effective_end_date',
                    'effective_from', 'effective_to', 'valid_from', 'valid_to',
                    'start_date', 'end_date'):
            assert bad not in fids, f'不得含生效期字段：{bad}'

    def test_no_profile_class_reference(self):
        """Oracle PROFILE_CLASS_ID（可配置默认值来源）本期不做"""
        assert 'profile_class_id' not in _field_ids()


class TestNoStatusField:
    """D4 锁定：不建 status（与 party_relation.internal_mark 重叠 + 无生效期则启停无意义）"""

    def test_no_status_field(self):
        assert 'status' not in _field_ids()

    def test_no_lifecycle_rules(self):
        """不建 activate / deactivate 生命周期规则（无 status 可驱动）"""
        assert not (_raw().get('rules') or []), '不该有状态转换规则'


class TestNoSiteUseFields:
    """D3 锁定：不建用途（site_use）字段 —— 四家一致判定为交易域"""

    def test_no_site_use_fields(self):
        fids = _field_ids()
        for bad in ('site_use_id', 'cust_acct_site_id', 'site_id',
                    'account_site_id', 'usage', 'usage_type', 'purpose'):
            assert bad not in fids, f'不得含用途/site_use 字段：{bad}'

    def test_no_bill_ship_sold_flags(self):
        """SAP VBPA / PeopleSoft 三张选择页的用途角色，本期不做"""
        fids = _field_ids()
        for bad in ('bill_to_flag', 'ship_to_flag', 'sold_to_flag',
                    'primary_flag', 'bill_to_party_id', 'ship_to_party_id'):
            assert bad not in fids

    def test_no_le_org_id_field(self):
        """法人粒度由 party_relation.le_org_id 承载，档案不重复落列"""
        assert 'le_org_id' not in _field_ids()

    def test_no_relations_declared(self):
        """不建声明式关系（platform 关系引擎用于多态关联，本场景是强 1:1 引用）"""
        assert (_raw().get('relations') or []) == []


# ────────────────────────────────────────
# ⑨ 索引口径
# ────────────────────────────────────────
class TestIndexes:
    def test_only_relation_id_index(self):
        """不建二级索引（无查询场景，避免孤例）"""
        idx = _raw().get('indexes') or []
        assert len(idx) == 1
        assert idx[0]['fields'] == ['relation_id']

    def test_no_type_index(self):
        names = {i.get('name') for i in (_raw().get('indexes') or [])}
        assert not any('type' in (n or '') for n in names)


# ────────────────────────────────────────
# ⑩ 命名裁定留痕
# ────────────────────────────────────────
class TestNamingDecision:
    def test_named_customer_account_not_profile(self):
        """命名裁定（PM 2026-10-06）：取 customer_account，避 ProfileConfig 撞车"""
        d = _raw()
        assert d['id'] == 'customer_account'
        assert d['table_name'] == 'customer_accounts'
        # 表名不得是 customer_profiles（那是 v1.0 被否决的方案）
        assert 'profile' not in d['table_name']

    def test_no_profile_config_collision(self):
        """不得引入 customer_profile（与平台 ProfileConfig 权限档案概念撞车）"""
        fids = _field_ids()
        assert 'profile_id' not in fids
        assert 'profile' not in fids

    def test_audit_no_pii_exclude_needed(self):
        """商务参照数据非 PII ⇒ audit 三模式不设 exclude（照 currency 口径）"""
        audit = _raw()['audit']
        assert 'exclude' not in audit['create']
        # update / delete 只排除 id + 时间戳
        assert set(audit['update']['exclude']) == {'id', 'created_at', 'updated_at'}

    def test_supplier_side_not_built(self):
        """供应商侧留第二步（PM 拍板）⇒ 不得出现 vendor 字段"""
        fids = _field_ids()
        for bad in ('vendor_id', 'vendor_relation_id', 'supplier_id'):
            assert bad not in fids

    def test_directory_registration_no_side_effects(self):
        """目录级加载：显式 6 字段 + audit_aspect 展开 3 字段

        实测（v1.2 纠错）：audit_aspect 展开 4 个字段 ——
          updated_at (VIRTUAL，不落列) · created_by · updated_by · created_at
        其中 created_at 与本对象显式声明的同 id ⇒ 去重后净增 3 个 ⇒ 6 + 3 = 9。
        （aspect 字段清单见 aspects.yaml: audit_aspect.fields 共 5 项，
          本对象显式声明 created_at 覆盖其中 1 项）
        """
        from meta.core.yaml_loader import FieldStorage, load_yaml_file, parse_aspects_yaml
        aspects = parse_aspects_yaml(_SCHEMA_DIR)
        obj = load_yaml_file(_YAML_PATH, aspects_defs=aspects)
        assert obj is not None
        loaded = {f.id for f in obj.fields}
        assert {
            'id', 'relation_id', 'name', 'customer_type', 'description',
            'created_at',
        } <= loaded, f'显式字段缺失：{loaded}'

        by_id = {f.id: f for f in obj.fields}
        # aspect 展开的 updated_at 是 virtual —— INSERT 不得写它（region 教训）
        assert by_id['updated_at'].storage == FieldStorage.VIRTUAL, (
            'updated_at 应为 virtual（不落物理列）')
        # aspect 展开的 actor 字段
        assert 'created_by' in loaded and 'updated_by' in loaded, (
            f'audit_aspect 应展开 created_by / updated_by，实际：{loaded}')
        # 总数 = 6 显式 + 3 净增
        assert len(obj.fields) == 9, f'实际展开 {len(obj.fields)} 个字段'

    def test_updated_at_not_writable(self, tmp_path):
        """updated_at 为 virtual ⇒ INSERT 不得写该列（region / person_profile 同教训）"""
        from meta.core.datasource import get_data_source
        from meta.core.schema_generator import sync_schema_from_meta
        from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

        aspects = parse_aspects_yaml(_SCHEMA_DIR)
        obj = load_yaml_file(_YAML_PATH, aspects_defs=aspects)
        ds = get_data_source('sqlite', database=str(tmp_path / 'ca_va.db'))
        sync_schema_from_meta(ds, [obj])

        raw = ds.get_table_columns('customer_accounts')
        # 实现返回 Dict[str, Dict]；若被包装成别的形态则退回直接查 PRAGMA
        cols = set(raw.keys()) if isinstance(raw, dict) else {str(c) for c in raw}
        assert 'updated_at' not in cols, (
            f'updated_at 为 virtual，不应落物理列；实际列：{sorted(cols)}')
        assert 'created_at' in cols, 'created_at 应落物理列'
        assert 'relation_id' in cols and 'name' in cols

        # 实际写入：不得写 updated_at
        ds.insert('customer_accounts', {'relation_id': 1, 'name': 'X'})
        rows = ds.query('SELECT created_at FROM customer_accounts')
        assert rows, 'INSERT 应成功且 created_at 自动填充'
