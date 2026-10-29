# -*- coding: utf-8 -*-
"""
test_audit_change_set.py

M1（审计补 change_set_id + reason_code / revision_policy 三开关）单测。

覆盖 spec §4.1 的 T1~T10：
  T1 解析默认值         只声明 enabled ⇒ fields=[]、reason_required_fields=[]
  T2 三开关默认         fields 只写 field ⇒ editable=False, diff=False, audit=True
  T3 非法字段           未声明字段 ⇒ 加载期 ValueError（含对象 id + 字段名）
  T4 派生字段隔离       fulfillment_status editable:true ⇒ 加载期 ValueError
  T5 原因为空拦截       reason_required_fields 命中且无 reason_code ⇒ REASON_CODE_REQUIRED 且未落库
  T6 原因码通过         同上 + reason_code ⇒ 成功，审计行 reason_code 落库
  T7 非必填字段不强制   只改白名单外字段 ⇒ 成功，reason_code 为空
  T8 变更集归组         一次 _write_audit_log_v2 只生成一个 cs_；同次保存多条审计共享
  T9 audit:false 排除   exclude_fields 传递 + log_update 真正跳过该字段
  T10 v148 幂等         连续 migrate 两次列存在；rollback 后索引消失（列按 SQLite 能力移除）

设计取舍：
  - _write_audit_log_v2 在 pytest 环境下会直接 return（PYTEST_CURRENT_TEST），
    因此 T8 先 delenv 再注入 fake audit_ds（in_transaction=True 走同步分支）；
  - T5/T7/T9 用 spy 替换 _write_audit_log_v2，避免依赖 audit_logs 表；
  - T6 直接调 AuditService.log 写临时库，验证真实落库。
"""
import importlib.util
import os
import re
import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.action_executor import ActionExecutor, AuditLogger
from meta.core.models import (
    MetaObject, MetaField, MetaAction, FieldType, ActionType,
)
from meta.core.rule_executor import RuleEngine
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.table_name_validator import register_table_name
from meta.core.yaml_loader import parse_revision_policy
from meta.services.audit_service import AuditService

CS_PATTERN = re.compile(r'^cs_[0-9a-f]{16}$')


# ---------------------------------------------------------------- 仓库对象

def _make_obj(revision_policy=None):
    """构造最简可更新对象（表 acs_order）。"""
    obj = MetaObject(
        id='acs_order',
        name='acs_order',
        table_name='acs_order',
        fields=[
            MetaField(id='id', name='ID', field_type=FieldType.INTEGER,
                      db_column='id', required=True),
            MetaField(id='name', name='名称', field_type=FieldType.STRING,
                      db_column='name', required=False),
            MetaField(id='total_amount', name='总额', field_type=FieldType.INTEGER,
                      db_column='total_amount', required=False),
            MetaField(id='customer_id', name='客户', field_type=FieldType.INTEGER,
                      db_column='customer_id', required=False),
        ],
        actions=[
            MetaAction(id='crud_update', name='更新', action_type=ActionType.CRUD,
                       method='PUT', path=''),
        ],
    )
    obj.revision_policy = revision_policy
    return obj


@pytest.fixture
def ds(tmp_path):
    data_source = SQLiteAdapter()
    data_source.connect(path=str(tmp_path / 'acs.db'))
    data_source.execute("""
        CREATE TABLE IF NOT EXISTS acs_order (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            total_amount INTEGER,
            customer_id INTEGER
        )
    """)
    register_table_name('acs_order')
    yield data_source
    data_source.disconnect()


@pytest.fixture
def executor(ds):
    return ActionExecutor(ds, RuleEngine(ds), audit_enabled=True)


@pytest.fixture
def spy_audit(monkeypatch):
    """替换 _write_audit_log_v2，记录 reason_code / exclude_fields。"""
    calls = []

    def spy(self, audit_fn, reason_code=None, exclude_fields=None):
        calls.append({'reason_code': reason_code, 'exclude_fields': exclude_fields})

    monkeypatch.setattr(ActionExecutor, '_write_audit_log_v2', spy)
    return calls


