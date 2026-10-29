# -*- coding: utf-8 -*-
"""test_revision_service.py

M2 T2/T3 版本服务单测（临时 SQLite 库）。

覆盖 spec §4：
  · record()              —— 版本唯一写入口；disabled 零操作；只记 diff:true 字段
  · collect_snapshot()    —— 抬头 + 子行自动发现（source_field 为空则跳过）
  · diff()                —— a==b 空差异；缺失报 REVISION_NOT_FOUND；方向 b→a；header/lines 分类
  · restore_payload()     —— 永不还原 status / 履约派生字段
  · update_with_revision()—— 命中 True / 版本不符 False / 不自动推进 revision_no
  · list_revisions()      —— 升序 + summary

注意：SQLiteAdapter 的全部 CRUD 都会 validate_table_name，
因此临时表必须逐个 register_table_name（含两张版本表）。
"""
import json
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.models import (
    FieldType,
    MetaField,
    MetaObject,
    MetaRelation,
    MetaRevisionPolicy,
    RelationType,
    RevisionFieldPolicy,
)
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.table_name_validator import register_table_name
from meta.services import revision_service
from meta.services.revision_service import (
    CHANGES_TABLE,
    NON_CONTENT_FIELDS,
    REVISIONS_TABLE,
    RevisionError,
    collect_snapshot,
    content_changed,
    diff,
    diff_fields,
    list_revisions,
    record,
    restore_payload,
    update_with_revision,
)

DDL = {
    'rev_order': """
        CREATE TABLE IF NOT EXISTS rev_order (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            total_amount INTEGER,
            customer_id INTEGER,
            status TEXT,
            fulfillment_status TEXT,
            fulfillment_derived_at TEXT,
            revision_no INTEGER DEFAULT 1
        )
    """,
    'rev_order_line': """
        CREATE TABLE IF NOT EXISTS rev_order_line (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            sku TEXT,
            qty INTEGER
        )
    """,
    REVISIONS_TABLE: """
        CREATE TABLE IF NOT EXISTS document_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT NOT NULL,
            object_id TEXT NOT NULL,
            revision_no INTEGER NOT NULL,
            snapshot TEXT,
            change_request_id TEXT,
            reason_code TEXT,
            change_set_id TEXT,
            created_by TEXT,
            created_at TEXT
        )
    """,
    CHANGES_TABLE: """
        CREATE TABLE IF NOT EXISTS document_revision_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            revision_id INTEGER NOT NULL,
            line_key TEXT,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT
        )
    """,
}


class RegistryStub:
    """替代 meta.core.models.registry，控制子对象发现。"""

    def __init__(self, objects=()):
        self._objects = list(objects)

    def all(self):
        return list(self._objects)


@pytest.fixture
def ds(tmp_path):
    data_source = SQLiteAdapter()
    data_source.connect(path=str(tmp_path / 'rev.db'))
    for name, ddl in DDL.items():
        data_source.execute(ddl)
        register_table_name(name)
    yield data_source
    data_source.disconnect()


@pytest.fixture(autouse=True)
def empty_registry(monkeypatch):
    """默认不扫描真实 registry（避免依赖生产元模型）。"""
    monkeypatch.setattr('meta.core.models.registry', RegistryStub())


def _obj(fields=None, **policy_kwargs):
    obj = MetaObject(
        id='rev_order',
        name='订单',
        table_name='rev_order',
        fields=[
            MetaField(id='id', name='ID', field_type=FieldType.INTEGER,
                      db_column='id', required=True),
            MetaField(id='name', name='名称', field_type=FieldType.STRING,
                      db_column='name'),
            MetaField(id='total_amount', name='总额', field_type=FieldType.INTEGER,
                      db_column='total_amount'),
            MetaField(id='customer_id', name='客户', field_type=FieldType.INTEGER,
                      db_column='customer_id'),
            MetaField(id='status', name='状态', field_type=FieldType.STRING,
                      db_column='status'),
            MetaField(id='fulfillment_status', name='履约状态',
                      field_type=FieldType.STRING, db_column='fulfillment_status'),
            MetaField(id='fulfillment_derived_at', name='履约派生时间',
                      field_type=FieldType.STRING, db_column='fulfillment_derived_at'),
            MetaField(id='revision_no', name='版本号', field_type=FieldType.INTEGER,
                      db_column='revision_no'),
        ],
    )
    if fields is None:
        fields = [RevisionFieldPolicy(field='total_amount', diff=True)]
    obj.revision_policy = MetaRevisionPolicy(
        enabled=True, fields=fields, **policy_kwargs)
    return obj


