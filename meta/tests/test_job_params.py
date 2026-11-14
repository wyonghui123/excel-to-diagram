# -*- coding: utf-8 -*-
"""作业参数清洗（`meta/core/job_params.py`）单元测试。

覆盖 spec §7.2：
  · `default_params` ← `params_override` 合并；
  · 未声明键丢弃（不报错）；
  · 必填缺失 / const / 类型不符 → 拒绝；
  · 禁止键（handler/module/class/`__` 前缀）→ 拒绝；
  · 16KB 上限；
  · 无 schema（NULL）→ 全部丢弃。
"""

import json

import pytest

pytestmark = pytest.mark.unit

from meta.core.job_params import (
    MAX_PARAMS_BYTES, is_secret_field, merge_job_params, redact_secrets,
    sanitize_params, sanitize_params_detailed,
)

SCHEMA = {
    'type': 'object',
    'required': ['action_id'],
    'properties': {
        'action_id': {'type': 'string', 'const': 'inspection.run'},
        'payload': {'type': 'object'},
        'limit': {'type': 'integer', 'enum': [10, 20]},
    },
}


def test_merge_default_params_with_override():
    job = {'default_params': json.dumps({'a': 1, 'b': 2})}
    assert merge_job_params(job, {'b': 3}) == {'a': 1, 'b': 3}
    assert merge_job_params(job) == {'a': 1, 'b': 2}
    assert merge_job_params({}, {'x': 1}) == {'x': 1}


def test_sanitize_keeps_declared_keys_and_drops_others():
    clean, error = sanitize_params(
        {'action_id': 'inspection.run', 'unknown': 1}, SCHEMA)
    assert error is None
    assert clean == {'action_id': 'inspection.run'}


def test_sanitize_without_schema_drops_everything():
    clean, error = sanitize_params({'anything': 1}, None)
    assert error is None
    assert clean == {}


def test_missing_required_key_is_rejected():
    clean, error = sanitize_params({'payload': {}}, SCHEMA)
    assert clean == {}
    assert 'action_id' in error


def test_const_mismatch_is_rejected():
    _, error = sanitize_params({'action_id': 'other.run'}, SCHEMA)
    assert error and 'action_id' in error


def test_type_mismatch_is_rejected():
    _, error = sanitize_params(
        {'action_id': 'inspection.run', 'payload': 'not-object'}, SCHEMA)
    assert error and 'payload' in error


def test_enum_mismatch_is_rejected():
    _, error = sanitize_params(
        {'action_id': 'inspection.run', 'limit': 15}, SCHEMA)
    assert error and 'limit' in error


@pytest.mark.parametrize('key', ['handler', 'module_name', 'exec_class', '__import__'])
def test_forbidden_keys_are_rejected(key):
    _, error = sanitize_params({key: 'x'}, None)
    assert error and '禁止' in error


def test_forbidden_key_is_detected_nested():
    _, error = sanitize_params({'payload': {'inner': {'handler': 'x'}}}, SCHEMA)
    assert error and '禁止' in error


def test_oversize_params_are_rejected():
    payload = {'action_id': 'inspection.run', 'payload': {'blob': 'x' * MAX_PARAMS_BYTES}}
    _, error = sanitize_params(payload, SCHEMA)
    assert error and '超过' in error


def test_non_object_params_are_rejected():
    clean, error = sanitize_params(['a'], SCHEMA)
    assert clean == {}
    assert error and 'object' in error


# ── 告警明细与脱敏（spec IF-002 / NFR-006）─────────────────────────────

def test_sanitize_detailed_reports_dropped_keys():
    clean, error, details = sanitize_params_detailed(
        {'action_id': 'inspection.run', 'unknown': 1}, SCHEMA)
    assert error is None
    assert clean == {'action_id': 'inspection.run'}
    assert details == [
        {'field': 'unknown', 'message': '未在 params_schema 声明，已忽略'},
    ]


def test_sanitize_detailed_has_no_details_for_fatal_error():
    clean, error, details = sanitize_params_detailed({}, SCHEMA)
    assert clean == {} and error and '必填' in error
    assert details == []


def test_is_secret_field_by_key_name_and_x_ui():
    assert is_secret_field('password') is True
    assert is_secret_field('api_token') is True
    assert is_secret_field('client_secret') is True
    assert is_secret_field('access_key') is True
    assert is_secret_field('note') is False
    assert is_secret_field('note', {'x-ui': {'secret': True}}) is True


def test_redact_secrets_masks_known_and_nested_keys():
    schema = {'properties': {
        'password': {'type': 'string'},
        'account': {'type': 'string'},
        'nested': {'type': 'object'},
    }}
    redacted = redact_secrets({
        'password': 'p@ss',
        'account': 'alice',
        'nested': {'db_password': 'x', 'keep': 1},
    }, schema)
    assert redacted == {
        'password': '***',
        'account': 'alice',
        'nested': {'db_password': '***', 'keep': 1},
    }


def test_redact_secrets_tolerates_non_dict():
    assert redact_secrets(None) == {}
    assert redact_secrets(['x']) == {}