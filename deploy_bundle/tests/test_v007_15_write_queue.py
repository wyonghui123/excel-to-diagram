# -*- coding: utf-8 -*-
"""
[V007.15 L3] Tests for sql_write_queue begin_transaction phantom detection
"""
import pytest
import sqlite3
import time
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# Add meta to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from meta.core.sql_write_queue import WriteQueue
from meta.core.sqlite_tx_state import TxState


def test_phantom_tx_detection():
    """SQLite in tx, Python state False → phantom, force ROLLBACK"""
    conn = sqlite3.connect(":memory:")
    conn.execute("BEGIN IMMEDIATE")

    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = False

    def mock_submit(fn):
        fn(conn)
    wq.submit_and_wait = mock_submit

    # Mock get_tx_state to return WRITE (phantom)
    with patch('meta.core.sql_write_queue.get_tx_state', return_value=TxState.WRITE):
        wq.begin_transaction()

    # After phantom recovery: ROLLBACK + new BEGIN, in_transaction=True
    assert wq._in_transaction is True
    conn.close()


def test_normal_begin_when_no_tx():
    """SQLite no tx, Python state False → normal BEGIN"""
    conn = sqlite3.connect(":memory:")
    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = False

    def mock_submit(fn):
        fn(conn)
    wq.submit_and_wait = mock_submit

    with patch('meta.core.sql_write_queue.get_tx_state', return_value=TxState.NONE):
        wq.begin_transaction()
    assert wq._in_transaction is True
    conn.execute("ROLLBACK")
    conn.close()


def test_begin_skipped_when_already_in_tx():
    """Python state True → skip begin entirely"""
    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = True
    called = []
    wq.submit_and_wait = lambda fn: called.append(True)
    wq.begin_transaction()
    assert len(called) == 0  # Skipped


def test_phantom_tx_emits_metric():
    """Phantom TX detection should emit phantom_tx_detected counter"""
    conn = sqlite3.connect(":memory:")
    conn.execute("BEGIN IMMEDIATE")
    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = False
    wq.submit_and_wait = lambda fn: fn(conn)

    with patch('meta.core.sql_write_queue.metrics_inc') as mock_metrics:
        with patch('meta.core.sql_write_queue.get_tx_state', return_value=TxState.WRITE):
            wq.begin_transaction()

    assert any(call.args[0] == 'phantom_tx_detected' for call in mock_metrics.call_args_list)
    conn.execute("ROLLBACK")
    conn.close()


def test_normal_begin_emits_success_metric():
    """Normal begin should emit begin_success counter"""
    conn = sqlite3.connect(":memory:")
    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = False
    wq.submit_and_wait = lambda fn: fn(conn)

    with patch('meta.core.sql_write_queue.metrics_inc') as mock_metrics:
        with patch('meta.core.sql_write_queue.get_tx_state', return_value=TxState.NONE):
            wq.begin_transaction()

    assert any(call.args[0] == 'begin_success' for call in mock_metrics.call_args_list)
    conn.execute("ROLLBACK")
    conn.close()


def test_skipped_begin_emits_metric():
    """Skipped begin (already in tx) should emit begin_skipped_already_in_tx"""
    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = True

    with patch('meta.core.sql_write_queue.metrics_inc') as mock_metrics:
        wq.begin_transaction()

    assert any(call.args[0] == 'begin_skipped_already_in_tx' for call in mock_metrics.call_args_list)


def test_unknown_tx_state_continues_to_begin():
    """UNKNOWN state should not block, just proceed"""
    conn = sqlite3.connect(":memory:")
    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = False
    wq.submit_and_wait = lambda fn: fn(conn)

    with patch('meta.core.sql_write_queue.get_tx_state', return_value=TxState.UNKNOWN):
        wq.begin_transaction()
    # Should still proceed with BEGIN
    assert wq._in_transaction is True
    conn.execute("ROLLBACK")
    conn.close()


def test_phantom_detection_increments_counter_only_once():
    """Each phantom detection should emit exactly one metric"""
    conn = sqlite3.connect(":memory:")
    conn.execute("BEGIN IMMEDIATE")
    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = False
    wq.submit_and_wait = lambda fn: fn(conn)

    with patch('meta.core.sql_write_queue.metrics_inc') as mock_metrics:
        with patch('meta.core.sql_write_queue.get_tx_state', return_value=TxState.WRITE):
            wq.begin_transaction()

    phantom_calls = [c for c in mock_metrics.call_args_list if c.args and c.args[0] == 'phantom_tx_detected']
    assert len(phantom_calls) == 1
    conn.execute("ROLLBACK")
    conn.close()


def test_state_none_normal_flow():
    """Verify normal flow: probe NONE → BEGIN → state True"""
    conn = sqlite3.connect(":memory:")
    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = False
    wq.submit_and_wait = lambda fn: fn(conn)

    with patch('meta.core.sql_write_queue.get_tx_state', return_value=TxState.NONE):
        wq.begin_transaction()
    assert wq._in_transaction is True
    conn.execute("ROLLBACK")
    conn.close()


def test_state_write_phantom_flow():
    """Verify phantom flow: probe WRITE → ROLLBACK → BEGIN → state True"""
    conn = sqlite3.connect(":memory:")
    conn.execute("BEGIN IMMEDIATE")  # Create phantom
    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = False
    wq.submit_and_wait = lambda fn: fn(conn)

    with patch('meta.core.sql_write_queue.get_tx_state', return_value=TxState.WRITE):
        wq.begin_transaction()
    # After phantom recovery, _in_transaction should be True
    assert wq._in_transaction is True
    conn.close()


def test_log_warning_on_phantom():
    """Phantom TX detection should log warning"""
    conn = sqlite3.connect(":memory:")
    conn.execute("BEGIN IMMEDIATE")
    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = False
    wq.submit_and_wait = lambda fn: fn(conn)

    with patch('meta.core.sql_write_queue.logger') as mock_logger:
        with patch('meta.core.sql_write_queue.get_tx_state', return_value=TxState.WRITE):
            wq.begin_transaction()

    assert mock_logger.warning.called
    conn.execute("ROLLBACK")
    conn.close()


def test_real_integration_no_mock():
    """Real begin_transaction with real conn (no mocks)"""
    conn = sqlite3.connect(":memory:")
    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = False
    wq.submit_and_wait = lambda fn: fn(conn)

    # First call: should do real BEGIN
    wq.begin_transaction()
    assert wq._in_transaction is True

    # Second call: should skip (already in tx)
    with patch('meta.core.sql_write_queue.metrics_inc') as mock_metrics:
        wq.begin_transaction()
    assert any(call.args[0] == 'begin_skipped_already_in_tx' for call in mock_metrics.call_args_list)

    conn.execute("ROLLBACK")
    conn.close()