def _insert_order(ds, **overrides):
    data = {
        'name': 'order-1',
        'total_amount': 100,
        'customer_id': 7,
        'status': 'draft',
        'fulfillment_status': 'not_started',
        'revision_no': 1,
    }
    data.update(overrides)
    return ds.insert('rev_order', data)


def _seed_two_revisions(ds):
    """两条版本：rev 2（100→200）、rev 3（200→300）。返回 (obj, rev2_row, rev3_row)。"""
    obj = _obj()
    with ds.transaction():
        record(ds, obj, 1, {'total_amount': 100}, {'total_amount': 200},
               {'total_amount'}, revision_no=2)
        record(ds, obj, 1, {'total_amount': 200}, {'total_amount': 300},
               {'total_amount'}, revision_no=3)
    rev2 = ds.find(REVISIONS_TABLE, {'revision_no': 2})[0]
    rev3 = ds.find(REVISIONS_TABLE, {'revision_no': 3})[0]
    return obj, rev2, rev3


# ---------------------------------------------------------------- 纯函数

class TestPureHelpers:
    def test_diff_fields_only_diff_true(self):
        obj = _obj(fields=[
            RevisionFieldPolicy(field='total_amount', diff=True),
            RevisionFieldPolicy(field='customer_id', diff=False),
            RevisionFieldPolicy(field='name', audit=False),
        ])
        assert diff_fields(obj) == {'total_amount'}

    def test_diff_fields_without_policy(self):
        obj = MetaObject(id='x', name='x', table_name='x')
        assert diff_fields(obj) == set()

    def test_content_changed_removes_non_content(self):
        assert content_changed({'status', 'total_amount', 'fulfillment_status',
                                'fulfillment_derived_at', 'name',
                                'updated_by'}) == {
            'total_amount', 'name'}

    def test_non_content_fields_frozen(self):
        # FR-012 基础三项 + updated_by：
        # action_executor._prepare_data 的 auto_fill.on_update 会把 updated_by 回写进
        # data（无请求上下文时为 ''），它属审计元数据而非单据内容；
        # 若不剔除，纯状态更新会被误判为内容变更而空推进 revision_no（2026-10-29 缺陷）。
        assert NON_CONTENT_FIELDS == {
            'status', 'fulfillment_status', 'fulfillment_derived_at',
            'updated_by'}


# ---------------------------------------------------------------- record

