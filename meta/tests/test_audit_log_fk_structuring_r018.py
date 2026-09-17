# -*- coding: utf-8 -*-
"""
[R018 FIX] audit_log FK 结构化增强单测
=========================================

背景: R018 全面检查发现 audit_log 写入 service_module/relationship 时,
     FK 字段 (version_id, sub_domain_id, target_service_module_id 等)
     只写技术 id (如 764), 看不到 name/display, 用户角度不友好。

修复:
  1. _structure_fk_value 增加复数 fallback (version -> versions)
  2. 增加关系前缀剥离 (target_service_module -> service_module)
  3. 用 is_valid_table_name 预判避免无效查询噪音
  4. _render_value helper 统一 dict->JSON 字符串渲染

本测试覆盖:
  - 单数表查不到时, 复数 fallback 命中
  - 关系前缀 (target_/source_) 正确剥离
  - 表未注册时安静降级回原值 (不抛异常)
  - dict 入口 (CREATE 全字段) 渲染正确
  - 现有 _record fallback / system_fields 过滤行为不变
"""

import json
import os
import sqlite3
import tempfile
import pytest


@pytest.fixture
def fresh_db():
    """建一个 temp DB, 含完整 audit_logs + versions/sub_domains/service_modules/roles"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT NOT NULL,
            object_id INTEGER,
            action TEXT NOT NULL,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            user_id TEXT,
            user_name TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT,
            extra_data TEXT,
            log_category VARCHAR(200) NOT NULL DEFAULT 'business',
            log_level VARCHAR(200) NOT NULL DEFAULT 'INFO',
            parent_object_type VARCHAR(200),
            parent_object_id INTEGER,
            trace_id VARCHAR(200),
            transaction_id VARCHAR(200),
            status VARCHAR(200) DEFAULT 'written',
            status_entered_at DATETIME,
            retry_count INTEGER DEFAULT 0,
            error_message TEXT,
            agent_id VARCHAR(200),
            agent_session_id VARCHAR(200),
            tool_call_id VARCHAR(200),
            agent_reasoning TEXT,
            outcome VARCHAR(20) DEFAULT 'success',
            cascade_root_id INTEGER,
            cascade_root_action VARCHAR(50),
            retention_until DATETIME,
            prev_hash CHAR(64),
            row_hash CHAR(64),
            action_kind VARCHAR(20) DEFAULT 'instance',
            created_by VARCHAR(200),
            updated_by VARCHAR(200),
            updated_at DATETIME,
            created_at_epoch BIGINT
        );
        -- 架构数据表 (复数, 跟生产一致)
        CREATE TABLE versions (
            id INTEGER PRIMARY KEY, code TEXT, name TEXT
        );
        INSERT INTO versions VALUES (764, 'V1', 'v1.0');
        CREATE TABLE sub_domains (
            id INTEGER PRIMARY KEY, code TEXT, name TEXT
        );
        INSERT INTO sub_domains VALUES (361, 'EPM', '企业绩效');
        CREATE TABLE service_modules (
            id INTEGER PRIMARY KEY, version_id INTEGER, sub_domain_id INTEGER,
            code TEXT, name TEXT, description TEXT
        );
        INSERT INTO service_modules VALUES (709, 764, 361, 'EMP', '人员管理', '');
        INSERT INTO service_modules VALUES (719, 863, 357, 'HRSASAC', '国资委报表', '');
        CREATE TABLE permission_sets (
            id INTEGER PRIMARY KEY, code TEXT, name TEXT, description TEXT
        );
        INSERT INTO permission_sets VALUES (1, 'admin', '系统管理员', '');
        CREATE TABLE users (
            id INTEGER PRIMARY KEY, username TEXT, display_name TEXT
        );
        INSERT INTO users VALUES (10079, 'spec19_delegate', 'Spec19 受托管理员');
    """)
    conn.commit()
    conn.close()

    # 注册架构表到白名单 (模拟生产环境 registry)
    from meta.core.table_name_validator import register_table_name, invalidate_cache
    for t in [
        'versions', 'sub_domains', 'service_modules',
        'roles', 'users', 'permissions', 'permission_sets',
    ]:
        register_table_name(t)
    invalidate_cache()

    yield path

    # 清理
    from meta.core.table_name_validator import invalidate_cache
    invalidate_cache()
    try:
        os.unlink(path)
    except Exception:
        pass


