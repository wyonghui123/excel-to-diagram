# -*- coding: utf-8 -*-
"""
factories/tests/ conftest.py

注册 pytest marker:
- slow: 慢速测试 (> 1s), 默认跳过, 手动跑用:
    pytest -m slow                       # 只跑 slow
    pytest -m "not slow"                 # 显式不跑 slow (默认行为)
    pytest                               # 默认: slow 自动 skip

实现:
- 文件名含 robustness 的所有测试 -> 标记 slow + 默认 skip
- 显式 > 1s 的测试 (test_unique_id_long_span) -> 标记 slow + 默认 skip
- 用 SKIP_SLOW=0 env 强制不跳过: SKIP_SLOW=0 pytest ...
"""
import os
import pytest


# 默认跳过 slow 测试, 可用环境变量覆盖
# SKIP_SLOW=0 -> 强制跑所有 slow 测试
# SKIP_SLOW=1 (默认) -> 自动跳过 slow 测试
SKIP_SLOW = os.environ.get('SKIP_SLOW', '1') != '0'


def pytest_configure(config):
    """注册自定义 marker (避免 UnknownMark 警告)"""
    config.addinivalue_line(
        "markers",
        "slow: 慢速测试 (> 1s), 默认跳过, 用 SKIP_SLOW=0 强制跑",
    )


def pytest_collection_modifyitems(config, items):
    """
    [FIX 2026-07-17 P2] 自动收集规则:
    - 文件名含 robustness 的所有测试 -> 标记 slow
    - test_unique_id_long_span -> 标记 slow
    - 如果 SKIP_SLOW != '0' -> 自动 skip slow 测试
    """
    slow_marker = pytest.mark.slow
    skip_marker = pytest.mark.skip(
        reason='[P2] 慢速测试默认跳过 (SKIP_SLOW=0 可强制跑)',
    )

    for item in items:
        filepath = str(item.fspath)
        filename = filepath.split('\\')[-1].split('/')[-1]

        # 已手动标记则保留
        if item.get_closest_marker('slow'):
            already_slow = True
        else:
            already_slow = False

        # robustness 测试 -> slow
        if not already_slow and 'robustness' in filename:
            item.add_marker(slow_marker)
            already_slow = True

        # 显式 > 1s 的测试
        if not already_slow and item.name == 'test_unique_id_long_span':
            item.add_marker(slow_marker)
            already_slow = True

        # SKIP_SLOW=1 (默认) -> skip slow 测试
        if already_slow and SKIP_SLOW:
            item.add_marker(skip_marker)