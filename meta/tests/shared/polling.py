# -*- coding: utf-8 -*-
"""轮询等待 helper（TEST-EFF P2-6）

固定 ``time.sleep(N)`` 在慢机器上必然假失败、在快机器上纯属浪费。
凡是"等某个可观测状态出现"的场景，一律用 ``wait_until``：

    from meta.tests.shared.polling import wait_until

    assert wait_until(lambda: _audit_count(parent_id) >= 1,
                      timeout=3.0, desc='audit_logs 写入')

    if not wait_until(cond, timeout=1.0):
        pytest.skip('审计拦截器未启用')

确属固定延迟的（TTL 过期语义、性能采样间隔）在文件头加 ``ALLOW_SLEEP``
+ 理由，不要为了消 lint 改成轮询。
"""
import os
import time

DEFAULT_INTERVAL = 0.02


def wait_until(predicate, timeout=3.0, interval=DEFAULT_INTERVAL, desc=None):
    """轮询 predicate 直到为真或超时。

    desc 非空时超时抛 AssertionError（带场景描述）；为空时返回 False，
    便于调用方自行 skip 或降级断言。
    """
    deadline = time.monotonic() + timeout
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            if desc:
                raise AssertionError(f'等待超时（{timeout}s）：{desc}')
            return False
        time.sleep(interval)


def remove_file(path, timeout=2.0, interval=0.05):
    """Windows 下文件被占用时删除会 PermissionError：重试到超时，静默放弃。

    返回 True 表示已删除或本来就不存在。
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.unlink(path)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(interval)