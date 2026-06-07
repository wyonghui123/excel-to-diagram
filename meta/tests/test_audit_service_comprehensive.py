import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
AuditService 核心服务全面测试用例

测试范围：
1. 审计日志写入 (log方法)
2. 审计日志查询 (query方法)
3. 对象历史查询 (get_object_history)
4. 用户活动查询 (get_user_activities)
5. 变更摘要 (get_change_summary)
6. 分类统计 (get_category_statistics)
7. 失败日志处理 (get_failed_audit_logs, retry_failed_record)
8. 导出功能 (export_audit_log)
"""

import pytest
import sqlite3
import tempfile
import os
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from meta.services.audit_service import AuditService, AuditQuery, AuditRecord
from meta.core.datasource import get_data_source


class TestAuditServiceInit:
    """AuditService 初始化测试"""
    
    def test_init_with_data_source(self):
        """测试使用数据源初始化"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            ds = get_data_source("sqlite", database=path)
            service = AuditService(ds)
            assert service.ds is ds
            assert service.AUDIT_TABLE == "audit_logs"
        finally:
            try:
                os.unlink(path)
            except:
                pass
    
    def test_audit_table_constant(self):
        """测试审计表常量"""
        assert AuditService.AUDIT_TABLE == "audit_logs"


class TestAuditQueryDataclass:
    """AuditQuery 数据类测试"""
    
    def test_default_values(self):
        """测试默认值"""
        query = AuditQuery()
        assert query.object_type is None
        assert query.object_id is None
        assert query.action is None
        assert query.user_id is None
        assert query.user_name is None
        assert query.start_time is None
        assert query.end_time is None
        assert query.field_name is None
        assert query.keyword is None
        assert query.trace_id is None
        assert query.transaction_id is None
        assert query.status is None
        assert query.log_category is None
        assert query.log_level is None
    
    def test_with_all_fields(self):
        """测试设置所有字段"""
        query = AuditQuery(
            object_type='user',
            object_id='1',
            action='CREATE',
            user_id='admin',
            user_name='Administrator',
            start_time='2024-01-01',
            end_time='2024-12-31',
            field_name='name',
            keyword='test',
            trace_id='trace-123',
            transaction_id='txn-456',
            status='written',
            log_category='business',
            log_level='INFO'
        )
        assert query.object_type == 'user'
        assert query.object_id == '1'
        assert query.action == 'CREATE'
        assert query.user_id == 'admin'
        assert query.user_name == 'Administrator'
        assert query.start_time == '2024-01-01'
        assert query.end_time == '2024-12-31'
        assert query.field_name == 'name'
        assert query.keyword == 'test'
        assert query.trace_id == 'trace-123'
        assert query.transaction_id == 'txn-456'
        assert query.status == 'written'
        assert query.log_category == 'business'
        assert query.log_level == 'INFO'


class TestAuditRecordDataclass:
    """AuditRecord 数据类测试"""
    
    def test_required_fields(self):
        """测试必需字段"""
        record = AuditRecord(
            id=1,
            object_type='user',
            object_id='1',
            action='CREATE',
            field_name='name',
            old_value='',
            new_value='test',
            user_id='admin',
            user_name='Administrator',
            ip_address='127.0.0.1',
            user_agent='Mozilla',
            created_at='2024-01-01T00:00:00'
        )
        assert record.id == 1
        assert record.object_type == 'user'
        assert record.action == 'CREATE'
    
    def test_optional_fields(self):
        """测试可选字段"""
        record = AuditRecord(
            id=1,
            object_type='user',
            object_id='1',
            action='CREATE',
            field_name='name',
            old_value='',
            new_value='test',
            user_id='admin',
            user_name='Administrator',
            ip_address='127.0.0.1',
            user_agent='Mozilla',
            created_at='2024-01-01T00:00:00',
            trace_id='trace-123',
            transaction_id='txn-456',
            status='written',
            agent_id='agent-1',
            agent_session_id='session-1',
            tool_call_id='tool-1',
            agent_reasoning='test reasoning',
            log_category='business',
            log_level='INFO'
        )
        assert record.trace_id == 'trace-123'
        assert record.transaction_id == 'txn-456'
        assert record.status == 'written'
        assert record.agent_id == 'agent-1'
        assert record.log_category == 'business'


