# -*- coding: utf-8 -*-
"""[FILE] test_audit_masking.py — 审计旁路脱敏（方案 1）

覆盖 `AuditService.log` 落库前统一脱敏：
  - 字段级 old_value / new_value（log_update 逐字段路径）
  - extra_data 整行快照 `data`（log_create）/ `deleted_data`（log_delete）
  - field_name 为中文名（AuditInterceptor 写 field.name）

规则与读面共用 field_masking_service（sensitivity + LOG_REDACT_IDS）。
"""
import json
import os
import sqlite3
import sys

# 审计落库点单测需要最小 audit_logs 库（项目无对应 Factory），按 test.py 约定显式放行 raw SQL
os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

pytestmark = pytest.mark.unit

from meta.services.audit_service import _mask_audit_payload
from meta.services.field_masking_service import REDACTED

_HASH = 'pbkdf2:sha256:600000$abc123$' + 'd' * 64


@pytest.fixture(scope='module', autouse=True)
def _ensure_schema_registry():
    """脱敏规则依赖 registry 中的 sensitivity 声明"""
    from meta.core.models import registry
    from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory

    if not getattr(registry, '_objects', None):
        register_from_directory(get_yaml_schema_dir())


@pytest.fixture
def audit_ds():
    """最小 audit_logs 库 + DataSource 替身"""
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.executescript("""
        CREATE TABLE audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type VARCHAR(200), object_id VARCHAR(200), action VARCHAR(200),
            field_name VARCHAR(200), old_value TEXT, new_value TEXT,
            user_id VARCHAR(200), user_name VARCHAR(200), ip_address VARCHAR(200),
            user_agent VARCHAR(500), created_at VARCHAR(200), trace_id VARCHAR(200),
            transaction_id VARCHAR(200), agent_id VARCHAR(200), agent_session_id VARCHAR(200),
            tool_call_id VARCHAR(200), agent_reasoning TEXT, status VARCHAR(100),
            extra_data TEXT, parent_object_type VARCHAR(200), parent_object_id VARCHAR(200),
            log_category VARCHAR(100), log_level VARCHAR(50), outcome VARCHAR(50),
            retention_until VARCHAR(200), cascade_root_id VARCHAR(200),
            cascade_root_action VARCHAR(200), change_set_id VARCHAR(200),
            reason_code VARCHAR(200)
        );
    """)

    class MockDS:
        in_transaction = False

        def execute(self, sql, params=None):
            cur = conn.cursor()
            cur.execute(sql, params or [])
            return cur

        def insert(self, table, record):
            cols = list(record.keys())
            cur = conn.cursor()
            cur.execute(
                f"INSERT INTO {table} ({', '.join(cols)}) "
                f"VALUES ({', '.join(['?'] * len(cols))})",
                [record[c] for c in cols],
            )
            conn.commit()
            return cur.lastrowid

        def find(self, table, filters=None, order_by=None):
            cur = conn.cursor()
            try:
                cur.execute(f"SELECT * FROM {table}")
            except sqlite3.OperationalError:
                return []
            names = [d[0] for d in cur.description]
            return [dict(zip(names, row)) for row in cur.fetchall()]

        def commit(self):
            conn.commit()

    yield MockDS()
    conn.close()


class TestMaskAuditPayload:
    def test_field_level_hash_redacted(self):
        logs = [{'field_name': 'password_hash', 'old_value': _HASH, 'new_value': '$new'}]
        masked, _ = _mask_audit_payload('user', logs, None)
        assert masked[0]['old_value'] == REDACTED
        assert masked[0]['new_value'] == REDACTED

    def test_chinese_field_name_redacted(self):
        logs = [{'field_name': '密码哈希', 'old_value': _HASH, 'new_value': ''}]
        masked, _ = _mask_audit_payload('user', logs, None)
        assert masked[0]['old_value'] == REDACTED

    def test_phone_masked(self):
        logs = [{'field_name': 'mobile', 'old_value': '13800138000', 'new_value': '13900139000'}]
        masked, _ = _mask_audit_payload('person_profile', logs, None)
        assert masked[0]['old_value'] == '138****8000'
        assert masked[0]['new_value'] == '139****9000'

    def test_email_masked(self):
        logs = [{'field_name': 'email', 'old_value': 'alice@example.com', 'new_value': ''}]
        masked, _ = _mask_audit_payload('person_profile', logs, None)
        assert masked[0]['old_value'] == 'a***@example.com'

    def test_deleted_data_whole_row_masked(self):
        extra = {'deleted_data': {
            'id': 7, 'username': 'alice', 'password_hash': _HASH,
            'password_history': '["' + _HASH + '"]',
        }}
        _, masked_extra = _mask_audit_payload('user', [], extra)
        assert masked_extra['deleted_data']['username'] == 'alice'
        assert masked_extra['deleted_data']['password_hash'] == REDACTED
        assert masked_extra['deleted_data']['password_history'] == REDACTED

    def test_create_data_whole_row_masked(self):
        extra = {'data': {'id': 7, 'username': 'alice', 'password_hash': _HASH}}
        _, masked_extra = _mask_audit_payload('user', [], extra)
        assert masked_extra['data']['password_hash'] == REDACTED

    def test_unrelated_fields_untouched(self):
        logs = [{'field_name': 'username', 'old_value': 'alice', 'new_value': 'bob'}]
        extra = {'deleted_data': {'username': 'alice'}}
        masked_logs, masked_extra = _mask_audit_payload('user', logs, extra)
        assert masked_logs[0]['new_value'] == 'bob'
        assert masked_extra['deleted_data']['username'] == 'alice'

    def test_input_not_mutated(self):
        extra = {'deleted_data': {'password_hash': _HASH}}
        _mask_audit_payload('user', None, extra)
        assert extra['deleted_data']['password_hash'] == _HASH


class TestAuditServiceLogMasking:
    def test_delete_snapshot_has_no_plain_hash(self, audit_ds):
        from meta.services.audit_service import AuditService

        AuditService(audit_ds).log(
            object_type='user', object_id=7, action='DELETE',
            extra_data={'deleted_data': {
                'id': 7, 'username': 'alice', 'password_hash': _HASH,
            }},
            user_id=1, user_name='admin',
        )
        rows = audit_ds.find('audit_logs')
        assert rows
        extra = json.loads(rows[0]['extra_data'])
        assert extra['deleted_data']['password_hash'] == REDACTED
        assert extra['deleted_data']['username'] == 'alice'

    def test_update_field_log_has_no_plain_hash(self, audit_ds):
        from meta.services.audit_service import AuditService

        AuditService(audit_ds).log(
            object_type='user', object_id=7, action='UPDATE',
            field_name='password_hash', old_value=_HASH, new_value='$new',
            user_id=1, user_name='admin',
        )
        rows = audit_ds.find('audit_logs')
        assert rows
        assert rows[0]['field_name'] == 'password_hash'
        assert rows[0]['old_value'] == REDACTED
        assert rows[0]['new_value'] == REDACTED

    def test_person_profile_phone_not_plain(self, audit_ds):
        from meta.services.audit_service import AuditService

        AuditService(audit_ds).log(
            object_type='person_profile', object_id=9, action='DELETE',
            extra_data={'deleted_data': {'id': 9, 'mobile': '13800138000'}},
            user_id=1, user_name='admin',
        )
        rows = audit_ds.find('audit_logs')
        assert rows
        extra = json.loads(rows[0]['extra_data'])
        assert extra['deleted_data']['mobile'] == '138****8000'
