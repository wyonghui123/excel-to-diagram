# -*- coding: utf-8 -*-
"""
[NEW 2026-06-09] 3 个 audit log bug 修复验证

Bug 1: CREATE/UPDATE 没有明细字段数据 (BusinessLogInterceptor → structured_logger →
        audit_service 路径只写 fallback `_record` 行, 不展开字段)
Bug 2: DISSOCIATE 没有审计日志 (AuditInterceptor 对 dissociate 应正常写)
Bug 3: ASSOCIATE 的 target_display=null (get_object_display 在 display_field 为 NULL 时无回退)
"""
import json
import os
import sqlite3
import tempfile
import pytest
from unittest.mock import MagicMock, PropertyMock


def _flush_async_writer(timeout=3.0):
    """等待 StructuredLogger 异步队列清空, 用于测试断言"""
    from meta.services.async_audit_writer import async_audit_writer
    try:
        async_audit_writer.flush(timeout=timeout)
    except Exception:
        pass


@pytest.fixture
def fresh_db():
    """建一个完整的 audit_logs 表 (含 agent_session_id, 跟生产一致)"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT, object_id TEXT, action TEXT,
            field_name TEXT, old_value TEXT, new_value TEXT,
            user_id TEXT, user_name TEXT, ip_address TEXT, user_agent TEXT,
            created_at TEXT, trace_id TEXT, transaction_id TEXT,
            status TEXT DEFAULT 'written', retry_count INTEGER DEFAULT 0,
            error_message TEXT, log_category TEXT DEFAULT 'business',
            log_level TEXT DEFAULT 'INFO', extra_data TEXT,
            parent_object_type TEXT, parent_object_id TEXT,
            agent_id TEXT, agent_session_id TEXT, tool_call_id TEXT, agent_reasoning TEXT
        );
    """)
    conn.commit()
    conn.close()
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


# ============================================================
# Bug 1: structured_logger → audit_service 字段展开
# ============================================================

class TestStructuredLoggerAuditFieldExpansion:
    """Bug 1: BusinessLogInterceptor 写业务日志时, 应展开每个字段为一行"""

    def test_create_with_dict_new_data_should_expand_fields(self, fresh_db):
        """CREATE 传 new_data=dict 时, 应展开为每字段一行 + 不依赖 fallback `_record`"""
        from meta.core.datasource import get_data_source
        from meta.services.structured_logger import StructuredLogger
        from meta.services.async_audit_writer import async_audit_writer

        ds = get_data_source("sqlite", database=fresh_db)
        async_audit_writer.set_data_source(ds)

        logger = StructuredLogger()
        # 模拟 BusinessLogInterceptor 调用: new_data 是 dict, field_name=None
        logger.log_business(
            action='CREATE',
            object_type='user_group',
            object_id='403',
            user_id='1',
            user_name='admin',
            new_data={'name': 'Test Group', 'code': 'test_grp', 'description': 'desc'},
            ip_address='127.0.0.1',
            trace_id='trace-bug1',
        )
        _flush_async_writer()

        conn = sqlite3.connect(fresh_db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT field_name, old_value, new_value, action FROM audit_logs WHERE trace_id = 'trace-bug1'"
        ).fetchall()
        conn.close()

        field_names = {r['field_name'] for r in rows}
        # 应该展开为每字段一行, 而不是只有 fallback `_record` 行
        assert 'name' in field_names, f"应展开 name 字段, 实际: {field_names}"
        assert 'code' in field_names, f"应展开 code 字段, 实际: {field_names}"
        assert 'description' in field_names, f"应展开 description 字段, 实际: {field_names}"
        for r in rows:
            if r['field_name'] == 'name':
                assert r['new_value'] == 'Test Group'
            elif r['field_name'] == 'code':
                assert r['new_value'] == 'test_grp'
        # 不应只有 fallback `_record` 行
        assert '_record' not in field_names, f"不应回退到 _record fallback, 实际: {field_names}"

    def test_update_with_dict_old_new_data_should_show_diff(self, fresh_db):
        """UPDATE 传 old_data + new_data 时, 应只写有变化的字段行"""
        from meta.core.datasource import get_data_source
        from meta.services.structured_logger import StructuredLogger
        from meta.services.async_audit_writer import async_audit_writer

        ds = get_data_source("sqlite", database=fresh_db)
        async_audit_writer.set_data_source(ds)

        logger = StructuredLogger()
        logger.log_business(
            action='UPDATE',
            object_type='user_group',
            object_id='403',
            user_id='1',
            user_name='admin',
            old_data={'name': 'Old Name', 'code': 'same_code', 'description': 'old desc'},
            new_data={'name': 'New Name', 'code': 'same_code', 'description': 'new desc'},
            ip_address='127.0.0.1',
            trace_id='trace-bug1-upd',
        )
        _flush_async_writer()

        conn = sqlite3.connect(fresh_db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT field_name, old_value, new_value FROM audit_logs WHERE trace_id = 'trace-bug1-upd'"
        ).fetchall()
        conn.close()

        rows_by_field = {r['field_name']: r for r in rows}
        assert 'name' in rows_by_field
        assert rows_by_field['name']['old_value'] == 'Old Name'
        assert rows_by_field['name']['new_value'] == 'New Name'
        assert 'description' in rows_by_field
        assert rows_by_field['description']['old_value'] == 'old desc'
        assert rows_by_field['description']['new_value'] == 'new desc'
        # code 没变化, 不应出现在日志中
        assert 'code' not in rows_by_field, "未变化的字段不应写日志"

    def test_associate_with_field_name_still_uses_field_name_branch(self, fresh_db):
        """ASSOCIATE 传 field_name + new_data 时, 应保持单行 (旧行为), 不被 Bug1 修复破坏"""
        from meta.core.datasource import get_data_source
        from meta.services.structured_logger import StructuredLogger
        from meta.services.async_audit_writer import async_audit_writer

        ds = get_data_source("sqlite", database=fresh_db)
        async_audit_writer.set_data_source(ds)

        logger = StructuredLogger()
        # 模拟 AuditInterceptor._log_association_event: 传 field_name='成员', new_data 是 dict
        logger.log_business(
            action='ASSOCIATE',
            object_type='user_group',
            object_id='403',
            user_id='1',
            user_name='admin',
            field_name='成员',
            new_data={'target_type': '用户', 'target_display': 'P13 Test', 'target_id': 1368},
            parent_object_type='user',
            parent_object_id='1368',
            ip_address='127.0.0.1',
            trace_id='trace-bug1-assoc',
        )
        _flush_async_writer()

        conn = sqlite3.connect(fresh_db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT field_name, old_value, new_value FROM audit_logs WHERE trace_id = 'trace-bug1-assoc'"
        ).fetchall()
        conn.close()

        # ASSOCIATE 应保持 field_name='成员', new_value=JSON 的单行格式 (旧行为)
        assert len(rows) == 1, f"ASSOCIATE 应单行, 实际 {len(rows)} 行"
        assert rows[0]['field_name'] == '成员'
        new_val = json.loads(rows[0]['new_value'])
        assert new_val['target_id'] == 1368
        assert new_val['target_display'] == 'P13 Test'