class TestRecord:
    def test_disabled_is_noop(self, ds):
        obj = _obj()
        obj.revision_policy.enabled = False
        assert record(ds, obj, 1, {'total_amount': 100}, {'total_amount': 200},
                      {'total_amount'}, revision_no=2) == 2
        assert ds.find(REVISIONS_TABLE) == []
        assert ds.find(CHANGES_TABLE) == []

    def test_writes_revision_and_only_diff_rows(self, ds):
        obj = _obj()
        assert record(
            ds, obj, 7,
            before={'total_amount': 100, 'customer_id': 7, 'name': 'a'},
            after={'total_amount': 200, 'customer_id': 9, 'name': 'b'},
            changed_fields={'total_amount', 'customer_id', 'name'},
            revision_no=2,
            reason_code='PRICE_FIX',
            change_set_id='cs_0123456789abcdef',
            user={'username': 'alice'},
        ) == 2

        rows = ds.find(REVISIONS_TABLE)
        assert len(rows) == 1
        row = rows[0]
        assert row['object_type'] == 'rev_order'
        assert row['object_id'] == '7'
        assert row['revision_no'] == 2
        assert row['change_request_id'] is None
        assert row['reason_code'] == 'PRICE_FIX'
        assert row['change_set_id'] == 'cs_0123456789abcdef'
        assert row['created_by'] == 'alice'
        assert row['created_at']
        assert json.loads(row['snapshot']) == {'header': {}, 'lines': {}}

        changes = ds.find(CHANGES_TABLE, {'revision_id': row['id']})
        assert [(c['field_name'], c['old_value'], c['new_value']) for c in changes] == [
            ('total_amount', '100', '200')]
        assert all(c['line_key'] is None for c in changes)

    def test_user_dict_fallbacks(self, ds):
        obj = _obj()
        record(ds, obj, 1, {}, {}, set(), revision_no=2, user={'display_name': 'Bob'})
        record(ds, obj, 1, {}, {}, set(), revision_no=3, user={'user_id': 'u-9'})
        record(ds, obj, 1, {}, {}, set(), revision_no=4, user='raw-user')
        creators = [r['created_by'] for r in ds.find(REVISIONS_TABLE, order_by='revision_no ASC')]
        assert creators == ['Bob', 'u-9', 'raw-user']

    def test_null_values_kept_null(self, ds):
        obj = _obj()
        record(ds, obj, 1, {'total_amount': 100}, {'total_amount': None},
               {'total_amount'}, revision_no=2)
        changes = ds.find(CHANGES_TABLE)
        assert changes[0]['old_value'] == '100'
        assert changes[0]['new_value'] is None

    def test_explicit_snapshot_used(self, ds):
        obj = _obj()
        snapshot = {'header': {'total_amount': 200}, 'lines': {}}
        record(ds, obj, 1, {}, {}, {'total_amount'}, revision_no=2, snapshot=snapshot)
        row = ds.find(REVISIONS_TABLE)[0]
        assert json.loads(row['snapshot']) == snapshot

    def test_snapshot_includes_child_lines(self, ds, monkeypatch):
        child = MetaObject(
            id='rev_order_line', name='行', table_name='rev_order_line',
            relations=[MetaRelation(
                id='rel_line', name='订单', relation_type=RelationType.PARENT_CHILD,
                target_object='rev_order', source_field='order_id')],
        )
        orphan = MetaObject(
            id='rev_orphan_line', name='孤儿', table_name='rev_orphan_line',
            relations=[MetaRelation(
                id='rel_orphan', name='订单', relation_type=RelationType.PARENT_CHILD,
                target_object='rev_order', source_field='')],
        )
        monkeypatch.setattr('meta.core.models.registry',
                            RegistryStub([child, orphan]))
        _insert_order(ds, total_amount=300)
        ds.insert('rev_order_line', {'order_id': 1, 'sku': 'A', 'qty': 2})
        ds.insert('rev_order_line', {'order_id': 2, 'sku': 'B', 'qty': 5})

        result = collect_snapshot(ds, _obj(), 1)

        assert result['header']['total_amount'] == 300
        assert result['lines'] == {'rev_order_line': [
            {'id': 1, 'order_id': 1, 'sku': 'A', 'qty': 2}]}

    def test_snapshot_empty_source_field_skipped(self, ds, monkeypatch):
        """relations.source_field 为空 ⇒ 不查表、不收录子行。"""
        orphan = MetaObject(
            id='rev_orphan_line', name='孤儿', table_name='rev_orphan_line',
            relations=[MetaRelation(
                id='rel_orphan', name='订单', relation_type=RelationType.PARENT_CHILD,
                target_object='rev_order', source_field='')],
        )
        monkeypatch.setattr('meta.core.models.registry', RegistryStub([orphan]))
        _insert_order(ds)

        result = collect_snapshot(ds, _obj(), 1)

        assert result['header']['id'] == 1
        assert result['lines'] == {}


# ---------------------------------------------------------------- diff

