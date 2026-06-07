# -*- coding: utf-8 -*-
"""
Migration up/down 完整性测试（P1-3）

验证 add_role_intents_2026.py 的：
- up() 创建表
- down() 删除表
- 幂等性（up 多次不应出错）
"""
import sys
import os
import sqlite3
import unittest
import tempfile
import shutil

sys.path.insert(0, 'd:/filework/excel-to-diagram')


def _use_temp_db():
    """使用空数据库文件（创建空 db 避免沙箱外拷贝）"""
    import os
    import tempfile
    import sqlite3 as _sqlite3
    tmp_dir = tempfile.mkdtemp()
    tmp_db = os.path.join(tmp_dir, 'test_migration.db')
    # 创建空 db（不拷贝源 db，避免沙箱外访问问题）
    conn = _sqlite3.connect(tmp_db)
    conn.close()
    return tmp_db, tmp_dir


def _cleanup_tmp(tmp_dir):
    """清理临时目录"""
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)


class TestRoleIntentsMigration(unittest.TestCase):
    """Migration up/down 测试"""

    def setUp(self):
        self.tmp_db, self.tmp_dir = _use_temp_db()

    def tearDown(self):
        _cleanup_tmp(self.tmp_dir)

    def _table_exists(self, tmp_db, name):
        conn = sqlite3.connect(tmp_db)
        cur = conn.cursor()
        cur.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        """, (name,))
        result = cur.fetchone()
        conn.close()
        return result is not None

    def _index_exists(self, tmp_db, name):
        conn = sqlite3.connect(tmp_db)
        cur = conn.cursor()
        cur.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name=?
        """, (name,))
        result = cur.fetchone()
        conn.close()
        return result is not None

    def test_01_up_creates_table(self):
        """up() 应创建 role_intents 表"""
        import importlib
        mod = importlib.import_module(
            'meta.migrations.add_role_intents_2026'
        )
        # 重定向 get_db_path 到 tmp_db
        mod.get_db_path = lambda: self.tmp_db
        mod.up()
        self.assertTrue(self._table_exists(self.tmp_db, 'role_intents'))
        # 验证表结构
        conn = sqlite3.connect(self.tmp_db)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(role_intents)")
        cols = [r[1] for r in cur.fetchall()]
        conn.close()
        self.assertIn('role_id', cols)
        self.assertIn('bo_id', cols)
        self.assertIn('action_name', cols)
        self.assertIn('parameters_hash', cols)
        self.assertIn('granted', cols)

    def test_02_up_creates_indexes(self):
        """up() 应创建 2 个索引"""
        import importlib
        mod = importlib.import_module(
            'meta.migrations.add_role_intents_2026'
        )
        mod.get_db_path = lambda: self.tmp_db
        mod.up()
        self.assertTrue(self._index_exists(
            self.tmp_db, 'idx_role_intents_role',
        ))
        self.assertTrue(self._index_exists(
            self.tmp_db, 'idx_role_intents_bo_action',
        ))

    def test_03_up_idempotent(self):
        """up() 多次调用应幂等"""
        import importlib
        mod = importlib.import_module(
            'meta.migrations.add_role_intents_2026'
        )
        mod.get_db_path = lambda: self.tmp_db
        mod.up()
        mod.up()  # 不应出错
        mod.up()  # 不应出错
        self.assertTrue(self._table_exists(self.tmp_db, 'role_intents'))

    def test_04_down_drops_table(self):
        """down() 应删除 role_intents 表"""
        import importlib
        mod = importlib.import_module(
            'meta.migrations.add_role_intents_2026'
        )
        mod.get_db_path = lambda: self.tmp_db
        mod.up()
        self.assertTrue(self._table_exists(self.tmp_db, 'role_intents'))
        mod.down()
        self.assertFalse(self._table_exists(self.tmp_db, 'role_intents'))

    def test_05_down_idempotent(self):
        """down() 多次调用应幂等"""
        import importlib
        mod = importlib.import_module(
            'meta.migrations.add_role_intents_2026'
        )
        mod.get_db_path = lambda: self.tmp_db
        mod.down()  # 表不存在，应 no-op
        mod.down()
        self.assertFalse(self._table_exists(self.tmp_db, 'role_intents'))

    def test_06_up_down_up_cycle(self):
        """完整 up → down → up 周期"""
        import importlib
        mod = importlib.import_module(
            'meta.migrations.add_role_intents_2026'
        )
        mod.get_db_path = lambda: self.tmp_db
        mod.up()
        self.assertTrue(self._table_exists(self.tmp_db, 'role_intents'))
        mod.down()
        self.assertFalse(self._table_exists(self.tmp_db, 'role_intents'))
        mod.up()
        self.assertTrue(self._table_exists(self.tmp_db, 'role_intents'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
