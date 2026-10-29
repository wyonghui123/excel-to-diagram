# -*- coding: utf-8 -*-
"""
test_revision_policy_load.py

T5：FR-011 revision_policy 加载期校验（M2）

覆盖：
  L1  无 revision_policy 段 ⇒ None（零回归）
  L2  parse_meta_object 正确挂载 revision_policy（默认值 + 全量字段）
  L3  fields 引用未声明字段 ⇒ ValueError（含对象 id + 字段名）
  L4  派生字段 fulfillment_status / fulfillment_derived_at 声明 editable 或 diff ⇒ ValueError
  L5  派生字段仅 audit（不 editable/diff）⇒ 放行
  L6  scope != header 且 enabled ⇒ ValueError；enabled=False 时不报错
  L7  reason_required_fields 引用未声明字段 ⇒ ValueError
  L8  source_file 透传：错误消息含文件名 + 字段名
  L9  load_yaml_file：非法 policy ⇒ 返回 None 且打印含文件名；合法 policy ⇒ 正常挂载
  L10 字符串形式的 fields 项 ⇒ editable/diff False，audit True

设计取舍：
  - 纯解析层，不依赖 DB / registry。
  - load_yaml_file 历史上对解析异常是「打印 + 返回 None」，T5 只补强消息内容，
    不改这条既有行为；因此 L9 用 capsys 断言打印内容，不期望异常外抛。
"""
import os
import sys

import pytest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.yaml_loader import (
    parse_meta_object, parse_revision_policy, load_yaml_file,
)
from meta.core.models import MetaRevisionPolicy, RevisionFieldPolicy


FIELD_IDS = [
    'id', 'name', 'total_amount', 'customer_id', 'status',
    'fulfillment_status', 'fulfillment_derived_at',
]


def _base_data(**policy):
    """最小可解析对象；policy 传入 dict 即写入 revision_policy 段。"""
    data = {
        'id': 'rev_order',
        'name': '订单',
        'table_name': 'rev_order',
        'fields': [
            {'id': 'id', 'name': 'ID', 'type': 'integer', 'db_column': 'id'},
            {'id': 'name', 'name': '名称', 'type': 'string', 'db_column': 'name'},
            {'id': 'total_amount', 'name': '总额', 'type': 'integer',
             'db_column': 'total_amount'},
            {'id': 'customer_id', 'name': '客户', 'type': 'integer',
             'db_column': 'customer_id'},
            {'id': 'status', 'name': '状态', 'type': 'string', 'db_column': 'status'},
            {'id': 'fulfillment_status', 'name': '履约状态', 'type': 'string',
             'db_column': 'fulfillment_status'},
            {'id': 'fulfillment_derived_at', 'name': '履约派生时间', 'type': 'string',
             'db_column': 'fulfillment_derived_at'},
        ],
    }
    if policy:
        data['revision_policy'] = policy
    return data


# ---------------------------------------------------------------- L1/L2 挂载

class TestMount:
    def test_l1_no_policy_returns_none(self):
        """L1 没有 revision_policy 段 ⇒ 对象行为完全不变。"""
        obj = parse_meta_object(_base_data())
        assert obj.revision_policy is None

    def test_l2_defaults(self):
        """L2 只声明 enabled ⇒ 其余字段走默认值。"""
        obj = parse_meta_object(_base_data(enabled=True))
        rp = obj.revision_policy
        assert isinstance(rp, MetaRevisionPolicy)
        assert rp.enabled is True
        assert rp.scope == 'header'
        assert rp.revision_field == 'revision_no'
        assert rp.generate_on == ['content_update']
        assert rp.require_reason is False
        assert rp.reason_required_fields == []
        assert rp.editable_in_states == []
        assert rp.editable_when == ''
        assert rp.fields == []

    def test_l2_full_config(self):
        """L2 全量字段原样解析。"""
        obj = parse_meta_object(_base_data(
            enabled=True,
            scope='header',
            revision_field='ver_no',
            generate_on=['content_update', 'submit'],
            require_reason=True,
            reason_required_fields=['total_amount'],
            editable_in_states=['draft'],
            editable_when="status == 'draft'",
            fields=[{'field': 'total_amount', 'editable': True, 'diff': True}],
        ))
        rp = obj.revision_policy
        assert rp.revision_field == 'ver_no'
        assert rp.generate_on == ['content_update', 'submit']
        assert rp.require_reason is True
        assert rp.reason_required_fields == ['total_amount']
        assert rp.editable_in_states == ['draft']
        assert rp.editable_when == "status == 'draft'"
        assert rp.fields == [RevisionFieldPolicy(
            field='total_amount', editable=True, diff=True, audit=True)]

    def test_l10_string_field_form(self):
        """L10 fields 写字符串 ⇒ editable/diff False，audit True。"""
        obj = parse_meta_object(_base_data(
            enabled=True, fields=['total_amount'],
        ))
        row = obj.revision_policy.fields[0]
        assert row.field == 'total_amount'
        assert row.editable is False
        assert row.diff is False
        assert row.audit is True

    def test_l6_disabled_non_header_allowed(self):
        """L6 enabled=False 时 scope 非 header 不报错（仅记录）。"""
        obj = parse_meta_object(_base_data(enabled=False, scope='line'))
        assert obj.revision_policy.scope == 'line'
        assert obj.revision_policy.enabled is False


# ---------------------------------------------------------------- L3~L8 校验

