# -*- coding: utf-8 -*-
"""
[FILE] test_audit_compliance.py
[DESCRIPTION] Phase 9 审计与合规 — TDD 测试用例
[SPEC] spec-permission-system-unification-2026-07-19 §3.17 / §4.9 / §8.9

测试覆盖 (P9 验收):
  P9-T1: 决策日志记录 — log_permission_decision() 异步写入
  P9-T2: 合规报告生成 — compliance_reporter.py 按角色/资源统计允许/拒绝比例
  P9-T3: 审计 API — GET /audit/decisions + /compliance (分页 + 角色访问控制)
  P9-T4: 审计字段清洗 — clean_audit_field() 历史占位值清洗
"""
import pytest

pytestmark = pytest.mark.unit

import sys
import os
import sqlite3
import tempfile
import json
import time
import threading

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def db_for_audit():
    """创建含 audit_logs + data_permission_rules 表的测试库"""
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    # check_same_thread=False 允许跨线程访问 (P9-T1 thread_safety 测试需要)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type VARCHAR(200),
            object_id VARCHAR(200),
            action VARCHAR(200),
            field_name VARCHAR(200),
            old_value TEXT,
            new_value TEXT,
            user_id VARCHAR(200),
            user_name VARCHAR(200),
            ip_address VARCHAR(200),
            user_agent VARCHAR(500),
            created_at VARCHAR(200),
            trace_id VARCHAR(200),
            transaction_id VARCHAR(200),
            agent_id VARCHAR(200),
            agent_session_id VARCHAR(200),
            tool_call_id VARCHAR(200),
            agent_reasoning TEXT,
            status VARCHAR(100) DEFAULT 'written',
            extra_data TEXT,
            parent_object_type VARCHAR(200),
            parent_object_id VARCHAR(200),
            log_category VARCHAR(100),
            log_level VARCHAR(50),
            outcome VARCHAR(50) DEFAULT 'success',
            retention_until VARCHAR(200),
            cascade_root_id VARCHAR(200),
            cascade_root_action VARCHAR(200),
            error_message TEXT
        );
        CREATE TABLE IF NOT EXISTS permission_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name VARCHAR(200),
            action VARCHAR(200) NOT NULL,
            resource_type VARCHAR(200) NOT NULL,
            resource_id VARCHAR(200),
            decision VARCHAR(50) NOT NULL,
            reason VARCHAR(500),
            trace_id VARCHAR(200),
            role_id INTEGER,
            extra_data TEXT,
            created_at VARCHAR(200) NOT NULL
        );
        CREATE TABLE IF NOT EXISTS data_permission_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            rule_type VARCHAR(50) NOT NULL DEFAULT 'condition',
            resource_type VARCHAR(200),
            dimension_code VARCHAR(200),
            condition TEXT,
            scope_mode VARCHAR(50) DEFAULT 'include',
            permission_level VARCHAR(50) DEFAULT 'read',
            is_denied INTEGER DEFAULT 0,
            inherit_to_children INTEGER DEFAULT 1,
            propagate_to_parents INTEGER DEFAULT 0,
            source_table VARCHAR(100),
            source_id INTEGER,
            created_at VARCHAR(200),
            updated_at VARCHAR(200)
        );
        CREATE TABLE IF NOT EXISTS user_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(200),
            code VARCHAR(200),
            is_active INTEGER DEFAULT 1
        );
    """)
    # 测试数据
    conn.execute("INSERT INTO roles (id, name, code) VALUES (1, 'Admin', 'admin')")
    conn.execute("INSERT INTO roles (id, name, code) VALUES (2, 'Auditor', 'auditor')")
    conn.execute("INSERT INTO roles (id, name, code) VALUES (3, 'User', 'user')")
    conn.execute("INSERT INTO user_roles (user_id, role_id) VALUES (100, 1)")
    conn.execute("INSERT INTO user_roles (user_id, role_id) VALUES (200, 2)")
    conn.execute("INSERT INTO user_roles (user_id, role_id) VALUES (300, 3)")
    conn.commit()

    class MockDS:
        def __init__(self, connection):
            self._conn = connection
            self.in_transaction = False

        def execute(self, sql, params=None):
            cursor = self._conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            self._conn.commit()
            return cursor

        def insert(self, table, record):
            cols = list(record.keys())
            placeholders = ', '.join(['?'] * len(cols))
            col_str = ', '.join(cols)
            cursor = self._conn.cursor()
            cursor.execute(
                f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})",
                [record[c] for c in cols]
            )
            self._conn.commit()
            return cursor.lastrowid

        def find(self, table, filters=None, order_by=None):
            sql = f"SELECT * FROM {table}"
            params = []
            if filters:
                where_clauses = []
                for k, v in filters.items():
                    if isinstance(v, (list, tuple)):
                        placeholders = ', '.join(['?'] * len(v))
                        where_clauses.append(f"{k} IN ({placeholders})")
                        params.extend(v)
                    else:
                        where_clauses.append(f"{k} = ?")
                        params.append(v)
                sql += " WHERE " + " AND ".join(where_clauses)
            if order_by:
                sql += f" ORDER BY {order_by}"
            cursor = self._conn.cursor()
            cursor.execute(sql, params)
            cols = [desc[0] for desc in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

        def update(self, table, record_id, data):
            set_clauses = []
            params = []
            for k, v in data.items():
                set_clauses.append(f"{k} = ?")
                params.append(v)
            params.append(record_id)
            cursor = self._conn.cursor()
            cursor.execute(f"UPDATE {table} SET {', '.join(set_clauses)} WHERE id = ?", params)
            self._conn.commit()

        def commit(self):
            self._conn.commit()

    yield MockDS(conn)
    conn.close()
    os.unlink(db_path)


# ============================================================================
# P9-T4: 审计字段清洗规则 (先做最简单的, 作为热身)
# ============================================================================

class TestP9T4CleanAuditField:
    """P9-T4: clean_audit_field() 清洗历史占位值"""

    def test_clean_audit_field_module_importable(self):
        """模块可导入且函数存在"""
        from meta.services.audit_service import clean_audit_field
        assert callable(clean_audit_field)

    def test_clean_none_to_dash(self):
        """None → '-'"""
        from meta.services.audit_service import clean_audit_field
        assert clean_audit_field(None) == '-'

    def test_clean_empty_string_to_dash(self):
        """空字符串 → '-'"""
        from meta.services.audit_service import clean_audit_field
        assert clean_audit_field('') == '-'
        assert clean_audit_field('   ') == '-'

    def test_clean_legacy_placeholders_to_dash(self):
        """历史占位值 → '-'"""
        from meta.services.audit_service import clean_audit_field
        for placeholder in ('legacy_null', 'null', 'undefined', 'none', 'n/a', 'na'):
            assert clean_audit_field(placeholder) == '-'
            # 大小写不敏感
            assert clean_audit_field(placeholder.upper()) == '-'

    def test_clean_keeps_valid_values(self):
        """合法值保留原样"""
        from meta.services.audit_service import clean_audit_field
        assert clean_audit_field('product') == 'product'
        assert clean_audit_field('admin') == 'admin'
        assert clean_audit_field(123) == 123
        # 带空格的合法值保留 (仅 strip 两端)
        assert clean_audit_field('  valid_value  ') == 'valid_value'

    def test_clean_phone_masking(self):
        """[v2 补充] 手机号字段清洗: 留前3后4, 中间用 * 脱敏"""
        from meta.services.audit_service import clean_audit_field
        # 11 位手机号: 前3 + **** + 后4
        assert clean_audit_field('13800138000', field_type='phone') == '138****8000'
        # 7 位字符串: 前3 + **** + 后4 (取自身前3后4, 中间用 ****)
        # '1380000' → 前3='138', 后4='0000' → '138****0000'
        result = clean_audit_field('1380000', field_type='phone')
        assert result == '138****0000'
        # 短于 7 位: 不脱敏, 原样返回
        assert clean_audit_field('138', field_type='phone') == '138'
        # 非 phone 类型不脱敏
        assert clean_audit_field('13800138000') == '13800138000'

    def test_clean_irreversible(self):
        """[v2 补充] 脱敏不可逆: 原始手机号不能从清洗结果反推"""
        from meta.services.audit_service import clean_audit_field
        masked = clean_audit_field('13912345678', field_type='phone')
        # 中间 4 位被替换, 不在结果中
        assert '1234' not in masked
        assert '5678' in masked  # 后 4 位保留
        assert masked.startswith('139')  # 前 3 位保留


# ============================================================================
# P9-T1: 决策日志记录 — log_permission_decision() 异步写入
# ============================================================================

class TestP9T1LogPermissionDecision:
    """P9-T1: log_permission_decision() 异步写入"""

    def test_log_permission_decision_module_importable(self):
        """模块可导入且函数存在"""
        from meta.services.audit_service import AuditService
        assert hasattr(AuditService, 'log_permission_decision')

    def test_log_decision_writes_record(self, db_for_audit):
        """写入 permission_decisions 表"""
        ds = db_for_audit
        from meta.services.audit_service import AuditService
        svc = AuditService(ds)

        svc.log_permission_decision(
            user={'id': 100, 'username': 'alice'},
            action='read',
            resource_type='product',
            resource_id='1',
            decision='allow',
            reason='owner_match',
        )
        # 查询验证
        rows = ds.find('permission_decisions')
        assert len(rows) == 1
        row = rows[0]
        assert row['user_id'] == 100
        assert row['user_name'] == 'alice'
        assert row['action'] == 'read'
        assert row['resource_type'] == 'product'
        assert row['resource_id'] == '1'
        assert row['decision'] == 'allow'
        assert row['reason'] == 'owner_match'

    def test_log_decision_deny_case(self, db_for_audit):
        """拒绝决策也可写入"""
        ds = db_for_audit
        from meta.services.audit_service import AuditService
        svc = AuditService(ds)

        svc.log_permission_decision(
            user={'id': 300, 'username': 'charlie'},
            action='delete',
            resource_type='product',
            resource_id='2',
            decision='deny',
            reason='prohibition_match',
        )
        rows = ds.find('permission_decisions', filters={'decision': 'deny'})
        assert len(rows) == 1
        assert rows[0]['reason'] == 'prohibition_match'

    def test_log_decision_does_not_block_main_flow(self, db_for_audit):
        """[关键] 异步写入不阻塞主流程 — 即使 DB 出错也返回 True/不影响主流程"""
        ds = db_for_audit
        from meta.services.audit_service import AuditService
        svc = AuditService(ds)

        # 模拟 DB 写入异常 (使用错误的 data_source)
        class BadDS:
            in_transaction = False
            def insert(self, *args, **kwargs):
                raise sqlite3.OperationalError("Simulated DB error")
            def find(self, *args, **kwargs):
                return []
            def commit(self):
                pass

        bad_svc = AuditService(BadDS())
        # log_permission_decision 不应抛异常
        result = bad_svc.log_permission_decision(
            user={'id': 100, 'username': 'alice'},
            action='read',
            resource_type='product',
            resource_id='1',
            decision='allow',
            reason='ok',
        )
        # 主流程不应被阻塞 (函数应正常返回, 即使日志写入失败)
        assert result is True or result is None or result is False  # 任意返回值, 不抛异常

    def test_log_decision_thread_safety(self, db_for_audit):
        """并发写入 permission_decisions 不冲突

        Spec 验证标准: "不阻塞主流程". SQLite 并发可能偶发 'database is locked',
        允许少量丢失, 但不应抛异常且大部分写入应成功.
        """
        ds = db_for_audit
        from meta.services.audit_service import AuditService
        svc = AuditService(ds)

        exceptions = []
        def writer(user_id):
            try:
                svc.log_permission_decision(
                    user={'id': user_id, 'username': f'user_{user_id}'},
                    action='read',
                    resource_type='product',
                    resource_id=str(user_id),
                    decision='allow',
                    reason='test',
                )
            except Exception as e:
                exceptions.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(100, 110)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # [关键] 主流程不被阻塞: 不抛任何异常
        assert len(exceptions) == 0, f"主流程被阻塞: {exceptions}"

        # 大部分写入成功 (允许偶发 SQLite 锁冲突丢失 1-2 条)
        rows = ds.find('permission_decisions')
        assert len(rows) >= 8, f"并发写入失败过多: 仅 {len(rows)}/10 成功"


# ============================================================================
# P9-T2: 合规报告生成 — compliance_reporter.py
# ============================================================================

class TestP9T2ComplianceReporter:
    """P9-T2: 合规报告生成"""

    def test_compliance_reporter_module_importable(self):
        """模块可导入"""
        from meta.services.compliance_reporter import ComplianceReporter
        assert ComplianceReporter is not None

    def test_generate_compliance_report_basic(self, db_for_audit):
        """基础报告生成 — total/denied/wildcard/prohibition 字段"""
        ds = db_for_audit
        from meta.services.audit_service import AuditService
        from meta.services.compliance_reporter import ComplianceReporter

        # 准备数据: 10 个 allow + 5 个 deny
        svc = AuditService(ds)
        for i in range(10):
            svc.log_permission_decision(
                user={'id': 100, 'username': 'alice'},
                action='read', resource_type='product', resource_id=str(i),
                decision='allow', reason='ok',
            )
        for i in range(5):
            svc.log_permission_decision(
                user={'id': 200, 'username': 'bob'},
                action='delete', resource_type='product', resource_id=str(i),
                decision='deny', reason='prohibition_match',
            )

        reporter = ComplianceReporter(ds)
        report = reporter.generate_report(start_date=None, end_date=None)
        assert report['total_decisions'] == 15
        assert report['denied_decisions'] == 5
        assert 'wildcard_configs' in report
        assert 'prohibition_matches' in report
        assert 'compliance_status' in report

    def test_generate_compliance_report_by_role(self, db_for_audit):
        """按角色统计允许/拒绝比例"""
        ds = db_for_audit
        from meta.services.audit_service import AuditService
        from meta.services.compliance_reporter import ComplianceReporter

        svc = AuditService(ds)
        # role 1 (admin) 5 allow
        for i in range(5):
            svc.log_permission_decision(
                user={'id': 100, 'username': 'alice', 'role_id': 1},
                action='read', resource_type='product', resource_id=str(i),
                decision='allow', reason='ok',
            )
        # role 3 (user) 3 allow + 2 deny
        for i in range(3):
            svc.log_permission_decision(
                user={'id': 300, 'username': 'charlie', 'role_id': 3},
                action='read', resource_type='product', resource_id=str(i),
                decision='allow', reason='ok',
            )
        for i in range(2):
            svc.log_permission_decision(
                user={'id': 300, 'username': 'charlie', 'role_id': 3},
                action='delete', resource_type='product', resource_id=str(i),
                decision='deny', reason='prohibition',
            )

        reporter = ComplianceReporter(ds)
        report = reporter.generate_report(start_date=None, end_date=None)
        # 按角色分组
        assert 'by_role' in report
        # role 1: 5 allow / 0 deny
        assert report['by_role'][1]['allow'] == 5
        assert report['by_role'][1]['deny'] == 0
        # role 3: 3 allow / 2 deny
        assert report['by_role'][3]['allow'] == 3
        assert report['by_role'][3]['deny'] == 2

    def test_generate_compliance_report_by_resource(self, db_for_audit):
        """按资源类型统计"""
        ds = db_for_audit
        from meta.services.audit_service import AuditService
        from meta.services.compliance_reporter import ComplianceReporter

        svc = AuditService(ds)
        for i in range(3):
            svc.log_permission_decision(
                user={'id': 100, 'username': 'alice'},
                action='read', resource_type='product', resource_id=str(i),
                decision='allow', reason='ok',
            )
        for i in range(2):
            svc.log_permission_decision(
                user={'id': 200, 'username': 'bob'},
                action='read', resource_type='version', resource_id=str(i),
                decision='deny', reason='visibility_denied',
            )

        reporter = ComplianceReporter(ds)
        report = reporter.generate_report(start_date=None, end_date=None)
        assert 'by_resource_type' in report
        assert report['by_resource_type']['product']['allow'] == 3
        assert report['by_resource_type']['version']['deny'] == 2

    def test_generate_compliance_report_wildcard_count(self, db_for_audit):
        """统计 wildcard_configs — `*` 配置数量"""
        ds = db_for_audit
        from meta.services.compliance_reporter import ComplianceReporter

        # 插入 2 条 wildcard 规则
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type, "
            "dimension_code, permission_level, is_denied) "
            "VALUES (1, 'condition', 'product', '*', 'read', 0)"
        )
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type, "
            "dimension_code, permission_level, is_denied) "
            "VALUES (1, 'condition', 'version', '*', 'read', 0)"
        )
        # 非 wildcard
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type, "
            "dimension_code, permission_level, is_denied) "
            "VALUES (1, 'condition', 'product', 'p1', 'read', 0)"
        )

        reporter = ComplianceReporter(ds)
        report = reporter.generate_report(start_date=None, end_date=None)
        assert report['wildcard_configs'] == 2

    def test_generate_compliance_report_prohibition_count(self, db_for_audit):
        """统计 prohibition_matches — prohibition 规则命中次数"""
        ds = db_for_audit
        from meta.services.audit_service import AuditService
        from meta.services.compliance_reporter import ComplianceReporter

        svc = AuditService(ds)
        # 3 次 prohibition 命中
        for i in range(3):
            svc.log_permission_decision(
                user={'id': 100, 'username': 'alice'},
                action='delete', resource_type='product', resource_id=str(i),
                decision='deny', reason='prohibition_match',
            )
        # 2 次 visibility 拒绝
        for i in range(2):
            svc.log_permission_decision(
                user={'id': 200, 'username': 'bob'},
                action='read', resource_type='product', resource_id=str(i),
                decision='deny', reason='visibility_denied',
            )

        reporter = ComplianceReporter(ds)
        report = reporter.generate_report(start_date=None, end_date=None)
        assert report['prohibition_matches'] == 3

    def test_generate_compliance_report_status(self, db_for_audit):
        """compliance_status: PASS/FAIL (deny 比例阈值)"""
        ds = db_for_audit
        from meta.services.audit_service import AuditService
        from meta.services.compliance_reporter import ComplianceReporter

        svc = AuditService(ds)
        # 全部 allow → PASS
        for i in range(10):
            svc.log_permission_decision(
                user={'id': 100, 'username': 'alice'},
                action='read', resource_type='product', resource_id=str(i),
                decision='allow', reason='ok',
            )
        reporter = ComplianceReporter(ds)
        report = reporter.generate_report(start_date=None, end_date=None)
        # deny 比例 = 0%, status 应为 PASS
        assert report['compliance_status'] == 'PASS'
        assert report['deny_rate'] == 0.0


# ============================================================================
# P9-T3: 审计 API — GET /audit/decisions + /compliance
# ============================================================================

class TestP9T3AuditAPI:
    """P9-T3: 审计 API — 分页 + 角色访问控制"""

    def test_audit_api_module_importable(self):
        """模块可导入"""
        from meta.api import audit_api
        assert audit_api is not None
        # 关键函数/路由存在
        assert hasattr(audit_api, 'get_permission_decisions') or hasattr(audit_api, 'permission_decisions_api')
        assert hasattr(audit_api, 'get_compliance_report') or hasattr(audit_api, 'compliance_report_api')

    def test_audit_api_pagination(self, db_for_audit):
        """分页正确"""
        ds = db_for_audit
        from meta.services.audit_service import AuditService
        from meta.api.audit_api import get_permission_decisions

        svc = AuditService(ds)
        for i in range(25):
            svc.log_permission_decision(
                user={'id': 100, 'username': 'alice'},
                action='read', resource_type='product', resource_id=str(i),
                decision='allow', reason='ok',
            )

        # page 1, page_size 10
        result = get_permission_decisions(ds, page=1, page_size=10)
        assert result['total'] == 25
        assert result['page'] == 1
        assert result['page_size'] == 10
        assert len(result['data']) == 10
        assert result['total_pages'] == 3

        # page 3 (最后一页, 5 条)
        result = get_permission_decisions(ds, page=3, page_size=10)
        assert len(result['data']) == 5

    def test_audit_api_role_access_control(self, db_for_audit):
        """[关键] 仅审计角色可访问"""
        ds = db_for_audit
        from meta.api.audit_api import get_permission_decisions, get_compliance_report

        # 普通用户 (role 3) 不能访问
        result = get_permission_decisions(
            ds, page=1, page_size=10,
            current_user={'id': 300, 'username': 'charlie', 'role_id': 3}
        )
        assert 'error' in result or result.get('forbidden') is True

        # 审计角色 (role 2) 可访问
        result = get_permission_decisions(
            ds, page=1, page_size=10,
            current_user={'id': 200, 'username': 'bob', 'role_id': 2}
        )
        assert 'data' in result
        assert 'error' not in result

        # Admin (role 1) 可访问
        result = get_permission_decisions(
            ds, page=1, page_size=10,
            current_user={'id': 100, 'username': 'alice', 'role_id': 1}
        )
        assert 'data' in result

    def test_audit_api_compliance_endpoint(self, db_for_audit):
        """GET /compliance 返回报告"""
        ds = db_for_audit
        from meta.api.audit_api import get_compliance_report

        result = get_compliance_report(
            ds,
            current_user={'id': 200, 'username': 'bob', 'role_id': 2}
        )
        # 返回 report 字段
        assert 'report' in result or 'total_decisions' in result


# ============================================================================
# P9 验收: 综合集成
# ============================================================================

class TestP9Acceptance:
    """P9 综合验收"""

    def test_full_audit_pipeline(self, db_for_audit):
        """完整审计链路: 决策 → 日志 → 报告 → API"""
        ds = db_for_audit
        from meta.services.audit_service import AuditService
        from meta.services.compliance_reporter import ComplianceReporter
        from meta.api.audit_api import get_permission_decisions, get_compliance_report

        # 1. 写入决策
        svc = AuditService(ds)
        for i in range(8):
            svc.log_permission_decision(
                user={'id': 100, 'username': 'alice', 'role_id': 1},
                action='read', resource_type='product', resource_id=str(i),
                decision='allow', reason='ok',
            )
        for i in range(2):
            svc.log_permission_decision(
                user={'id': 300, 'username': 'charlie', 'role_id': 3},
                action='delete', resource_type='product', resource_id=str(i),
                decision='deny', reason='prohibition_match',
            )

        # 2. 通过 API 查询
        result = get_permission_decisions(
            ds, page=1, page_size=10,
            current_user={'id': 200, 'username': 'bob', 'role_id': 2}
        )
        assert result['total'] == 10

        # 3. 通过 API 获取合规报告
        report_result = get_compliance_report(
            ds,
            current_user={'id': 200, 'username': 'bob', 'role_id': 2}
        )
        report = report_result.get('report', report_result)
        assert report['total_decisions'] == 10
        assert report['denied_decisions'] == 2
        assert report['prohibition_matches'] == 2

    def test_field_cleaning_in_audit_render(self, db_for_audit):
        """审计字段渲染时调用 clean_audit_field"""
        from meta.services.audit_service import clean_audit_field

        # 模拟从 DB 读出的脏数据
        dirty_values = [None, '', 'null', 'undefined', 'legacy_null', 'n/a', 'na', 'none', 'valid']
        cleaned = [clean_audit_field(v) for v in dirty_values]
        # 前 8 个应为 '-'
        assert cleaned[:8] == ['-', '-', '-', '-', '-', '-', '-', '-']
        # 最后一个保留
        assert cleaned[8] == 'valid'
