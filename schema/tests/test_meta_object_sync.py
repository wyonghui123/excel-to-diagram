"""
test_meta_object_sync.py - M13 v1.5.0 meta_object 同步测试
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestMetaObjectSync(unittest.TestCase):
    """meta_object 同步测试"""

    def test_sync_without_dao(self):
        """无 DAO 时（内存模式）正常返回"""
        from schema.audit.meta_object_sync import sync_meta_object_table
        with patch('schema.audit.meta_object_sync._get_meta_object_table', return_value=None):
            result = sync_meta_object_table()
            self.assertGreater(result['synced'], 0)
            self.assertEqual(result['created'], 0)
            self.assertEqual(result['updated'], 0)
            self.assertEqual(result['drift_detected'], 0)

    def test_sync_with_mock_dao_creates(self):
        """有 DAO 时新建 entity"""
        from schema.audit.meta_object_sync import sync_meta_object_table
        mock_dao = MagicMock()
        mock_dao.find_by_name.return_value = None  # 无 existing
        mock_dao.create = MagicMock()

        with patch('schema.audit.meta_object_sync._get_meta_object_table', return_value=mock_dao):
            result = sync_meta_object_table()
            self.assertGreater(result['created'], 0)
            self.assertGreaterEqual(mock_dao.create.call_count, 10)

    def test_sync_with_existing_detects_drift(self):
        """existing 被手工改 → 漂移检测"""
        from schema.audit.meta_object_sync import sync_meta_object_table
        mock_existing = MagicMock()
        mock_existing.manual_modified = True
        mock_existing.fields = '["id"]'
        mock_existing.id = 1

        mock_dao = MagicMock()
        mock_dao.find_by_name.return_value = mock_existing
        mock_dao.update = MagicMock()

        with patch('schema.audit.meta_object_sync._get_meta_object_table', return_value=mock_dao):
            result = sync_meta_object_table()
            self.assertGreater(result['drift_detected'], 0)

    def test_detect_drift_returns_list(self):
        """detect_drift 返回 list"""
        from schema.audit.meta_object_sync import detect_drift
        # 内存模式（无 DAO）→ 返回空 list
        with patch('schema.audit.meta_object_sync._get_meta_object_table', return_value=None):
            drifts = detect_drift()
            self.assertIsInstance(drifts, list)

    def test_safe_json_dumps(self):
        """_safe_json_dumps 正确序列化"""
        from schema.audit.meta_object_sync import _safe_json_dumps
        obj = {'key': 'value', 'list': [1, 2, 3]}
        result = _safe_json_dumps(obj)
        self.assertIn('"key"', result)
        self.assertIn('"value"', result)

    def test_safe_json_dumps_with_chinese(self):
        """_safe_json_dumps 支持中文"""
        from schema.audit.meta_object_sync import _safe_json_dumps
        obj = {'description': '用户', 'tag': '用户管理'}
        result = _safe_json_dumps(obj)
        self.assertIn('用户', result)

    def test_sync_returns_dict(self):
        """sync 返回 dict 包含 5 个键"""
        from schema.audit.meta_object_sync import sync_meta_object_table
        with patch('schema.audit.meta_object_sync._get_meta_object_table', return_value=None):
            result = sync_meta_object_table()
            for key in ['synced', 'created', 'updated', 'drift_detected', 'errors']:
                self.assertIn(key, result)


if __name__ == '__main__':
    unittest.main()
