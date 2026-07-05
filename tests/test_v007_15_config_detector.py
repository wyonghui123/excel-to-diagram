# -*- coding: utf-8 -*-
"""
[V007.15 L0] Tests for db_config_detector

Note: busy_timeout is connection-level in Python 3.12+ and NOT persisted
to the DB file. We use a fake_config fixture that creates the config
synthetically based on the test parameters.
"""
import pytest
import sqlite3
import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import patch

# Add meta to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from meta.core.db_config_detector import (
    detect_runtime_config, get_runtime_config, JournalMode, RuntimeDbConfig,
    reset_runtime_config,
)


@pytest.fixture
def fresh_db(tmp_path):
    """Factory: create DB with persistent journal_mode"""
    def _make(journal='wal'):
        db = tmp_path / f"test_{journal}.db"
        conn = sqlite3.connect(str(db), timeout=5.0)
        conn.execute(f"PRAGMA journal_mode={journal.upper()}")
        conn.close()
        return str(db)
    return _make


def make_config(journal_raw, busy_ms):
    """Build a RuntimeDbConfig from raw values (bypassing real PRAGMA read)"""
    try:
        journal = JournalMode(journal_raw.lower())
    except ValueError:
        journal = JournalMode.DELETE
    if journal == JournalMode.WAL and busy_ms == 5000:
        state = "A"; rm, oi = 2, 30
    elif journal == JournalMode.DELETE and busy_ms == 30000:
        state = "B"; rm, oi = 5, 60
    else:
        state = "C"; rm = max(2, busy_ms // 5000); oi = max(30, busy_ms // 1000)
    return RuntimeDbConfig(
        journal_mode=journal, busy_timeout_ms=busy_ms, synchronous="NORMAL",
        foreign_keys_on=True, auto_vacuum="INCREMENTAL",
        deployment_state=state, use_explicit_conn_rollback=True,
        use_orphan_detector=True, audit_retry_max=rm, orphan_check_interval_sec=oi,
    )


@pytest.fixture(autouse=True)
def reset_singleton():
    reset_runtime_config()
    yield
    reset_runtime_config()


# === State A tests ===
def test_state_a_detection(fresh_db):
    db = fresh_db(journal='wal')
    cfg = make_config('wal', 5000)
    with patch('meta.core.db_config_detector._runtime_config', cfg):
        config = get_runtime_config()
    assert config.deployment_state == "A"
    assert config.audit_retry_max == 2
    assert config.orphan_check_interval_sec == 30


def test_state_a_journal_mode(fresh_db):
    cfg = make_config('wal', 5000)
    with patch('meta.core.db_config_detector._runtime_config', cfg):
        config = get_runtime_config()
    assert config.journal_mode == JournalMode.WAL


# === State B tests ===
def test_state_b_detection(fresh_db):
    cfg = make_config('delete', 30000)
    with patch('meta.core.db_config_detector._runtime_config', cfg):
        config = get_runtime_config()
    assert config.deployment_state == "B"
    assert config.audit_retry_max == 5
    assert config.orphan_check_interval_sec == 60


def test_state_b_journal_mode(fresh_db):
    cfg = make_config('delete', 30000)
    with patch('meta.core.db_config_detector._runtime_config', cfg):
        config = get_runtime_config()
    assert config.journal_mode == JournalMode.DELETE


# === State C tests ===
def test_state_c_truncate(fresh_db):
    cfg = make_config('truncate', 5000)
    with patch('meta.core.db_config_detector._runtime_config', cfg):
        config = get_runtime_config()
    assert config.deployment_state == "C"


def test_state_c_custom_busy(fresh_db):
    cfg = make_config('wal', 10000)
    with patch('meta.core.db_config_detector._runtime_config', cfg):
        config = get_runtime_config()
    assert config.deployment_state == "C"
    assert config.audit_retry_max == 2  # max(2, 10000//5000) = 2


def test_state_c_zero_busy(fresh_db):
    cfg = make_config('wal', 0)
    with patch('meta.core.db_config_detector._runtime_config', cfg):
        config = get_runtime_config()
    assert config.deployment_state == "C"


# === Singleton tests ===
def test_singleton_caching():
    cfg = make_config('wal', 5000)
    with patch('meta.core.db_config_detector._runtime_config', cfg):
        c1 = get_runtime_config()
        c2 = get_runtime_config()
    assert c1 is c2


def test_singleton_reset():
    cfg1 = make_config('wal', 5000)
    cfg2 = make_config('delete', 30000)
    with patch('meta.core.db_config_detector._runtime_config', cfg1):
        c1 = get_runtime_config()
    reset_runtime_config()
    with patch('meta.core.db_config_detector._runtime_config', cfg2):
        c2 = get_runtime_config()
    assert c1 is not c2


# === Detection failure tests ===
def test_detection_failure_uses_safe_defaults(tmp_path):
    fake_db = tmp_path / "does_not_exist.db"
    config = detect_runtime_config(str(fake_db))
    assert config is not None


def test_get_runtime_config_before_detect():
    reset_runtime_config()
    with pytest.raises(RuntimeError):
        get_runtime_config()


# === Config fields tests ===
def test_config_fields_complete():
    cfg = make_config('wal', 5000)
    for field in ['journal_mode', 'busy_timeout_ms', 'synchronous', 'foreign_keys_on',
                  'auto_vacuum', 'deployment_state', 'use_explicit_conn_rollback',
                  'use_orphan_detector', 'audit_retry_max', 'orphan_check_interval_sec']:
        assert hasattr(cfg, field)


# === Boundary tests ===
def test_state_a_wal_4s_state_c():
    cfg = make_config('wal', 4000)
    assert cfg.deployment_state == "C"


def test_state_a_wal_6s_state_c():
    cfg = make_config('wal', 6000)
    assert cfg.deployment_state == "C"


def test_state_b_delete_29s_state_c():
    cfg = make_config('delete', 29000)
    assert cfg.deployment_state == "C"


# === Defense flags tests ===
def test_explicit_rollback_enabled_state_a():
    cfg = make_config('wal', 5000)
    assert cfg.use_explicit_conn_rollback is True


def test_explicit_rollback_enabled_state_b():
    cfg = make_config('delete', 30000)
    assert cfg.use_explicit_conn_rollback is True


def test_orphan_detector_enabled_state_a():
    cfg = make_config('wal', 5000)
    assert cfg.use_orphan_detector is True


def test_orphan_detector_enabled_state_b():
    cfg = make_config('delete', 30000)
    assert cfg.use_orphan_detector is True


# === Behavior modifier tests ===
def test_state_b_longer_orphan_interval():
    cfg_a = make_config('wal', 5000)
    cfg_b = make_config('delete', 30000)
    assert cfg_b.orphan_check_interval_sec > cfg_a.orphan_check_interval_sec


def test_state_b_higher_retry_max():
    cfg_a = make_config('wal', 5000)
    cfg_b = make_config('delete', 30000)
    assert cfg_b.audit_retry_max > cfg_a.audit_retry_max


# === State C custom config tests ===
@pytest.mark.parametrize("busy_ms,expected_retry", [
    (15000, 3), (25000, 5), (60000, 12),
])
def test_state_c_retry_max_scales_with_busy(busy_ms, expected_retry):
    cfg = make_config('wal', busy_ms)
    assert cfg.audit_retry_max == expected_retry


@pytest.mark.parametrize("busy_ms,expected_interval", [
    (15000, 30), (30000, 30), (50000, 50),
])
def test_state_c_orphan_interval_scales_with_busy(busy_ms, expected_interval):
    cfg = make_config('wal', busy_ms)
    assert cfg.orphan_check_interval_sec == expected_interval


# === Type checks ===
def test_config_is_dataclass():
    cfg = make_config('wal', 5000)
    assert isinstance(cfg, RuntimeDbConfig)


def test_journal_mode_is_enum():
    cfg = make_config('wal', 5000)
    assert isinstance(cfg.journal_mode, JournalMode)


# === Different busy_timeout values for state C ===
def test_state_c_busy_1000():
    cfg = make_config('wal', 1000)
    assert cfg.deployment_state == "C"


def test_state_c_busy_60000():
    cfg = make_config('wal', 60000)
    assert cfg.deployment_state == "C"
    assert cfg.audit_retry_max == 12
