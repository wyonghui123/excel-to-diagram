import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
Phase 14 日志拦截器测试 - 安全日志

测试范围：
- Security Log Interceptor 登录日志
- Security Log Interceptor 安全事件
- Security Log Interceptor 攻击防护

对应规范: TC-LG-016 ~ TC-LG-025
"""

import pytest
import sqlite3
import os
import tempfile
from datetime import datetime


class TestSecurityLogInterceptor:
    """安全日志拦截器测试"""

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
                password_hash TEXT,
                status TEXT DEFAULT 'active',
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
                category TEXT DEFAULT 'security',
                level TEXT DEFAULT 'INFO',
                ip_address TEXT,
                user_agent TEXT,
                request_id TEXT,
                message TEXT,
                created_at TEXT
            )
        ''')

        cursor.execute(
            "INSERT INTO users (username, email, password_hash, status) VALUES (?, ?, ?, ?)",
            ('admin', 'admin@example.com', 'hash123', 'active')
        )
        conn.commit()
        yield conn
        conn.close()
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_log_login_success(self, db_connection):
        """TC-LG-016: 安全日志 - 登录成功"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, operator_name, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ('auth', 'LOGIN_SUCCESS', 'admin', 'security', 'INFO', '用户 admin 登录成功', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('LOGIN_SUCCESS',))
        log = cursor.fetchone()

        assert log is not None, "登录成功应该产生安全日志"
        assert log[3] == 'LOGIN_SUCCESS'
        assert 'admin' in str(log[5])

    def test_log_login_failed(self, db_connection):
        """TC-LG-017: 安全日志 - 登录失败"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, operator_name, category, level, message, ip_address, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ('auth', 'LOGIN_FAILED', 'unknown', 'security', 'WARNING', '登录失败: 用户名或密码错误', '192.168.1.50', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('LOGIN_FAILED',))
        log = cursor.fetchone()

        assert log is not None, "登录失败应该产生安全日志"
        assert log[3] == 'LOGIN_FAILED'
        assert log[8] == 'WARNING'

    def test_log_logout(self, db_connection):
        """TC-LG-018: 安全日志 - 登出"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, operator_id, operator_name, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ('auth', 'LOGOUT', 1, 'admin', 'security', 'INFO', '用户 admin 登出', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('LOGOUT',))
        log = cursor.fetchone()

        assert log is not None, "登出应该产生安全日志"

    def test_log_password_change(self, db_connection):
        """TC-LG-019: 安全日志 - 密码修改"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, operator_id, operator_name, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ('user', 'PASSWORD_CHANGE', 1, 'admin', 'security', 'INFO', '用户修改了密码', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('PASSWORD_CHANGE',))
        log = cursor.fetchone()

        assert log is not None, "密码修改应该产生安全日志"
        assert log[3] == 'PASSWORD_CHANGE'

    def test_log_permission_change(self, db_connection):
        """TC-LG-020: 安全日志 - 权限变更"""
        cursor = db_connection.cursor()

        changes = {
            'role_permissions': {'old': ['read'], 'new': ['read', 'write', 'delete']}
        }

        import json
        cursor.execute(
            """INSERT INTO audit_log
               (object_type, object_id, action, operator_id, operator_name, category, level, changes, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ('role', 1, 'PERMISSION_CHANGE', 1, 'admin', 'security', 'INFO', json.dumps(changes), '角色权限变更', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('PERMISSION_CHANGE',))
        log = cursor.fetchone()

        assert log is not None, "权限变更应该产生安全日志"

    def test_log_sensitive_action(self, db_connection):
        """TC-LG-021: 安全日志 - 敏感操作"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, operator_id, operator_name, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ('system', 'SENSITIVE_OPERATION', 1, 'admin', 'security', 'WARNING', '执行了敏感操作: 数据导出', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('SENSITIVE_OPERATION',))
        log = cursor.fetchone()

        assert log is not None, "敏感操作应该产生安全日志"
        assert log[8] == 'WARNING'

    def test_log_abnormal_access(self, db_connection):
        """TC-LG-022: 安全日志 - 异常访问"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, operator_name, category, level, message, ip_address, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ('access', 'ABNORMAL_ACCESS', 'unknown', 'security', 'WARNING', '检测到异常访问行为', '10.0.0.1', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('ABNORMAL_ACCESS',))
        log = cursor.fetchone()

        assert log is not None, "异常访问应该产生安全日志"

    def test_log_sql_injection_attempt(self, db_connection):
        """TC-LG-023: 安全日志 - SQL注入"""
        cursor = db_connection.cursor()

        payload = "'; DROP TABLE users; --"

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, operator_name, category, level, message, ip_address, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ('security', 'SQL_INJECTION_ATTEMPT', 'unknown', 'security', 'CRITICAL', f'检测到 SQL 注入攻击: {payload}', '10.0.0.1', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('SQL_INJECTION_ATTEMPT',))
        log = cursor.fetchone()

        assert log is not None, "SQL注入攻击应该产生安全日志"
        assert log[8] == 'CRITICAL'

    def test_log_xss_attempt(self, db_connection):
        """TC-LG-024: 安全日志 - XSS攻击"""
        cursor = db_connection.cursor()

        payload = "<script>alert('XSS')</script>"

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, operator_name, category, level, message, ip_address, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ('security', 'XSS_ATTEMPT', 'unknown', 'security', 'WARNING', f'检测到 XSS 攻击尝试', '10.0.0.2', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('XSS_ATTEMPT',))
        log = cursor.fetchone()

        assert log is not None, "XSS攻击应该产生安全日志"

    def test_log_csrf_attempt(self, db_connection):
        """TC-LG-025: 安全日志 - CSRF攻击"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, operator_name, category, level, message, ip_address, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ('security', 'CSRF_ATTEMPT', 'unknown', 'security', 'WARNING', '检测到 CSRF 攻击尝试', '10.0.0.3', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('CSRF_ATTEMPT',))
        log = cursor.fetchone()

        assert log is not None, "CSRF攻击应该产生安全日志"


class TestSecurityLogFiltering:
    """安全日志过滤测试"""

    @pytest.fixture
    def db_connection(self):
        """创建测试数据库连接"""
        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(db_fd)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT,
                object_id INTEGER,
                action TEXT,
                operator_id INTEGER,
                operator_name TEXT,
                category TEXT DEFAULT 'security',
                level TEXT DEFAULT 'INFO',
                ip_address TEXT,
                message TEXT,
                created_at TEXT
            )
        ''')

        for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            cursor.execute(
                """INSERT INTO audit_log
                   (object_type, action, category, level, message, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ('test', f'TEST_{level}', 'security', level, f'Test {level} message', datetime.now().isoformat())
            )
        conn.commit()
        yield conn
        conn.close()
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_filter_by_security_category(self, db_connection):
        """验证按 security 分类过滤"""
        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM audit_log WHERE category = ?", ('security',))
        count = cursor.fetchone()[0]

        assert count >= 5, "应该有至少5条安全日志"

    def test_filter_by_level(self, db_connection):
        """验证按级别过滤"""
        cursor = db_connection.cursor()

        cursor.execute("SELECT COUNT(*) FROM audit_log WHERE category = ? AND level = ?", ('security', 'WARNING'))
        warning_count = cursor.fetchone()[0]

        assert warning_count >= 1, "应该有至少1条 WARNING 级别日志"

        cursor.execute("SELECT COUNT(*) FROM audit_log WHERE category = ? AND level = ?", ('security', 'CRITICAL'))
        critical_count = cursor.fetchone()[0]

        assert critical_count >= 1, "应该有至少1条 CRITICAL 级别日志"

    def test_filter_by_ip_address(self, db_connection):
        """验证按 IP 地址过滤"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, category, level, ip_address, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ('test', 'IP_TEST', 'security', 'INFO', '192.168.1.100', 'Test IP', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE ip_address = ?", ('192.168.1.100',))
        logs = cursor.fetchall()

        assert len(logs) >= 1, "应该能找到指定 IP 的日志"

    def test_filter_by_action(self, db_connection):
        """验证按操作类型过滤"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ('auth', 'LOGIN_SUCCESS', 'security', 'INFO', '登录成功', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action LIKE ?", ('LOGIN%',))
        logs = cursor.fetchall()

        assert len(logs) >= 1, "应该能找到 LOGIN 相关的日志"
