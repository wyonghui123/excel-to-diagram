# -*- coding: utf-8 -*-
"""TBD-12 元数据声明式约束接线测试 (2026-10-06)

依据: docs/superpowers/specs/2026-10-06-tbd9-metadata-constraint-wiring-design.md
      §1 根因 / §2 影响面 / §5 阶段 1 实施方案

背景（接线前的事实）:
  - metadata_driven_validator._check_pattern / _check_max_length **早已实现**（含 i18n）
  - 但 MetaField 无 pattern / max_length 属性，parse_field 也未映射
    ⇒ YAML 顶层写的 pattern / max_length 被**静默丢弃**（无报错无告警）
  - 受影响：pattern 9 处顶层声明（party/region/org/items/address/location/
    item_group/enum_value/sales_order_enhanced）+ max_length 14 schema / 40+ 处

本测试锁定「接线后行为」：
  ① 顶层 pattern 生效（修复前 FAIL）
  ② semantics.pattern 不回退
  ③ 顶层 max_length 生效
  ④ 不误伤 key_template 的 pattern（PATY-{SEQ:8} 走编码引擎）
  ⑤ 真实既有 schema（party/region）端到端生效
  ⑥ 非法值必须被拒（负向断言）

模式: S1-a 直连（PM 2026-10-06 拍板）—— 无影子开关，接线即严格。
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
def _load_field(name, field_id):
    """从真实 schema 加载单个字段的 MetaField"""
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    obj = load_yaml_file(os.path.join(_SCHEMA_DIR, name),
                         aspects_defs=aspects)
    assert obj is not None, f'{name} 加载失败'
    for f in obj.fields:
        if f.id == field_id:
            return f
    raise AssertionError(f'{name} 中找不到字段 {field_id}')


def _validator(tmp_path, name):
    from meta.core.datasource import get_data_source
    from meta.core.metadata_driven_validator import MetadataDrivenValidator
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    obj = load_yaml_file(os.path.join(_SCHEMA_DIR, name), aspects_defs=aspects)
    ds = get_data_source('sqlite',
                         database=str(tmp_path / f'{name.replace(".", "_")}.db'))
    sync_schema_from_meta(ds, [obj])
    return obj, MetadataDrivenValidator(ds)


def _pattern_errs(v, mo, code, field_id='code'):
    errs = v.validate_create(mo, {field_id: code, 'name': 'x'})
    return [e for e in (errs or []) if getattr(e, 'rule', '') == 'pattern']


def _maxlen_errs(v, mo, field_id, value):
    errs = v.validate_create(mo, {field_id: value})
    return [e for e in (errs or []) if getattr(e, 'rule', '') == 'max_length']


# ────────────────────────────────────────
# ① 顶层 pattern 生效（核心回归：修复前 FAIL）
# ────────────────────────────────────────
class TestTopLevelPatternWired:
    def test_metafield_has_pattern_attr(self):
        """MetaField 须有 pattern 属性（接线前不存在）"""
        from meta.core.models import MetaField
        assert hasattr(MetaField, 'pattern'), 'MetaField 缺 pattern（TBD-12 未实施？）'

    def test_metafield_has_max_length_attr(self):
        from meta.core.models import MetaField
        assert hasattr(MetaField, 'max_length'), 'MetaField 缺 max_length'

    @pytest.mark.parametrize('schema,field_id,expect', [
        ('party.yaml', 'code', r'^[A-Za-z0-9][A-Za-z0-9_\-]*$'),
        ('region.yaml', 'code', r'^[A-Za-z0-9]{2,12}$'),
        ('org.yaml', 'code', r'^[a-z][a-z0-9_]*$'),
        ('items.yaml', 'code', r'^[A-Za-z0-9][A-Za-z0-9_\-]*$'),
    ])
    def test_top_level_pattern_loaded(self, schema, field_id, expect):
        """顶层 pattern 须映射到 MetaField.pattern（接线前为空 ⇒ 静默失效）"""
        f = _load_field(schema, field_id)
        assert f.pattern == expect, (
            f'{schema}:{field_id} 顶层 pattern 未映射到 MetaField')

    def test_top_level_pattern_enforced_party(self, tmp_path):
        """端到端：party.code 顶层 pattern 现在真的生效"""
        mo, v = _validator(tmp_path, 'party.yaml')
        ok_errs = v.validate_create(mo, {'code': 'ABC', 'name': 'x'})
        bad_errs = v.validate_create(mo, {'code': 'has space', 'name': 'x'})
        assert not _pattern_errs(v, mo, 'ABC'), (
            f'合法 code 应放行, 实际错误={[str(e) for e in (ok_errs or [])]}')
        assert _pattern_errs(v, mo, 'has space'), '含空格 code 应被拒'
        assert _pattern_errs(v, mo, '中文'), '中文 code 应被拒'
        assert _pattern_errs(v, mo, '_leading'), '下划线开头应被拒'

    def test_top_level_pattern_enforced_region(self, tmp_path):
        """端到端：region.code 顶层 pattern（{2,12} 长度区间）生效"""
        mo, v = _validator(tmp_path, 'region.yaml')
        assert not _pattern_errs(v, mo, 'CN'), (
            f'2 位应放行, 实际={[str(e) for e in (v.validate_create(mo, {"code": "CN", "name": "x"}) or [])]}')
        assert _pattern_errs(v, mo, 'CN-SH'), '含连字符应被拒'
        assert _pattern_errs(v, mo, 'X'), '1 位应被拒（不足 2）'
        assert _pattern_errs(v, mo, 'ABCDEFGHIJKLM'), '13 位应被拒（超 12）'


# ────────────────────────────────────────
# ② semantics.pattern 不回退
# ────────────────────────────────────────
class TestSemanticsPatternNoRegression:
    @pytest.mark.parametrize('schema,field_id', [
        ('enum_type.yaml', 'id'),
        ('product.yaml', 'code'),
    ])
    def test_semantics_pattern_still_loaded(self, schema, field_id):
        """写在 semantics 下的 pattern 必须仍然生效（本就正确，不得回退）"""
        f = _load_field(schema, field_id)
        assert f.semantics.pattern, f'{schema}:{field_id} semantics.pattern 丢失'

    def test_semantics_pattern_still_enforced(self, tmp_path):
        """enum_type 的业务键字段 id 名为 'id'（db_column=id），
        其 pattern 写在 semantics 下（本就生效的一派），接线后不得回退"""
        mo, v = _validator(tmp_path, 'enum_type.yaml')
        assert _pattern_errs(v, mo, 'Bad_Case', 'id'), '大写开头应被拒'
        assert not _pattern_errs(v, mo, 'good_code', 'id'), '小写下划线应放行'


# ────────────────────────────────────────
# ③ 顶层 max_length 生效
# ────────────────────────────────────────
class TestMaxLengthWired:
    def test_max_length_loaded(self):
        """顶层 max_length 须映射（接线前被静默丢弃）"""
        assert _load_field('party.yaml', 'code').max_length == 20
        assert _load_field('region.yaml', 'code').max_length == 20
        assert _load_field('org.yaml', 'code').max_length == 50
        assert _load_field('items.yaml', 'code').max_length == 40

    def test_max_length_enforced_party(self, tmp_path):
        """端到端：party.code 超 20 字符被拒"""
        mo, v = _validator(tmp_path, 'party.yaml')
        assert not _maxlen_errs(v, mo, 'code', 'A' * 20), '恰好 20 应放行'
        assert _maxlen_errs(v, mo, 'code', 'A' * 21), '21 位应被拒'

    def test_max_length_enforced_items(self, tmp_path):
        mo, v = _validator(tmp_path, 'items.yaml')
        assert not _maxlen_errs(v, mo, 'code', 'B' * 40), '恰好 40 应放行'
        assert _maxlen_errs(v, mo, 'code', 'B' * 41), '41 位应被拒'

    def test_max_length_none_when_undeclared(self):
        """未声明 max_length 的字段须为 None（不得误伤）"""
        # party.party_type / party.source 声明了 max_length: 30；
        # party.party_type 的兄弟字段 code 才有 20 —— 此处取**确实未声明**的字段
        from meta.core.yaml_loader import parse_field
        f = parse_field({'id': 'x', 'name': 'X', 'type': 'string'})
        assert f.max_length is None, '未声明时须为 None'
        assert f.pattern == '', '未声明时 pattern 须为空串'

    def test_max_length_only_applies_to_string(self, tmp_path):
        """非 string/text 字段不做长度校验（消费端既有行为）"""
        mo, v = _validator(tmp_path, 'party.yaml')
        # id 是 integer，超长不应触发 max_length 规则
        errs = [e for e in (v.validate_create(mo, {
            'code': 'OK', 'name': 'x', 'id': 12345678901234,
        }) or []) if getattr(e, 'rule', '') == 'max_length']
        assert errs == [], 'integer 字段不应触发 max_length'


# ────────────────────────────────────────
# ④ 不误伤 key_template 的 pattern
# ────────────────────────────────────────
class TestKeyTemplatePatternUntouched:
    def test_key_template_pattern_is_template_syntax(self):
        """key_template.pattern 是编码模板语法，不是字段格式校验

        party.yaml:148 的 'PATY-{SEQ:8}' 若被 _check_pattern 消费会误拒所有 code。
        """
        import yaml
        with open(os.path.join(_SCHEMA_DIR, 'party.yaml'), 'r',
                  encoding='utf-8') as f:
            data = yaml.safe_load(f)
        kt = (data.get('key_template') or {})
        assert '{SEQ:' in str(kt.get('pattern', '')), (
            'key_template 形态变化 —— 本测试的「不误伤」前提需重估')

    def test_key_template_block_has_no_field_pattern(self):
        """key_template 是独立块，不参与 fields[].pattern 映射"""
        f = _load_field('party.yaml', 'code')
        # 字段级 pattern 应是字段正则，而非模板串
        assert '{' not in f.pattern and '}' not in f.pattern, (
            '字段 pattern 被误填为 key_template 模板串')

    def test_party_code_still_validates_against_field_pattern(self, tmp_path):
        """回归：接线后 party.code 仍按字段正则校验（非模板）"""
        mo, v = _validator(tmp_path, 'party.yaml')
        assert _pattern_errs(v, mo, 'has space'), '应按字段正则拒绝'


# ────────────────────────────────────────
# ⑤⑥ 负向：非法值必拒 + 既有 schema 无回退
# ────────────────────────────────────────
class TestNoFalsePass:
    def test_pattern_invalid_rejected_not_silently_passed(self, tmp_path):
        """核心负向：接线前非法值**静默通过**，接线后必须被拒"""
        mo, v = _validator(tmp_path, 'party.yaml')
        assert _pattern_errs(v, mo, 'bad code!'), '非法 code 必须被拒（不得静默放行）'

    def test_max_length_invalid_rejected(self, tmp_path):
        mo, v = _validator(tmp_path, 'party.yaml')
        assert _maxlen_errs(v, mo, 'code', 'X' * 100), '超长必须被拒'

    def test_address_and_location_and_item_group(self, tmp_path):
        """其余受影响对象一并生效（address/location/item_group）"""
        for schema in ('address.yaml', 'location.yaml', 'item_group.yaml'):
            f = _load_field(schema, 'code')
            assert f.pattern, f'{schema} 顶层 pattern 未生效'

    def test_invalid_max_length_type_ignored(self):
        """max_length 写成非数字时应忽略并告警，不得抛异常"""
        from meta.core.yaml_loader import parse_field
        f = parse_field({
            'id': 'x', 'name': 'X', 'type': 'string',
            'max_length': 'not-a-number',
        })
        assert f.max_length is None, '非法 max_length 应被忽略为 None'
