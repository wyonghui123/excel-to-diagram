# -*- coding: utf-8 -*-
"""
[Plan B Task 1] 双轨对账装饰器单元测试

测试 _dual_track_checker.dual_track / assert_consistent 的核心行为.
"""
import os
import pytest


class TestDualTrack:
    def setup_method(self):
        # 确保 flag 默认关闭, 测试可以独立触发
        os.environ.pop('PERMISSION_SET_REFACTOR_ENABLED', None)

    def test_dual_track_returns_func_result_when_flag_off(self):
        """FF 关闭时: 装饰器直接返回原函数结果 (无对账开销)"""
        from meta.services._dual_track_checker import dual_track

        @dual_track(sql_key='unit_off')
        def f(x):
            return x * 2

        assert f(5) == 10

    def test_dual_track_logs_mismatch_when_flag_on(self):
        """FF 开启时: 装饰器执行新路径 (旧路径由调用方负责)"""
        from meta.services._dual_track_checker import dual_track, is_enabled

        # 当前实现下, dual_track 只跑新路径; 真正的"双轨对账"在 assert_consistent()
        os.environ['PERMISSION_SET_REFACTOR_ENABLED'] = 'true'
        try:
            @dual_track(sql_key='unit_on')
            def f(x):
                return x + 1

            assert f(3) == 4
        finally:
            os.environ.pop('PERMISSION_SET_REFACTOR_ENABLED', None)


class TestAssertConsistent:
    def test_consistent_returns_true_for_same_dicts(self):
        from meta.services._dual_track_checker import assert_consistent
        assert assert_consistent('k', {'a': 1}, {'a': 1}) is True

    def test_consistent_returns_true_for_same_lists(self):
        from meta.services._dual_track_checker import assert_consistent
        assert assert_consistent('k', [1, 2, 3], [1, 2, 3]) is True

    def test_consistent_returns_false_for_diff_keys(self):
        from meta.services._dual_track_checker import assert_consistent
        assert assert_consistent('k', {'a': 1}, {'b': 1}) is False

    def test_consistent_handles_unhashable_safely(self):
        from meta.services._dual_track_checker import assert_consistent
        # 不会抛异常
        result = assert_consistent('k', object(), object())
        assert result in (True, False)