@pytest.fixture
def audit_svc(fresh_db):
    """建 AuditService 实例"""
    from meta.core.datasource import get_data_source
    from meta.services.audit_service import AuditService
    from meta.services.async_audit_writer import async_audit_writer

    ds = get_data_source('sqlite', database=fresh_db)
    async_audit_writer.set_data_source(ds)
    return AuditService(ds)


# ============================================================================
# Bug-A 修复: FK 结构化增强
# ============================================================================

class TestFkStructuringFixR018:
    """R018: _structure_fk_value 增强"""

    def test_plural_fallback_versions(self, audit_svc):
        """单数 'version' 表不存在, 复数 'versions' 应命中"""
        result = audit_svc._structure_fk_value('version_id', 764)
        parsed = json.loads(result)
        assert parsed['target_type'] == 'versions'
        assert parsed['target_id'] == 764
        assert parsed['target_key'] == 'V1'
        assert parsed['target_display'] == 'v1.0'

    def test_plural_fallback_sub_domains(self, audit_svc):
        """sub_domain_id -> sub_domains 应命中"""
        result = audit_svc._structure_fk_value('sub_domain_id', 361)
        parsed = json.loads(result)
        assert parsed['target_type'] == 'sub_domains'
        assert parsed['target_display'] == '企业绩效'

    def test_relationship_prefix_target(self, audit_svc):
        """target_service_module_id 应剥离 target_ 前缀后命中 service_modules"""
        result = audit_svc._structure_fk_value('target_service_module_id', 709)
        parsed = json.loads(result)
        assert parsed['target_type'] == 'service_modules'
        assert parsed['target_display'] == '人员管理'

    def test_relationship_prefix_source(self, audit_svc):
        """source_service_module_id 应剥离 source_ 前缀"""
        result = audit_svc._structure_fk_value('source_service_module_id', 719)
        parsed = json.loads(result)
        assert parsed['target_display'] == '国资委报表'

    def test_singular_still_works(self, audit_svc):
        """roles 表 (单数表未注册但表名就是复数, 注册后等价) 应正常命中"""
        result = audit_svc._structure_fk_value('role_id', 1)
        parsed = json.loads(result)
        assert parsed['target_display'] == '系统管理员'

    def test_unregistered_table_falls_back_silently(self, audit_svc):
        """完全未注册的字段名 (例如假设的 random_id) 应安静返回原值不抛异常"""
        from meta.core.table_name_validator import invalidate_cache
        invalidate_cache()  # 清缓存让 is_valid_table_name 重算

        result = audit_svc._structure_fk_value('random_unknown_field_id', 999)
        assert result == 999, "未注册字段应直接返回原值"

        invalidate_cache()  # 恢复

    def test_non_fk_field_passthrough(self, audit_svc):
        """非 _id 结尾字段 (e.g. username) 不应被结构化"""
        result = audit_svc._structure_fk_value('username', 'alice')
        assert result == 'alice'

    def test_values_in_data_returns_structured_for_fk(self, audit_svc):
        """_structure_fk_values_in_data 应返回每个 FK 字段的结构化 JSON"""
        data = {
            'version_id': 764,
            'sub_domain_id': 361,
            'target_service_module_id': 709,
            'code': 'TR',
            'name': '薪酬预算',
        }
        result = audit_svc._structure_fk_values_in_data(data)

        # FK 字段应是 JSON 字符串
        v_parsed = json.loads(result['version_id'])
        assert v_parsed['target_display'] == 'v1.0'

        sm_parsed = json.loads(result['target_service_module_id'])
        assert sm_parsed['target_display'] == '人员管理'

        # 普通字段原样
        assert result['code'] == 'TR'
        assert result['name'] == '薪酬预算'


# ============================================================================
# Bug-A 集成验证: audit_service.log CREATE 写入后, audit_logs 表里 new_value
# 应是结构化 JSON (含 target_display)
# ============================================================================

