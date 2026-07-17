# -*- coding: utf-8 -*-
"""
test_unique_id_robustness.py
============================

[FIX 2026-07-17] regression test for unique_id() pre-existing bug
修复: 进程内单调 atomic counter + PID 维度隔离
原 bug: int(time.time()*1000) + os.getpid() 在毫秒级时间精度下,
       同一进程快速循环 (100 次) 返回相同 ID

覆盖场景:
1. 串行 100 次循环 (原 bug 场景, 回归用例)
2. 串行 1000 次循环 (压力)
3. 多线程并发 (10 线程 × 100 次)
4. 长时间跨度 (5 秒)
5. counter 部分单调递增
6. ID 长度合理 (< 25 字符, 保证 email VARCHAR(255) 安全)
"""
import json
import subprocess
import sys
import threading
import time

import pytest

# [FIX 2026-07-17 P2] 全部 robustness 测试默认 slow, CI 默认跳过
# 显式跑: pytest -m slow
pytestmark = pytest.mark.slow


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def fresh_unique_id():
    """保证 unique_id 模块已加载 (无 pyc 缓存污染)"""
    # 移除已加载模块, 避免 pyc 缓存影响
    for m in list(sys.modules.keys()):
        if 'factories' in m:
            del sys.modules[m]
    from meta.tests.factories import unique_id
    return unique_id


# ============================================================
# 回归测试 (P0)
# ============================================================

class TestUniqueIdRegression:
    """回归测试: unique_id() 修复 pre-existing bug"""

    def test_unique_id_unique_100_loops(self, fresh_unique_id):
        """回归: 100 次串行循环必须全部唯一

        原 bug: 同毫秒内 100 次调用返回相同 ID
        """
        ids = [fresh_unique_id() for _ in range(100)]
        assert len(set(ids)) == 100, (
            f"Expected 100 unique IDs, got {len(set(ids))} "
            f"(suggests counter/timestamp dimension missing)"
        )

    def test_unique_id_unique_1000_loops(self, fresh_unique_id):
        """压力: 1000 次循环全部唯一"""
        ids = [fresh_unique_id() for _ in range(1000)]
        assert len(set(ids)) == 1000


class TestUniqueIdConcurrent:
    """并发安全: 多线程/多进程"""

    def test_unique_id_concurrent_10_threads(self, fresh_unique_id):
        """10 线程 × 100 次 = 1000 个 ID 全部唯一

        验证 threading.Lock 保证 atomic counter 增量
        """
        results = []
        lock = threading.Lock()

        def worker():
            local_ids = [fresh_unique_id() for _ in range(100)]
            with lock:
                results.extend(local_ids)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 1000
        assert len(set(results)) == 1000, (
            f"Concurrent: expected 1000 unique IDs, got {len(set(results))} "
            f"(thread-safety violation in counter increment)"
        )

    def test_unique_id_cross_process_isolation(self, fresh_unique_id):
        """跨进程隔离: 父进程 + 子进程 ID 不冲突

        验证 PID 维度天然隔离
        """
        # 父进程 ID
        parent_ids = [fresh_unique_id() for _ in range(50)]

        # 子进程 ID
        script = (
            "import sys; sys.path.insert(0, '.'); "
            "from meta.tests.factories import unique_id; "
            "import json; "
            "print(json.dumps([unique_id() for _ in range(50)]))"
        )
        result = subprocess.run(
            [sys.executable, '-c', script],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"Subprocess failed: {result.stderr}"
        child_ids = json.loads(result.stdout.strip())

        # 父子进程合并, 应全部唯一 (PID 维度隔离)
        all_ids = parent_ids + child_ids
        assert len(set(all_ids)) == len(all_ids), (
            f"Cross-process: expected {len(all_ids)} unique IDs, "
            f"got {len(set(all_ids))} (PID isolation failed)"
        )


class TestUniqueIdStability:
    """稳定性: 长时间跨度 / ID 格式"""

    def test_unique_id_long_span(self, fresh_unique_id):
        """5 秒跨度 (5 个 ID, 每秒 1 个) 全部唯一"""
        ids = []
        for _ in range(5):
            ids.append(fresh_unique_id())
            time.sleep(1)
        assert len(set(ids)) == 5

    def test_unique_id_length_reasonable(self, fresh_unique_id):
        """ID 长度 < 25 字符 (保证 email VARCHAR(255) 安全)

        email 模板: prefix_{uid}_{suffix}@test.local
        4 + 25 + 1 + 4 + 1 + 11 = ~46 chars (well under 255)
        """
        sample = [fresh_unique_id() for _ in range(10)]
        max_len = max(len(str(i)) for i in sample)
        assert max_len < 25, (
            f"unique_id() max length {max_len} exceeds 25 chars; "
            f"may overflow email VARCHAR(255)"
        )

    def test_unique_id_counter_monotonic_within_millisecond(self, fresh_unique_id):
        """同毫秒内 counter 部分单调递增

        验证 counter 部分 (低 4 位) 在快速循环中递增
        """
        batch = [fresh_unique_id() for _ in range(100)]
        counters = [i % 10000 for i in batch]
        # 后 4 位是 counter (0-9999), 在同毫秒内应递增
        # 注意: 跨毫秒时 counter 可能从 0 重新开始 (时间戳进位)
        # 所以只验证递增比例 > 50%
        increasing = sum(
            1 for i in range(len(counters) - 1)
            if counters[i + 1] > counters[i]
        )
        ratio = increasing / (len(counters) - 1)
        assert ratio > 0.5, (
            f"Counter monotonic ratio {ratio:.1%} too low "
            f"(expected > 50% within same millisecond)"
        )

    def test_unique_email_length_under_varchar_255(self, fresh_unique_id):
        """unique_email() 整体长度 < 255 (DB VARCHAR 安全)

        email 模板: prefix_{uid}_{suffix}@test.local
        4(prefix) + 1(_) + 21(uid) + 1(_) + 4(suffix) + 1(@) + 11(domain) = ~43 chars
        """
        from meta.tests.factories import unique_email
        emails = [unique_email() for _ in range(10)]
        max_email_len = max(len(e) for e in emails)
        assert max_email_len < 255, (
            f"unique_email() max length {max_email_len} exceeds 255 chars"
        )
        # 验证格式
        for e in emails:
            assert '@test.local' in e
            assert e.startswith('user_')