def _insert_order(ds, total_amount=100, customer_id=7, name='order-1'):
    ds.insert('acs_order', {
        'id': 1, 'name': name,
        'total_amount': total_amount, 'customer_id': customer_id,
    })


def _policy(**kwargs):
    from meta.core.models import MetaRevisionPolicy
    return MetaRevisionPolicy(**kwargs)


# ---------------------------------------------------------------- T1~T4 解析

class TestParsePolicy:
    def test_t1_defaults(self):
        """T1 只声明 enabled ⇒ 其余走默认值。"""
        rp = parse_revision_policy(
            {'id': 'demo', 'revision_policy': {'enabled': True}},
            ['total_amount'],
        )
        assert rp is not None
        assert rp.enabled is True
        assert rp.fields == []
        assert rp.reason_required_fields == []
        assert rp.scope == 'header'
        assert rp.generate_on == ['content_update']

    def test_t2_three_switches_default(self):
        """T2 fields 只写 field ⇒ editable=False, diff=False, audit=True。"""
        rp = parse_revision_policy(
            {'id': 'demo', 'revision_policy': {
                'enabled': True,
                'fields': [{'field': 'total_amount'}],
            }},
            ['total_amount'],
        )
        row = rp.fields[0]
        assert row.field == 'total_amount'
        assert row.editable is False
        assert row.diff is False
        assert row.audit is True

    def test_t3_unknown_field_raises(self):
        """T3 未声明字段 ⇒ 加载期报错，信息含对象 id 与字段名。"""
        with pytest.raises(ValueError) as ei:
            parse_revision_policy(
                {'id': 'demo', 'revision_policy': {
                    'enabled': True,
                    'fields': [{'field': 'not_exist'}],
                }},
                ['total_amount'],
            )
        msg = str(ei.value)
        assert 'demo' in msg
        assert 'not_exist' in msg

    def test_t4_derived_field_not_editable(self):
        """T4 派生字段不得 editable/diff。"""
        with pytest.raises(ValueError) as ei:
            parse_revision_policy(
                {'id': 'sales_order', 'revision_policy': {
                    'enabled': True,
                    'fields': [{'field': 'fulfillment_status', 'editable': True}],
                }},
                ['fulfillment_status'],
            )
        assert '派生字段' in str(ei.value)

    def test_no_policy_returns_none(self):
        """零回归：没有 revision_policy 段 ⇒ None（对象行为完全不变）。"""
        assert parse_revision_policy({'id': 'demo'}, ['total_amount']) is None


# ---------------------------------------------------------------- T5~T7/T9 更新策略