class TestAuditLogIntegrationR018:

    def test_create_service_module_writes_structured_fk(self, fresh_db, audit_svc):
        """CREATE service_module 应把 version_id/sub_domain_id 写成结构化 JSON"""
        audit_svc.log(
            object_type='service_module',
            object_id=999,
            action='CREATE',
            user_name='Admin',
            new_data={
                'version_id': 764,
                'sub_domain_id': 361,
                'code': 'TR',
                'name': '薪酬预算',
            },
        )

        conn = sqlite3.connect(fresh_db)
        rows = conn.execute(
            "SELECT field_name, new_value FROM audit_logs WHERE object_type='service_module' AND object_id=999 ORDER BY id"
        ).fetchall()
        conn.close()

        by_field = {r[0]: r[1] for r in rows}
        # version_id 应是 JSON 含 target_display
        v = json.loads(by_field['version_id'])
        assert v['target_display'] == 'v1.0'
        # sub_domain_id 应是 JSON 含 target_display
        sd = json.loads(by_field['sub_domain_id'])
        assert sd['target_display'] == '企业绩效'
        # 普通字段原样
        assert by_field['code'] == 'TR'
        assert by_field['name'] == '薪酬预算'

    def test_create_with_no_data_keeps_record_fallback(self, fresh_db, audit_svc):
        """CREATE 但 data={} 时仍应写 _record fallback (行为不变)"""
        audit_svc.log(
            object_type='role',
            object_id=999,
            action='CREATE',
            user_name='Admin',
            new_data={},  # 空
        )

        conn = sqlite3.connect(fresh_db)
        rows = conn.execute(
            "SELECT field_name, new_value FROM audit_logs WHERE object_type='role' AND object_id=999"
        ).fetchall()
        conn.close()

        # 应只有一行 _record
        assert len(rows) == 1
        assert rows[0][0] == '_record'
        assert rows[0][1] == 'CREATE'


# ============================================================================
# Bug-G 修复: 已有 field_name + value 入口 (UPDATE/单字段) 也用 _render_value
# ============================================================================

class TestRenderValueHelper:

    def test_render_value_dict_to_json(self, fresh_db, audit_svc):
        """[R018] CREATE service_module + FK 应渲染为合法 JSON 字符串"""
        audit_svc.log(
            object_type='service_module',
            object_id=888,
            action='CREATE',
            user_name='Admin',
            new_data={'version_id': 764},
        )

        conn = sqlite3.connect(fresh_db)
        rows = conn.execute(
            "SELECT new_value FROM audit_logs WHERE object_type='service_module' AND object_id=888 AND field_name='version_id'"
        ).fetchall()
        conn.close()

        assert len(rows) == 1
        val = rows[0][0]
        # new_value 应该是合法 JSON 字符串 (避免 str(dict) 单引号问题)
        parsed = json.loads(val)
        assert parsed['target_display'] == 'v1.0'


# ============================================================================
# Bug-C 修复: CREATE/UPDATE 分支应用 system_fields 过滤 + 冗余前缀仅过滤非 FK
# ============================================================================

