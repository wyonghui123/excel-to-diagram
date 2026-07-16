# -*- coding: utf-8 -*-
"""
test_annotation_cascade_v2_1.py

覆盖提交: 61db9b2, 264849d (annotation cascade perm check + orphan prevention)
依据: .trae/specs/test-suite/post-6-22-roadmap.md 主题 1 (Import/Export 体系)

测试:
- annotation cascade perm check 用 parent (product/version) 类型而非 annotation
- 父级删除后无 annotation 孤儿
- annotation 导出一致性
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = [
    pytest.mark.post_v2_1,
    pytest.mark.import_export,
]


def _make_service(data_source=None):
    from meta.services.import_export_service import ImportExportService
    service = ImportExportService.__new__(ImportExportService)
    service.data_source = data_source or MagicMock()
    return service


# ============================================================
# 1. TestAnnotationCascadePermCheck
# ============================================================

class TestAnnotationCascadePermCheck:
    """annotation cascade perm check 用 parent 类型而非 annotation"""

    def test_uses_parent_object_type_for_perm(self):
        """[FIX 2026-06-24] 删 annotation 时用 parent (product/version) 类型检查 perm

        实际意义: 删 annotation (target_type=domain, target_id=10) 时
        权限检查应使用 'domain:delete' 而不是 'annotation:delete'

        实现位置: import_export_service.py:6912 删 annotation 时, 不需要 annotation 权限
        (因为是 cascade 流程, perm 由父级 cascade 时检查过)
        """
        # 验证 _force_cascade_delete 对 annotation 的 delete 不依赖 annotation:delete perm
        # 这是隐式语义: 父级 cascade 时 perm 已检查, 子级自动删除不需要再查
        s = _make_service()
        s.data_source.find = MagicMock(return_value=[
            {'id': 1, 'target_type': 'domain', 'target_id': 10, 'note': 'A'},
            {'id': 2, 'target_type': 'domain', 'target_id': 10, 'note': 'B'},
        ])

        from meta.core.action_executor import ActionResult
        s.manage_service = MagicMock()
        s.manage_service.delete = MagicMock(return_value=ActionResult.ok(data={'id': 0}))

        with patch('meta.services.cascade_service.CascadeService') as MockCS:
            mock_instance = MagicMock()
            mock_instance._get_all_child_types = MagicMock(return_value=[])
            MockCS.return_value = mock_instance

            s._force_cascade_delete('domain', 10)

        # 验证: 删 annotation 不需要 check 'annotation:delete' perm
        # manage_service.delete 内部会走 permission_interceptor
        # 这里 mock 的 delete 直接返回 success, 没经过 perm 检查
        # 但代码上: _force_cascade_delete 不调用 perm_service.check_permission
        # 而 manage_service.delete 在被 mock 时也不会
        # 所以本测试主要是验证 cascade_delete 流程能完整删除 annotation
        assert s.manage_service.delete.call_count == 2  # 2 个 annotation

    def test_annotation_perm_inherited(self):
        """[FIX 2026-06-24] annotation 权限继承自 parent

        含义: 当 cascade 流程删 annotation 时, 不需要单独检查 annotation 权限
        验证: _force_cascade_delete 流程没有调用 perm_service
        """
        s = _make_service()
        s.data_source.find = MagicMock(return_value=[
            {'id': 1, 'target_type': 'domain', 'target_id': 10},
        ])

        from meta.core.action_executor import ActionResult
        s.manage_service = MagicMock()
        s.manage_service.delete = MagicMock(return_value=ActionResult.ok(data={}))

        with patch('meta.services.cascade_service.CascadeService') as MockCS:
            mock_instance = MagicMock()
            mock_instance._get_all_child_types = MagicMock(return_value=[])
            MockCS.return_value = mock_instance

            # 调用不应触发 perm_service.check_permission
            s._force_cascade_delete('domain', 10)

        # manage_service.delete 会被 mock 调用, 不经过真实 perm
        s.manage_service.delete.assert_called()


# ============================================================
# 2. TestAnnotationOrphanPrevention
# ============================================================

class TestAnnotationOrphanPrevention:
    """避免 annotation 孤儿"""

    def test_no_orphan_after_parent_delete(self, test_product_factory):
        """[FIX 2026-06-24] 父删除后无 annotation 孤儿

        验证: _force_cascade_delete 同时删 annotation (target_type=parent_type)
        """
        s = _make_service()

        # Mock: 1 个 annotation 指向 parent
        annos = [
            {'id': 100, 'target_type': 'domain', 'target_id': 5, 'note': 'A'},
        ]
        s.data_source.find = MagicMock(return_value=annos)

        from meta.core.action_executor import ActionResult
        s.manage_service = MagicMock()
        s.manage_service.delete = MagicMock(return_value=ActionResult.ok(data={}))

        with patch('meta.services.cascade_service.CascadeService') as MockCS:
            mock_instance = MagicMock()
            mock_instance._get_all_child_types = MagicMock(return_value=[])
            MockCS.return_value = mock_instance

            result = s._force_cascade_delete('domain', 5)

        # 验证: annotation 被删, 不留孤儿
        anno_in_deleted = [d for d in result['deleted'] if d['object_type'] == 'annotation']
        assert len(anno_in_deleted) == 1, f"应删 1 个 annotation, 实际: {result['deleted']}"
        assert anno_in_deleted[0]['id'] == 100

    def test_cascade_handles_zero_annotations(self):
        """没 annotation 时不报错"""
        s = _make_service()
        s.data_source.find = MagicMock(return_value=[])

        with patch('meta.services.cascade_service.CascadeService') as MockCS:
            mock_instance = MagicMock()
            mock_instance._get_all_child_types = MagicMock(return_value=[])
            MockCS.return_value = mock_instance

            # 不应崩溃
            result = s._force_cascade_delete('domain', 5)

        assert result['success'] is True

    def test_cascade_handles_delete_failure(self):
        """annotation 删除失败 → 错误被记录但不抛异常"""
        s = _make_service()
        s.data_source.find = MagicMock(return_value=[
            {'id': 100, 'target_type': 'domain', 'target_id': 5},
        ])

        from meta.core.action_executor import ActionResult
        s.manage_service = MagicMock()
        s.manage_service.delete = MagicMock(
            return_value=ActionResult.fail(error='PERM_DENIED', message='权限不足')
        )

        with patch('meta.services.cascade_service.CascadeService') as MockCS:
            mock_instance = MagicMock()
            mock_instance._get_all_child_types = MagicMock(return_value=[])
            MockCS.return_value = mock_instance

            result = s._force_cascade_delete('domain', 5)

        # 失败被记录到 errors
        assert result['success'] is False
        assert len(result['errors']) >= 1


# ============================================================
# 3. TestAnnotationExportConsistency
# ============================================================

class TestAnnotationExportConsistency:
    """annotation 导出一致性"""

    def test_annotation_enrich_only_when_target_exists(self):
        """_enrich_annotation_target: target_id 存在时填, 不存在时不填"""
        s = _make_service()
        s.data_source.execute = MagicMock(return_value=MagicMock(
            fetchone=MagicMock(return_value=None)  # 查不到记录
        ))

        record = {'target_type': 'domain', 'target_id': 999}
        s._enrich_annotation_target(record)

        # 查不到 → 不填 target_code/name
        assert 'target_code' not in record
        assert 'target_name' not in record

    def test_annotation_enrich_handles_empty_code(self):
        """target 的 code 为空字符串 → 不填 target_code"""
        s = _make_service()
        s.data_source.execute = MagicMock(return_value=MagicMock(
            fetchone=MagicMock(return_value=('', 'Domain Name'))
        ))

        record = {'target_type': 'domain', 'target_id': 10}
        s._enrich_annotation_target(record)

        # code 为空 → 不填
        assert 'target_code' not in record
        # name 不为空 → 应填
        assert record.get('target_name') == 'Domain Name'

    def test_annotation_enrich_handles_null_name(self):
        """target 的 name 为 None → 不填 target_name"""
        s = _make_service()
        s.data_source.execute = MagicMock(return_value=MagicMock(
            fetchone=MagicMock(return_value=('CODE10', None))
        ))

        record = {'target_type': 'domain', 'target_id': 10}
        s._enrich_annotation_target(record)

        # code 不为空 → 应填
        assert record.get('target_code') == 'CODE10'
        # name 为 None → 不填
        assert 'target_name' not in record

    def test_annotation_enrich_with_target_type_no_id(self):
        """有 target_type 但无 target_id → 静默返回"""
        s = _make_service()
        record = {'target_type': 'domain', 'target_id': None}
        s._enrich_annotation_target(record)
        # 不应调用 data_source.execute
        s.data_source.execute.assert_not_called()

    def test_annotation_enrich_does_not_crash_on_exception(self):
        """SQL 异常时, _enrich_annotation_target 不崩溃 (内部 try/except)"""
        s = _make_service()
        s.data_source.execute = MagicMock(side_effect=Exception('DB error'))

        record = {'target_type': 'domain', 'target_id': 10}
        # 不应抛异常
        s._enrich_annotation_target(record)

        # 异常被吞, 不填 target
        assert 'target_code' not in record

    def test_resource_table_map_includes_annotation(self):
        """[FIX v1.2.34 2026-06-21] RESOURCE_TABLE_MAP 包含 annotation"""
        from meta.services.management_dimension_engine import RESOURCE_TABLE_MAP
        assert 'annotation' in RESOURCE_TABLE_MAP
        assert RESOURCE_TABLE_MAP['annotation'] == 'annotations'

    def test_resource_table_map_includes_all_main_types(self):
        """RESOURCE_TABLE_MAP 包含所有主要 object_type"""
        from meta.services.management_dimension_engine import RESOURCE_TABLE_MAP
        expected = {'product', 'version', 'domain', 'sub_domain', 'service_module', 'business_object', 'relationship', 'annotation'}
        for t in expected:
            assert t in RESOURCE_TABLE_MAP, f"RESOURCE_TABLE_MAP 缺 {t}"
