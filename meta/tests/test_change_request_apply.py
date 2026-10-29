# -*- coding: utf-8 -*-
"""test_change_request_apply.py

M3 T6：变更申请生效编排（FR-009 / FR-010 / NFR-003 / NFR-004）

覆盖：
  A1 正常生效（头 + 行各 1 字段）：
       revision_no +1（头/行各一版本行）、change_request_id 落版本行、
       change_set_id 与审计行一致、申请 status=='applied' 且回写 applied_revision_no、
       返回 {status, revision_no, applied_at}
  A2 partial 目标放行（via_change_request=True，RevisionGuard 不拦）
  A3 fulfilled 目标拒绝 ⇒ REVISION_NOT_ALLOWED (409)，申请落 failed，无新版本行
  A4 乐观锁冲突（目标 revision_no 已被推进）⇒ REVISION_CONFLICT (409) +
       申请落 failed + 无新版本行（不写任何版本）
  A5 未审批就生效 ⇒ CHANGE_REQUEST_NOT_APPROVED (409)
  A6 重复生效 ⇒ 同一回执、版本行数不变（NFR-003 幂等）
  A7 line_key 指向不存在的行 ⇒ INVALID_LINE_KEY (400) + 申请落 failed

设计取舍：
  - 临时 SQLite（SQLiteAdapter）+ register_table_name，绝不动 meta/architecture.db；
  - monkeypatch meta.core.models.registry 为 stub（头 + 行两个对象），
    阻断真实元模型扫描（冗余字段 / 聚合 / 快照都只看到测试对象）；
  - _write_audit_log_v2 在 pytest 下直接 return，故用 spy 捕获 change_set_id；
  - 对象 id 用 cr_apply_order* 而非真实 sales_order，避免命中生产配置。
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
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.table_name_validator import register_table_name
from meta.services import revision_service
from meta.services.change_request_service import (
    CRL_TABLE,
    CR_TABLE,
    ChangeRequestError,
)
from meta.services.revision_service import CHANGES_TABLE, REVISIONS_TABLE

ORDER_TABLE = 'cr_apply_order'
LINE_TABLE = 'cr_apply_order_line'
CS_ID = 'cs_00000000cafe0001'

CS_PATTERN = re.compile(r'^cs_[0-9a-f]{16}$')

DDL = {
    ORDER_TABLE: """
        CREATE TABLE IF NOT EXISTS cr_apply_order (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            total_amount INTEGER,
            status TEXT,
            fulfillment_status TEXT,
            revision_no INTEGER DEFAULT 1
        )
    """,
    LINE_TABLE: """
        CREATE TABLE IF NOT EXISTS cr_apply_order_line (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            qty INTEGER,
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
    CR_TABLE: """
        CREATE TABLE IF NOT EXISTS change_requests (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            target_object_type  TEXT NOT NULL,
            target_object_id    TEXT NOT NULL,
            target_revision_no  INTEGER NOT NULL,
            status              TEXT NOT NULL DEFAULT 'draft',
            reason_code         TEXT NULL,
            summary             TEXT NULL,
            submitted_by        TEXT NULL,
            submitted_at        TEXT NULL,
            approved_by         TEXT NULL,
            approved_at         TEXT NULL,
            applied_at          TEXT NULL,
            applied_revision_no INTEGER NULL,
            fail_reason         TEXT NULL,
            change_set_id       TEXT NULL,
            created_by          TEXT NULL,
            created_at          TEXT NOT NULL,
            updated_by          TEXT NULL,
            updated_at          TEXT NULL
        )
    """,
    CRL_TABLE: """
        CREATE TABLE IF NOT EXISTS change_request_lines (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            change_request_id INTEGER NOT NULL,
            line_key          TEXT NULL,
            field_name        TEXT NOT NULL,
            old_value         TEXT NULL,
            new_value         TEXT NULL
        )
    """,
}


class RegistryStub:
    """替代 meta.core.models.registry：只暴露测试对象。"""

    def __init__(self, objects=()):
        self._objects = list(objects)

    def get(self, object_id):
        for obj in self._objects:
            if obj.id == object_id:
                return obj
        return None

    def all(self):
        return list(self._objects)


