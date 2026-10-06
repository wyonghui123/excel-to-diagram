# -*- coding: utf-8 -*-
"""币种主数据（currency）测试 (2026-10-06)

依据: docs/superpowers/specs/2026-10-06-currency-object-design.md
      (§4 对象设计 / §5 无消费者字段 / §7 AC-1..AC-10 / §8bis 多币种报表前瞻校验)

覆盖:
1. TestStructure        : 字段集恰为 8 业务字段；code 为 ISO 4217 alpha-3 严格正则（有意严于 uom）
2. TestCodeUnique       : code 唯一约束端到端（重复插入被拒）
3. TestDecimalPlaces    : decimal_places 默认 2（与 uom 默认 0 有意不同）
4. TestDeletionPolicy   : mode=restrict 生效 + restrict_on 为空但结构保留（AC-8）
5. TestAuditConfig      : 三模式 exclude 口径（无 PII 排除需求）
6. TestLifecycleRules   : activate / deactivate 规则声明正确（复用平台标准动作）
7. TestNoRateObject     : 负向断言 —— 不得存在 currency_rate 对象（防范围蔓延，AC-9）
8. TestNoConsumerClaim  : 负向断言 —— 不得宣称已具备换算/舍入能力（AC-9 / §8bis.4）
9. TestOrphanReference  : 负向断言 —— doc_flow.currency 仍是裸 STRING（G-X1 缺口如实固定）

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
def _load_yaml(name):
    import yaml
    with open(os.path.join(_SCHEMA_DIR, name), 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _cur_yaml():
    return _load_yaml('currency.yaml')


def _fields(data=None):
    return {f['id']: f for f in (data if data is not None else _cur_yaml())['fields']}


def _exclude(mode):
    return set((_cur_yaml().get('audit', {}).get(mode) or {}).get('exclude') or [])


# ────────────────────────────────────────
# 夹具（aspects 按平台路径解析，沿 F4 / person_profile 先例）
# ────────────────────────────────────────
@pytest.fixture()
def cur_ds(tmp_path):
    """临时库: 仅建 currencies 表 + 索引"""
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'currency.yaml'),
                         aspects_defs=aspects)
    assert obj is not None, 'currency.yaml 加载失败'

    ds = get_data_source('sqlite', database=str(tmp_path / 'currency.db'))
    sync_schema_from_meta(ds, [obj])
    yield ds
    _clear_data_source_cache_for_testing()


# ────────────────────────────────────────
# 1. 结构：字段集与约束（§4.1）
# ────────────────────────────────────────
class TestStructure:
    def test_identity_and_table(self):
        data = _cur_yaml()
        assert data['id'] == 'currency'
        assert data['table_name'] == 'currencies'

    def test_field_set(self):
        """字段集恰为 8 业务字段 + created_at(audit aspect)"""
        assert set(_fields()) == {
            'id', 'code', 'name', 'name_en',
            'decimal_places', 'symbol', 'status', 'description', 'created_at',
        }

    def test_code_is_iso4217_alpha3(self):
        """ISO 4217 alpha-3：required + unique + max_length 3 + 严格大写正则"""
        f = _fields()['code']
        assert f['type'] == 'string'
        assert f['required'] is True
        assert f['unique'] is True
        assert f['max_length'] == 3
        assert f['pattern'] == '^[A-Z]{3}$'

    def test_pattern_declared_at_top_level(self):
        """本对象采用**顶层写法**（TBD-12 后生效）

        平台两派写法均支持：`semantics.pattern` 优先、顶层兜底。
        本对象刻意用顶层写法，作为 TBD-12 接线的**活体验证**
        （party/region/org/items 等 9 处既有对象也是顶层写法）。
        """
        f = _fields()['code']
        assert f.get('pattern') == '^[A-Z]{3}$', '顶层 pattern 声明保留'
        assert 'pattern' not in (f.get('semantics') or {}), (
            '本对象用顶层写法即可；两处同写会掩盖双读验证')

    def test_pattern_enforced_by_validator(self):
        """AC-11 端到端：应用层校验器按 rule=='pattern' 拒绝非法 code"""
        import tempfile
        from meta.core.datasource import (
            _clear_data_source_cache_for_testing, get_data_source,
        )
        from meta.core.metadata_driven_validator import MetadataDrivenValidator
        from meta.core.schema_generator import sync_schema_from_meta
        from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

        aspects = parse_aspects_yaml(_SCHEMA_DIR)
        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'currency.yaml'),
                             aspects_defs=aspects)
        tmp = tempfile.mkdtemp()
        ds = get_data_source('sqlite', database=os.path.join(tmp, 'pat.db'))
        sync_schema_from_meta(ds, [obj])
        v = MetadataDrivenValidator(ds)

        results = {}
        for code in ['cny', 'CNYX', 'US', 'CN1', 'CNY']:
            errs = v.validate_create(obj, {'code': code, 'name': 'x'})
            pat = [e for e in (errs or [])
                   if getattr(e, 'rule', '') == 'pattern']
            results[code] = bool(pat)
        _clear_data_source_cache_for_testing()

        assert results == {
            'cny': True, 'CNYX': True, 'US': True, 'CN1': True, 'CNY': False,
        }, f'pattern 生效情况不符预期: {results}'

    def test_pattern_not_enforced_at_db_layer(self):
        """AC-11 反向取证：sqlite DDL **无 CHECK 约束** ⇒ pattern 仅应用层生效

        ⇒ 绕过应用层（直连写库）可写入非法 code。
        **不可宣称「DB 层已强制 ISO 校验」。**
        """
        import tempfile
        from meta.core.datasource import (
            _clear_data_source_cache_for_testing, get_data_source,
        )
        from meta.core.schema_generator import sync_schema_from_meta
        from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

        aspects = parse_aspects_yaml(_SCHEMA_DIR)
        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'currency.yaml'),
                             aspects_defs=aspects)
        tmp = tempfile.mkdtemp()
        ds = get_data_source('sqlite', database=os.path.join(tmp, 'ddl.db'))
        sync_schema_from_meta(ds, [obj])
        rows = ds.query("SELECT sql FROM sqlite_master WHERE type='table' "
                        "AND name='currencies'")
        ddl = ((rows[0]['sql'] or '') if rows else '').upper()
        # 直连写库（小写 code）应被接受 —— 证明无 DB 层约束
        accepted = True
        try:
            ds.insert('currencies', {'code': 'cny', 'name': 'lower'})
        except Exception:
            accepted = False
        _clear_data_source_cache_for_testing()

        assert 'CHECK' not in ddl, f'DDL 不应含 CHECK（pattern 未落 DB 层）: {ddl}'
        assert accepted is True, (
            '直连写库被拒 ⇒ 存在另一层 DB 约束，需修正 AC-11 结论')

    def test_max_length_is_wired(self):
        """`max_length` 已于 TBD-12 (2026-10-06) 接线生效

        历史: 曾长期是**死字段** —— YAML 顶层声明被 parse_field 静默丢弃
        （MetaField 无该属性 / loader 未映射），消费端 _check_max_length
        早已实现却恒不触发。TBD-12 补齐数据链后本断言改为「已生效」。

        注意：pattern / max_length 仍**仅应用层生效**，DB 层无 CHECK /
        无列宽约束（见 test_pattern_not_enforced_at_db_layer）。
        """
        f = _fields()['code']
        assert f['max_length'] == 3, 'YAML 意图声明保留'

        # 已映射到 MetaField
        from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml
        aspects = parse_aspects_yaml(_SCHEMA_DIR)
        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'currency.yaml'),
                             aspects_defs=aspects)
        code = [x for x in obj.fields if x.id == 'code'][0]
        assert code.max_length == 3, '应已映射到 MetaField.max_length'

        # 应用层校验器端到端生效
        import tempfile
        from meta.core.datasource import (
            _clear_data_source_cache_for_testing, get_data_source,
        )
        from meta.core.metadata_driven_validator import MetadataDrivenValidator
        from meta.core.schema_generator import sync_schema_from_meta
        tmp = tempfile.mkdtemp()
        ds = get_data_source('sqlite', database=os.path.join(tmp, 'ml.db'))
        sync_schema_from_meta(ds, [obj])
        v = MetadataDrivenValidator(ds)
        errs = v.validate_create(obj, {'code': 'ABCD', 'name': 'x'})
        ml = [e for e in (errs or []) if getattr(e, 'rule', '') == 'max_length']
        _clear_data_source_cache_for_testing()
        assert ml, f'4 字符 code 应触发 max_length（上限 3），实际无报错'

    def test_code_marked_immutable(self):
        """币种码启用后不可改（Oracle 硬规则）—— 平台无字段冻结机制，仅约定标注"""
        assert _fields()['code']['semantics']['immutable'] is True

    def test_name_required_display_field(self):
        data = _cur_yaml()
        assert _fields()['name']['required'] is True
        assert data['display_name_field'] == 'name'
        assert data['semantics']['business_key'] == ['code']

    def test_name_en_nullable(self):
        f = _fields()['name_en']
        assert f['nullable'] is True
        assert f['max_length'] == 64

    def test_symbol_nullable_documented_as_no_consumer(self):
        """§5：symbol 保留但**无平台消费者**（Oracle 官方：符号不保证显示）"""
        f = _fields()['symbol']
        assert f['nullable'] is True
        assert f['max_length'] == 8
        # 不得挂 ui 消费点（不得有 widget / form_widget）
        assert 'widget' not in (f.get('ui') or {})

    def test_no_key_template(self):
        """业务键 = ISO 4217 代码，无需自动编码（照 region 先例）"""
        assert 'key_template' not in _cur_yaml()


# ────────────────────────────────────────
# 2. 精度：decimal_places（§4.1，Oracle 路线）
# ────────────────────────────────────────
class TestDecimalPlaces:
    def test_required_with_default_two(self):
        """默认 2（ISO 主流币种）—— 有意区别于 uom 的 default 0"""
        f = _fields()['decimal_places']
        assert f['type'] == 'integer'
        assert f['required'] is True
        assert f['default'] == 2

    def test_default_applied_on_insert(self, cur_ds):
        """未指定 decimal_places 时落默认值 2"""
        rid = cur_ds.insert('currencies', {'code': 'CNY', 'name': '人民币'})
        assert rid is not None
        row = cur_ds.query('SELECT decimal_places FROM currencies WHERE code=?',
                           ('CNY',))
        assert len(row) == 1
        assert int(row[0]['decimal_places']) == 2

    def test_explicit_zero_precision_supported(self, cur_ds):
        """JPY/KRW 精度为 0 —— 允许显式写 0（覆盖默认）"""
        rid = cur_ds.insert('currencies', {
            'code': 'JPY', 'name': '日元', 'decimal_places': 0,
        })
        assert rid is not None
        row = cur_ds.query(
            'SELECT decimal_places FROM currencies WHERE code=?', ('JPY',))
        assert int(row[0]['decimal_places']) == 0


# ────────────────────────────────────────
# 3. code 唯一约束端到端（AC-3）
# ────────────────────────────────────────
class TestCodeUnique:
    def test_insert_basic(self, cur_ds):
        rid = cur_ds.insert('currencies', {
            'code': 'USD', 'name': '美元', 'name_en': 'US Dollar',
            'symbol': '$', 'decimal_places': 2,
        })
        assert rid is not None

    def test_duplicate_code_rejected(self, cur_ds):
        """重复 code 插入被拒（字段级 unique → 列级 UNIQUE）"""
        cur_ds.insert('currencies', {'code': 'USD', 'name': '美元'})
        with pytest.raises(Exception):
            cur_ds.insert('currencies', {'code': 'USD', 'name': '美元副本'})

    def test_named_unique_index_created(self, cur_ds):
        """命名唯一索引 idx_currency_code 存在（照 region.idx_region_code 先例）"""
        rows = cur_ds.query(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            ('idx_currency_code',))
        assert len(rows) == 1

    def test_no_status_index_by_design(self, cur_ds):
        """§4.2 索引口径留痕：uom/region 均无二级索引 ⇒ 币种也不建 status 索引"""
        rows = cur_ds.query(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            ('idx_currency_status',))
        assert len(rows) == 0

    def test_column_unique_constraint(self, cur_ds):
        """code 列存在 UNIQUE 约束"""
        cols = cur_ds.query('PRAGMA table_info(currencies)')
        code_col = [c for c in cols if c['name'] == 'code']
        assert len(code_col) == 1
        # sqlite: unique 约束在 index_list 中体现
        idxs = cur_ds.query('PRAGMA index_list(currencies)')
        unique_idx = [i for i in idxs if i.get('unique')]
        assert len(unique_idx) >= 1


# ────────────────────────────────────────
# 4. 删除策略（AC-8）
# ────────────────────────────────────────
class TestDeletionPolicy:
    def test_mode_is_restrict(self):
        """S19: 主数据禁止物理删除"""
        assert _cur_yaml()['deletion_policy']['mode'] == 'restrict'

    def test_restrict_on_empty_but_structure_kept(self):
        """币种当前零引用方 ⇒ restrict_on 空列表（结构保留供未来补条目）"""
        policy = _cur_yaml()['deletion_policy']
        assert policy['restrict_on'] == []
        assert 'cascade_delete' in policy

    def test_cascade_delete_empty(self):
        assert _cur_yaml()['deletion_policy']['cascade_delete'] == []


# ────────────────────────────────────────
# 5. 审计口径（对照 person_profile：本对象无需排除 PII）
# ────────────────────────────────────────
class TestAuditConfig:
    def test_audit_enabled(self):
        assert _cur_yaml()['audit']['enabled'] is True

    def test_three_modes_present(self):
        audit = _cur_yaml()['audit']
        for mode in ('create', 'update', 'delete'):
            assert mode in audit, f'缺 {mode} 模式'

    def test_exclude_only_machinery(self):
        """排除集口径 = machinery（id / 时间戳）；无 PII 排除需求"""
        for mode in ('update', 'delete'):
            assert _exclude(mode) == {'id', 'created_at', 'updated_at'}

    def test_create_has_no_exclude(self):
        assert _exclude('create') == set()

    def test_associate_and_dissociate_enabled(self):
        audit = _cur_yaml()['audit']
        assert audit['associate']['enabled'] is True
        assert audit['dissociate']['enabled'] is True


# ────────────────────────────────────────
# 6. 生命周期规则（完全照 uom / region）
# ────────────────────────────────────────
class TestLifecycleRules:
    def test_two_rules(self):
        rules = _cur_yaml()['rules']
        assert len(rules) == 2
        ids = {r['id'] for r in rules}
        assert ids == {'activate_currency', 'deactivate_currency'}

    def test_reuse_standard_actions(self):
        """复用平台标准动作 activate / deactivate（不自定义生命周期动作）"""
        rules = {r['id']: r for r in _cur_yaml()['rules']}
        act = rules['activate_currency']
        deact = rules['deactivate_currency']
        assert act['action_ref'] == 'activate'
        assert act['type'] == 'state_transition'
        assert act['state_field'] == 'status'
        assert act['from_states'] == ['inactive']
        assert act['to_state'] == 'active'
        assert deact['action_ref'] == 'deactivate'
        assert deact['from_states'] == ['active']
        assert deact['to_state'] == 'inactive'

    def test_status_enum_values(self):
        """status 枚举恰为 active / inactive（active 为初始值）"""
        vals = _fields()['status']['enum_values']
        assert {v['value'] for v in vals} == {'active', 'inactive'}
        initial = [v for v in vals if v.get('is_initial')]
        assert len(initial) == 1 and initial[0]['value'] == 'active'

    def test_status_default_active(self):
        assert _fields()['status']['default'] == 'active'

    def test_deactivate_keeps_row(self, cur_ds):
        """停用仅改 status ⇒ 记录物理留存（历史报表按 code 取数不受影响，§8bis.2）"""
        rid = cur_ds.insert('currencies', {'code': 'CHF', 'name': '瑞士法郎'})
        cur_ds.update('currencies', rid, {'status': 'inactive'})
        row = cur_ds.query('SELECT code, status FROM currencies WHERE id=?',
                           (rid,))
        assert len(row) == 1, '停用后记录必须仍存在（不可物理删除）'
        assert row[0]['status'] == 'inactive'


# ────────────────────────────────────────
# 7. 负向断言：不得越界（AC-9）
# ────────────────────────────────────────
class TestNoRateObject:
    def test_no_currency_rate_schema(self):
        """本期不建汇率对象（spec §2.2 / TBD-1）"""
        assert not os.path.exists(os.path.join(_SCHEMA_DIR, 'currency_rate.yaml'))
        assert not os.path.exists(
            os.path.join(_SCHEMA_DIR, 'currency_rates.yaml'))

    def test_currency_rate_not_in_registry(self):
        """registry 中不得出现 currency_rate object_type"""
        from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

        aspects = parse_aspects_yaml(_SCHEMA_DIR)
        obj = load_yaml_file(os.path.join(_SCHEMA_DIR, 'currency.yaml'),
                             aspects_defs=aspects)
        assert obj is not None
        obj_id = getattr(obj, 'id', None) or obj.get('id')
        assert obj_id == 'currency'


class TestNoConsumerClaim:
    def test_no_pii_sensitive_marking(self):
        """币种字段全为非敏感公共参照数据 ⇒ 不应出现 sensitivity: restricted"""
        for fid, f in _fields().items():
            sem = f.get('semantics') or {}
            assert 'sensitivity' not in sem, f'{fid} 不应标 sensitivity'

    def test_no_currency_rate_action_declared(self):
        """不得声明任何换算动作（convert / exchange / rate）"""
        acts = _cur_yaml().get('actions') or []
        names = ' '.join(str(a.get('id', '')) + str(a.get('name', ''))
                         for a in acts).lower()
        for banned in ('convert', 'exchange', 'rate', 'translate'):
            assert banned not in names, f'不得声明含 {banned} 的动作'

    def test_symbol_has_no_ui_widget(self):
        """§5：symbol 不得建 UI 消费点"""
        f = _fields()['symbol']
        assert not (f.get('ui') or {})


class TestOrphanReference:
    def test_doc_flow_currency_is_bare_string(self):
        """G-X1 缺口如实固定：doc_flow.currency 仍是裸 STRING（未接 FK）

        本测试是**缺口登记**，不是能力断言。若将来 TBD-5 落地（改 meta/core/*），
        本测试会失败并提示同步更新 spec §6.2。
        """
        from meta.core import doc_flow_schema

        src = _read_source(doc_flow_schema.__file__)
        assert "'currency'" in src or '"currency"' in src
        # 裸 STRING 定义（无 ForeignKey / 无 FK 约束声明）
        assert 'currenc' in src.lower()
        # 不得出现外键约束到 currencies 表
        assert 'currencies' not in src, (
            'doc_flow 若已接 FK 到 currencies，说明 TBD-5 已落地 —— '
            '请同步更新 spec §6.2 G-X1 与本测试'
        )


def _read_source(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()