class TestUpdatePolicy:
    def test_t5_missing_reason_blocked(self, ds, executor, spy_audit):
        """T5 命中必填且无 reason_code ⇒ REASON_CODE_REQUIRED，且不写审计/不落库。"""
        _insert_order(ds, total_amount=100)
        obj = _make_obj(_policy(
            enabled=True,
            reason_required_fields=['total_amount'],
            fields=[],
        ))

        result = executor._do_update(obj, {'id': 1, 'total_amount': 200})

        assert result.success is False
        assert result.error == 'REASON_CODE_REQUIRED'
        assert 'total_amount' in result.message
        assert spy_audit == []
        row = ds.find_by_id('acs_order', 1)
        assert row['total_amount'] == 100

    def test_t6_reason_code_accepted_and_logged(self, ds, executor, spy_audit):
        """T6 带 reason_code ⇒ 成功，审计调用携带 reason_code。"""
        _insert_order(ds, total_amount=100)
        obj = _make_obj(_policy(
            enabled=True,
            reason_required_fields=['total_amount'],
            fields=[],
        ))

        result = executor._do_update(
            obj, {'id': 1, 'total_amount': 200, 'reason_code': 'PRICE_FIX'}
        )

        assert result.success is True, result.message
        assert ds.find_by_id('acs_order', 1)['total_amount'] == 200
        assert len(spy_audit) == 1
        assert spy_audit[0]['reason_code'] == 'PRICE_FIX'

    def test_t7_non_required_field_not_forced(self, ds, executor, spy_audit):
        """T7 只改白名单外字段 ⇒ 不强制原因码。"""
        _insert_order(ds, customer_id=7)
        obj = _make_obj(_policy(
            enabled=True,
            reason_required_fields=['total_amount'],
            fields=[],
        ))

        result = executor._do_update(obj, {'id': 1, 'customer_id': 9})

        assert result.success is True, result.message
        assert ds.find_by_id('acs_order', 1)['customer_id'] == 9
        assert spy_audit[0]['reason_code'] is None

    def test_t9_audit_false_excluded(self, ds, executor, spy_audit):
        """T9 audit:false ⇒ exclude_fields 传给审计层。"""
        from meta.core.models import RevisionFieldPolicy

        _insert_order(ds, customer_id=7)
        obj = _make_obj(_policy(
            enabled=True,
            fields=[RevisionFieldPolicy(field='customer_id', audit=False)],
        ))

        result = executor._do_update(obj, {'id': 1, 'customer_id': 9})

        assert result.success is True, result.message
        assert spy_audit[0]['exclude_fields'] == {'customer_id'}

    def test_t9_log_update_skips_excluded_field(self, monkeypatch):
        """T9 审计层真正跳过 exclude 字段（其它字段照常记录）。"""
        recorded = []

        def spy_log(self, **kwargs):
            recorded.append(kwargs.get('field_name'))
            return True

        monkeypatch.setattr(AuditLogger, 'log', spy_log)
        al = AuditLogger.__new__(AuditLogger)
        al.enabled = True
        al._current_user = {}
        al._agent_context = {}

        al.log_update(
            'acs_order', 1,
            {'total_amount': 100, 'customer_id': 7},
            {'total_amount': 200, 'customer_id': 9},
            change_set_id='cs_0123456789abcdef',
            exclude_fields={'customer_id'},
        )

        assert recorded == ['total_amount']


# ---------------------------------------------------------------- T8 变更集

class TestChangeSet:
    def test_t8_generated_and_shared(self, tmp_path, monkeypatch):
        """T8 一次 _write_audit_log_v2 生成一个 cs_，同次保存的多条审计共享。"""
        monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)

        class _FakeAuditDS:
            in_transaction = True

            def transaction(self):
                raise AssertionError('同步分支不应开启新事务')

        class _FakeAuditLogger:
            def __init__(self):
                self.audit_ds = _FakeAuditDS()

        data_source = SQLiteAdapter()
        data_source.connect(path=str(tmp_path / 'acs8.db'))
        try:
            ex = ActionExecutor(data_source, RuleEngine(data_source), audit_enabled=True)
            ex.audit_logger = _FakeAuditLogger()

            captured = []

            def audit_fn(**kwargs):
                captured.append(kwargs)

            ex._write_audit_log_v2(audit_fn, reason_code='WHY')
            ex._write_audit_log_v2(audit_fn)

            assert len(captured) == 2, '每次调用应触发一次 audit_fn'

            first, second = captured[0]['change_set_id'], captured[1]['change_set_id']
            assert CS_PATTERN.match(first), first
            assert CS_PATTERN.match(second), second
            assert first != second, '不同保存动作应生成不同变更集'
            assert captured[0]['reason_code'] == 'WHY'

            tx = captured[0]['transaction_id']
            assert tx is None or tx != first, 'change_set_id 与 transaction_id 解耦'
        finally:
            data_source.disconnect()

    def test_t8_field_rows_share_change_set(self, monkeypatch):
        """T8 同一次 log_update 扇出的多条字段审计共享同一 change_set_id。"""
        recorded = []

        def spy_log(self, **kwargs):
            recorded.append(kwargs.get('change_set_id'))
            return True

        monkeypatch.setattr(AuditLogger, 'log', spy_log)
        al = AuditLogger.__new__(AuditLogger)
        al.enabled = True
        al._current_user = {}
        al._agent_context = {}

        al.log_update(
            'acs_order', 1,
            {'total_amount': 100, 'customer_id': 7, 'name': 'a'},
            {'total_amount': 200, 'customer_id': 9, 'name': 'b'},
            change_set_id='cs_fedcba9876543210',
        )

        assert len(recorded) == 3
        assert set(recorded) == {'cs_fedcba9876543210'}