def _order_obj():
    obj = MetaObject(
        id=ORDER_TABLE,
        name='生效订单',
        table_name=ORDER_TABLE,
        fields=[
            MetaField(id='id', name='ID', field_type=FieldType.INTEGER,
                      db_column='id', required=True),
            MetaField(id='name', name='名称', field_type=FieldType.STRING,
                      db_column='name'),
            MetaField(id='total_amount', name='总额', field_type=FieldType.INTEGER,
                      db_column='total_amount'),
            MetaField(id='status', name='状态', field_type=FieldType.STRING,
                      db_column='status'),
            MetaField(id='fulfillment_status', name='履约状态',
                      field_type=FieldType.STRING, db_column='fulfillment_status'),
            MetaField(id='revision_no', name='版本号', field_type=FieldType.INTEGER,
                      db_column='revision_no'),
        ],
        actions=[
            MetaAction(id='crud_update', name='更新', action_type=ActionType.CRUD,
                       method='PUT', path=''),
        ],
    )
    obj.revision_policy = MetaRevisionPolicy(
        enabled=True,
        fields=[
            RevisionFieldPolicy(field='total_amount', editable=True, diff=True),
        ],
    )
    return obj


def _line_obj():
    obj = MetaObject(
        id=LINE_TABLE,
        name='生效订单行',
        table_name=LINE_TABLE,
        parent_object=ORDER_TABLE,
        fields=[
            MetaField(id='id', name='ID', field_type=FieldType.INTEGER,
                      db_column='id', required=True),
            MetaField(id='order_id', name='订单', field_type=FieldType.INTEGER,
                      db_column='order_id'),
            MetaField(id='qty', name='数量', field_type=FieldType.INTEGER,
                      db_column='qty'),
            MetaField(id='revision_no', name='版本号', field_type=FieldType.INTEGER,
                      db_column='revision_no'),
        ],
        actions=[
            MetaAction(id='crud_update', name='更新', action_type=ActionType.CRUD,
                       method='PUT', path=''),
        ],
    )
    obj.hierarchy = {'enabled': True, 'parent_field': 'order_id'}
    obj.revision_policy = MetaRevisionPolicy(
        enabled=True,
        fields=[RevisionFieldPolicy(field='qty', editable=True, diff=True)],
    )
    return obj


@pytest.fixture
def ds(tmp_path):
    from meta.core.task_schema import ensure_task_tables

    data_source = SQLiteAdapter()
    data_source.connect(path=str(tmp_path / 'm3_apply.db'))
    for name, ddl in DDL.items():
        data_source.execute(ddl)
        register_table_name(name)
    register_table_name('tasks')
    ensure_task_tables(data_source)
    yield data_source
    data_source.disconnect()


@pytest.fixture(autouse=True)
def registry_stub(monkeypatch):
    monkeypatch.setattr('meta.core.models.registry',
                        RegistryStub([_order_obj(), _line_obj()]))


@pytest.fixture
def spy_audit(monkeypatch):
    calls = []

    def spy(self, audit_fn, reason_code=None, exclude_fields=None, change_set_id=None):
        calls.append({'reason_code': reason_code, 'exclude_fields': exclude_fields,
                      'change_set_id': change_set_id})

    monkeypatch.setattr(ActionExecutor, '_write_audit_log_v2', spy)
    return calls


def _insert_order(ds, **overrides):
    data = {'name': 'order-1', 'total_amount': 100, 'status': 'draft',
            'fulfillment_status': 'not_started', 'revision_no': 1}
    data.update(overrides)
    return ds.insert(ORDER_TABLE, data)


def _insert_line(ds, order_id, qty=3, revision_no=1):
    return ds.insert(LINE_TABLE, {
        'order_id': order_id, 'qty': qty, 'revision_no': revision_no,
    })


def _make_cr(ds, order_id, **extra):
    row = {
        'target_object_type': ORDER_TABLE,
        'target_object_id': str(order_id),
        'target_revision_no': 1,
        'status': 'approved',
        'approved_by': 'u-appr',
        'approved_at': '2026-10-29 01:00:00',
        'change_set_id': CS_ID,
        'created_at': '2026-10-29 00:00:00',
    }
    row.update(extra)
    return ds.insert(CR_TABLE, row)


