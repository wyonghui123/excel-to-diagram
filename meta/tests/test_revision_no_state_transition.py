# -*- coding: utf-8 -*-
"""test_revision_no_state_transition.py

M2 T3/T4 集成测试：`ActionExecutor._do_update` 的版本记录与闸门行为。

覆盖：
  · enabled=False                    —— 零逻辑（不写版本、revision_no 不变）
  · 内容变更                          —— revision_no +1、1 版本行、仅 diff 字段差异行
  · FR-012                           —— status / fulfillment_status 单独变更不出版本
  · FR-010 乐观锁                     —— 影响 0 行 ⇒ REVISION_CONFLICT，回滚且不写审计
  · FR-006 闸门                       —— partial / 状态白名单
  · change_set_id                    —— 版本行与审计行共享同一 cs_（D4 前移）
  · reason_code                      —— 落入版本行

设计取舍：
  - 用 autouse fixture 把 meta.core.models.registry 换成空 stub，
    阻断 collect_snapshot 扫描真实元模型（避免依赖生产对象表）；
  - _write_audit_log_v2 在 pytest 下直接 return，因此用 spy 捕获 change_set_id。
"""
import json
import os
import re
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.action_executor import ActionExecutor
from meta.core.models import (
    ActionType,
    FieldType,
    MetaAction,
    MetaField,
    MetaObject,
    MetaRevisionPolicy,
    RevisionFieldPolicy,
)
from meta.core.rule_executor import RuleEngine
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.table_name_validator import register_table_name
from meta.services import revision_service
from meta.services.revision_service import CHANGES_TABLE, REVISIONS_TABLE

CS_PATTERN = re.compile(r'^cs_[0-9a-f]{16}$')

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
    def __init__(self, objects=()):
        self._objects = list(objects)

    def all(self):
        return list(self._objects)


@pytest.fixture
def ds(tmp_path):
    data_source = SQLiteAdapter()
    data_source.connect(path=str(tmp_path / 'rev_state.db'))
    for name, ddl in DDL.items():
        data_source.execute(ddl)
        register_table_name(name)
    yield data_source
    data_source.disconnect()


@pytest.fixture(autouse=True)
def empty_registry(monkeypatch):
    monkeypatch.setattr('meta.core.models.registry', RegistryStub())


@pytest.fixture
def executor(ds):
    return ActionExecutor(ds, RuleEngine(ds), audit_enabled=True)


@pytest.fixture
def spy_audit(monkeypatch):
    calls = []

    def spy(self, audit_fn, reason_code=None, exclude_fields=None, change_set_id=None):
        calls.append({'reason_code': reason_code, 'exclude_fields': exclude_fields,
                      'change_set_id': change_set_id})

    monkeypatch.setattr(ActionExecutor, '_write_audit_log_v2', spy)
    return calls


@pytest.fixture
def spy_record(monkeypatch):
    calls = []
    real = revision_service.record

    def wrapper(*args, **kwargs):
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(revision_service, 'record', wrapper)
    return calls


def _policy(**kwargs):
    return MetaRevisionPolicy(**kwargs)


def _make_obj(policy=None):
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
        actions=[
            MetaAction(id='crud_update', name='更新', action_type=ActionType.CRUD,
                       method='PUT', path=''),
        ],
    )
    obj.revision_policy = policy
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


DIFF_TOTAL = [RevisionFieldPolicy(field='total_amount', diff=True)]


# ---------------------------------------------------------------- enabled=False

class TestDisabledPolicy:
    def test_zero_logic(self, ds, executor, spy_record, spy_audit):
        _insert_order(ds)

        result = executor._do_update(
            _make_obj(_policy(enabled=False)), {'id': 1, 'total_amount': 200})

        assert result.success is True, result.message
        row = ds.find_by_id('rev_order', 1)
        assert row['total_amount'] == 200
        assert row['revision_no'] == 1
        assert spy_record == []
        assert ds.find(REVISIONS_TABLE) == []
        assert spy_audit[0]['change_set_id'] is not None


# ---------------------------------------------------------------- 内容变更

class TestContentChange:
    def test_bumps_revision_and_records(self, ds, executor, spy_audit):
        _insert_order(ds)
        obj = _make_obj(_policy(enabled=True, fields=DIFF_TOTAL))

        result = executor._do_update(
            obj, {'id': 1, 'total_amount': 200, 'customer_id': 9})

        assert result.success is True, result.message
        row = ds.find_by_id('rev_order', 1)
        assert row['total_amount'] == 200
        assert row['customer_id'] == 9
        assert row['revision_no'] == 2

        revs = ds.find(REVISIONS_TABLE)
        assert len(revs) == 1
        rev = revs[0]
        assert rev['object_type'] == 'rev_order'
        assert rev['object_id'] == '1'
        assert rev['revision_no'] == 2
        assert rev['created_by'] is None
        assert CS_PATTERN.match(rev['change_set_id'])
        assert len(spy_audit) == 1
        assert spy_audit[0]['change_set_id'] == rev['change_set_id']

        snapshot = json.loads(rev['snapshot'])
        assert snapshot['header']['total_amount'] == 200
        assert snapshot['header']['revision_no'] == 2
        assert snapshot['lines'] == {}

        changes = ds.find(CHANGES_TABLE, {'revision_id': rev['id']})
        assert [(c['field_name'], c['old_value'], c['new_value']) for c in changes] == [
            ('total_amount', '100', '200')]

    def test_second_change_chains_revision(self, ds, executor, spy_audit):
        _insert_order(ds)
        obj = _make_obj(_policy(enabled=True, fields=DIFF_TOTAL))

        assert executor._do_update(obj, {'id': 1, 'total_amount': 200}).success
        assert executor._do_update(obj, {'id': 1, 'total_amount': 300}).success

        assert ds.find_by_id('rev_order', 1)['revision_no'] == 3
        assert [r['revision_no'] for r in ds.find(
            REVISIONS_TABLE, order_by='revision_no ASC')] == [2, 3]


