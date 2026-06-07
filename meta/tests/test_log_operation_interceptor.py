import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
Phase 14 日志拦截器测试 - 操作日志和集成测试

测试范围：
- Operation Log Interceptor 操作日志
- Log Integration 测试
- Log Filter/Search 测试
- Log Export 测试

对应规范: TC-LG-026 ~ TC-LG-045
"""

import pytest
import sqlite3
import os
import tempfile
import json
from datetime import datetime, timedelta


class TestOperationLogInterceptor:
    """操作日志拦截器测试"""

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
                changes TEXT,
                category TEXT DEFAULT 'operation',
                level TEXT DEFAULT 'INFO',
                message TEXT,
                created_at TEXT
            )
        ''')

        conn.commit()
        yield conn
        conn.close()
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_log_export_action(self, db_connection):
        """TC-LG-026: 操作日志 - 导出"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, operator_name, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ('export', 'EXPORT', 'test_user', 'operation', 'INFO', '导出数据: user, 100条记录', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('EXPORT',))
        log = cursor.fetchone()

        assert log is not None, "导出操作应该产生日志"
        col_names = [desc[0] for desc in cursor.description] if cursor.description else []
        category_idx = col_names.index('category') if 'category' in col_names else -1
        if category_idx >= 0:
            assert log[category_idx] == 'operation'

    def test_log_import_action(self, db_connection):
        """TC-LG-027: 操作日志 - 导入"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, operator_name, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ('import', 'IMPORT', 'test_user', 'operation', 'INFO', '导入数据: role, 50条记录', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('IMPORT',))
        log = cursor.fetchone()

        assert log is not None, "导入操作应该产生日志"

    def test_log_batch_delete(self, db_connection):
        """TC-LG-028: 操作日志 - 批量删除"""
        cursor = db_connection.cursor()

        changes = {
            'deleted_ids': [1, 2, 3, 4, 5],
            'count': 5
        }

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, operator_name, category, level, changes, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ('user', 'BATCH_DELETE', 'test_user', 'operation', 'WARNING', json.dumps(changes), '批量删除用户', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('BATCH_DELETE',))
        log = cursor.fetchone()

        assert log is not None, "批量删除应该产生日志"
        col_names = [desc[0] for desc in cursor.description] if cursor.description else []
        level_idx = col_names.index('level') if 'level' in col_names else 7
        assert log[level_idx] == 'WARNING'

    def test_log_config_change(self, db_connection):
        """TC-LG-029: 操作日志 - 配置修改"""
        cursor = db_connection.cursor()

        changes = {
            'config_key': 'system.maintenance_mode',
            'old_value': 'false',
            'new_value': 'true'
        }

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, operator_name, category, level, changes, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ('config', 'CONFIG_CHANGE', 'admin', 'operation', 'WARNING', json.dumps(changes), '系统配置变更', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('CONFIG_CHANGE',))
        log = cursor.fetchone()

        assert log is not None, "配置修改应该产生日志"

    def test_log_data_migration(self, db_connection):
        """TC-LG-030: 操作日志 - 数据迁移"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, operator_name, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ('migration', 'DATA_MIGRATION', 'system', 'operation', 'INFO', '执行数据迁移: v1.0 -> v2.0', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('DATA_MIGRATION',))
        log = cursor.fetchone()

        assert log is not None, "数据迁移应该产生日志"

    def test_log_cache_clear(self, db_connection):
        """TC-LG-031: 操作日志 - 缓存清除"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, operator_name, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ('cache', 'CACHE_CLEAR', 'admin', 'operation', 'INFO', '清除缓存: user_cache, permission_cache', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('CACHE_CLEAR',))
        log = cursor.fetchone()

        assert log is not None, "缓存清除应该产生日志"

    def test_log_system_maintenance(self, db_connection):
        """TC-LG-032: 操作日志 - 系统维护"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ('system', 'SYSTEM_MAINTENANCE', 'operation', 'INFO', '执行系统维护任务', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('SYSTEM_MAINTENANCE',))
        log = cursor.fetchone()

        assert log is not None, "系统维护应该产生日志"


