"""
[2026-09-18 P1-2] 测试 prod history 两步写策略.

策略:
  - upload OK → _record_prod_deploy(stamp, status='PENDING_VERIFY')
  - deploy 完成 → _update_prod_history(stamp, status='OK', ...)
  - 中途 abort → _update_prod_history(stamp, status='FAIL_RESTART'/'FAIL_VERIFY')

防回归: 即使 abort, stamp 仍存在, 操作者可定位 + 用 prod-rollback 回滚.
"""
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools'))
import staging_round as sr  # noqa: E402


def _fresh_history(tmp_path):
    """重定向 PROD_HISTORY 到 tmp_path, 让每个测试隔离."""
    h = tmp_path / 'prod_history.json'
    sr.PROD_HISTORY = h
    return h


def test_two_step_pending_then_ok(tmp_path):
    """正常路径: PENDING → OK."""
    h = _fresh_history(tmp_path)

    # 1. upload OK 写 PENDING
    sr._record_prod_deploy({
        'stamp': 'prod_20260918_120000_abc1234',
        'status': 'PENDING_VERIFY',
        'files': ['meta/schemas/role.yaml'],
    })
    entries = json.loads(h.read_text())['entries']
    assert len(entries) == 1
    assert entries[0]['status'] == 'PENDING_VERIFY'

    # 2. deploy 完成 update OK
    ok = sr._update_prod_history(entries[0]['stamp'], status='OK',
                                  service_active_after=True, port_listen=True,
                                  introspect_ok=True, endpoints=[])
    assert ok is True
    entries = json.loads(h.read_text())['entries']
    assert len(entries) == 1, 'update 不应 append 新条目'
    assert entries[0]['status'] == 'OK'
    assert entries[0]['service_active_after'] is True
    assert entries[0]['port_listen'] is True


def test_two_step_pending_then_fail_restart(tmp_path):
    """abort 在 step 6 restart grace: PENDING → FAIL_RESTART."""
    h = _fresh_history(tmp_path)

    sr._record_prod_deploy({'stamp': 'prod_test_fail_restart', 'status': 'PENDING_VERIFY'})
    ok = sr._update_prod_history('prod_test_fail_restart', status='FAIL_RESTART',
                                  service_active_after=False, port_listen=False)
    assert ok is True
    e = json.loads(h.read_text())['entries'][0]
    assert e['status'] == 'FAIL_RESTART'
    assert e['service_active_after'] is False


def test_two_step_pending_then_fail_verify(tmp_path):
    """abort 在 step 7 verify: PENDING → FAIL_VERIFY."""
    h = _fresh_history(tmp_path)

    sr._record_prod_deploy({'stamp': 'prod_test_fail_verify', 'status': 'PENDING_VERIFY'})
    ok = sr._update_prod_history('prod_test_fail_verify', status='FAIL_VERIFY',
                                  endpoints=[{'error': True, 'path': '/api/v1/x', 'stage': 'probe'}])
    assert ok is True
    e = json.loads(h.read_text())['entries'][0]
    assert e['status'] == 'FAIL_VERIFY'
    assert e['endpoints'][0]['error'] is True


def test_update_missing_stamp_no_throw(tmp_path):
    """update 不存在的 stamp → return False, 不抛错."""
    h = _fresh_history(tmp_path)
    sr._record_prod_deploy({'stamp': 'prod_a', 'status': 'PENDING_VERIFY'})

    ok = sr._update_prod_history('prod_nonexistent', status='OK')
    assert ok is False
    # PENDING 仍在
    e = json.loads(h.read_text())['entries'][0]
    assert e['stamp'] == 'prod_a'
    assert e['status'] == 'PENDING_VERIFY'


def test_history_capacity_truncation(tmp_path):
    """30 条上限."""
    _fresh_history(tmp_path)
    for i in range(35):
        sr._record_prod_deploy({'stamp': f'prod_{i}', 'status': 'OK'})
    h = sr.PROD_HISTORY
    entries = json.loads(h.read_text())['entries']
    assert len(entries) == 30, f'expected 30 cap, got {len(entries)}'
    # 只保留最后 30 条 (idx 5..34)
    assert entries[0]['stamp'] == 'prod_5'
    assert entries[-1]['stamp'] == 'prod_34'


def test_history_keeps_pending_after_fail(tmp_path):
    """abort 后 stamp 仍存在 (这是两步写的核心价值)."""
    h = _fresh_history(tmp_path)
    sr._record_prod_deploy({'stamp': 'prod_x', 'status': 'PENDING_VERIFY',
                            'files': ['a.py'], 'db_backup': '/tmp/x.bak'})
    sr._update_prod_history('prod_x', status='FAIL_RESTART')

    e = json.loads(h.read_text())['entries'][0]
    assert e['stamp'] == 'prod_x'
    assert e['files'] == ['a.py']
    assert e['db_backup'] == '/tmp/x.bak'
    assert e['status'] == 'FAIL_RESTART'


if __name__ == '__main__':
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        test_two_step_pending_then_ok(Path(t))
    with tempfile.TemporaryDirectory() as t:
        test_two_step_pending_then_fail_restart(Path(t))
    with tempfile.TemporaryDirectory() as t:
        test_two_step_pending_then_fail_verify(Path(t))
    with tempfile.TemporaryDirectory() as t:
        test_update_missing_stamp_no_throw(Path(t))
    with tempfile.TemporaryDirectory() as t:
        test_history_capacity_truncation(Path(t))
    with tempfile.TemporaryDirectory() as t:
        test_history_keeps_pending_after_fail(Path(t))
    print('OK: 6/6 history two-step tests passed')