# ---------------------------------------------------------------- FR-012

class TestNonContentFields:
    @pytest.mark.parametrize('field,value', [
        ('status', 'approved'),
        ('fulfillment_status', 'in_progress'),
        ('fulfillment_derived_at', '2026-10-29 10:00:00'),
    ])
    def test_non_content_change_no_revision(self, ds, executor, spy_record,
                                            spy_audit, field, value):
        _insert_order(ds)
        obj = _make_obj(_policy(
            enabled=True,
            fields=[RevisionFieldPolicy(field='status', diff=True)],
        ))

        result = executor._do_update(obj, {'id': 1, field: value})

        assert result.success is True, result.message
        row = ds.find_by_id('rev_order', 1)
        assert row[field] == value
        assert row['revision_no'] == 1
        assert spy_record == []
        assert ds.find(REVISIONS_TABLE) == []
        assert len(spy_audit) == 1


# ---------------------------------------------------------------- FR-010 乐观锁

class TestOptimisticLock:
    def test_conflict_returns_error_and_rolls_back(self, ds, executor,
                                                   spy_audit, monkeypatch):
        _insert_order(ds)
        obj = _make_obj(_policy(enabled=True, fields=DIFF_TOTAL))
        monkeypatch.setattr(revision_service, 'update_with_revision',
                            lambda *args, **kwargs: False)

        result = executor._do_update(obj, {'id': 1, 'total_amount': 200})

        assert result.success is False
        assert result.error == 'REVISION_CONFLICT'
        assert '1' in result.message
        row = ds.find_by_id('rev_order', 1)
        assert row['total_amount'] == 100
        assert row['revision_no'] == 1
        assert ds.find(REVISIONS_TABLE) == []
        assert spy_audit == []


# ---------------------------------------------------------------- FR-006 闸门

class TestRevisionGuard:
    def test_partial_fulfillment_blocked(self, ds, executor, spy_audit):
        _insert_order(ds, fulfillment_status='partial')
        obj = _make_obj(_policy(enabled=True, fields=DIFF_TOTAL))

        result = executor._do_update(obj, {'id': 1, 'total_amount': 200})

        assert result.success is False
        assert result.error == 'REVISION_REQUIRES_CHANGE_REQUEST'
        row = ds.find_by_id('rev_order', 1)
        assert row['total_amount'] == 100
        assert row['revision_no'] == 1
        assert ds.find(REVISIONS_TABLE) == []
        assert spy_audit == []

    def test_fulfilled_blocked(self, ds, executor):
        _insert_order(ds, fulfillment_status='fulfilled')
        obj = _make_obj(_policy(enabled=True, fields=DIFF_TOTAL))

        result = executor._do_update(obj, {'id': 1, 'total_amount': 200})

        assert result.success is False
        assert result.error == 'REVISION_NOT_ALLOWED_FULFILLED'
        assert ds.find_by_id('rev_order', 1)['total_amount'] == 100

    def test_status_whitelist_blocked(self, ds, executor, spy_audit):
        _insert_order(ds, status='approved')
        obj = _make_obj(_policy(enabled=True, editable_in_states=['draft'],
                                fields=DIFF_TOTAL))

        result = executor._do_update(obj, {'id': 1, 'name': 'x'})

        assert result.success is False
        assert result.error == 'REVISION_STATE_NOT_EDITABLE'
        assert ds.find_by_id('rev_order', 1)['name'] == 'order-1'
        assert spy_audit == []

    def test_status_whitelist_passes(self, ds, executor):
        _insert_order(ds, status='draft')
        obj = _make_obj(_policy(enabled=True, editable_in_states=['draft'],
                                fields=DIFF_TOTAL))

        result = executor._do_update(obj, {'id': 1, 'total_amount': 200})

        assert result.success is True, result.message
        assert ds.find_by_id('rev_order', 1)['revision_no'] == 2


# ---------------------------------------------------------------- reason_code

class TestReasonCode:
    def test_reason_code_persisted_in_revision(self, ds, executor, spy_audit):
        _insert_order(ds)
        obj = _make_obj(_policy(
            enabled=True,
            reason_required_fields=['total_amount'],
            fields=DIFF_TOTAL,
        ))

        result = executor._do_update(
            obj, {'id': 1, 'total_amount': 200, 'reason_code': 'PRICE_FIX'})

        assert result.success is True, result.message
        rev = ds.find(REVISIONS_TABLE)[0]
        assert rev['reason_code'] == 'PRICE_FIX'
        assert spy_audit[0]['reason_code'] == 'PRICE_FIX'
        assert spy_audit[0]['change_set_id'] == rev['change_set_id']

    def test_missing_reason_blocked_before_write(self, ds, executor, spy_audit):
        _insert_order(ds)
        obj = _make_obj(_policy(
            enabled=True,
            reason_required_fields=['total_amount'],
            fields=DIFF_TOTAL,
        ))

        result = executor._do_update(obj, {'id': 1, 'total_amount': 200})

        assert result.success is False
        assert result.error == 'REASON_CODE_REQUIRED'
        assert ds.find_by_id('rev_order', 1)['revision_no'] == 1
        assert ds.find(REVISIONS_TABLE) == []
        assert spy_audit == []
