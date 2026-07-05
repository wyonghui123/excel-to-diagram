# -*- coding: utf-8 -*-
"""
[V007.15 L5] Tests for orphan_tx_detector
"""
import pytest
import sqlite3
import time
from unittest.mock import MagicMock, patch, PropertyMock
import sys
from pathlib import Path

# Add meta to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from meta.core.orphan_tx_detector import OrphanTxDetector
from meta.core.sqlite_tx_state import TxState


class FakeDataSource:
    """Test double - real conn + state attributes for manual control"""
    def __init__(self, conn):
        self._write_queue = MagicMock()
        self._write_queue._write_conn = conn
        self._in_transaction = False
        self.in_transaction = False


@pytest.fixture
def real_conn():
    c = sqlite3.connect(":memory:", timeout=5.0)
    yield c
    c.close()


@pytest.fixture
def mock_ds(real_conn):
    """Real conn wrapped in fake data source"""
    return FakeDataSource(real_conn)


@pytest.fixture(autouse=True)
def mock_config():
    """Default config: enabled, fast interval"""
    with patch('meta.core.orphan_tx_detector.get_runtime_config') as mock:
        mock.return_value = MagicMock(
            use_orphan_detector=True,
            orphan_check_interval_sec=0.1,
            deployment_state='A',
        )
        yield mock


# === Clean state tests ===
def test_detector_clean_state(mock_ds):
    """No orphan, app state matches SQLite state"""
    detector = OrphanTxDetector(mock_ds)
    detector._check_once()
    stats = detector.get_stats()
    assert stats['check_count'] == 1
    assert stats['recovery_count'] == 0
    assert stats['last_check_result'] == 'clean'


# === Orphan recovery tests ===
def test_detector_recovers_orphan(mock_ds, real_conn):
    """SQLite in tx, app says no → orphan, recover"""
    real_conn.execute("BEGIN IMMEDIATE")
    real_conn.execute("CREATE TABLE t1 (x INT)")
    real_conn.execute("INSERT INTO t1 VALUES (1)")
    mock_ds._in_transaction = False
    mock_ds.in_transaction = False

    detector = OrphanTxDetector(mock_ds)
    detector._check_once()

    stats = detector.get_stats()
    assert stats['recovery_count'] == 1
    assert stats['last_check_result'] == 'recovered'
    # Verify orphan was rolled back
    cur = real_conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='t1'")
    assert cur.fetchone()[0] == 0


def test_detector_recovers_orphan_with_data(mock_ds, real_conn):
    """Orphan with data should be fully rolled back"""
    real_conn.execute("BEGIN IMMEDIATE")
    real_conn.execute("CREATE TABLE t1 (id INT PRIMARY KEY, val TEXT)")
    real_conn.execute("INSERT INTO t1 VALUES (1, 'before')")

    detector = OrphanTxDetector(mock_ds)
    detector._check_once()

    # Data should be gone
    try:
        cur = real_conn.execute("SELECT val FROM t1 WHERE id=1")
        val = cur.fetchone()
        assert val is None
    except sqlite3.OperationalError:
        pass  # Table gone


# === App state pollution tests ===
def test_detector_resets_false_positive(mock_ds):
    """App says yes, SQLite says no → reset app state"""
    mock_ds._in_transaction = True
    mock_ds.in_transaction = True

    detector = OrphanTxDetector(mock_ds)
    detector._check_once()

    # App state should be reset
    assert mock_ds._in_transaction is False


# === Config tests ===
def test_detector_disabled_by_config(mock_ds):
    with patch('meta.core.orphan_tx_detector.get_runtime_config') as mock_cfg:
        mock_cfg.return_value = MagicMock(use_orphan_detector=False)
        detector = OrphanTxDetector(mock_ds)
        detector.start()
    assert detector._thread is None


def test_detector_start_stop(mock_ds):
    detector = OrphanTxDetector(mock_ds)
    detector.start()
    assert detector._thread is not None
    detector.stop()
    assert detector._stop is True


# === Stats tests ===
def test_detector_get_stats(mock_ds):
    detector = OrphanTxDetector(mock_ds)
    stats = detector.get_stats()
    for key in ['check_count', 'recovery_count', 'interval_sec',
                'deployment_state', 'last_check_ts', 'last_check_result']:
        assert key in stats


# === Multi-iteration tests ===
def test_detector_runs_multiple_times(mock_ds):
    detector = OrphanTxDetector(mock_ds)
    for _ in range(3):
        detector._check_once()
    stats = detector.get_stats()
    assert stats['check_count'] == 3


def test_detector_recovery_resets_app_state(mock_ds, real_conn):
    real_conn.execute("BEGIN IMMEDIATE")
    mock_ds._in_transaction = True  # Both say tx

    detector = OrphanTxDetector(mock_ds)
    detector._check_once()

    # Both should be reset
    assert mock_ds._in_transaction is False


# === No write_conn tests ===
def test_detector_no_write_conn():
    """No write_conn - should report no_write_conn"""
    ds = MagicMock()
    ds._write_queue = MagicMock()
    ds._write_queue._write_conn = None
    ds._connection = None
    detector = OrphanTxDetector(ds)
    detector._check_once()
    stats = detector.get_stats()
    assert stats['last_check_result'] == 'no_write_conn'


# === Error handling tests ===
def test_detector_handles_probe_error(mock_ds, real_conn):
    """Closed conn causes probe error - should not raise"""
    real_conn.close()  # closed conn causes probe error
    detector = OrphanTxDetector(mock_ds)
    detector._check_once()  # Should not raise
    stats = detector.get_stats()
    # Should not raise
    assert 'error' in stats['last_check_result'] or stats['last_check_result'] == 'no_write_conn' or stats['last_check_result'] == 'probe_error: ...'


# === Metrics tests ===
def test_detector_emits_metrics(mock_ds):
    detector = OrphanTxDetector(mock_ds)
    with patch('meta.core.orphan_tx_detector.metrics_inc') as mock_metrics:
        detector._check_once()
    assert any(call.args[0] == 'orphan_detector_runs' for call in mock_metrics.call_args_list)
    assert any(call.args[0] == 'orphan_detector_clean' for call in mock_metrics.call_args_list)


def test_detector_recovery_emits_metric(mock_ds, real_conn):
    real_conn.execute("BEGIN IMMEDIATE")
    mock_ds._in_transaction = False
    detector = OrphanTxDetector(mock_ds)
    with patch('meta.core.orphan_tx_detector.metrics_inc') as mock_metrics:
        detector._check_once()
    assert any(call.args[0] == 'orphan_recovered' for call in mock_metrics.call_args_list)


def test_detector_app_state_pollution_emits_metric(mock_ds):
    mock_ds._in_transaction = True
    mock_ds.in_transaction = True
    detector = OrphanTxDetector(mock_ds)
    with patch('meta.core.orphan_tx_detector.metrics_inc') as mock_metrics:
        detector._check_once()
    assert any(call.args[0] == 'orphan_app_state_pollution' for call in mock_metrics.call_args_list)


# === Healthz format test ===
def test_detector_healthz_format(mock_ds):
    detector = OrphanTxDetector(mock_ds)
    detector._check_count = 100
    detector._recovery_count = 5
    stats = detector.get_stats()
    assert stats['check_count'] == 100
    assert stats['recovery_count'] == 5
    assert stats['interval_sec'] == 0.1
    assert stats['deployment_state'] == 'A'
