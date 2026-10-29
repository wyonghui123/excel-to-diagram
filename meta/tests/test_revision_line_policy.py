# -*- coding: utf-8 -*-
"""test_revision_line_policy.py

M4 T6：行级变更接入（`revision_policy.lines`）

覆盖：
  加载校验（parse_revision_lines）
    L1 lines 但 enabled=False            ⇒ ValueError
    L2 缺 child_object / parent_field / line_type_field ⇒ ValueError
    L3 清单含派生字段                    ⇒ ValueError
    L4 同档 editable 与 via 交叉         ⇒ ValueError
  加载校验（validate_line_policies）
    L5 child_object 不存在               ⇒ ValueError
    L6 子对象缺 parent_field 字段        ⇒ ValueError
    L7 清单字段未在子对象声明            ⇒ ValueError
    L8 父对象缺主键字段 'id'             ⇒ ValueError
  字段三态（RevisionGuard.check）
    G1 editable 放行
    G2 via_change_request 直接改         ⇒ REVISION_REQUIRES_CHANGE_REQUEST
    G3 未列入分档                         ⇒ REVISION_NOT_ALLOWED
    G4 申请内（via_change_request=True）放行 editable + via
    G5 申请内未列入分档仍拒              ⇒ REVISION_NOT_ALLOWED
    G6 by_type 命中覆盖 default（policy_for）
  父单据闸门
    P1 父状态不在 editable_in_states     ⇒ REVISION_STATE_NOT_EDITED
    P2 父 partial 直接改行               ⇒ REVISION_REQUIRES_CHANGE_REQUEST
    P3 父 fulfilled/voided               ⇒ REVISION_NOT_ALLOWED_FULFILLED
  单版本合并（revision_service.apply）
    M1 同一申请 2 行变更 ⇒ 父 revision_no 只 +1，changes 两条不同 line_key
    M2 同一申请 头 + 2 行 ⇒ 仅 1 条父单据版本行
  行级申请提交校验（change_request_service.after_status_change）
    R1 不存在的 line_key                 ⇒ INVALID_LINE_KEY
    R2 行类型分档外的字段                ⇒ INVALID_CHANGE_FIELD

设计取舍：
  - 临时 SQLite（SQLiteAdapter）+ register_table_name，绝不动 meta/architecture.db；
  - monkeypatch meta.core.models.registry 为 stub（父 + 行两个对象），阻断真实元模型扫描；
  - 对象 id 用 lp_order* 而非真实 sales_order，避免命中生产配置。
"""
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.models import (
    ActionType,
    FieldType,
    MetaAction,
    MetaField,
    MetaObject,
    MetaRevisionLines,
    MetaRevisionPolicy,
    RevisionFieldPolicy,
    RevisionLineDefaultPolicy,
    RevisionLineTypePolicy,
)
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.table_name_validator import register_table_name
from meta.core.yaml_loader import parse_revision_lines, validate_line_policies
from meta.services import revision_service
from meta.services.change_request_service import (
    CRL_TABLE,
    CR_TABLE,
    ChangeRequestError,
    after_status_change,
)
from meta.services.revision_guard import (
    NOT_ALLOWED,
    NOT_ALLOWED_FULFILLED,
    REQUIRES_CHANGE_REQUEST,
    STATUS_NOT_EDITABLE,
    RevisionGuard,
    RevisionError,
)
from meta.services.revision_service import CHANGES_TABLE, REVISIONS_TABLE

ORDER_TABLE = 'lp_order'
LINE_TABLE = 'lp_order_line'

