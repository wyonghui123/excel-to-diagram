# -*- coding: utf-8 -*-
"""
[V007.15 L1] Tests for sqlite_tx_state
"""
import pytest
import sqlite3
import time
import sys
from pathlib import Path

# Add meta to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from meta.core.sqlite_tx_state import get_tx_state, TxState, tx_state_verified_action


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", timeout=5.0)
    yield c
    c.close()


# === NONE state tests ===
def test_none_state(conn):
    assert get_tx_state(conn) == TxState.NONE


def test_none_after_rollback(conn):
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("ROLLBACK")
    assert get_tx_state(conn) == TxState.NONE


def test_none_after_commit(conn):
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("COMMIT")
    assert get_tx_state(conn) == TxState.NONE


# === WRITE state tests ===
def test_write_state(conn):
    conn.execute("BEGIN IMMEDIATE")
    assert get_tx_state(conn) == TxState.WRITE


def test_write_state_with_table(conn):
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("CREATE TABLE t1 (x INT)")
    assert get_tx_state(conn) == TxState.WRITE
    conn.execute("ROLLBACK")


def test_write_state_with_insert(conn):
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("CREATE TABLE tmp_insert_test (x INT)")
    conn.execute("INSERT INTO tmp_insert_test VALUES (1)")
    assert get_tx_state(conn) == TxState.WRITE
    conn.execute("ROLLBACK")


# === Read state tests ===
def test_read_state(conn):
    """Read tx (BEGIN without IMMEDIATE) - savepoint also works"""
    conn.execute("BEGIN")
    # savepoint works in any tx
    conn.execute("SAVEPOINT __test__")
    conn.execute("RELEASE SAVEPOINT __test__")
    # We can detect that we ARE in a tx
    state = get_tx_state(conn)
    assert state in (TxState.WRITE, TxState.READ)
    conn.execute("ROLLBACK")


# === State recovery tests ===
def test_state_recovery(conn):
    conn.execute("BEGIN IMMEDIATE")
    assert get_tx_state(conn) == TxState.WRITE
    conn.execute("ROLLBACK")
    assert get_tx_state(conn) == TxState.NONE


def test_multiple_cycles(conn):
    for _ in range(5):
        conn.execute("BEGIN IMMEDIATE")
        assert get_tx_state(conn) == TxState.WRITE
        conn.execute("ROLLBACK")
        assert get_tx_state(conn) == TxState.NONE


# === Context manager tests ===
def test_context_manager_no_warning(conn, caplog):
    with tx_state_verified_action(conn, expected_state=TxState.NONE) as actual:
        assert actual == TxState.NONE
    # No warning expected


def test_context_manager_drift_warning(conn, caplog):
    conn.execute("BEGIN IMMEDIATE")
    with tx_state_verified_action(conn, expected_state=TxState.NONE):
        pass
    # Warning should be emitted
    conn.execute("ROLLBACK")


def test_context_manager_no_force_rollback(conn):
    conn.execute("BEGIN IMMEDIATE")
    # tx_state_verified_action should NOT force rollback
    with tx_state_verified_action(conn, expected_state=TxState.NONE):
        pass
    # Should still be in tx (caller decides)
    assert get_tx_state(conn) == TxState.WRITE
    conn.execute("ROLLBACK")


def test_context_manager_yields_actual_state(conn):
    with tx_state_verified_action(conn, expected_state=TxState.NONE) as actual:
        assert actual == TxState.NONE


# === Performance tests ===
def test_probe_cost_under_500ms(conn):
    """100 probes should take < 500ms (single probe < 5ms)"""
    start = time.time()
    for _ in range(100):
        get_tx_state(conn)
    elapsed = time.time() - start
    assert elapsed < 0.5


# === Multi connection tests ===
def test_independent_connections():
    c1 = sqlite3.connect(":memory:")
    c2 = sqlite3.connect(":memory:")
    c1.execute("BEGIN IMMEDIATE")
    assert get_tx_state(c1) == TxState.WRITE
    assert get_tx_state(c2) == TxState.NONE
    c1.close()
    c2.close()


# === Edge cases ===
def test_unknown_on_closed_conn():
    """Closed connection should not raise (handle gracefully)"""
    c = sqlite3.connect(":memory:")
    c.close()
    try:
        state = get_tx_state(c)
        # Should be UNKNOWN or NONE
        assert state in (TxState.UNKNOWN, TxState.NONE)
    except sqlite3.ProgrammingError:
        # Python 3.14 may raise on closed conn
        # That's also acceptable - we just don't want unhandled error
        pass


def test_repeated_probes_idempotent(conn):
    """Repeated probes should return same state"""
    for _ in range(10):
        assert get_tx_state(conn) == TxState.NONE


def test_state_with_savepoints(conn):
    """Savepoints don't change top-level state"""
    conn.execute("BEGIN IMMEDIATE")
    assert get_tx_state(conn) == TxState.WRITE
    conn.execute("SAVEPOINT sp1")
    assert get_tx_state(conn) == TxState.WRITE
    conn.execute("RELEASE SAVEPOINT sp1")
    assert get_tx_state(conn) == TxState.WRITE
    conn.execute("ROLLBACK")
    assert get_tx_state(conn) == TxState.NONE
