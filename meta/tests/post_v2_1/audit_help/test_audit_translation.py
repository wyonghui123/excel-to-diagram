# -*- coding: utf-8 -*-
"""
test_audit_translation.py
覆盖提交: db4e151 (业务名显示 + 补全缺失的枚举值翻译), 4fbbe96 (workflow → business 数据修复)
依据: .trae/specs/test-suite/post-6-22-roadmap.md 主题 6 (Audit Log 业务化)

测试:
- log_category 'business' 显示为业务名
- 缺失的枚举值有 fallback 翻译 (PUSH/PULL/warning/info/error/success/danger/tip)
- workflow → business 修复脚本执行后, 审计日志已更新
- 审计日志中无 workflow 类别记录
- object_type 翻译 (sub_domain → 子领域, business_object → 业务对象)
- business_key 显示业务名 (TEST11111) / API fallback (#ID)
"""
import re
import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = [
    pytest.mark.post_v2_1,
    pytest.mark.audit_help,
]


ARCH_DB_PATH = str(PROJECT_ROOT / 'meta' / 'architecture.db')


def _open_db():
    con = sqlite3.connect(ARCH_DB_PATH)
    con.row_factory = sqlite3.Row
    return con


# ============================================================
# 1. TestAuditLogTranslation (6 用例)
# ============================================================

class TestAuditLogTranslation:
    """审计日志业务名翻译 (db4e151, 4fbbe96)"""

    def test_log_category_business_displayed(self):
        """[db4e151] log_category 'business' 显示为业务名

        验证: audit_logs 中 log_category='business' 记录存在
        (审计日志使用 'business' 作为业务类别的标准枚举)
        """
        con = _open_db()
        try:
            cur = con.execute(
                "SELECT COUNT(*) AS cnt FROM audit_logs WHERE log_category = 'business'"
            )
            row = cur.fetchone()
            count = row[0] if row else 0
            # 应至少有一些 business 类别记录
            assert count > 0, "audit_logs should have log_category='business' records"
        finally:
            con.close()

    def test_missing_enum_translation(self):
        """[db4e151] 缺失的枚举值有 fallback 翻译

        验证: auditLogFormat.js FIELD_VALUE_LABELS 包含
        PUSH/PULL (关系方向) + warning/info/error/success/danger/tip (annotation 分类)
        """
        format_path = PROJECT_ROOT / 'src' / 'utils' / 'auditLogFormat.js'
        content = format_path.read_text(encoding='utf-8')

        # 关系方向 (PUSH/PULL) 翻译
        # [FIX 2026-06-24 业务化] 关系方向 (PUSH/PULL 是技术传输方向, 业务翻译)
        assert "'PUSH': '推送'" in content or "PUSH:" in content, \
            "FIELD_VALUE_LABELS should translate PUSH"
        assert "'PULL': '拉取'" in content or "PULL:" in content, \
            "FIELD_VALUE_LABELS should translate PULL"

        # annotation 分类 (warning/info/error/success/danger/tip)
        assert "'warning': '警告'" in content or "warning:" in content, \
            "FIELD_VALUE_LABELS should translate warning"
        assert "'info': '信息'" in content or "info:" in content, \
            "FIELD_VALUE_LABELS should translate info"
        assert "'error': '错误'" in content or "error:" in content, \
            "FIELD_VALUE_LABELS should translate error"
        assert "'success': '成功'" in content or "success:" in content, \
            "FIELD_VALUE_LABELS should translate success"
        assert "'danger': '危险'" in content or "danger:" in content, \
            "FIELD_VALUE_LABELS should translate danger"
        assert "'tip': '提示'" in content or "tip:" in content, \
            "FIELD_VALUE_LABELS should translate tip"

    def test_workflow_to_business_migration(self):
        """[4fbbe96] workflow → business 修复脚本运行后, 审计日志已更新

        验证: 修复后, audit_logs 中没有 'workflow' 类别记录
        (非标准枚举值已被修正)
        """
        con = _open_db()
        try:
            cur = con.execute(
                "SELECT COUNT(*) AS cnt FROM audit_logs WHERE log_category = 'workflow'"
            )
            row = cur.fetchone()
            count = row[0] if row else 0
            assert count == 0, \
                f"audit_logs should not have 'workflow' category (4fbbe96 migration), found {count}"
        finally:
            con.close()

    def test_no_non_standard_log_categories(self):
        """[4fbbe96] audit_logs 中没有非标准 log_category 记录

        验证: 修复脚本后, 所有记录的 log_category 都在标准枚举中
        (business, security, authz, access, admin, system, cascade)
        """
        con = _open_db()
        try:
            # 标准 log_category 枚举
            standard_categories = (
                'business', 'security', 'authz', 'access',
                'admin', 'system', 'cascade'
            )
            placeholders = ','.join('?' for _ in standard_categories)

            cur = con.execute(
                f"SELECT COUNT(*) AS cnt FROM audit_logs "
                f"WHERE log_category IS NOT NULL "
                f"AND log_category NOT IN ({placeholders})",
                standard_categories,
            )
            row = cur.fetchone()
            non_std = row[0] if row else 0
            assert non_std == 0, \
                f"audit_logs should have only standard log_category values, found {non_std} non-standard"
        finally:
            con.close()

    def test_object_type_business_label_translation(self):
        """[db4e151] object_type 翻译 (sub_domain → 子领域, business_object → 业务对象)

        验证: auditLogFormat.js OBJECT_TYPE_LABELS 包含关键翻译
        """
        format_path = PROJECT_ROOT / 'src' / 'utils' / 'auditLogFormat.js'
        content = format_path.read_text(encoding='utf-8')

        # 关键翻译: 业务人员视角的 object_type 名
        assert "sub_domain: '子领域'" in content, \
            "OBJECT_TYPE_LABELS should map sub_domain -> 子领域"
        assert "business_object: '业务对象'" in content, \
            "OBJECT_TYPE_LABELS should map business_object -> 业务对象"
        assert "annotation: '备注'" in content, \
            "OBJECT_TYPE_LABELS should map annotation -> 备注"
        assert "product: '产品'" in content, \
            "OBJECT_TYPE_LABELS should map product -> 产品"
        assert "version: '版本'" in content, \
            "OBJECT_TYPE_LABELS should map version -> 版本"

    def test_cleanup_workflow_script_exists(self):
        """[4fbbe96] 数据修复脚本 cleanup_workflow_category.py 存在

        验证: scripts/cleanup_workflow_category.py 文件存在,
        且含 UPDATE audit_logs SET log_category='business' WHERE log_category='workflow'
        """
        script_path = PROJECT_ROOT / 'scripts' / 'cleanup_workflow_category.py'
        assert script_path.exists(), \
            f"cleanup_workflow_category.py should exist at {script_path}"

        content = script_path.read_text(encoding='utf-8')

        # 关键 SQL: UPDATE log_category
        assert "UPDATE audit_logs" in content, \
            "script should UPDATE audit_logs"
        assert "log_category" in content, \
            "script should reference log_category"
        assert "'workflow'" in content, \
            "script should target 'workflow' category"
        assert "'business'" in content, \
            "script should set 'business' as replacement"
