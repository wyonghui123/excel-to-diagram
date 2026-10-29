# -*- coding: utf-8 -*-
"""test_change_request_service.py

M3 T6：变更申请提交钩子 + 状态迁移单测（FR-007 / FR-008 / FR-010 / FR-011）

覆盖：
  C1 非法字段（不在 revision_policy editable 白名单）⇒ INVALID_CHANGE_FIELD (400)
  C2 派生字段（fulfillment_status）即使声明 editable 也被白名单剔除 ⇒ 同上 400
  C3 target_revision_no 与目标行 revision_no 不一致 ⇒ TARGET_REVISION_STALE (400，
     消息含「请重新提交」)
  C4 0 行变更明细 ⇒ INVALID_CHANGE_REQUEST
  C5 正常提交 ⇒ tasks 表 1 行，字段口径（type/status/assign_policy/
     decision_actions 成对 / inputs 4 键 / doc_ref / attempt）
  C6 transition 非法边 ⇒ INVALID_TRANSITION (409)；合法边写 approved_by/approved_at

设计取舍：
  - 临时 SQLite（SQLiteAdapter）+ register_table_name，绝不动 meta/architecture.db；
  - monkeypatch meta.core.models.registry 为 stub，阻断真实元模型扫描；
  - 显式 ensure_task_tables(ds)：change_request_service._ensure_tables 的
    _TABLES_READY 是模块级缓存，跨用例复用会跳过建表，这里自带建表避免顺序依赖。
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
    MetaRevisionPolicy,
    RevisionFieldPolicy,
)
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.table_name_validator import register_table_name
from meta.services.change_request_service import (
    CRL_TABLE,
    CR_TABLE,
    ChangeRequestError,
    after_status_change,
    transition,
)


DDL = {
    'sales_order': """
        CREATE TABLE IF NOT EXISTS sales_order (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            total_amount INTEGER,
            status TEXT,
            fulfillment_status TEXT,
            revision_no INTEGER DEFAULT 1
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


def _sales_order():
    obj = MetaObject(
        id='sales_order',
        name='销售订单',
        table_name='sales_order',
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
    )
    obj.revision_policy = MetaRevisionPolicy(
        enabled=True,
        fields=[
            RevisionFieldPolicy(field='name', editable=True, diff=True),
            RevisionFieldPolicy(field='total_amount', editable=True, diff=True),
            # 声明 editable 也无效：派生字段会在白名单里被剔除（FR-011）
            RevisionFieldPolicy(field='fulfillment_status', editable=True, diff=True),
        ],
    )
    return obj


@pytest.fixture
def ds(tmp_path):
    data_source = SQLiteAdapter()
    data_source.connect(path=str(tmp_path / 'm3_service.db'))
    from meta.core.task_schema import ensure_task_tables

    for name, ddl in DDL.items():
        data_source.execute(ddl)
        register_table_name(name)
    register_table_name('tasks')
    ensure_task_tables(data_source)
    yield data_source
    data_source.disconnect()


@pytest.fixture(autouse=True)
def empty_registry(monkeypatch):
    monkeypatch.setattr('meta.core.models.registry', RegistryStub([_sales_order()]))


def _make_cr(ds, *, target_type='sales_order', target_id='1',
             target_revision_no=1, status='draft', **extra):
    row = {
        'target_object_type': target_type,
        'target_object_id': str(target_id),
        'target_revision_no': target_revision_no,
        'status': status,
        'created_at': '2026-10-29 00:00:00',
        'change_set_id': 'cs_m3service0000',
    }
    row.update(extra)
    return ds.insert(CR_TABLE, row)


def _add_line(ds, cr_id, field_name, *, line_key=None, old_value='100',
              new_value='200'):
    ds.insert(CRL_TABLE, {
        'change_request_id': cr_id,
        'line_key': line_key,
        'field_name': field_name,
        'old_value': old_value,
        'new_value': new_value,
    })


def _insert_order(ds, **overrides):
    data = {'name': 'order-1', 'total_amount': 100, 'status': 'draft',
            'fulfillment_status': 'not_started', 'revision_no': 1}
    data.update(overrides)
    return ds.insert('sales_order', data)


def _submit(ds, cr_id):
    """模拟 draft → submitted：照 _do_update 传入 before / after / ctx。"""
    row = ds.find_by_id(CR_TABLE, cr_id)
    before = dict(row)
    after = dict(row, status='submitted', submitted_by='u-sub')
    after_status_change(ds, before, after, {'actor': 'u-sub'})


# ---------------------------------------------------------------- 提交校验

class TestSubmitValidation:
    def test_c1_invalid_field(self, ds):
        _insert_order(ds)
        cr_id = _make_cr(ds)
        _add_line(ds, cr_id, 'status')

        with pytest.raises(ChangeRequestError) as ei:
            _submit(ds, cr_id)

        assert ei.value.code == 'INVALID_CHANGE_FIELD'
        assert ei.value.status_code == 400
        assert 'status' in ei.value.message

    def test_c2_derived_field_rejected(self, ds):
        _insert_order(ds)
        cr_id = _make_cr(ds)
        _add_line(ds, cr_id, 'fulfillment_status')

        with pytest.raises(ChangeRequestError) as ei:
            _submit(ds, cr_id)

        assert ei.value.code == 'INVALID_CHANGE_FIELD'
        assert ei.value.status_code == 400
        assert 'fulfillment_status' in ei.value.message

    def test_c3_target_revision_stale(self, ds):
        _insert_order(ds, revision_no=2)
        cr_id = _make_cr(ds, target_revision_no=1)
        _add_line(ds, cr_id, 'total_amount')

        with pytest.raises(ChangeRequestError) as ei:
            _submit(ds, cr_id)

        assert ei.value.code == 'TARGET_REVISION_STALE'
        assert ei.value.status_code == 400
        assert '请重新提交' in ei.value.message

    def test_c4_no_lines(self, ds):
        _insert_order(ds)
        cr_id = _make_cr(ds)

        with pytest.raises(ChangeRequestError) as ei:
            _submit(ds, cr_id)

        assert ei.value.code == 'INVALID_CHANGE_REQUEST'
        # 校验失败时不得建审批任务
        assert ds.find('tasks') == []


# ---------------------------------------------------------------- 正常提交

class TestSubmitCreatesApprovalTask:
    def test_c5_task_row_contract(self, ds):
        _insert_order(ds)
        cr_id = _make_cr(ds)
        _add_line(ds, cr_id, 'total_amount', old_value='100', new_value='200')

        _submit(ds, cr_id)

        tasks = ds.find('tasks')
        assert len(tasks) == 1
        task = tasks[0]

        assert task['type'] == 'approval'
        assert task['status'] == 'waiting_approval'
        assert task['assign_policy'] == 'claim'
        assert task['executor_type'] == 'human'
        assert task['attempt'] == 1
        assert task['doc_ref'] == str(cr_id)
        assert task['created_by'] == 'u-sub'
        assert task['title'] == '变更申请审批 #%s' % cr_id

        config = json.loads(task['executor_config'])
        assert config['decision_actions'] == {
            'approve': 'change_request.approve',
            'reject': 'change_request.reject',
        }

        inputs = json.loads(task['inputs'])
        assert set(inputs) == {
            'change_request_id', 'target_object_type',
            'target_object_id', 'target_revision_no',
        }
        assert inputs['change_request_id'] == cr_id
        assert inputs['target_object_type'] == 'sales_order'
        assert inputs['target_object_id'] == '1'
        assert inputs['target_revision_no'] == 1


# ---------------------------------------------------------------- 状态迁移

class TestTransition:
    def test_c6_invalid_edge(self, ds):
        cr_id = _make_cr(ds, status='draft')
        row = ds.find_by_id(CR_TABLE, cr_id)

        with pytest.raises(ChangeRequestError) as ei:
            transition(ds, row, 'applied')

        assert ei.value.code == 'INVALID_TRANSITION'
        assert ei.value.status_code == 409

    def test_c6_valid_edge_writes_approval_audit_columns(self, ds):
        cr_id = _make_cr(ds, status='submitted')
        row = ds.find_by_id(CR_TABLE, cr_id)

        updates = transition(ds, row, 'approved', 'u-appr')

        assert updates['status'] == 'approved'
        assert updates['approved_by'] == 'u-appr'
        assert updates['approved_at']

        fresh = ds.find_by_id(CR_TABLE, cr_id)
        assert fresh['status'] == 'approved'
        assert fresh['approved_by'] == 'u-appr'
        assert fresh['approved_at'] == updates['approved_at']