# ============================================================
# Bug 3: get_object_display 在 display_field 为 NULL 时回退
# ============================================================

class TestGetObjectDisplayNullFallback:
    """Bug 3: display_field 为 NULL 时, get_object_display 应回退到其他字段"""

    @pytest.fixture
    def db_with_user(self):
        """建一个临时 DB, 里面有 display_name=NULL 的用户"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                display_name TEXT,
                email TEXT
            );
            INSERT INTO users (id, username, display_name, email)
            VALUES (1, 'p13_user', NULL, 'p13@example.com');
            INSERT INTO users (id, username, display_name, email)
            VALUES (2, 'p14_user', 'Real Name', 'p14@example.com');
        """)
        conn.commit()
        conn.close()
        yield path
        try:
            os.unlink(path)
        except Exception:
            pass

    def test_display_name_null_should_fallback_to_username(self, db_with_user):
        from meta.core.datasource import get_data_source
        from meta.core.model_utils import get_object_display

        ds = get_data_source("sqlite", database=db_with_user)
        # 用户 display_name=NULL, username='p13_user' → 应回退到 username
        result = get_object_display('user', 1, ds)
        assert result == 'p13_user', f"display_name=NULL 时应回退到 username, 实际: {result!r}"

    def test_display_name_present_should_use_display_name(self, db_with_user):
        from meta.core.datasource import get_data_source
        from meta.core.model_utils import get_object_display

        ds = get_data_source("sqlite", database=db_with_user)
        # display_name 有值 → 直接用
        result = get_object_display('user', 2, ds)
        assert result == 'Real Name', f"display_name 有值时直接用, 实际: {result!r}"


# ============================================================
# Bug 2: DISSOCIATE 应正常写审计日志
# ============================================================

class TestDissociateAuditLog:
    """Bug 2: AuditInterceptor 对 dissociate 应写审计日志, 不静默失败"""

    def test_dissociate_via_real_interceptor(self):
        """用真实 ActionContext 调 AuditInterceptor.after_action 模拟 dissociate 流程"""
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        from meta.core.action_context import ActionContext, ActionResult
        from meta.core.models import AuditConfig, AuditActionConfig
        from meta.services.structured_logger import StructuredLogger

        mock_logger = MagicMock(spec=StructuredLogger)
        interceptor = AuditInterceptor(structured_logger=mock_logger)

        # 用真实的 AuditConfig, 避免 MagicMock 把 property 当 truthy
        audit_cfg = AuditConfig(enabled=True)
        audit_cfg.dissociate = AuditActionConfig(enabled=True)

        # 用一个简单的 namespace 对象模拟 meta_object
        # 必须包含 id (ActionContext.object_type 用), table_name, fields
        meta_obj = type('M', (), {
            'id': 'user_group',
            'table_name': 'user_groups',
            'fields': [],
            'audit': audit_cfg,
        })()

        ctx = ActionContext(
            meta_object=meta_obj,
            action='dissociate',
            params={'src_id': 403, 'tgt_type': 'user', 'tgt_id': 1378, 'association_name': 'members'},
            data_source=MagicMock(),
            user_id=1,
            user_name='admin',
            ip_address='127.0.0.1',
            trace_id='trace-bug2',
        )
        ctx.result = ActionResult(success=True, data=None)

        interceptor.after_action(ctx)

        # 验证 structured_logger.log_business 被调用
        assert mock_logger.log_business.called, "DISSOCIATE 应调用 log_business 写日志"
        call_kwargs = mock_logger.log_business.call_args.kwargs
        assert call_kwargs.get('action') == 'DISSOCIATE', f"action 应为 DISSOCIATE, 实际: {call_kwargs.get('action')}"
        # DISSOCIATE 应记录被移除的对象 (old_data)
        assert call_kwargs.get('old_data') is not None
        assert call_kwargs.get('new_data') is None