class TestValidationErrors:
    def test_l3_unknown_field(self):
        """L3 fields 引用未声明字段 ⇒ ValueError，消息含对象 id + 字段名。"""
        with pytest.raises(ValueError) as ei:
            parse_meta_object(_base_data(
                enabled=True, fields=[{'field': 'not_exist'}],
            ))
        msg = str(ei.value)
        assert 'rev_order' in msg
        assert 'not_exist' in msg

    def test_l7_unknown_reason_field(self):
        """L7 reason_required_fields 引用未声明字段 ⇒ ValueError。"""
        with pytest.raises(ValueError) as ei:
            parse_meta_object(_base_data(
                enabled=True, reason_required_fields=['not_exist'],
            ))
        msg = str(ei.value)
        assert 'reason_required_fields' in msg
        assert 'not_exist' in msg

    def test_l4_derived_field_editable(self):
        """L4 fulfillment_status 声明 editable ⇒ ValueError。"""
        with pytest.raises(ValueError) as ei:
            parse_meta_object(_base_data(
                enabled=True,
                fields=[{'field': 'fulfillment_status', 'editable': True}],
            ))
        assert '派生字段' in str(ei.value)

    def test_l4_derived_field_diff(self):
        """L4 fulfillment_derived_at 声明 diff ⇒ ValueError。"""
        with pytest.raises(ValueError) as ei:
            parse_meta_object(_base_data(
                enabled=True,
                fields=[{'field': 'fulfillment_derived_at', 'diff': True}],
            ))
        assert '派生字段' in str(ei.value)

    def test_l6_scope_not_supported_when_enabled(self):
        """L6 enabled=True 且 scope != header ⇒ ValueError。"""
        with pytest.raises(ValueError) as ei:
            parse_meta_object(_base_data(enabled=True, scope='line'))
        msg = str(ei.value)
        assert 'scope' in msg
        assert 'line' in msg

    def test_l8_source_file_in_error(self):
        """L8 source_file 透传 ⇒ 错误消息含文件名 + 字段名。"""
        with pytest.raises(ValueError) as ei:
            parse_meta_object(
                _base_data(enabled=True, fields=[{'field': 'not_exist'}]),
                source_file='meta/schemas/rev_order.yaml',
            )
        msg = str(ei.value)
        assert 'meta/schemas/rev_order.yaml' in msg
        assert 'not_exist' in msg

    def test_l8_parse_revision_policy_direct(self):
        """L8 parse_revision_policy 直接调用时同样带文件名。"""
        with pytest.raises(ValueError) as ei:
            parse_revision_policy(
                _base_data(enabled=True,
                           fields=[{'field': 'fulfillment_status', 'diff': True}]),
                FIELD_IDS,
                source_file='sales_order.yaml',
            )
        assert 'sales_order.yaml' in str(ei.value)
        assert 'fulfillment_status' in str(ei.value)


# ---------------------------------------------------------------- L5 派生字段容错

class TestDerivedFieldTolerance:
    def test_l5_derived_audit_only_allowed(self):
        """L5 派生字段只声明 audit（不 editable/diff）⇒ 放行。"""
        obj = parse_meta_object(_base_data(
            enabled=True,
            fields=[{'field': 'fulfillment_status', 'audit': False}],
        ))
        row = obj.revision_policy.fields[0]
        assert row.field == 'fulfillment_status'
        assert row.editable is False
        assert row.diff is False
        assert row.audit is False


# ---------------------------------------------------------------- L9 文件加载

class TestLoadYamlFile:
    def _write(self, tmp_path, data, name='rev_order.yaml'):
        path = tmp_path / name
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding='utf-8',
        )
        return str(path)

    def test_l9_invalid_policy_rejected_with_file_name(self, tmp_path, capsys):
        """L9 非法 policy ⇒ load_yaml_file 返回 None，打印含文件名 + 字段名。"""
        path = self._write(tmp_path, _base_data(
            enabled=True, fields=[{'field': 'fulfillment_status', 'editable': True}],
        ))
        obj = load_yaml_file(path)
        out = capsys.readouterr().out
        assert obj is None
        assert 'rev_order.yaml' in out
        assert 'fulfillment_status' in out

    def test_l9_valid_policy_loaded(self, tmp_path):
        """L9 合法 policy ⇒ 正常加载并挂载。"""
        path = self._write(tmp_path, _base_data(
            enabled=True,
            fields=[{'field': 'total_amount', 'diff': True}],
        ))
        obj = load_yaml_file(path)
        assert obj is not None
        assert obj.revision_policy is not None
        assert obj.revision_policy.enabled is True
        assert obj.revision_policy.fields == [RevisionFieldPolicy(
            field='total_amount', editable=False, diff=True, audit=True)]


# ---------------------------------------------------------------- T7 真实 schema

def test_sales_order_declares_revision_policy():
    """T7 真实 schema：sales_order.yaml 已声明 revision_policy（TR-003 未决 ⇒ enabled=False）。"""
    from pathlib import Path
    from meta.core.yaml_loader import get_yaml_schema_dir
    data = yaml.safe_load(
        (Path(get_yaml_schema_dir()) / 'sales_order.yaml').read_text(encoding='utf-8')
    )
    field_ids = [f['id'] for f in data['fields']]
    policy = parse_revision_policy(data, field_ids)
    assert policy is not None
    assert policy.enabled is True           # TR-003 已开启
    assert policy.scope == 'header'
    assert policy.revision_field == 'revision_no'
    assert policy.require_reason is True
    assert {f.field for f in policy.fields if f.diff} == {
        'customer_account_id', 'gross_amount', 'header_discount_percent', 'status'}