DDL = {
    ORDER_TABLE: """
        CREATE TABLE IF NOT EXISTS lp_order (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            total_amount INTEGER,
            status TEXT,
            fulfillment_status TEXT,
            revision_no INTEGER DEFAULT 1
        )
    """,
    LINE_TABLE: """
        CREATE TABLE IF NOT EXISTS lp_order_line (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            line_type_id INTEGER,
            qty INTEGER,
            unit_price INTEGER,
            requested_date TEXT,
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

CS_ID = 'cs_00000000beef0001'

# 行类型分档（与 sales_order.yaml 同构：类型 1 / 类型 3 覆盖 default）
LINE_DEFAULT = RevisionLineDefaultPolicy(
    editable=['qty', 'requested_date'],
    via_change_request=['unit_price'],
)
LINE_BY_TYPE = [
    RevisionLineTypePolicy(when='line_type_id == 1',
                           editable=['qty'], via_change_request=['unit_price']),
    RevisionLineTypePolicy(when='line_type_id == 3',
                           editable=['requested_date'], via_change_request=['unit_price']),
]


def _lines_cfg():
    return MetaRevisionLines(
        child_object=LINE_TABLE,
        parent_field='order_id',
        line_type_field='line_type_id',
        default=RevisionLineDefaultPolicy(
            editable=list(LINE_DEFAULT.editable),
            via_change_request=list(LINE_DEFAULT.via_change_request),
        ),
        by_type=[RevisionLineTypePolicy(when=t.when, editable=list(t.editable),
                                        via_change_request=list(t.via_change_request))
                 for t in LINE_BY_TYPE],
    )


def _policy(lines):
    return MetaRevisionPolicy(
        enabled=True,
        editable_in_states=['draft', 'submitted', 'confirmed'],
        fields=[RevisionFieldPolicy(field='total_amount', editable=True, diff=True)],
        lines=lines,
    )


def _parent_obj(lines=None):
    obj = MetaObject(
        id=ORDER_TABLE,
        name='行级策略订单',
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
    obj.revision_policy = _policy(lines)
    return obj


def _line_obj():
    obj = MetaObject(
        id=LINE_TABLE,
        name='行级策略订单行',
        table_name=LINE_TABLE,
        parent_object=ORDER_TABLE,
        fields=[
            MetaField(id='id', name='ID', field_type=FieldType.INTEGER,
                      db_column='id', required=True),
            MetaField(id='order_id', name='订单', field_type=FieldType.INTEGER,
                      db_column='order_id'),
            MetaField(id='line_type_id', name='行类型', field_type=FieldType.INTEGER,
                      db_column='line_type_id'),
            MetaField(id='qty', name='数量', field_type=FieldType.INTEGER,
                      db_column='qty'),
            MetaField(id='unit_price', name='单价', field_type=FieldType.INTEGER,
                      db_column='unit_price'),
            MetaField(id='requested_date', name='需求日期', field_type=FieldType.STRING,
                      db_column='requested_date'),
            MetaField(id='revision_no', name='版本号', field_type=FieldType.INTEGER,
                      db_column='revision_no'),
        ],
        actions=[
            MetaAction(id='crud_update', name='更新', action_type=ActionType.CRUD,
                       method='PUT', path=''),
        ],
    )
    obj.hierarchy = {'enabled': True, 'parent_field': 'order_id'}
    # 行对象自身无 revision_policy：版本归属由父单据 revision_policy.lines 决定
    obj.revision_policy = None
    return obj


class RegistryStub:
    def __init__(self, objects=()):
        self._objects = list(objects)

    def get(self, object_id):
        for obj in self._objects:
            if obj.id == object_id:
                return obj
        return None

    def all(self):
        return list(self._objects)


@pytest.fixture
def ds(tmp_path):
    from meta.core.task_schema import ensure_task_tables

    data_source = SQLiteAdapter()
    data_source.connect(path=str(tmp_path / 'm4_line.db'))
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
                        RegistryStub([_parent_obj(_lines_cfg()), _line_obj()]))


def _insert_order(ds, **overrides):
    data = {'name': 'order-1', 'total_amount': 100, 'status': 'draft',
            'fulfillment_status': 'not_started', 'revision_no': 1}
    data.update(overrides)
    return ds.insert(ORDER_TABLE, data)


def _insert_line(ds, order_id, line_type_id=1, qty=3, unit_price=10,
                 requested_date='2026-11-01', revision_no=1):
    return ds.insert(LINE_TABLE, {
        'order_id': order_id, 'line_type_id': line_type_id, 'qty': qty,
        'unit_price': unit_price, 'requested_date': requested_date,
        'revision_no': revision_no,
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
    return revision_service.apply(ds, ds.find_by_id(CR_TABLE, cr_id), actor=actor)


# ---------------------------------------------------------------- 加载校验

def _raw_lines(**overrides):
    raw = {
        'child_object': LINE_TABLE,
        'parent_field': 'order_id',
        'line_type_field': 'line_type_id',
        'default': {'editable': ['qty'], 'via_change_request': ['unit_price']},
    }
    raw.update(overrides)
    return raw


class TestParseRevisionLines:
    def test_happy_path(self):
        lines = parse_revision_lines({'lines': _raw_lines()}, ORDER_TABLE, True)

        assert lines.child_object == LINE_TABLE
        assert lines.parent_field == 'order_id'
        assert lines.line_type_field == 'line_type_id'
        assert lines.default.editable == ['qty']
        assert lines.default.via_change_request == ['unit_price']
        assert lines.by_type == []
        assert lines.all_fields() == {'qty', 'unit_price'}

    def test_lines_without_enabled(self):
        with pytest.raises(ValueError, match='enabled'):
            parse_revision_lines({'lines': _raw_lines()}, ORDER_TABLE, False)

    @pytest.mark.parametrize('key', ['child_object', 'parent_field', 'line_type_field'])
    def test_missing_required_key(self, key):
        raw = _raw_lines()
        raw.pop(key)
        with pytest.raises(ValueError, match=key):
            parse_revision_lines({'lines': raw}, ORDER_TABLE, True)

    def test_derived_field_rejected(self):
        raw = _raw_lines(default={'editable': ['fulfillment_status']})
        with pytest.raises(ValueError, match='派生字段'):
            parse_revision_lines({'lines': raw}, ORDER_TABLE, True)

    def test_editable_via_overlap_rejected(self):
        raw = _raw_lines(default={'editable': ['qty'],
                                  'via_change_request': ['qty']})
        with pytest.raises(ValueError, match='同时出现在'):
            parse_revision_lines({'lines': raw}, ORDER_TABLE, True)

    def test_no_lines_returns_none(self):
        assert parse_revision_lines({}, ORDER_TABLE, True) is None


class TestValidateLinePolicies:
    def _pair(self, child_fields, parent_fields, lines):
        parent = _parent_obj(lines)
        parent.fields = [f for f in parent.fields if f.id in parent_fields]
        child = _line_obj()
        child.fields = [f for f in child.fields if f.id in child_fields]
        return {ORDER_TABLE: parent, LINE_TABLE: child}

    def test_child_object_missing(self):
        parent = _parent_obj(_lines_cfg())
        with pytest.raises(ValueError, match='不存在'):
            validate_line_policies({ORDER_TABLE: parent})

    def test_parent_field_not_in_child(self):
        objects = self._pair(
            child_fields={'id', 'line_type_id', 'qty', 'unit_price'},
            parent_fields={'id', 'total_amount'},
            lines=_lines_cfg(),
        )
        with pytest.raises(ValueError, match='parent_field'):
            validate_line_policies(objects)

    def test_field_not_declared_in_child(self):
        lines = MetaRevisionLines(
            child_object=LINE_TABLE, parent_field='order_id',
            line_type_field='line_type_id',
            default=RevisionLineDefaultPolicy(editable=['qty', 'missing_field']),
        )
        objects = self._pair(
            child_fields={'id', 'order_id', 'line_type_id', 'qty'},
            parent_fields={'id', 'total_amount'},
            lines=lines,
        )
        with pytest.raises(ValueError, match='missing_field'):
            validate_line_policies(objects)

    def test_parent_without_id_field(self):
        objects = self._pair(
            child_fields={'id', 'order_id', 'line_type_id', 'qty', 'unit_price',
                          'requested_date'},
            parent_fields={'total_amount'},
            lines=_lines_cfg(),
        )
        with pytest.raises(ValueError, match="主键字段"):
            validate_line_policies(objects)

    def test_valid_pair_passes(self):
        objects = self._pair(
            child_fields={'id', 'order_id', 'line_type_id', 'qty', 'unit_price',
                          'requested_date'},
            parent_fields={'id', 'total_amount', 'status', 'fulfillment_status'},
            lines=_lines_cfg(),
        )
        validate_line_policies(objects)


# ---------------------------------------------------------------- 字段三态

GATE = {'status': 'draft', 'fulfillment_status': 'not_started'}


def _check(changed_fields, line_fields, gate=None, via=False, policy=None):
    RevisionGuard().check(
        _line_obj(), {},
        changed_fields=changed_fields,
        via_change_request=via,
        policy=policy or _policy(_lines_cfg()),
        line_fields=line_fields,
        gate_record=dict(gate or GATE),
    )


class TestLineFieldTriState:
    def test_g1_editable_passes(self):
        _check(['qty'], {'editable': ['qty'], 'via_change_request': ['unit_price']})

    def test_g2_via_requires_change_request(self):
        with pytest.raises(RevisionError) as ei:
            _check(['unit_price'],
                   {'editable': ['qty'], 'via_change_request': ['unit_price']})
        assert ei.value.code == REQUIRES_CHANGE_REQUEST

    def test_g3_not_listed_rejected(self):
        with pytest.raises(RevisionError) as ei:
            _check(['requested_date'],
                   {'editable': ['qty'], 'via_change_request': ['unit_price']})
        assert ei.value.code == NOT_ALLOWED

    def test_g4_in_request_both_pass(self):
        _check(['qty', 'unit_price'],
               {'editable': ['qty'], 'via_change_request': ['unit_price']},
               via=True)

    def test_g5_in_request_unlisted_still_rejected(self):
        with pytest.raises(RevisionError) as ei:
            _check(['requested_date'],
                   {'editable': ['qty'], 'via_change_request': ['unit_price']},
                   via=True)
        assert ei.value.code == NOT_ALLOWED

    def test_g6_by_type_overrides_default(self):
        lines = _lines_cfg()
        assert lines.policy_for({'line_type_id': 1}).editable == ['qty']
        assert lines.policy_for({'line_type_id': 3}).editable == ['requested_date']
        assert lines.policy_for({'line_type_id': 7}) is lines.default
        assert lines.all_fields() == {
            'qty', 'requested_date', 'unit_price'}


# ---------------------------------------------------------------- 父单据闸门

class TestParentGate:
    def _line_fields(self):
        return {'editable': ['qty'], 'via_change_request': ['unit_price']}

    def test_p1_state_not_editable(self):
        with pytest.raises(RevisionError) as ei:
            _check(['qty'], self._line_fields(),
                   gate={'status': 'closed', 'fulfillment_status': 'not_started'})
        assert ei.value.code == STATUS_NOT_EDITABLE

    def test_p2_partial_requires_change_request(self):
        with pytest.raises(RevisionError) as ei:
            _check(['qty'], self._line_fields(),
                   gate={'status': 'submitted', 'fulfillment_status': 'partial'})
        assert ei.value.code == REQUIRES_CHANGE_REQUEST

    @pytest.mark.parametrize('fulfillment', ['fulfilled', 'voided'])
    def test_p3_fulfilled_not_allowed(self, fulfillment):
        with pytest.raises(RevisionError) as ei:
            _check(['qty'], self._line_fields(),
                   gate={'status': 'confirmed', 'fulfillment_status': fulfillment})
        assert ei.value.code == NOT_ALLOWED_FULFILLED


# ---------------------------------------------------------------- 单版本合并

class TestSingleVersionMerge:
    def test_m1_two_lines_one_revision(self, ds):
        order_id = _insert_order(ds)
        l1 = _insert_line(ds, order_id, line_type_id=1, qty=3)
        l2 = _insert_line(ds, order_id, line_type_id=1, qty=4)
        cr_id = _make_cr(ds, order_id)
        _add_line(ds, cr_id, 'qty', '3', '5', line_key=str(l1))
        _add_line(ds, cr_id, 'qty', '4', '6', line_key=str(l2))

        receipt = _apply(ds, cr_id)

        assert receipt['revision_no'] == 2
        assert ds.find_by_id(ORDER_TABLE, order_id)['revision_no'] == 2
        assert ds.find_by_id(LINE_TABLE, l1)['qty'] == 5
        assert ds.find_by_id(LINE_TABLE, l2)['qty'] == 6

        revs = ds.find(REVISIONS_TABLE)
        assert len(revs) == 1
        assert revs[0]['object_type'] == ORDER_TABLE
        assert revs[0]['revision_no'] == 2

        changes = ds.find(CHANGES_TABLE, {'revision_id': revs[0]['id']})
        keys = {(c['line_key'], c['field_name'], c['old_value'], c['new_value'])
                for c in changes}
        assert keys == {
            (str(l1), 'qty', '3', '5'),
            (str(l2), 'qty', '4', '6'),
        }

    def test_m2_header_and_two_lines_one_revision(self, ds):
        order_id = _insert_order(ds)
        l1 = _insert_line(ds, order_id, line_type_id=1, qty=3)
        l2 = _insert_line(ds, order_id, line_type_id=1, qty=4)
        cr_id = _make_cr(ds, order_id)
        _add_line(ds, cr_id, 'total_amount', '100', '200')
        _add_line(ds, cr_id, 'qty', '3', '5', line_key=str(l1))
        _add_line(ds, cr_id, 'qty', '4', '6', line_key=str(l2))

        receipt = _apply(ds, cr_id)

        assert receipt['revision_no'] == 2
        header = ds.find_by_id(ORDER_TABLE, order_id)
        assert header['total_amount'] == 200
        assert header['revision_no'] == 2
        assert ds.find_by_id(CR_TABLE, cr_id)['applied_revision_no'] == 2

        revs = ds.find(REVISIONS_TABLE)
        assert len(revs) == 1
        changes = ds.find(CHANGES_TABLE, {'revision_id': revs[0]['id']})
        assert len(changes) == 3
        assert {c['line_key'] for c in changes} == {None, str(l1), str(l2)}


# ---------------------------------------------------------------- 行级申请提交校验

class TestLineSubmitValidation:
    def _submitted(self, cr_id, order_id, revision_no=1):
        return (
            {'id': cr_id, 'status': 'draft'},
            {
                'id': cr_id, 'status': 'submitted',
                'target_object_type': ORDER_TABLE,
                'target_object_id': str(order_id),
                'target_revision_no': revision_no,
                'submitted_by': 'u-sub',
            },
        )

    def test_r1_missing_line_key(self, ds):
        order_id = _insert_order(ds)
        cr_id = _make_cr(ds, order_id, status='draft')
        _add_line(ds, cr_id, 'qty', '3', '5', line_key='999')

        with pytest.raises(ChangeRequestError) as ei:
            after_status_change(ds, *self._submitted(cr_id, order_id))

        assert ei.value.code == 'INVALID_LINE_KEY'

    def test_r2_field_outside_tier(self, ds):
        order_id = _insert_order(ds)
        line_id = _insert_line(ds, order_id, line_type_id=1)
        cr_id = _make_cr(ds, order_id, status='draft')
        # 行类型 1 的分档只含 qty / unit_price，requested_date 不在清单内
        _add_line(ds, cr_id, 'requested_date', '2026-11-01', '2026-12-01',
                  line_key=str(line_id))

        with pytest.raises(ChangeRequestError) as ei:
            after_status_change(ds, *self._submitted(cr_id, order_id))

        assert ei.value.code == 'INVALID_CHANGE_FIELD'