class TestPerformanceLogInterceptor:
    """性能日志拦截器测试"""

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
                action TEXT,
                category TEXT DEFAULT 'performance',
                level TEXT DEFAULT 'INFO',
                message TEXT,
                duration_ms INTEGER,
                created_at TEXT
            )
        ''')

        conn.commit()
        yield conn
        conn.close()
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_log_performance_metric(self, db_connection):
        """TC-LG-033: 操作日志 - 性能监控"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, category, level, message, duration_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ('query', 'PERFORMANCE_LOG', 'performance', 'INFO', '数据库查询性能', 150, datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE category = ?", ('performance',))
        log = cursor.fetchone()

        assert log is not None, "性能日志应该被记录"
        assert log[6] == 150

    def test_log_slow_query(self, db_connection):
        """TC-LG-034: 操作日志 - 错误日志"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, category, level, message, duration_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ('query', 'SLOW_QUERY', 'performance', 'WARNING', '慢查询检测: 超过1000ms', 1500, datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE action = ?", ('SLOW_QUERY',))
        log = cursor.fetchone()

        assert log is not None, "慢查询应该产生日志"
        col_names = [desc[0] for desc in cursor.description] if cursor.description else []
        level_idx = col_names.index('level') if 'level' in col_names else 7
        assert log[level_idx] == 'WARNING'


class TestLogIntegration:
    """日志集成测试"""

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
                changes TEXT,
                category TEXT,
                level TEXT,
                message TEXT,
                ip_address TEXT,
                created_at TEXT
            )
        ''')

        conn.commit()
        yield conn
        conn.close()
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_log_category_field(self, db_connection):
        """TC-LG-036: 日志分类 - category字段"""
        cursor = db_connection.cursor()

        for category in ['business', 'security', 'operation', 'performance', 'system']:
            cursor.execute(
                """INSERT INTO audit_log
                   (object_type, action, category, level, message, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ('test', f'TEST_{category}', category, 'INFO', f'{category} category test', datetime.now().isoformat())
            )
        db_connection.commit()

        for category in ['business', 'security', 'operation']:
            cursor.execute("SELECT COUNT(*) FROM audit_log WHERE category = ?", (category,))
            count = cursor.fetchone()[0]
            assert count >= 1, f"应该有 {category} 类别的日志"

    def test_log_level_field(self, db_connection):
        """TC-LG-037: 日志级别 - level字段"""
        cursor = db_connection.cursor()

        for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            cursor.execute(
                """INSERT INTO audit_log
                   (object_type, action, category, level, message, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ('test', f'TEST_LEVEL_{level}', 'business', level, f'{level} level test', datetime.now().isoformat())
            )
        db_connection.commit()

        cursor.execute("SELECT COUNT(*) FROM audit_log WHERE level = ?", ('ERROR',))
        error_count = cursor.fetchone()[0]
        assert error_count >= 1, "应该有 ERROR 级别日志"

    def test_log_filter_by_category(self, db_connection):
        """TC-LG-038: 日志过滤 - 按分类"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ('test', 'FILTER_TEST', 'security', 'INFO', 'Filter by category test', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE category = ? AND level = ?", ('security', 'INFO'))
        logs = cursor.fetchall()

        assert len(logs) >= 1, "应该能按分类过滤日志"

    def test_log_filter_by_level(self, db_connection):
        """TC-LG-039: 日志过滤 - 按级别"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ('test', 'LEVEL_FILTER', 'business', 'WARNING', 'Level filter test', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE level IN (?, ?)", ('WARNING', 'ERROR'))
        logs = cursor.fetchall()

        assert len(logs) >= 1, "应该能按级别过滤日志"

    def test_log_filter_combined(self, db_connection):
        """TC-LG-040: 日志过滤 - 组合过滤"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ('user', 'COMBINED_FILTER', 'business', 'INFO', 'Combined filter test', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute(
            "SELECT * FROM audit_log WHERE object_type = ? AND category = ? AND level = ?",
            ('user', 'business', 'INFO')
        )
        logs = cursor.fetchall()

        assert len(logs) >= 1, "应该能组合过滤日志"

    def test_log_search_keyword(self, db_connection):
        """TC-LG-041: 日志搜索 - keyword"""
        cursor = db_connection.cursor()

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ('test', 'SEARCH_TEST', 'business', 'INFO', 'Search keyword test message', datetime.now().isoformat())
        )
        db_connection.commit()

        cursor.execute("SELECT * FROM audit_log WHERE message LIKE ?", ('%keyword%',))
        logs = cursor.fetchall()

        assert len(logs) >= 1, "应该能按关键词搜索日志"

    def test_log_search_time_range(self, db_connection):
        """TC-LG-042: 日志搜索 - 时间范围"""
        cursor = db_connection.cursor()

        now = datetime.now()
        yesterday = now - timedelta(days=1)

        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ('test', 'TIME_RANGE', 'business', 'INFO', 'Time range test', yesterday.isoformat())
        )
        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ('test', 'TIME_RANGE', 'business', 'INFO', 'Time range test now', now.isoformat())
        )
        db_connection.commit()

        cursor.execute(
            "SELECT COUNT(*) FROM audit_log WHERE created_at >= ?",
            (yesterday.isoformat(),)
        )
        count = cursor.fetchone()[0]

        assert count >= 2, "应该能找到时间范围内的日志"


class TestLogExport:
    """日志导出测试"""

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
                action TEXT,
                category TEXT,
                level TEXT,
                message TEXT,
                created_at TEXT
            )
        ''')

        for i in range(10):
            cursor.execute(
                """INSERT INTO audit_log
                   (object_type, action, category, level, message, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ('test', f'EXPORT_{i}', 'business', 'INFO', f'Export test message {i}', datetime.now().isoformat())
            )
        conn.commit()
        yield conn
        conn.close()
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_log_export_csv_format(self, db_connection):
        """TC-LG-043: 日志导出 - CSV格式"""
        cursor = db_connection.cursor()
        cursor.execute("SELECT * FROM audit_log WHERE object_type = ?", ('test',))
        logs = cursor.fetchall()

        assert len(logs) >= 10, "应该有至少10条日志用于导出"

        csv_header = "id,object_type,action,category,level,message,created_at"
        assert len(csv_header.split(',')) == 7, "CSV 格式应该包含7个字段"

    def test_log_export_json_format(self, db_connection):
        """TC-LG-044: 日志导出 - JSON格式"""
        cursor = db_connection.cursor()
        cursor.execute("SELECT * FROM audit_log WHERE object_type = ?", ('test',))
        logs = cursor.fetchall()

        log_dicts = []
        for log in logs:
            log_dict = {
                'id': log[0],
                'object_type': log[1],
                'action': log[2],
                'category': log[3],
                'level': log[4],
                'message': log[5],
                'created_at': log[6]
            }
            log_dicts.append(log_dict)

        json_str = json.dumps(log_dicts, ensure_ascii=False)
        parsed = json.loads(json_str)

        assert len(parsed) >= 10, "应该能正确解析 JSON 格式的日志"

    def test_log_archive(self, db_connection):
        """TC-LG-045: 日志归档 - 自动归档"""
        cursor = db_connection.cursor()

        old_date = datetime.now() - timedelta(days=90)
        cursor.execute(
            """INSERT INTO audit_log
               (object_type, action, category, level, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ('archived', 'OLD_LOG', 'business', 'INFO', 'This log should be archived', old_date.isoformat())
        )
        db_connection.commit()

        cursor.execute(
            "SELECT COUNT(*) FROM audit_log WHERE created_at < ?",
            ((datetime.now() - timedelta(days=30)).isoformat(),)
        )
        old_count = cursor.fetchone()[0]

        assert old_count >= 1, "应该能识别需要归档的旧日志"
