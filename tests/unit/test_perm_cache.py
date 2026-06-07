# -*- coding: utf-8 -*-
"""
NFR-001 性能缓存单元测试
"""
import sys
import time
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.perm_cache import PermissionCache, get_permission_cache


class TestPermissionCache(unittest.TestCase):
    """NFR-001 缓存测试"""

    def setUp(self):
        self.cache = PermissionCache(max_size=10, ttl=2)

    def test_01_make_key_deterministic(self):
        """相同输入生成相同 key"""
        k1 = PermissionCache.make_key(1, 'domain', [1, 2, 3], {'a': 1})
        k2 = PermissionCache.make_key(1, 'domain', [1, 2, 3], {'a': 1})
        self.assertEqual(k1, k2)

    def test_02_make_key_order_independent(self):
        """role_ids 顺序不影响 key（用 sorted）"""
        k1 = PermissionCache.make_key(1, 'domain', [1, 2, 3])
        k2 = PermissionCache.make_key(1, 'domain', [3, 1, 2])
        self.assertEqual(k1, k2)

    def test_03_get_set_basic(self):
        """基本 set/get"""
        key = 'test_key'
        value = [{'field': 'id', 'op': 'in', 'value': [1, 2]}]
        self.cache.set(key, value)
        result = self.cache.get(key)
        self.assertEqual(result, value)

    def test_04_get_miss(self):
        """未 set 的 key 返回 None"""
        result = self.cache.get('non_existent')
        self.assertIsNone(result)

    def test_05_ttl_expiry(self):
        """TTL 过期后返回 None"""
        key = 'test_ttl'
        self.cache.set(key, [{'a': 1}])
        # TTL=2s，等待 2.5s
        time.sleep(2.5)
        result = self.cache.get(key)
        self.assertIsNone(result)

    def test_06_lru_eviction(self):
        """LRU 淘汰：超出 max_size 后淘汰最久未用"""
        # max_size=10
        for i in range(10):
            self.cache.set(f'key_{i}', [{'i': i}])
        # 访问 key_0（移到末尾）
        self.cache.get('key_0')
        # 添加新 key
        self.cache.set('key_10', [{'i': 10}])
        # 此时 key_0 还在（刚被访问），但 key_1 被淘汰
        self.assertIsNotNone(self.cache.get('key_0'))
        self.assertIsNone(self.cache.get('key_1'))

    def test_07_stats(self):
        """缓存统计"""
        self.cache.set('k1', [{'a': 1}])
        self.cache.get('k1')  # hit
        self.cache.get('k2')  # miss
        stats = self.cache.stats()
        self.assertEqual(stats['hits'], 1)
        self.assertEqual(stats['misses'], 1)
        self.assertIn('50.00%', stats['hit_rate'])

    def test_08_clear(self):
        """clear 重置"""
        self.cache.set('k1', [{'a': 1}])
        self.cache.get('k1')  # hit
        self.cache.clear()
        self.assertEqual(self.cache.stats()['hits'], 0)
        self.assertEqual(self.cache.stats()['misses'], 0)
        self.assertIsNone(self.cache.get('k1'))

    def test_09_singleton(self):
        """get_permission_cache 是单例"""
        c1 = get_permission_cache()
        c2 = get_permission_cache()
        self.assertIs(c1, c2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
