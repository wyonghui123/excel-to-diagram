# -*- coding: utf-8 -*-
"""
P2-6 perm_cache 并发测试
"""
import sys
import threading
import time
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.perm_cache import PermissionCache


class TestPermissionCacheConcurrency(unittest.TestCase):
    """并发安全测试"""

    def test_01_concurrent_set_get(self):
        """并发 set/get 不崩溃"""
        cache = PermissionCache(max_size=100, ttl=60)
        errors = []

        def worker(i):
            try:
                for j in range(20):
                    key = f'k_{i}_{j}'
                    cache.set(key, [{'i': i, 'j': j}])
                    value = cache.get(key)
                    assert value == [{'i': i, 'j': j}]
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])

    def test_02_concurrent_ttl_expiry(self):
        """并发 TTL 过期不崩溃"""
        cache = PermissionCache(max_size=100, ttl=1)
        # 设置 50 个 key
        for i in range(50):
            cache.set(f'k_{i}', [{'i': i}])
        # 立即再设置（覆盖）
        for i in range(50):
            cache.set(f'k_{i}', [{'i': i * 2}])
        # 等 TTL 过期
        time.sleep(1.2)
        # 此时所有 get 都应返回 None
        for i in range(50):
            value = cache.get(f'k_{i}')
            self.assertIsNone(value)

    def test_03_concurrent_lru_eviction(self):
        """并发 LRU 淘汰不出错"""
        cache = PermissionCache(max_size=10, ttl=60)
        errors = []

        def worker(i):
            try:
                for j in range(50):
                    cache.set(f'k_{i}_{j}', [{'i': i, 'j': j}])
                    cache.get(f'k_{i}_{j}')
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 缓存大小不应超过 max_size
        stats = cache.stats()
        self.assertLessEqual(stats['size'], 10)
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
