# -*- coding: utf-8 -*-
"""
V007.35 — Windows/Linux 一致性 PRAGMA 测试

验证 sql_connection_pool 创建连接时设定了对齐的 PRAGMA:
- mmap_size = 256MB
- cache_size = -2000 (2MB)
- busy_timeout = 30000 (V007.20)
- journal_mode = WAL
- synchronous = NORMAL
"""
import sys
import os
import unittest
import sqlite3
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from meta.core.sql_connection_pool import SQLiteConnectionPool


class TestV00735PlatformPragmas(unittest.TestCase):
    """V007.35: 验证所有对齐 PRAGMA 在连接创建时生效"""

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp_db.close()
        self.db_path = self.tmp_db.name

        self.pool = SQLiteConnectionPool(self.db_path)
        self.pool.initialize()

    def tearDown(self):
        try:
            self.pool.shutdown()
        except:
            pass
        try:
            os.unlink(self.db_path)
        except:
            pass

    def _get_pragmas(self, conn):
        """读取当前连接的所有关键 PRAGMA 值"""
        return {
            'busy_timeout': conn.execute("PRAGMA busy_timeout").fetchone()[0],
            'journal_mode': conn.execute("PRAGMA journal_mode").fetchone()[0],
            'synchronous': conn.execute("PRAGMA synchronous").fetchone()[0],
            'cache_size': conn.execute("PRAGMA cache_size").fetchone()[0],
            'mmap_size': conn.execute("PRAGMA mmap_size").fetchone()[0],
        }

    def test_01_busy_timeout_30000(self):
        """V007.20: PRAGMA busy_timeout = 30000"""
        with self.pool.reader() as conn:
            val = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        self.assertEqual(val, 30000, f"busy_timeout 应为 30000, 实际 {val}")

    def test_02_journal_mode_wal(self):
        """PRAGMA journal_mode = wal"""
        with self.pool.reader() as conn:
            val = conn.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(val.lower(), 'wal', f"journal_mode 应为 wal, 实际 {val}")

    def test_03_synchronous_normal(self):
        """PRAGMA synchronous = NORMAL (1)"""
        with self.pool.reader() as conn:
            val = conn.execute("PRAGMA synchronous").fetchone()[0]
        self.assertIn(val, [1, 'normal'], f"synchronous 应为 NORMAL/1, 实际 {val}")

    def test_04_mmap_size_256mb(self):
        """V007.35: PRAGMA mmap_size = 268435456 (256MB)"""
        with self.pool.reader() as conn:
            val = conn.execute("PRAGMA mmap_size").fetchone()[0]
        self.assertEqual(val, 268435456,
                         f"mmap_size 应为 268435456, 实际 {val}")

    def test_05_cache_size_neg2000(self):
        """V007.35: PRAGMA cache_size = -2000 (2MB)"""
        with self.pool.reader() as conn:
            val = conn.execute("PRAGMA cache_size").fetchone()[0]
        self.assertEqual(val, -2000,
                         f"cache_size 应为 -2000, 实际 {val}")

    def test_06_all_pragmas_together(self):
        """V007.35: 所有 PRAGMA 一次性验证"""
        with self.pool.reader() as conn:
            pragmas = self._get_pragmas(conn)

        self.assertEqual(pragmas['busy_timeout'], 30000)
        self.assertEqual(pragmas['journal_mode'].lower(), 'wal')
        self.assertIn(pragmas['synchronous'], [1, 'normal'])
        self.assertEqual(pragmas['mmap_size'], 268435456)
        self.assertEqual(pragmas['cache_size'], -2000)

    def test_07_pragma_persists_across_readers(self):
        """V007.35: PRAGMA 设置跨多个 reader 连接保持一致"""
        values_a = {}
        values_b = {}

        with self.pool.reader() as conn:
            values_a = self._get_pragmas(conn)

        with self.pool.reader() as conn:
            values_b = self._get_pragmas(conn)

        self.assertEqual(values_a, values_b,
                         f"两个 reader 的 PRAGMA 应一致:\n  A: {values_a}\n  B: {values_b}")


if __name__ == '__main__':
    unittest.main()
