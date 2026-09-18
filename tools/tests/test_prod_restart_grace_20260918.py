"""
[2026-09-18 P0-1] 测试 prod restart grace + 3 次重试, 防止 false-negative 误 abort.

bug: 2026-09-18 prod 部署 role.yaml 后, restart 实际成功 (service active=true, port 5001 LISTEN),
但脚本 sleep 2s + 一次探活捕到 NOT LISTEN → [ABORT] → history 丢失.
fix: 8s grace + 3 次探活 (中间 sleep 1s).

测 3 个场景:
  1. service/port 都 false → 第 1 次 grace 后仍 false → 重试 1.5s → 第 2 次成功
  2. service/port 都 true → 第 1 次探活即成功, 不需要重试
  3. service/port 一直 false → 3 次后 abort

抽走 cmd_prod_deploy 的 step 6 grace 循环, mock _check_prod_service_active / _check_prod_port_listen
"""
import sys
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools'))
import staging_round as sr  # noqa: E402


def _graced_probe(sleep_s, check_active, check_port, sleep_fn=None):
    """[2026-09-18] 提取 cmd_prod_deploy step 6 grace 循环逻辑, 便于测."""
    GRACE_SECONDS = 8
    PROBE_RETRY_MAX = 3
    sleep_fn = sleep_fn or (lambda _s: None)  # 默认 fake sleep (不阻塞)

    sleep_s.append(GRACE_SECONDS)
    service_ok = False
    port_ok = False
    service_info = ''
    port_info = ''
    for attempt in range(1, PROBE_RETRY_MAX + 1):
        service_ok, service_info = check_active()
        port_ok, port_info = check_port()
        if service_ok and port_ok:
            return service_ok, port_ok, service_info, port_info, attempt
        if attempt < PROBE_RETRY_MAX:
            sleep_s.append(1.0)
            sleep_fn(1.0)
    return service_ok, port_ok, service_info, port_info, PROBE_RETRY_MAX


def test_grace_recovers_from_false_negative():
    """场景 1: 第 1 次探活 false (systemd 还在拉), 第 2 次 true."""
    sleep_s = []
    # 序列: (active, port)
    seq = [(False, False, 'inactive', 'no LISTEN'),
           (True, True, 'active', '*:5001')]
    idx = [0]

    def check_active():
        a = seq[idx[0]]; idx[0] += 1; return a[0], a[2]

    def check_port():
        a = seq[idx[0] - 1]; return a[1], a[3]

    s_ok, p_ok, s_info, p_info, attempts = _graced_probe(sleep_s, check_active, check_port)
    assert s_ok is True and p_ok is True, f'expected both ok, got s={s_ok} p={p_ok}'
    assert attempts == 2, f'expected 2 attempts (1 false + 1 true), got {attempts}'
    assert sleep_s == [8.0, 1.0], f'expected [8.0 grace, 1.0 retry], got {sleep_s}'


def test_grace_first_probe_success():
    """场景 2: 第 1 次就 true (正常路径, 启动快)."""
    sleep_s = []
    s_ok, p_ok, _, _, attempts = _graced_probe(
        sleep_s,
        lambda: (True, 'active'),
        lambda: (True, '*:5001'),
    )
    assert s_ok and p_ok
    assert attempts == 1
    assert sleep_s == [8.0], f'grace only once, got {sleep_s}'


def test_grace_exhaust_retries():
    """场景 3: 3 次都 false → 返回 False + 记录 attempts=3."""
    sleep_s = []
    s_ok, p_ok, _, _, attempts = _graced_probe(
        sleep_s,
        lambda: (False, 'inactive'),
        lambda: (False, 'no LISTEN'),
    )
    assert s_ok is False and p_ok is False
    assert attempts == 3
    assert sleep_s == [8.0, 1.0, 1.0], f'grace + 2 retry sleeps, got {sleep_s}'


def test_grace_partial_success_then_full():
    """场景 4: 第 1 次 service true 但 port false → 持续重试到两次都 true."""
    sleep_s = []
    seq = [(True, False), (True, True)]
    idx = [0]

    def check_active():
        a = seq[idx[0]]; idx[0] += 1; return a[0], 'active'

    def check_port():
        a = seq[idx[0] - 1]; return a[1], 'no LISTEN' if not a[1] else '*:5001'

    s_ok, p_ok, _, _, attempts = _graced_probe(sleep_s, check_active, check_port)
    assert s_ok and p_ok
    assert attempts == 2


if __name__ == '__main__':
    test_grace_recovers_from_false_negative()
    test_grace_first_probe_success()
    test_grace_exhaust_retries()
    test_grace_partial_success_then_full()
    print('OK: 4/4 grace tests passed')