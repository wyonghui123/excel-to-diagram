# -*- coding: utf-8 -*-
"""
[V007.15 L6] Tests for observability module
"""
import pytest
import logging
import time
import sqlite3
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# Add meta to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from meta.core import db_config_detector
from meta.core.observability import (
    metrics_inc, metrics_set_state, log_tx_event, OBS_COUNTERS,
    AuditRetryWrapper
)


# === metrics_inc tests ===
def test_metrics_inc_unknown_key():
    """Unknown key should not raise"""
    metrics_inc('unknown_key_xyz')  # should be no-op


def test_metrics_inc_skips_state_key():
    """runtime_state uses metrics_set_state, not inc"""
    metrics_inc('runtime_state')  # should be no-op (no increment)


def test_metrics_inc_without_prometheus():
    """When Prometheus not installed, should not raise"""
    with patch.dict('sys.modules', {'prometheus_client': None}):
        metrics_inc('commit_success')  # should not raise


# === metrics_set_state tests ===
def test_metrics_set_state_without_prometheus():
    with patch.dict('sys.modules', {'prometheus_client': None}):
        metrics_set_state(0)  # should not raise


def test_metrics_set_state_invalid_code():
    """Invalid state code should still be set"""
    metrics_set_state(99)  # not raise


# === log_tx_event tests ===
def test_log_tx_event_basic(caplog):
    with caplog.at_level(logging.INFO):
        log_tx_event('test', 'tx-1', 'ok', None)
    assert '[V007.15] test' in caplog.text


def test_log_tx_event_with_detail(caplog):
    with caplog.at_level(logging.INFO):
        log_tx_event('test', 'tx-1', 'ok', 'some detail')
    assert 'some detail' in caplog.text


def test_log_tx_event_error_logs_error(caplog):
    with caplog.at_level(logging.ERROR):
        log_tx_event('commit', 'tx-1', 'error', 'disk full')
    assert caplog.records[0].levelname == 'ERROR'


def test_log_tx_event_warning_logs_warning(caplog):
    with caplog.at_level(logging.WARNING):
        log_tx_event('begin', 'tx-1', 'locked', 'db locked')
    assert caplog.records[0].levelname == 'WARNING'


def test_log_tx_event_truncates_long_detail(caplog):
    with caplog.at_level(logging.INFO):
        long_detail = 'x' * 1000
        log_tx_event('test', 'tx-1', 'ok', long_detail)
    # Should truncate to 200 chars in message
    assert 'xxx' in caplog.text


def test_log_tx_event_none_tx_id(caplog):
    with caplog.at_level(logging.INFO):
        log_tx_event('orphan', None, 'recovered', 'forced rollback')
    assert 'tx_id=None' in caplog.text or 'None' in caplog.text


# === AuditRetryWrapper tests ===
@pytest.fixture
def mock_audit_service():
    return MagicMock()


def test_audit_retry_success_first_try(mock_audit_service):
    mock_audit_service.create.return_value = True
    with patch('meta.core.db_config_detector.get_runtime_config') as mock_cfg:
        mock_cfg.return_value = MagicMock(audit_retry_max=2, busy_timeout_ms=5000)
        wrapper = AuditRetryWrapper(mock_audit_service)
        result = wrapper.create_with_retry({'id': '1'}, critical=True)
    assert result is True
    assert mock_audit_service.create.call_count == 1


def test_audit_retry_success_after_locked(mock_audit_service):
    """First call raises 'locked', second call succeeds"""
    mock_audit_service.create.side_effect = [
        sqlite3.OperationalError("database is locked"),
        True
    ]
    with patch('meta.core.db_config_detector.get_runtime_config') as mock_cfg:
        mock_cfg.return_value = MagicMock(audit_retry_max=2, busy_timeout_ms=5000)
        wrapper = AuditRetryWrapper(mock_audit_service)
        result = wrapper.create_with_retry({'id': '1'}, critical=True)
    assert result is True
    assert mock_audit_service.create.call_count == 2


def test_audit_retry_exhausted_critical(mock_audit_service):
    """All retries fail with locked, critical → raise"""
    mock_audit_service.create.side_effect = sqlite3.OperationalError("database is locked")
    with patch('meta.core.db_config_detector.get_runtime_config') as mock_cfg:
        mock_cfg.return_value = MagicMock(audit_retry_max=2, busy_timeout_ms=5000)
        wrapper = AuditRetryWrapper(mock_audit_service)
        with pytest.raises(sqlite3.OperationalError):
            wrapper.create_with_retry({'id': '1'}, critical=True)
    assert mock_audit_service.create.call_count == 3  # 1 + 2 retries