class TestAuditServiceLog:
    """AuditService.log 方法测试"""
    
    @pytest.fixture
    def audit_service(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT,
                object_id TEXT,
                action TEXT,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                user_id TEXT,
                user_name TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT,
                trace_id TEXT,
                transaction_id TEXT,
                status TEXT DEFAULT 'written',
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                log_category TEXT DEFAULT 'business',
                log_level TEXT DEFAULT 'INFO',
                extra_data TEXT,
                parent_object_type TEXT,
                parent_object_id TEXT,
                agent_id TEXT,
                agent_session_id TEXT,
                tool_call_id TEXT,
                agent_reasoning TEXT
            );
        """)
        conn.commit()
        conn.close()
        
        ds = get_data_source("sqlite", database=path)
        service = AuditService(ds)
        yield service, path
        
        try:
            os.unlink(path)
        except:
            pass
    
    def test_log_create_action(self, audit_service):
        """测试CREATE动作日志"""
        service, path = audit_service
        
        result = service.log(
            object_type='user',
            object_id='1',
            action='CREATE',
            user_id='admin',
            user_name='Administrator',
            new_data={'name': 'Test User', 'email': 'test@example.com'},
            ip_address='127.0.0.1',
            user_agent='Mozilla'
        )
        
        assert result is True
        
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM audit_logs WHERE action = 'CREATE'")
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) >= 2
        field_names = [row['field_name'] for row in rows]
        assert 'name' in field_names
        assert 'email' in field_names
    
    def test_log_update_action(self, audit_service):
        """测试UPDATE动作日志"""
        service, path = audit_service
        
        result = service.log(
            object_type='user',
            object_id='1',
            action='UPDATE',
            user_id='admin',
            user_name='Administrator',
            old_data={'name': 'Old Name', 'email': 'old@example.com'},
            new_data={'name': 'New Name', 'email': 'new@example.com'},
            ip_address='127.0.0.1'
        )
        
        assert result is True
        
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM audit_logs WHERE action = 'UPDATE'")
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) >= 2
    
    def test_log_delete_action(self, audit_service):
        """测试DELETE动作日志"""
        service, path = audit_service
        
        result = service.log(
            object_type='user',
            object_id='1',
            action='DELETE',
            user_id='admin',
            user_name='Administrator',
            old_data={'name': 'Test User', 'email': 'test@example.com'},
            ip_address='127.0.0.1'
        )
        
        assert result is True
        
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM audit_logs WHERE action = 'DELETE'")
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) >= 1
    
    def test_log_associate_action(self, audit_service):
        """测试ASSOCIATE动作日志"""
        service, path = audit_service
        
        result = service.log(
            object_type='user_group',
            object_id='1',
            action='ASSOCIATE',
            user_id='admin',
            user_name='Administrator',
            field_name='members',
            new_data={'user_id': 2, 'user_name': 'Test User'},
            ip_address='127.0.0.1'
        )
        
        assert result is True
        
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM audit_logs WHERE action = 'ASSOCIATE'")
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) == 1
        assert rows[0]['field_name'] == 'members'
    
    def test_log_dissociate_action(self, audit_service):
        """测试DISSOCIATE动作日志"""
        service, path = audit_service
        
        result = service.log(
            object_type='user_group',
            object_id='1',
            action='DISSOCIATE',
            user_id='admin',
            user_name='Administrator',
            field_name='members',
            old_data={'user_id': 2, 'user_name': 'Test User'},
            ip_address='127.0.0.1'
        )
        
        assert result is True
        
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM audit_logs WHERE action = 'DISSOCIATE'")
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) == 1
    
    def test_log_with_field_name_directly(self, audit_service):
        """测试直接传递字段名"""
        service, path = audit_service
        
        result = service.log(
            object_type='user',
            object_id='1',
            action='UPDATE',
            user_id='admin',
            user_name='Administrator',
            field_name='status',
            old_value='active',
            new_value='inactive',
            ip_address='127.0.0.1'
        )
        
        assert result is True
        
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM audit_logs")
        row = cursor.fetchone()
        conn.close()
        
        assert row['field_name'] == 'status'
        assert row['old_value'] == 'active'
        assert row['new_value'] == 'inactive'
    
    def test_log_with_trace_id(self, audit_service):
        """测试带trace_id的日志"""
        service, path = audit_service
        
        result = service.log(
            object_type='user',
            object_id='1',
            action='CREATE',
            user_id='admin',
            user_name='Administrator',
            new_data={'name': 'Test'},
            trace_id='trace-123',
            transaction_id='txn-456',
            ip_address='127.0.0.1'
        )
        
        assert result is True
        
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM audit_logs")
        row = cursor.fetchone()
        conn.close()
        
        assert row['trace_id'] == 'trace-123'
        assert row['transaction_id'] == 'txn-456'
    
    def test_log_with_agent_context(self, audit_service):
        """测试带Agent上下文的日志"""
        service, path = audit_service
        
        result = service.log(
            object_type='document',
            object_id='1',
            action='CREATE',
            user_id='admin',
            user_name='Administrator',
            new_data={'content': 'test'},
            agent_id='agent-1',
            agent_session_id='session-1',
            tool_call_id='tool-1',
            agent_reasoning='Creating document for user request',
            ip_address='127.0.0.1'
        )
        
        assert result is True
        
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM audit_logs")
        row = cursor.fetchone()
        conn.close()
        
        assert row['agent_id'] == 'agent-1'
        assert row['agent_session_id'] == 'session-1'
        assert row['tool_call_id'] == 'tool-1'
        assert row['agent_reasoning'] == 'Creating document for user request'
    
    def test_log_with_log_category_and_level(self, audit_service):
        """测试带日志分类和级别的日志"""
        service, path = audit_service
        
        result = service.log(
            object_type='user',
            object_id='1',
            action='LOGIN',
            user_id='admin',
            user_name='Administrator',
            field_name='session',
            new_value='created',
            log_category='security',
            log_level='WARNING',
            ip_address='127.0.0.1'
        )
        
        assert result is True
        
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM audit_logs")
        row = cursor.fetchone()
        conn.close()
        
        assert row['log_category'] == 'security'
        assert row['log_level'] == 'WARNING'
    
    def test_log_with_parent_object(self, audit_service):
        """测试带父对象的日志"""
        service, path = audit_service
        
        result = service.log(
            object_type='user_group_member',
            object_id='1',
            action='CREATE',
            user_id='admin',
            user_name='Administrator',
            new_data={'user_id': 2},
            parent_object_type='user_group',
            parent_object_id='1',
            ip_address='127.0.0.1'
        )
        
        assert result is True
        
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM audit_logs")
        row = cursor.fetchone()
        conn.close()
        
        assert row['parent_object_type'] == 'user_group'
        assert row['parent_object_id'] == '1'


class TestAuditServiceQuery:
    """AuditService.query 方法测试"""
    
    @pytest.fixture
    def audit_service_with_data(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT,
                object_id TEXT,
                action TEXT,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                user_id TEXT,
                user_name TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT,
                trace_id TEXT,
                transaction_id TEXT,
                status TEXT DEFAULT 'written',
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                log_category TEXT DEFAULT 'business',
                log_level TEXT DEFAULT 'INFO',
                extra_data TEXT,
                parent_object_type TEXT,
                parent_object_id TEXT,
                agent_id TEXT,
                agent_session_id TEXT,
                tool_call_id TEXT,
                agent_reasoning TEXT
            );
        """)
        
        now = datetime.now().isoformat()
        old_date = (datetime.now() - timedelta(days=10)).isoformat()
        
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, user_id, user_name, created_at, log_category)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('user', '1', 'CREATE', 'admin', 'Administrator', now, 'business'))
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, user_id, user_name, created_at, log_category)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('user', '2', 'UPDATE', 'admin', 'Administrator', now, 'business'))
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, user_id, user_name, created_at, log_category)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('role', '1', 'CREATE', 'admin', 'Administrator', old_date, 'security'))
        conn.commit()
        conn.close()
        
        ds = get_data_source("sqlite", database=path)
        service = AuditService(ds)
        yield service, path
        
        try:
            os.unlink(path)
        except:
            pass
    
    def test_query_all(self, audit_service_with_data):
        """测试查询所有日志"""
        service, _ = audit_service_with_data
        
        result = service.query(AuditQuery(), page=1, page_size=10)
        
        assert result['total'] == 3
        assert len(result.get('data', {})) == 3
        assert result['page'] == 1
        assert result['page_size'] == 10
    
    def test_query_by_object_type(self, audit_service_with_data):
        """测试按对象类型查询"""
        service, _ = audit_service_with_data
        
        result = service.query(AuditQuery(object_type='user'), page=1, page_size=10)
        
        assert result['total'] == 2
        assert all(r.object_type == 'user' for r in result.get('data', {}))
    
    def test_query_by_action(self, audit_service_with_data):
        """测试按动作查询"""
        service, _ = audit_service_with_data
        
        result = service.query(AuditQuery(action='CREATE'), page=1, page_size=10)
        
        assert result['total'] == 2
        assert all(r.action == 'CREATE' for r in result.get('data', {}))
    
    def test_query_by_user_id(self, audit_service_with_data):
        """测试按用户ID查询"""
        service, _ = audit_service_with_data
        
        result = service.query(AuditQuery(user_id='admin'), page=1, page_size=10)
        
        assert result['total'] == 3
    
    def test_query_by_log_category(self, audit_service_with_data):
        """测试按日志分类查询"""
        service, _ = audit_service_with_data
        
        result = service.query(AuditQuery(log_category='security'), page=1, page_size=10)
        
        assert result['total'] == 1
        assert result.get('data', {})[0].object_type == 'role'
    
    def test_query_with_pagination(self, audit_service_with_data):
        """测试分页查询"""
        service, _ = audit_service_with_data
        
        result = service.query(AuditQuery(), page=1, page_size=2)
        
        assert result['total'] == 3
        assert len(result.get('data', {})) == 2
        assert result['total_pages'] == 2
        
        result2 = service.query(AuditQuery(), page=2, page_size=2)
        assert len(result2['data']) == 1


