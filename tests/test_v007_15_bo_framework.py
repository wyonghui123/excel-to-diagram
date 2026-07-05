# -*- coding: utf-8 -*-
"""
[V007.15 L2] Tests for bo_framework.commit/rollback state-aware defense
"""
import pytest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# Add meta to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from meta.core.bo_framework import BOFramework
from meta.core.sqlite_tx_state import TxState


@pytest.fixture
def mock_ds():
    ds = MagicMock()
    ds._in_transaction = False
    ds._write_queue = MagicMock()
    ds._write_queue._in_transaction = False
    ds._write_queue._write_conn = MagicMock()
    return ds


@pytest.fixture
def bo_framework(mock_ds):
    bf = BOFramework.__new__(BOFramework)  # skip __init__
    bf._data_source = mock_ds
    return bf


@pytest.fixture(autouse=True)
def mock_config():
    """Default config mock"""
    with patch('meta.core.bo_framework.get_runtime_config') as mock:
        mock.return_value = MagicMock(
            use_explicit_conn_rollback=True,
            audit_retry_max=2,
            orphan_check_interval_sec=30,
            deployment_state='A',
        )
        yield mock


# === Commit success ===
def test_commit_success_resets_state(bo_framework, mock_ds):
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.commit()
    assert result is True
    assert mock_ds._in_transaction is False
    assert mock_ds._write_queue._in_transaction is False


def test_commit_failure_still_resets_state(bo_framework, mock_ds):
    """Commit failure must still reset state via finally"""
    mock_ds.commit.side_effect = Exception("disk full")
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.commit()
    assert result is False
    # CRITICAL: state must be reset even on failure
    assert mock_ds._in_transaction is False
    assert mock_ds._write_queue._in_transaction is False


def test_commit_forced_rollback_when_state_drift(bo_framework, mock_ds):
    """If commit 'succeeds' but conn still in tx → force ROLLBACK"""
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.WRITE):
        result = bo_framework.commit()
    # Should force ROLLBACK
    mock_ds._write_queue._write_conn.execute.assert_called_with("ROLLBACK")


# === Rollback ===
def test_rollback_success_resets_state(bo_framework, mock_ds):
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.rollback()
    assert result is True
    assert mock_ds._in_transaction is False


def test_rollback_failure_still_resets_state(bo_framework, mock_ds):
    """Rollback failure must still reset state"""
    mock_ds.rollback.side_effect = Exception("disk full")
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.rollback()
    assert result is False
    assert mock_ds._in_transaction is False


def test_rollback_forced_rollback(bo_framework, mock_ds):
    """If rollback 'succeeds' but conn still in tx → force ROLLBACK"""
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.WRITE):
        result = bo_framework.rollback()
    mock_ds._write_queue._write_conn.execute.assert_called_with("ROLLBACK")


# === State-aware behavior ===
def test_explicit_rollback_disabled(bo_framework, mock_ds):
    """If config.use_explicit_conn_rollback=False, skip direct conn.rollback()"""
    with patch('meta.core.bo_framework.get_runtime_config') as mock_cfg:
        mock_cfg.return_value = MagicMock(use_explicit_conn_rollback=False)
        with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.WRITE):
            bo_framework.rollback()
    # Should NOT have called conn.rollback directly
    mock_ds._write_queue._write_conn.rollback.assert_not_called()


# === Defensive cases ===
def test_commit_no_write_queue(bo_framework, mock_ds):
    """No write_queue should not crash"""
    mock_ds._write_queue = None
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.commit()
    assert result is True
    assert mock_ds._in_transaction is False


def test_commit_no_write_conn(bo_framework, mock_ds):
    """No write_conn should not crash"""
    mock_ds._write_queue._write_conn = None
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.commit()
    assert result is True


def test_rollback_no_write_queue(bo_framework, mock_ds):
    mock_ds._write_queue = None
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.rollback()
    assert result is True
    assert mock_ds._in_transaction is False


# === Observability ===
def test_commit_emits_success_metrics(bo_framework, mock_ds):
    with patch('meta.core.bo_framework.metrics_inc') as mock_metrics:
        with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
            bo_framework.commit()
    # Should have called metrics_inc with commit_success
    assert any(call.args[0] == 'commit_success' for call in mock_metrics.call_args_list)


def test_commit_failure_emits_failure_metric(bo_framework, mock_ds):
    mock_ds.commit.side_effect = Exception("disk full")
    with patch('meta.core.bo_framework.metrics_inc') as mock_metrics:
        with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
            bo_framework.commit()
    assert any(call.args[0] == 'commit_failure' for call in mock_metrics.call_args_list)


def test_rollback_emits_success_metrics(bo_framework, mock_ds):
    with patch('meta.core.bo_framework.metrics_inc') as mock_metrics:
        with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
            bo_framework.rollback()
    assert any(call.args[0] == 'rollback_success' for call in mock_metrics.call_args_list)


def test_rollback_failure_emits_metric(bo_framework, mock_ds):
    mock_ds.rollback.side_effect = Exception("disk full")
    with patch('meta.core.bo_framework.metrics_inc') as mock_metrics:
        with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
            bo_framework.rollback()
    assert any(call.args[0] == 'rollback_failure' for call in mock_metrics.call_args_list)


def test_forced_rollback_emits_metric(bo_framework, mock_ds):
    with patch('meta.core.bo_framework.metrics_inc') as mock_metrics:
        with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.WRITE):
            bo_framework.commit()
    assert any(call.args[0] == 'forced_rollback_after_commit' for call in mock_metrics.call_args_list)


def test_forced_rollback_after_rollback_emits_metric(bo_framework, mock_ds):
    with patch('meta.core.bo_framework.metrics_inc') as mock_metrics:
        with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.WRITE):
            bo_framework.rollback()
    assert any(call.args[0] == 'forced_rollback_after_rollback' for call in mock_metrics.call_args_list)


# === Logging ===
def test_commit_logs_event(bo_framework, mock_ds):
    with patch('meta.core.bo_framework.log_tx_event') as mock_log:
        with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
            bo_framework.commit()
    # Should call log_tx_event with status='ok'
    assert any(call.args[2] == 'ok' for call in mock_log.call_args_list)


def test_commit_failure_logs_error(bo_framework, mock_ds):
    mock_ds.commit.side_effect = Exception("boom")
    with patch('meta.core.bo_framework.log_tx_event') as mock_log:
        with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
            bo_framework.commit()
    # Should call log_tx_event with status='error'
    assert any(call.args[2] == 'error' for call in mock_log.call_args_list)


# === Stress ===
def test_commit_rollback_alternating(bo_framework, mock_ds):
    for _ in range(20):
        with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
            bo_framework.commit()
        with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
            bo_framework.rollback()
    # No state leak
    assert mock_ds._in_transaction is False


# === No data_source.commit ===
def test_no_commit_method(bo_framework, mock_ds):
    """If data_source has no commit, should return True (no-op)"""
    del mock_ds.commit
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.commit()
    assert result is True


# === transaction_id param ===
def test_commit_with_transaction_id(bo_framework, mock_ds):
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.commit(transaction_id="test-tx-123")
    assert result is True
    # Should not crash with transaction_id