def _add_line(ds, cr_id, field_name, old_value, new_value, line_key=None):
    ds.insert(CRL_TABLE, {
        'change_request_id': cr_id,
        'line_key': line_key,
        'field_name': field_name,
        'old_value': old_value,
        'new_value': new_value,
    })


def _apply(ds, cr_id, actor='u-appr'):
    row = ds.find_by_id(CR_TABLE, cr_id)
    return revision_service.apply(ds, row, actor=actor)


# ---------------------------------------------------------------- A1 正常生效

class TestApplySuccess:
    def test_a1_header_and_line_both_applied(self, ds, spy_audit):
        order_id = _insert_order(ds)
        line_id = _insert_line(ds, order_id, qty=3, revision_no=1)
        cr_id = _make_cr(ds, order_id)
        _add_line(ds, cr_id, 'total_amount', '100', '200')
        _add_line(ds, cr_id, 'qty', '3', '5', line_key=str(line_id))

        receipt = _apply(ds, cr_id)

        assert set(receipt) == {'status', 'revision_no', 'applied_at'}
        assert receipt['status'] == 'applied'
        assert receipt['revision_no'] == 2
        assert receipt['applied_at']

        header = ds.find_by_id(ORDER_TABLE, order_id)
        assert header['total_amount'] == 200
        assert header['revision_no'] == 2
        line = ds.find_by_id(LINE_TABLE, line_id)
        assert line['qty'] == 5
        assert line['revision_no'] == 2

        revs = ds.find(REVISIONS_TABLE)
        assert len(revs) == 2
        by_type = {r['object_type']: r for r in revs}
        assert set(by_type) == {ORDER_TABLE, LINE_TABLE}
        for rev in revs:
            assert rev['revision_no'] == 2
            assert str(rev['change_request_id']) == str(cr_id)
            assert rev['change_set_id'] == CS_ID
        assert by_type[ORDER_TABLE]['object_id'] == str(order_id)
        assert by_type[LINE_TABLE]['object_id'] == str(line_id)

        # 头部版本行只记 total_amount 差异
        changes = ds.find(CHANGES_TABLE, {'revision_id': by_type[ORDER_TABLE]['id']})
        assert [(c['field_name'], c['old_value'], c['new_value']) for c in changes] == [
            ('total_amount', '100', '200')]

        # 版本行 / 审计行共享同一 change_set_id（NFR-004 可追溯）
        assert len(spy_audit) == 2
        assert {c['change_set_id'] for c in spy_audit} == {CS_ID}

        fresh = ds.find_by_id(CR_TABLE, cr_id)
        assert fresh['status'] == 'applied'
        assert fresh['applied_revision_no'] == 2
        assert fresh['applied_at'] == receipt['applied_at']

    def test_a1_change_set_id_falls_back_when_absent(self, ds, spy_audit):
        """申请无 change_set_id 时，版本行与审计行仍共享漏斗新生成的同一 ID。"""
        order_id = _insert_order(ds)
        cr_id = _make_cr(ds, order_id, change_set_id=None)
        _add_line(ds, cr_id, 'total_amount', '100', '200')

        receipt = _apply(ds, cr_id)

        assert receipt['revision_no'] == 2
        rev = ds.find(REVISIONS_TABLE)[0]
        assert CS_PATTERN.match(rev['change_set_id'])
        assert spy_audit[0]['change_set_id'] == rev['change_set_id']
        assert ds.find_by_id(CR_TABLE, cr_id)['change_set_id'] == rev['change_set_id']


# ---------------------------------------------------------------- A2 partial 放行

class TestPartialAllowed:
    def test_a2_partial_passes_via_change_request(self, ds, spy_audit):
        order_id = _insert_order(ds, fulfillment_status='partial')
        cr_id = _make_cr(ds, order_id)
        _add_line(ds, cr_id, 'total_amount', '100', '200')

        receipt = _apply(ds, cr_id)

        assert receipt['status'] == 'applied'
        assert receipt['revision_no'] == 2
        header = ds.find_by_id(ORDER_TABLE, order_id)
        assert header['total_amount'] == 200
        assert header['revision_no'] == 2
        assert len(ds.find(REVISIONS_TABLE)) == 1


# ---------------------------------------------------------------- A3 fulfilled 拒绝