# ---------------------------------------------------------------- T6 落库

class TestAuditServicePersist:
    def test_t6_reason_code_persisted(self, tmp_path):
        """T6 AuditService.log 把 reason_code / change_set_id 真正写入 audit_logs。"""
        db_path = tmp_path / 'audit.db'
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT, object_id TEXT, action TEXT,
                field_name TEXT, old_value TEXT, new_value TEXT,
                user_id TEXT, user_name TEXT, ip_address TEXT, user_agent TEXT,
                created_at TEXT, trace_id TEXT, transaction_id TEXT,
                change_set_id TEXT, reason_code TEXT,
                agent_id TEXT, agent_session_id TEXT, tool_call_id TEXT,
                agent_reasoning TEXT, status TEXT, extra_data TEXT,
                parent_object_type TEXT, parent_object_id TEXT,
                log_category TEXT, log_level TEXT, outcome TEXT,
                retention_until TEXT, cascade_root_id TEXT,
                cascade_root_action TEXT, error_message TEXT
            )
        """)
        conn.commit()
        conn.close()

        data_source = SQLiteAdapter()
        data_source.connect(path=str(db_path))
        try:
            ok = AuditService(data_source).log(
                object_type='acs_order', object_id=1, action='UPDATE',
                field_name='total_amount', old_value='100', new_value='200',
                change_set_id='cs_0123456789abcdef',
                reason_code='PRICE_FIX',
                user_name='tester',
            )
            assert ok is True

            rows = data_source.execute(
                "SELECT change_set_id, reason_code FROM audit_logs"
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == 'cs_0123456789abcdef'
            assert rows[0][1] == 'PRICE_FIX'
        finally:
            data_source.disconnect()


# ---------------------------------------------------------------- T10 迁移

def _load_migration():
    path = Path(PROJECT_ROOT) / 'meta' / 'migrations' / 'v148__audit_change_set.py'
    spec = importlib.util.spec_from_file_location('v148_audit_change_set', str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMigrationV148:
    def test_t10_idempotent_and_rollback(self, tmp_path, capsys):
        """T10 migrate 两次幂等；rollback 后索引消失（列按 SQLite 能力移除）。"""
        m = _load_migration()
        db_path = tmp_path / 'm148.db'

        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT, object_id TEXT, action TEXT, created_at TEXT
            )
        """)
        conn.commit()
        conn.close()

        assert m.migrate(db_path) is True
        assert m.verify(db_path) is True

        # 第二次：两列应打印 SKIP，终态仍一致
        assert m.migrate(db_path) is True
        assert m.verify(db_path) is True
        assert capsys.readouterr().out.count('[SKIP]') >= 2

        cols = _columns(db_path, 'audit_logs')
        assert 'change_set_id' in cols and 'reason_code' in cols

        assert m.rollback(db_path) is True
        assert m.verify(db_path) is False, 'rollback 后索引必须消失，verify 应失败'

        if sqlite3.sqlite_version_info >= (3, 35, 0):
            cols_after = _columns(db_path, 'audit_logs')
            assert 'change_set_id' not in cols_after
            assert 'reason_code' not in cols_after


def _columns(db_path, table):
    conn = sqlite3.connect(str(db_path))
    try:
        return {row[1] for row in conn.execute('PRAGMA table_info(%s)' % table)}
    finally:
        conn.close()
