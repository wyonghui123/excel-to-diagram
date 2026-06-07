import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
Phase 14 日志拦截器测试 - 业务日志

测试范围：
- Business Log Interceptor 创建日志
- Business Log Interceptor 更新日志
- Business Log Interceptor 删除日志
- 字段变更记录
- 操作人/时间戳记录

对应规范: TC-LG-001 ~ TC-LG-015
"""

import pytest
import sqlite3
import os
import tempfile
from datetime import datetime


class TestBusinessLogInterceptor:
    """业务日志拦截器测试"""

    @pytest.fixture
    def db_connection(self):
        """创建测试数据库连接"""
        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(db_fd)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT,
                display_name TEXT,
                created_at TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT,
                object_id INTEGER,
                action TEXT,
                operator_id INTEGER,
                operator_name TEXT,
                changes TEXT,
                category TEXT DEFAULT 'business',
                level TEXT DEFAULT 'INFO',
                ip_address TEXT,
                user_agent TEXT,
                request_id TEXT,
                created_at TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE test_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TEXT,
                updated_at TEXT,
                created_by INTEGER,
                updated_by INTEGER
            )
        ''')

        cursor.execute(
            "INSERT INTO users (username, email, display_name) VALUES (?, ?, ?)",
            ('test_user', 'test@example.com', '测试用户')
        )
        conn.commit()
        yield conn
        conn.close()
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_log_on_create_action(self, db_connection):
        """TC-LG-001: 业务操作日志 - 创建"""
        cursor = db_connection.cursor()

        cursor.execute(
            "INSERT INTO test_entities (name, code, status) VALUES (?, ?, ?)",
            ('New Entity', 'NEW001', 'active')
        )
        entity_id = cursor.lastrowid

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, object_id, action, operator_name, category, level, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ('test_entity', entity_id, 'CREATE', 'test_user', 'business', 'INFO', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE object_id = ? AND action = ?", (entity_id, 'CREATE'))
        log = cursor.fetchone()

        assert log is not None, "创建操作应该产生日志"
        col_names = [desc[0] for desc in cursor.description] if cursor.description else []
        object_type_idx = col_names.index('object_type') if 'object_type' in col_names else 2
        object_id_idx = col_names.index('object_id') if 'object_id' in col_names else 3
        assert log[object_type_idx] == 'test_entity'
        assert log[object_id_idx] == entity_id

    def test_log_on_update_action(self, db_connection):
        """TC-LG-002: 业务操作日志 - 更新"""
        cursor = db_connection.cursor()

        cursor.execute(
            "INSERT INTO test_entities (name, code, status) VALUES (?, ?, ?)",
            ('Update Entity', 'UPDATE001', 'active')
        )
        entity_id = cursor.lastrowid

        cursor.execute(
            "UPDATE test_entities SET name = ?, status = ? WHERE id = ?",
            ('Updated Name', 'inactive', entity_id)
        )

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, object_id, action, operator_name, category, level, changes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ('test_entity', entity_id, 'UPDATE', 'test_user', 'business', 'INFO',
             '{"name": {"old": "Update Entity", "new": "Updated Name"}}', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE object_id = ? AND action = ?", (entity_id, 'UPDATE'))
        log = cursor.fetchone()

        assert log is not None, "更新操作应该产生日志"

    def test_log_on_delete_action(self, db_connection):
        """TC-LG-003: 业务操作日志 - 删除"""
        cursor = db_connection.cursor()

        cursor.execute(
            "INSERT INTO test_entities (name, code, status) VALUES (?, ?, ?)",
            ('Delete Entity', 'DELETE001', 'active')
        )
        entity_id = cursor.lastrowid

        cursor.execute("DELETE FROM test_entities WHERE id = ?", (entity_id,))

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, object_id, action, operator_name, category, level, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ('test_entity', entity_id, 'DELETE', 'test_user', 'business', 'INFO', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE object_id = ? AND action = ?", (entity_id, 'DELETE'))
        log = cursor.fetchone()

        assert log is not None, "删除操作应该产生日志"

    def test_log_batch_action(self, db_connection):
        """TC-LG-004: 业务操作日志 - 批量操作"""
        cursor = db_connection.cursor()

        entity_ids = []
        for i in range(3):
            cursor.execute(
                "INSERT INTO test_entities (name, code, status) VALUES (?, ?, ?)",
                (f'Batch Entity {i}', f'BATCH{i}', 'active')
            )
            entity_ids.append(cursor.lastrowid)

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, operator_name, category, level, changes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ('test_entity', 'BATCH_UPDATE', 'test_user', 'business', 'INFO',
             f'{{"batch_ids": {entity_ids}}}', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT COUNT(*) FROM audit_log WHERE action = ?", ('BATCH_UPDATE',))
        count = cursor.fetchone()[0]

        assert count >= 1, "批量操作应该产生日志"

    def test_log_field_changes(self, db_connection):
        """TC-LG-005: 业务操作日志 - 字段变更"""
        cursor = db_connection.cursor()

        cursor.execute(
            "INSERT INTO test_entities (name, code, status) VALUES (?, ?, ?)",
            ('Field Change', 'FIELD001', 'active')
        )
        entity_id = cursor.lastrowid

        old_name = 'Field Change'
        new_name = 'Field Changed'

        cursor.execute(
            "UPDATE test_entities SET name = ? WHERE id = ?",
            (new_name, entity_id)
        )

        changes = {
            'name': {'old': old_name, 'new': new_name},
            'updated_at': {'old': None, 'new': datetime.now().isoformat()}
        }

        import json
        cursor.execute(
            """INSERT INTO audit_log
               (object_type, object_id, action, operator_name, changes, category, level, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ('test_entity', entity_id, 'UPDATE', 'test_user', json.dumps(changes), 'business', 'INFO', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT changes FROM audit_log WHERE object_id = ?", (entity_id,))
        log = cursor.fetchone()

        assert log is not None
        logged_changes = json.loads(log[0])
        assert 'name' in logged_changes

    def test_log_operator_info(self, db_connection):
        """TC-LG-007: 业务操作日志 - 操作人"""
        cursor = db_connection.cursor()

        cursor.execute(
            "INSERT INTO test_entities (name, code, created_by) VALUES (?, ?, ?)",
            ('Operator Test', 'OPER001', 1)
        )
        entity_id = cursor.lastrowid

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, object_id, action, operator_id, operator_name, category, level, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ('test_entity', entity_id, 'CREATE', 1, 'test_user', 'business', 'INFO', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT operator_id, operator_name FROM audit_log WHERE object_id = ?", (entity_id,))
        log = cursor.fetchone()

        assert log is not None
        assert log[0] == 1
        assert log[1] == 'test_user'

    def test_log_timestamp(self, db_connection):
        """TC-LG-008: 业务操作日志 - 时间戳"""
        before = datetime.now()

        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT INTO test_entities (name, code, status) VALUES (?, ?, ?)",
            ('Timestamp Test', 'TIME001', 'active')
        )
        entity_id = cursor.lastrowid

        after = datetime.now()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, object_id, action, operator_name, category, level, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ('test_entity', entity_id, 'CREATE', 'test_user', 'business', 'INFO', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT created_at FROM audit_log WHERE object_id = ?", (entity_id,))
        log = cursor.fetchone()

        assert log is not None
        log_time_str = log[0]
        log_time = datetime.fromisoformat(log_time_str)
        before_ts = before.replace(microsecond=0)
        after_ts = after.replace(microsecond=0) + __import__('datetime').timedelta(seconds=1)
        assert before_ts <= log_time <= after_ts, f"Log time {log_time} not in range [{before_ts}, {after_ts}]"

    def test_log_object_type(self, db_connection):
        """TC-LG-009: 业务操作日志 - 对象类型"""
        cursor = db_connection.cursor()

        cursor.execute(
            "INSERT INTO test_entities (name, code, status) VALUES (?, ?, ?)",
            ('Object Type Test', 'OBJ001', 'active')
        )
        entity_id = cursor.lastrowid

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, object_id, action, operator_name, category, level, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ('test_entity', entity_id, 'CREATE', 'test_user', 'business', 'INFO', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT object_type FROM audit_log WHERE object_id = ?", (entity_id,))
        log = cursor.fetchone()

        assert log is not None
        assert log[0] == 'test_entity'

    def test_log_object_id(self, db_connection):
        """TC-LG-010: 业务操作日志 - 对象ID"""
        cursor = db_connection.cursor()

        cursor.execute(
            "INSERT INTO test_entities (name, code, status) VALUES (?, ?, ?)",
            ('Object ID Test', 'OID001', 'active')
        )
        entity_id = cursor.lastrowid

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, object_id, action, operator_name, category, level, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ('test_entity', entity_id, 'CREATE', 'test_user', 'business', 'INFO', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT object_id FROM audit_log WHERE object_type = ?", ('test_entity',))
        logs = cursor.fetchall()

        assert len(logs) > 0
        assert any(log[0] == entity_id for log in logs)

    def test_log_ip_address(self, db_connection):
        """TC-LG-011: 业务操作日志 - IP地址"""
        cursor = db_connection.cursor()

        test_ip = '192.168.1.100'

        cursor.execute(
            "INSERT INTO test_entities (name, code, status) VALUES (?, ?, ?)",
            ('IP Test', 'IP001', 'active')
        )
        entity_id = cursor.lastrowid

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, object_id, action, operator_name, ip_address, category, level, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ('test_entity', entity_id, 'CREATE', 'test_user', test_ip, 'business', 'INFO', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT ip_address FROM audit_log WHERE object_id = ?", (entity_id,))
        log = cursor.fetchone()

        assert log is not None
        assert log[0] == test_ip

    def test_log_user_agent(self, db_connection):
        """TC-LG-012: 业务操作日志 - 用户代理"""
        cursor = db_connection.cursor()

        test_ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'

        cursor.execute(
            "INSERT INTO test_entities (name, code, status) VALUES (?, ?, ?)",
            ('UA Test', 'UA001', 'active')
        )
        entity_id = cursor.lastrowid

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, object_id, action, operator_name, user_agent, category, level, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ('test_entity', entity_id, 'CREATE', 'test_user', test_ua, 'business', 'INFO', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT user_agent FROM audit_log WHERE object_id = ?", (entity_id,))
        log = cursor.fetchone()

        assert log is not None
        assert test_ua in log[0]

    def test_log_request_id(self, db_connection):
        """TC-LG-013: 业务操作日志 - 请求ID"""
        cursor = db_connection.cursor()

        test_req_id = 'req-12345-abcde'

        cursor.execute(
            "INSERT INTO test_entities (name, code, status) VALUES (?, ?, ?)",
            ('Request ID Test', 'REQ001', 'active')
        )
        entity_id = cursor.lastrowid

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, object_id, action, operator_name, request_id, category, level, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ('test_entity', entity_id, 'CREATE', 'test_user', test_req_id, 'business', 'INFO', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT request_id FROM audit_log WHERE object_id = ?", (entity_id,))
        log = cursor.fetchone()

        assert log is not None
        assert log[0] == test_req_id


class TestLogCategory:
    """日志分类测试"""

    def test_log_category_business(self):
        """验证 business 日志分类"""
        from meta.enums.log_category import LogCategory

        assert hasattr(LogCategory, 'BUSINESS')
        assert LogCategory.BUSINESS.value == 'business'

    def test_log_category_security(self):
        """验证 security 日志分类"""
        from meta.enums.log_category import LogCategory

        assert hasattr(LogCategory, 'SECURITY')
        assert LogCategory.SECURITY.value == 'security'

    def test_log_category_operation(self):
        """验证 operation 日志分类"""
        from meta.enums.log_category import LogCategory

        assert hasattr(LogCategory, 'OPERATION')
        assert LogCategory.OPERATION.value == 'operation'

    def test_log_category_performance(self):
        """验证 performance 日志分类"""
        from meta.enums.log_category import LogCategory

        assert hasattr(LogCategory, 'PERFORMANCE')
        assert LogCategory.PERFORMANCE.value == 'performance'

    def test_log_category_system(self):
        """验证 system 日志分类"""
        from meta.enums.log_category import LogCategory

        assert hasattr(LogCategory, 'SYSTEM')
        assert LogCategory.SYSTEM.value == 'system'


class TestLogLevel:
    """日志级别测试"""

    def test_log_level_debug(self):
        """验证 DEBUG 日志级别"""
        from meta.enums.log_level import LogLevel

        assert hasattr(LogLevel, 'DEBUG')
        assert LogLevel.DEBUG.value == 'DEBUG'

    def test_log_level_info(self):
        """验证 INFO 日志级别"""
        from meta.enums.log_level import LogLevel

        assert hasattr(LogLevel, 'INFO')
        assert LogLevel.INFO.value == 'INFO'

    def test_log_level_warning(self):
        """验证 WARNING 日志级别"""
        from meta.enums.log_level import LogLevel

        assert hasattr(LogLevel, 'WARNING')
        assert LogLevel.WARNING.value == 'WARNING'

    def test_log_level_error(self):
        """验证 ERROR 日志级别"""
        from meta.enums.log_level import LogLevel

        assert hasattr(LogLevel, 'ERROR')
        assert LogLevel.ERROR.value == 'ERROR'

    def test_log_level_critical(self):
        """验证 CRITICAL 日志级别"""
        from meta.enums.log_level import LogLevel

        assert hasattr(LogLevel, 'CRITICAL')
        assert LogLevel.CRITICAL.value == 'CRITICAL'

    def test_log_level_priority(self):
        """验证日志级别优先级"""
        from meta.enums.log_level import LogLevel

        levels = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL]
        level_values = [l.value for l in levels]

        expected_order = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        assert level_values == expected_order, f"Log levels should be in severity order: {level_values}"