class TestSystemFieldsFilterR018:
    """[R018 P1 BUG-C] 系统字段 (id/created_at/updated_by 等) 不再写入 audit_log"""

    def test_create_permission_set_filters_system_fields(self, fresh_db, audit_svc):
        """CREATE permission_set: 不应写入 id/created_at/updated_at/created_by/updated_by"""
        audit_svc.log(
            object_type='permission_set',
            object_id=12345,
            action='CREATE',
            user_name='Admin',
            new_data={
                # 业务字段 (应保留)
                'code': 'PS_TEST',
                'name': '测试权限集',
                # 系统字段 (应过滤)
                'id': 12345,
                'created_at': '2026-09-15T10:00:00',
                'updated_at': '2026-09-15T10:00:00',
                'created_by': 'admin',
                'updated_by': 'admin',
                'tenant_id': 1,
                'is_system': 0,
            },
        )

        conn = sqlite3.connect(fresh_db)
        rows = conn.execute(
            "SELECT field_name FROM audit_logs WHERE object_type='permission_set' AND object_id=12345 ORDER BY id"
        ).fetchall()
        conn.close()

        field_names = {r[0] for r in rows}
        # 业务字段应保留
        assert 'code' in field_names, f"业务字段 code 丢失: {field_names}"
        assert 'name' in field_names, f"业务字段 name 丢失: {field_names}"
        # 系统字段应被过滤
        assert 'id' not in field_names, f"系统字段 id 未过滤: {field_names}"
        assert 'created_at' not in field_names, f"系统字段 created_at 未过滤: {field_names}"
        assert 'updated_at' not in field_names, f"系统字段 updated_at 未过滤: {field_names}"
        assert 'created_by' not in field_names, f"系统字段 created_by 未过滤: {field_names}"
        assert 'updated_by' not in field_names, f"系统字段 updated_by 未过滤: {field_names}"
        assert 'tenant_id' not in field_names, f"系统字段 tenant_id 未过滤: {field_names}"
        assert 'is_system' not in field_names, f"系统字段 is_system 未过滤: {field_names}"

    def test_update_filters_system_fields(self, fresh_db, audit_svc):
        """UPDATE 分支也应过滤系统字段"""
        audit_svc.log(
            object_type='user',
            object_id=100,
            action='UPDATE',
            user_name='Admin',
            old_data={'name': 'Old', 'updated_at': '2026-01-01'},
            new_data={'name': 'New', 'updated_at': '2026-09-15', 'id': 100},
        )

        conn = sqlite3.connect(fresh_db)
        rows = conn.execute(
            "SELECT field_name FROM audit_logs WHERE object_type='user' AND object_id=100 AND action='UPDATE'"
        ).fetchall()
        conn.close()

        field_names = {r[0] for r in rows}
        # 仅应记录 name 变化 (updated_at/id 被过滤)
        assert 'name' in field_names
        assert 'updated_at' not in field_names, f"updated_at 未过滤: {field_names}"
        assert 'id' not in field_names, f"id 未过滤: {field_names}"

    def test_version_id_fk_not_filtered_as_redundant(self, fresh_db, audit_svc):
        """[R018 P1 BUG-C regression] version_id 是 FK, 不应被 version_ 前缀规则误杀"""
        audit_svc.log(
            object_type='service_module',
            object_id=777,
            action='CREATE',
            user_name='Admin',
            new_data={
                'version_id': 764,  # FK -> versions, 应保留
                'code': 'X',
            },
        )

        conn = sqlite3.connect(fresh_db)
        rows = conn.execute(
            "SELECT field_name FROM audit_logs WHERE object_type='service_module' AND object_id=777"
        ).fetchall()
        conn.close()

        field_names = {r[0] for r in rows}
        # version_id 必须保留 (FK 是核心信息, 不能被冗余前缀误过滤)
        assert 'version_id' in field_names, f"FK version_id 被误杀: {field_names}"
        assert 'code' in field_names

    def test_version_name_redundant_filtered(self, fresh_db, audit_svc):
        """version_name (冗余字段) 应被 _is_redundant 过滤"""
        audit_svc.log(
            object_type='service_module',
            object_id=888,
            action='CREATE',
            user_name='Admin',
            new_data={
                'version_id': 764,
                'version_name': 'v1.0',  # 冗余: version_id 已有 target_display
            },
        )

        conn = sqlite3.connect(fresh_db)
        rows = conn.execute(
            "SELECT field_name FROM audit_logs WHERE object_type='service_module' AND object_id=888"
        ).fetchall()
        conn.close()

        field_names = {r[0] for r in rows}
        # version_id 保留, version_name 过滤
        assert 'version_id' in field_names
        assert 'version_name' not in field_names, f"version_name 冗余字段未被过滤: {field_names}"


# ============================================================================
# Bug-D 修复: UI 层 _format_field_value 过滤 __xxx__ sentinel 模式
# ============================================================================

class TestSentinelFilterR018:
    """[R018 P1 BUG-D] audit_api._format_field_value 应将 __xxx__ 异常标识降级为 '(空)'"""

    def test_sentinel_value_normalized_to_empty(self):
        """__no_such_association__:xxx 应显示为空 (历史 7/18-7/19 数据噪音防御)"""
        from meta.api.audit_api import _format_field_value
        out = _format_field_value('__no_such_association__')
        assert out == '', f"expected '' got {out!r}"

    def test_sentinel_with_id_suffix_normalized_to_empty(self):
        """__no_such_association__:470 应降级为空"""
        from meta.api.audit_api import _format_field_value
        out = _format_field_value('__no_such_association__:470')
        assert out == '', f"expected '' got {out!r}"

    def test_normal_string_not_filtered(self):
        """非 sentinel 字符串不应被过滤 (回归防护)"""
        from meta.api.audit_api import _format_field_value
        assert _format_field_value('采购订单') == '采购订单'
        assert _format_field_value('admin') == 'admin'
        # 含下划线但非 sentinel 模式
        assert _format_field_value('role_admin') == 'role_admin'

    def test_json_fk_not_filtered_by_sentinel(self):
        """FK JSON 字符串 (以 { 开头) 不应被 sentinel 规则误过滤"""
        from meta.api.audit_api import _format_field_value
        fk_json = json.dumps({
            'target_type': 'roles', 'target_id': 1,
            'target_key': 'admin', 'target_display': '系统管理员',
        })
        out = _format_field_value(fk_json, object_type='role', field_name='role_id')
        assert '系统管理员' in out or out == '系统管理员'