class TestDiff:
    def test_same_revision_empty(self, ds):
        _seed_two_revisions(ds)
        assert diff(ds, 'rev_order', 1, 2, 2) == {'header': [], 'lines': []}

    def test_same_revision_missing_raises(self, ds):
        _seed_two_revisions(ds)
        with pytest.raises(RevisionError) as ei:
            diff(ds, 'rev_order', 1, 9, 9)
        assert ei.value.code == 'REVISION_NOT_FOUND'

    def test_missing_side_raises(self, ds):
        _seed_two_revisions(ds)
        with pytest.raises(RevisionError) as ei:
            diff(ds, 'rev_order', 1, 2, 9)
        assert ei.value.code == 'REVISION_NOT_FOUND'
        assert '9' in ei.value.message

    def test_direction_b_to_a_and_classification(self, ds):
        _, rev2, rev3 = _seed_two_revisions(ds)
        # 人工插入一条行级差异（line_key 非空 → 归入 lines）
        ds.insert(CHANGES_TABLE, {
            'revision_id': rev2['id'], 'line_key': 'L1',
            'field_name': 'qty', 'old_value': '1', 'new_value': '2',
        })

        result = diff(ds, 'rev_order', 1, rev_a=3, rev_b=2)

        assert result['header'] == [
            {'field_name': 'total_amount', 'old_value': '200', 'new_value': '300'}]
        assert result['lines'] == [
            {'field_name': 'qty', 'old_value': '2', 'new_value': None,
             'line_key': 'L1'}]
        assert rev3['revision_no'] == 3

    def test_reverse_direction(self, ds):
        _seed_two_revisions(ds)
        result = diff(ds, 'rev_order', 1, rev_a=2, rev_b=3)
        assert result['header'] == [
            {'field_name': 'total_amount', 'old_value': '300', 'new_value': '200'}]


# ---------------------------------------------------------------- restore_payload

class TestRestorePayload:
    SNAPSHOT = {
        'header': {
            'name': 'order-1', 'total_amount': 200,
            'status': 'approved', 'fulfillment_status': 'fulfilled',
            'fulfillment_derived_at': '2026-10-29 00:00:00',
        },
        'lines': {},
    }

    def test_excludes_non_content_fields(self):
        payload = restore_payload(self.SNAPSHOT)
        assert payload == {'name': 'order-1', 'total_amount': 200}

    def test_limited_to_given_fields(self):
        assert restore_payload(self.SNAPSHOT, ['total_amount', 'status']) == {
            'total_amount': 200}

    def test_str_input_parsed(self):
        assert restore_payload(json.dumps(self.SNAPSHOT)) == {
            'name': 'order-1', 'total_amount': 200}

    def test_invalid_json_returns_empty(self):
        assert restore_payload('{not-json') == {}

    def test_non_dict_returns_empty(self):
        assert restore_payload(None) == {}
        assert restore_payload(['x']) == {}


# ---------------------------------------------------------------- update_with_revision

class TestUpdateWithRevision:
    def test_hit_and_no_auto_increment(self, ds):
        _insert_order(ds)
        with ds.transaction():
            assert update_with_revision(
                ds, 'rev_order', 1, {'name': 'x'}, expected_revision=1) is True
        row = ds.find_by_id('rev_order', 1)
        assert row['name'] == 'x'
        assert row['revision_no'] == 1

    def test_mismatch_returns_false_and_no_write(self, ds):
        _insert_order(ds)
        with ds.transaction():
            assert update_with_revision(
                ds, 'rev_order', 1, {'name': 'y'}, expected_revision=5) is False
        assert ds.find_by_id('rev_order', 1)['name'] == 'order-1'

    def test_empty_data_returns_false(self, ds):
        _insert_order(ds)
        assert update_with_revision(
            ds, 'rev_order', 1, {}, expected_revision=1) is False


# ---------------------------------------------------------------- list_revisions

class TestListRevisions:
    def test_ascending_with_summary(self, ds):
        _seed_two_revisions(ds)
        rows = list_revisions(ds, 'rev_order', 1)
        assert [r['revision_no'] for r in rows] == [2, 3]
        assert [r['summary'] for r in rows] == ['1 个字段变更', '1 个字段变更']
        assert rows[0]['created_by'] is None
        assert rows[0]['reason_code'] is None
        assert rows[0]['change_set_id'] is None
        assert rows[0]['created_at']

    def test_other_object_isolated(self, ds):
        _seed_two_revisions(ds)
        assert list_revisions(ds, 'rev_order', 2) == []


# ---------------------------------------------------------------- 模块边界

class TestModuleSurface:
    def test_no_update_or_delete_exported(self):
        """版本表 append-only：模块不提供 update / delete。"""
        assert not hasattr(revision_service, 'update_revision')
        assert not hasattr(revision_service, 'delete_revision')