class TestAuditServiceObjectHistory:
    """AuditService.get_object_history 方法测试"""
    
    @pytest.fixture
    def audit_service_with_history(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT,
                object_id TEXT,
                action TEXT,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                user_id TEXT,
                user_name TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT,
                trace_id TEXT,
                transaction_id TEXT,
                status TEXT DEFAULT 'written',
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                log_category TEXT DEFAULT 'business',
                log_level TEXT DEFAULT 'INFO',
                extra_data TEXT,
                parent_object_type TEXT,
                parent_object_id TEXT,
                agent_id TEXT,
                agent_session_id TEXT,
                tool_call_id TEXT,
                agent_reasoning TEXT
            );
        """)
        
        now = datetime.now().isoformat()
        
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, field_name, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, ('user', '1', 'CREATE', 'name', now))
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, field_name, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, ('user', '1', 'UPDATE', 'email', now))
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, field_name, parent_object_type, parent_object_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('user_role', '1', 'CREATE', 'role_id', 'user', '1', now))
        conn.commit()
        conn.close()
        
        ds = get_data_source("sqlite", database=path)
        service = AuditService(ds)
        yield service, path
        
        try:
            os.unlink(path)
        except:
            pass
    
    def test_get_object_history_basic(self, audit_service_with_history):
        """测试获取对象历史"""
        service, _ = audit_service_with_history
        
        history = service.get_object_history('user', '1')
        
        assert len(history) == 2
        assert all(h['object_type'] == 'user' for h in history)
    
    def test_get_object_history_with_children(self, audit_service_with_history):
        """测试获取对象历史包含子对象"""
        service, _ = audit_service_with_history
        
        history = service.get_object_history('user', '1', include_children=True)
        
        assert len(history) == 3


class TestAuditServiceUserActivities:
    """AuditService.get_user_activities 方法测试"""
    
    @pytest.fixture
    def audit_service_with_activities(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT,
                object_id TEXT,
                action TEXT,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                user_id TEXT,
                user_name TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT,
                trace_id TEXT,
                transaction_id TEXT,
                status TEXT DEFAULT 'written',
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                log_category TEXT DEFAULT 'business',
                log_level TEXT DEFAULT 'INFO'
            );
        """)
        
        now = datetime.now().isoformat()
        
        for i in range(5):
            conn.execute("""
                INSERT INTO audit_logs (object_type, object_id, action, user_id, user_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ('user', str(i), 'CREATE', 'admin', 'Administrator', now))
        
        for i in range(3):
            conn.execute("""
                INSERT INTO audit_logs (object_type, object_id, action, user_id, user_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ('role', str(i), 'UPDATE', 'admin', 'Administrator', now))
        
        conn.commit()
        conn.close()
        
        ds = get_data_source("sqlite", database=path)
        service = AuditService(ds)
        yield service, path
        
        try:
            os.unlink(path)
        except:
            pass
    
    def test_get_user_activities(self, audit_service_with_activities):
        """测试获取用户活动"""
        service, _ = audit_service_with_activities
        
        activities = service.get_user_activities('admin', days=30)
        
        assert activities['user_id'] == 'admin'
        assert activities['total_actions'] == 8
        assert 'action_counts' in activities
        assert 'object_type_counts' in activities
        assert activities['action_counts'].get('CREATE', 0) == 5
        assert activities['action_counts'].get('UPDATE', 0) == 3


class TestAuditServiceChangeSummary:
    """AuditService.get_change_summary 方法测试"""
    
    @pytest.fixture
    def audit_service_with_changes(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT,
                object_id TEXT,
                action TEXT,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                user_id TEXT,
                user_name TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT,
                trace_id TEXT,
                transaction_id TEXT,
                status TEXT DEFAULT 'written',
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                log_category TEXT DEFAULT 'business',
                log_level TEXT DEFAULT 'INFO'
            );
        """)
        
        now = datetime.now().isoformat()
        
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, field_name, user_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('user', '1', 'CREATE', 'name', 'admin', now))
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, field_name, user_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('user', '1', 'UPDATE', 'email', 'admin', now))
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, field_name, user_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('role', '1', 'CREATE', 'name', 'user1', now))
        
        conn.commit()
        conn.close()
        
        ds = get_data_source("sqlite", database=path)
        service = AuditService(ds)
        yield service, path
        
        try:
            os.unlink(path)
        except:
            pass
    
    def test_get_change_summary(self, audit_service_with_changes):
        """测试获取变更摘要"""
        service, _ = audit_service_with_changes
        
        summary = service.get_change_summary()
        
        assert summary['total_changes'] == 3
        assert 'action_counts' in summary
        assert 'object_type_counts' in summary
        assert 'user_counts' in summary
    
    def test_get_change_summary_by_object_type(self, audit_service_with_changes):
        """测试按对象类型获取变更摘要"""
        service, _ = audit_service_with_changes
        
        summary = service.get_change_summary(object_type='user')
        
        assert summary['total_changes'] == 2


class TestAuditServiceCategoryStatistics:
    """AuditService.get_category_statistics 方法测试"""
    
    @pytest.fixture
    def audit_service_with_categories(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT,
                object_id TEXT,
                action TEXT,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                user_id TEXT,
                user_name TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT,
                trace_id TEXT,
                transaction_id TEXT,
                status TEXT DEFAULT 'written',
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                log_category TEXT DEFAULT 'business',
                log_level TEXT DEFAULT 'INFO'
            );
        """)
        
        now = datetime.now().isoformat()
        
        for i in range(5):
            conn.execute("""
                INSERT INTO audit_logs (object_type, object_id, action, log_category, log_level, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ('user', str(i), 'CREATE', 'business', 'INFO', now))
        
        for i in range(3):
            conn.execute("""
                INSERT INTO audit_logs (object_type, object_id, action, log_category, log_level, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ('user', str(i), 'LOGIN', 'security', 'WARNING', now))
        
        conn.commit()
        conn.close()
        
        ds = get_data_source("sqlite", database=path)
        service = AuditService(ds)
        yield service, path
        
        try:
            os.unlink(path)
        except:
            pass
    
    def test_get_category_statistics(self, audit_service_with_categories):
        """测试获取分类统计"""
        service, _ = audit_service_with_categories
        
        stats = service.get_category_statistics()
        
        assert stats['total'] == 8
        assert 'by_category' in stats
        assert 'by_level' in stats
        assert stats['by_category'].get('business', 0) == 5
        assert stats['by_category'].get('security', 0) == 3
        assert stats['by_level'].get('INFO', 0) == 5
        assert stats['by_level'].get('WARNING', 0) == 3


class TestAuditServiceFailedLogs:
    """AuditService 失败日志处理测试"""
    
    @pytest.fixture
    def audit_service_with_failed(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT,
                object_id TEXT,
                action TEXT,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                user_id TEXT,
                user_name TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT,
                trace_id TEXT,
                transaction_id TEXT,
                status TEXT DEFAULT 'written',
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                log_category TEXT DEFAULT 'business',
                log_level TEXT DEFAULT 'INFO'
            );
        """)
        
        now = datetime.now().isoformat()
        
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, status, retry_count, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('user', '1', 'CREATE', 'failed', 0, 'Connection error', now))
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, status, retry_count, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('user', '2', 'UPDATE', 'failed', 2, 'Timeout', now))
        conn.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, status, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, ('user', '3', 'DELETE', 'written', now))
        
        conn.commit()
        conn.close()
        
        ds = get_data_source("sqlite", database=path)
        service = AuditService(ds)
        yield service, path
        
        try:
            os.unlink(path)
        except:
            pass
    
    def test_get_failed_audit_logs(self, audit_service_with_failed):
        """测试获取失败日志"""
        service, _ = audit_service_with_failed
        
        result = service.get_failed_audit_logs(page=1, page_size=10)
        
        assert result['total'] == 2
        assert len(result.get('data', {})) == 2
    
    def test_retry_failed_record_success(self, audit_service_with_failed):
        """测试重试失败记录成功"""
        service, path = audit_service_with_failed
        
        result = service.retry_failed_record(1)
        
        assert result.get('success', False) is True
        
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT status, retry_count FROM audit_logs WHERE id = 1")
        row = cursor.fetchone()
        conn.close()
        
        assert row['status'] == 'written'
        assert row['retry_count'] == 1
    
    def test_retry_failed_record_not_found(self, audit_service_with_failed):
        """测试重试不存在的记录"""
        service, _ = audit_service_with_failed
        
        result = service.retry_failed_record(999)
        
        assert result.get('success', False) is False
        assert '不存在' in result['message']
    
    def test_retry_failed_record_not_failed(self, audit_service_with_failed):
        """测试重试非失败状态的记录"""
        service, _ = audit_service_with_failed
        
        result = service.retry_failed_record(3)
        
        assert result.get('success', False) is False
        assert '不是failed' in result['message']