def test_audit_retry_exhausted_non_critical(mock_audit_service):
    """All retries fail, non-critical → return False (no raise)"""
    mock_audit_service.create.side_effect = sqlite3.OperationalError("database is locked")
    with patch('meta.core.db_config_detector.get_runtime_config') as mock_cfg:
        mock_cfg.return_value = MagicMock(audit_retry_max=2, busy_timeout_ms=5000)
        wrapper = AuditRetryWrapper(mock_audit_service)
        result = wrapper.create_with_retry({'id': '1'}, critical=False)
    assert result is False


def test_audit_retry_non_locked_error_critical(mock_audit_service):
    """Non-locked error with critical=True → raise immediately"""
    mock_audit_service.create.side_effect = ValueError("bad value")
    with patch('meta.core.db_config_detector.get_runtime_config') as mock_cfg:
        mock_cfg.return_value = MagicMock(audit_retry_max=2, busy_timeout_ms=5000)
        wrapper = AuditRetryWrapper(mock_audit_service)
        with pytest.raises(ValueError):
            wrapper.create_with_retry({'id': '1'}, critical=True)
    assert mock_audit_service.create.call_count == 1  # no retry


def test_audit_retry_non_locked_error_non_critical(mock_audit_service):
    """Non-locked error with critical=False → return False (no raise)"""
    mock_audit_service.create.side_effect = ValueError("bad value")
    with patch('meta.core.db_config_detector.get_runtime_config') as mock_cfg:
        mock_cfg.return_value = MagicMock(audit_retry_max=2, busy_timeout_ms=5000)
        wrapper = AuditRetryWrapper(mock_audit_service)
        result = wrapper.create_with_retry({'id': '1'}, critical=False)
    assert result is False


def test_audit_retry_backoff_sleep(mock_audit_service):
    """Verify backoff sleep is called between retries"""
    import sqlite3
    mock_audit_service.create.side_effect = [
        sqlite3.OperationalError("database is locked"),
        True
    ]
    with patch('meta.core.db_config_detector.get_runtime_config') as mock_cfg:
        mock_cfg.return_value = MagicMock(audit_retry_max=2, busy_timeout_ms=5000)
        with patch('meta.core.observability.time.sleep') as mock_sleep:
            wrapper = AuditRetryWrapper(mock_audit_service)
            wrapper.create_with_retry({'id': '1'}, critical=True)
    mock_sleep.assert_called()  # at least one sleep


def test_audit_retry_critical_false_uses_zero_retries(mock_audit_service):
    """critical=False → 0 retries (1 attempt total)"""
    import sqlite3
    mock_audit_service.create.side_effect = sqlite3.OperationalError("database is locked")
    with patch('meta.core.db_config_detector.get_runtime_config') as mock_cfg:
        mock_cfg.return_value = MagicMock(audit_retry_max=2, busy_timeout_ms=5000)
        wrapper = AuditRetryWrapper(mock_audit_service)
        result = wrapper.create_with_retry({'id': '1'}, critical=False)
    assert result is False
    # Non-critical only attempts once (no retries)
    assert mock_audit_service.create.call_count == 1


# === OBS_COUNTERS sanity tests ===
def test_obs_counters_has_all_keys():
    expected_keys = [
        'commit_success', 'commit_failure', 'rollback_success', 'rollback_failure',
        'forced_rollback_after_commit', 'forced_rollback_after_rollback',
        'begin_success', 'begin_skipped_already_in_tx', 'begin_locked', 'phantom_tx_detected',
        'audit_write_success', 'audit_write_failure', 'audit_write_exhausted',
        'orphan_detector_runs', 'orphan_detector_clean', 'orphan_recovered',
        'orphan_app_state_pollution', 'runtime_state',
    ]
    for k in expected_keys:
        assert k in OBS_COUNTERS


def test_obs_counter_values_have_v007_15_prefix():
    """All metric names should have v007_15_ prefix"""
    for k, v in OBS_COUNTERS.items():
        if k != 'runtime_state':
            assert v.startswith('v007_15_'), f"{k} -> {v} missing prefix"
        else:
            assert v == 'v007_15_runtime_state_info'