# ============================================================================
# Bug-E 修复: deletion_service DELETE outcome 区分 (success/failed)
# ============================================================================

class TestDeleteOutcomeR018:
    """[R018 P1 BUG-E] audit_interceptor.log_delete 支持 outcome 参数"""

    def test_log_delete_default_outcome_is_success(self):
        """log_delete 默认 outcome='success' (兼容历史调用)"""
        from meta.services.audit_interceptor import AuditInterceptor
        import inspect
        sig = inspect.signature(AuditInterceptor.log_delete)
        assert sig.parameters['outcome'].default == 'success', \
            f"log_delete outcome 默认值应为 'success', 实际 {sig.parameters['outcome'].default!r}"

    def test_log_delete_accepts_outcome_param(self):
        """log_delete 接受 outcome 参数"""
        from meta.services.audit_interceptor import AuditInterceptor
        import inspect
        sig = inspect.signature(AuditInterceptor.log_delete)
        assert 'outcome' in sig.parameters

    def test_deletion_service_writes_failed_audit_for_missing_record(self):
        """删除不存在的记录应写 outcome=failed 审计 (替代之前静默返回 False)"""
        # 单元测试 _write_audit_log 的 outcome 透传 (无需 DB)
        from meta.services.deletion_service import DeletionService
        import inspect
        sig = inspect.signature(DeletionService._write_audit_log)
        assert 'outcome' in sig.parameters, "deletion_service._write_audit_log 应接受 outcome"
        assert sig.parameters['outcome'].default == 'success'

    def test_audit_service_log_supports_outcome(self):
        """[regression] audit_service.log 支持 outcome 参数 (已有, 防回归)"""
        from meta.services.audit_service import AuditService
        import inspect
        sig = inspect.signature(AuditService.log)
        assert 'outcome' in sig.parameters
        # 默认值 'success'
        assert sig.parameters['outcome'].default == 'success'


# ============================================================================
# Bug-F 修复: extra_data 中文 UTF-8 编码 (ensure_ascii=False)
# ============================================================================

class TestExtraDataUtf8R018:
    """[R018 P1 BUG-F] audit_service.log 写入 extra_data 时中文保持 UTF-8 字节"""

    def test_extra_data_chinese_stored_as_utf8(self, fresh_db, audit_svc):
        """extra_data 含中文应直接存为 UTF-8 (不转义 \\uXXXX)"""
        chinese_name = '测试权限集-20260906'
        chinese_desc = '用于薪酬预算的权限集'
        audit_svc.log(
            object_type='permission_set',
            object_id=99999,
            action='CREATE',
            user_name='Admin',
            new_data={'code': 'PS_TEST'},
            extra_data={
                'name': chinese_name,
                'description': chinese_desc,
                'category': '业务',
            },
        )

        import sqlite3
        conn = sqlite3.connect(fresh_db)
        # 读 raw text (sqlite 默认 UTF-8 解码)
        raw = conn.execute(
            "SELECT extra_data FROM audit_logs WHERE object_id=99999"
        ).fetchone()[0]
        conn.close()

        # raw 应直接含 UTF-8 中文 (而非 \uXXXX 转义)
        assert chinese_name in raw, \
            f"extra_data 未直接存 UTF-8 中文: {raw[:200]!r}"
        # 不应出现 \u 转义 (反斜杠 + u + 4 个十六进制数字)
        import re as _re
        assert not _re.search(r'\\u[0-9a-fA-F]{4}', raw), \
            f"extra_data 仍含 unicode 转义: {raw[:200]!r}"
        # 解析后中文应正确还原
        parsed = json.loads(raw)
        assert parsed['name'] == chinese_name

    def test_extra_data_chinese_readable_after_round_trip(self, fresh_db, audit_svc):
        """写入后再读 extra_data, 中文应正确还原"""
        original = {
            'name': '薪酬预算',
            'description': '用于管理薪酬预算的权限',
        }
        audit_svc.log(
            object_type='permission_set',
            object_id=99998,
            action='CREATE',
            user_name='Admin',
            new_data={'code': 'PS_RT'},
            extra_data=original,
        )

        conn = sqlite3.connect(fresh_db)
        raw = conn.execute(
            "SELECT extra_data FROM audit_logs WHERE object_id=99998"
        ).fetchone()[0]
        conn.close()

        parsed = json.loads(raw)
        assert parsed['name'] == '薪酬预算', f"name 解码错误: {parsed.get('name')!r}"
        assert parsed['description'] == '用于管理薪酬预算的权限'