class TestFulfilledRejected:
    @pytest.mark.parametrize('fulfillment', ['fulfilled', 'voided'])
    def test_a3_fulfilled_not_allowed_and_marks_failed(self, ds, spy_audit,
                                                       fulfillment):
        order_id = _insert_order(ds, fulfillment_status=fulfillment)
        cr_id = _make_cr(ds, order_id)
        _add_line(ds, cr_id, 'total_amount', '100', '200')

        with pytest.raises(ChangeRequestError) as ei:
            _apply(ds, cr_id)

        assert ei.value.code == 'REVISION_NOT_ALLOWED'
        assert ei.value.status_code == 409

        header = ds.find_by_id(ORDER_TABLE, order_id)
        assert header['total_amount'] == 100
        assert header['revision_no'] == 1
        assert ds.find(REVISIONS_TABLE) == []
        assert spy_audit == []

        fresh = ds.find_by_id(CR_TABLE, cr_id)
        assert fresh['status'] == 'failed'
        assert fresh['fail_reason']


# ---------------------------------------------------------------- A4 乐观锁冲突

class TestRevisionConflict:
    def test_a4_conflict_marks_failed_without_new_revision(self, ds, spy_audit):
        order_id = _insert_order(ds, revision_no=2)
        cr_id = _make_cr(ds, order_id, target_revision_no=1)
        _add_line(ds, cr_id, 'total_amount', '100', '200')

        with pytest.raises(ChangeRequestError) as ei:
            _apply(ds, cr_id)

        assert ei.value.code == 'REVISION_CONFLICT'
        assert ei.value.status_code == 409
        assert '请重新提交' in ei.value.message

        assert ds.find(REVISIONS_TABLE) == []
        assert spy_audit == []
        assert ds.find_by_id(ORDER_TABLE, order_id)['total_amount'] == 100

        fresh = ds.find_by_id(CR_TABLE, cr_id)
        assert fresh['status'] == 'failed'
        assert '请重新提交' in fresh['fail_reason']


# ---------------------------------------------------------------- A5 未审批

class TestNotApproved:
    def test_a5_not_approved_rejected(self, ds, spy_audit):
        order_id = _insert_order(ds)
        cr_id = _make_cr(ds, order_id, status='draft')
        _add_line(ds, cr_id, 'total_amount', '100', '200')

        with pytest.raises(ChangeRequestError) as ei:
            _apply(ds, cr_id)

        assert ei.value.code == 'CHANGE_REQUEST_NOT_APPROVED'
        assert ei.value.status_code == 409
        assert ds.find_by_id(CR_TABLE, cr_id)['status'] == 'draft'
        assert ds.find(REVISIONS_TABLE) == []
        assert spy_audit == []


# ---------------------------------------------------------------- A6 幂等

class TestIdempotent:
    def test_a6_repeat_apply_returns_same_receipt(self, ds, spy_audit):
        order_id = _insert_order(ds)
        cr_id = _make_cr(ds, order_id)
        _add_line(ds, cr_id, 'total_amount', '100', '200')

        first = _apply(ds, cr_id)
        revs_before = len(ds.find(REVISIONS_TABLE))
        rev_no_before = ds.find_by_id(ORDER_TABLE, order_id)['revision_no']
        audits_before = len(spy_audit)

        second = _apply(ds, cr_id)

        assert second == first
        assert len(ds.find(REVISIONS_TABLE)) == revs_before
        assert ds.find_by_id(ORDER_TABLE, order_id)['revision_no'] == rev_no_before
        assert len(spy_audit) == audits_before


# ---------------------------------------------------------------- A7 行主键非法

class TestInvalidLineKey:
    def test_a7_missing_line_key(self, ds, spy_audit):
        order_id = _insert_order(ds)
        cr_id = _make_cr(ds, order_id)
        _add_line(ds, cr_id, 'qty', '3', '5', line_key='999')

        with pytest.raises(ChangeRequestError) as ei:
            _apply(ds, cr_id)

        assert ei.value.code == 'INVALID_LINE_KEY'
        assert ei.value.status_code == 400

        assert ds.find(REVISIONS_TABLE) == []
        assert spy_audit == []
        assert ds.find_by_id(ORDER_TABLE, order_id)['revision_no'] == 1

        fresh = ds.find_by_id(CR_TABLE, cr_id)
        assert fresh['status'] == 'failed'
        assert '999' in fresh['fail_reason']
