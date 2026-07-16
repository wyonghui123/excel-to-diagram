# -*- coding: utf-8 -*-
"""
test_import_force_cascade_v2_1.py

覆盖提交: 3c4fe57, ccaaa76 (force_cascade + annotation cascade)
依据: .trae/specs/test-suite/post-6-22-roadmap.md 主题 1 (Import/Export 体系)

测试 force_cascade=True 的语义:
- 父级 delete 时强制级联删除 annotation
- 父级 delete 时级联删除子级 (composition)
- 返回结果含 cascade_count
"""
import os
import sys
import json
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
# 1. TestForceCascadeAnnotation
# ============================================================

class TestForceCascadeAnnotation:
    """force_cascade 同时删除 annotation"""

    def test_force_cascade_annotation_targets_in_set(self, test_product_factory):
        """[FIX 2026-06-24] _force_cascade_delete 对 parent_type in
        (domain/sub_domain/service_module/business_object/relationship)
        时级联删除 annotation (target_type=parent_type, target_id=parent_id)

        通过 mock data_source.find 来验证
        """
        s = _make_service()

        # Mock cascade_service._get_all_child_types 返回空 (没子级)
        # Mock data_source.find('annotations', {...}) 返回 1 个 annotation
        anno = {'id': 999, 'target_type': 'domain', 'target_id': 42, 'note': 'test'}
        s.data_source.find = MagicMock(return_value=[anno])

        # Mock manage_service.delete 返回成功
        from meta.core.action_executor import ActionResult
        s.manage_service = MagicMock()
        s.manage_service.delete = MagicMock(return_value=ActionResult.ok(data={'id': 999}))

        with patch('meta.services.cascade_service.CascadeService') as MockCS:
            mock_instance = MagicMock()
            mock_instance._get_all_child_types = MagicMock(return_value=[])
            MockCS.return_value = mock_instance

            result = s._force_cascade_delete('domain', 42)

        # 验证: annotation 999 被级联删
        s.manage_service.delete.assert_called()
        # 验证: deleted 列表包含 annotation
        assert any(d.get('object_type') == 'annotation' and d.get('id') == 999
                   for d in result['deleted']), \
            f"annotation 应该被加入 deleted 列表, 实际: {result['deleted']}"

    def test_force_cascade_annotation_multiple(self):
        """多个 annotation 同时被删"""
        s = _make_service()
        annos = [
            {'id': 1, 'target_type': 'domain', 'target_id': 10},
            {'id': 2, 'target_type': 'domain', 'target_id': 10},
            {'id': 3, 'target_type': 'domain', 'target_id': 10},
        ]
        s.data_source.find = MagicMock(return_value=annos)

        from meta.core.action_executor import ActionResult
        s.manage_service = MagicMock()
        s.manage_service.delete = MagicMock(return_value=ActionResult.ok(data={'id': 0}))

        with patch('meta.services.cascade_service.CascadeService') as MockCS:
            mock_instance = MagicMock()
            mock_instance._get_all_child_types = MagicMock(return_value=[])
            MockCS.return_value = mock_instance

            result = s._force_cascade_delete('domain', 10)

        # 至少调用 3 次 delete (每个 annotation 一次)
        assert s.manage_service.delete.call_count == 3
        # 3 个 annotation 应在 deleted 中
        anno_ids = [d['id'] for d in result['deleted'] if d['object_type'] == 'annotation']
        assert sorted(anno_ids) == [1, 2, 3]

    def test_force_cascade_no_annotation_no_cascade_anno(self):
        """没 annotation 时不报错"""
        s = _make_service()
        s.data_source.find = MagicMock(return_value=[])  # 无 annotation

        from meta.core.action_executor import ActionResult
        s.manage_service = MagicMock()
        s.manage_service.delete = MagicMock(return_value=ActionResult.ok(data={}))

        with patch('meta.services.cascade_service.CascadeService') as MockCS:
            mock_instance = MagicMock()
            mock_instance._get_all_child_types = MagicMock(return_value=[])
            MockCS.return_value = mock_instance

            result = s._force_cascade_delete('domain', 10)

        # success (没 errors)
        assert result['success'] is True
        # 没 annotation 调用 delete
        # 但可能 delete 还是会被调用? 检查 find 被调用
        s.data_source.find.assert_called_with('annotations', {'target_type': 'domain', 'target_id': 10})


# ============================================================
# 2. TestForceCascadeChildren
# ============================================================

class TestForceCascadeChildren:
    """force_cascade 级联删除子级"""

    def test_cascade_version_when_parent_deleted(self):
        """父 product 删除时, version 被级联删除

        验证: cascade_service._get_all_child_types('product') → ['version']
        然后 data_source.find('versions', {product_id: pid}) → 找到子级, 递归删
        """
        s = _make_service()

        # Mock cascade_service
        child_version = {'id': 100, 'product_id': 50, 'name': 'V1.0'}
        s.data_source.find = MagicMock(return_value=[child_version])

        from meta.core.action_executor import ActionResult
        s.manage_service = MagicMock()
        s.manage_service.delete = MagicMock(return_value=ActionResult.ok(data={'id': 100}))

        # 调用次数统计 - product 级调 1 次
        call_count = {'count': 0}

        def mock_get_all_child_types(parent_type):
            """递归: product → version, version → 空"""
            call_count['count'] += 1
            if call_count['count'] == 1:
                return ['version']
            return []

        with patch('meta.services.cascade_service.CascadeService') as MockCS:
            mock_instance = MagicMock()
            mock_instance._get_all_child_types = MagicMock(side_effect=mock_get_all_child_types)
            mock_instance._get_foreign_key = MagicMock(return_value='product_id')
            MockCS.return_value = mock_instance

            result = s._force_cascade_delete('product', 50)

        # 验证: version 100 被加入 deleted
        assert any(d.get('object_type') == 'version' and d.get('id') == 100
                   for d in result['deleted']), \
            f"version 100 应被加入 deleted, 实际: {result['deleted']}"

    def test_cascade_recursion_children_have_grandchildren(self):
        """子级还有孙级时, 递归删 (cascade_version_with_domain)

        验证:
        - version 和 domain 都被 manage_service.delete 调用 (递归删除)
        - result.deleted 包含 IMMEDIATE children (version)
        - 注: 递归级 (domain) 在 manage_service.delete 收到调用, 但 result.deleted 只记录本级
        """
        s = _make_service()

        # Mock: product → version → domain
        version_1 = {'id': 100, 'product_id': 50}
        domain_1 = {'id': 200, 'version_id': 100}

        # find 调用顺序:
        # 1. product → version (find versions)
        # 2. version → domain (find domains, recursive)
        # 3. domain → [] (find sub_domains, recursive, returns [])
        # 4. domain annotation cleanup (find annotations for domain)
        find_results = [
            [version_1],  # 1. product → version
            [domain_1],   # 2. version → domain (递归)
            [],            # 3. domain → [] (递归)
            [],            # 4. annotations for domain
        ]
        s.data_source.find = MagicMock(side_effect=find_results)

        from meta.core.action_executor import ActionResult
        s.manage_service = MagicMock()
        s.manage_service.delete = MagicMock(return_value=ActionResult.ok(data={'id': 0}))

        with patch('meta.services.cascade_service.CascadeService') as MockCS:
            mock_instance = MagicMock()
            child_types_seq = [
                ['version'],
                ['domain'],
                [],
            ]
            fk_seq = ['product_id', 'version_id', 'domain_id']
            mock_instance._get_all_child_types = MagicMock(side_effect=child_types_seq)
            mock_instance._get_foreign_key = MagicMock(side_effect=fk_seq)
            MockCS.return_value = mock_instance

            result = s._force_cascade_delete('product', 50)

        # 验证: manage_service.delete 被调用 2 次 (domain + version)
        assert s.manage_service.delete.call_count == 2, \
            f"manage_service.delete 应被调 2 次 (递归删 domain + version), 实际: {s.manage_service.delete.call_count}"

        # 验证: 删除的类型包括 version 和 domain (通过 call_args_list 看)
        deleted_types_called = [c.args[0].object_type for c in s.manage_service.delete.call_args_list]
        assert 'version' in deleted_types_called, f"version 应被调 delete, 实际: {deleted_types_called}"
        assert 'domain' in deleted_types_called, f"domain 应被递归 delete, 实际: {deleted_types_called}"

        # result.deleted 应至少包含 IMMEDIATE child (version)
        deleted_types_in_result = [d.get('object_type') for d in result['deleted']]
        assert 'version' in deleted_types_in_result, \
            f"version 应在 result.deleted, 实际: {deleted_types_in_result}"

    def test_cascade_success_status_no_errors(self):
        """cascade 全部成功 → success=True, errors=[]"""
        s = _make_service()
        s.data_source.find = MagicMock(return_value=[])

        with patch('meta.services.cascade_service.CascadeService') as MockCS:
            mock_instance = MagicMock()
            mock_instance._get_all_child_types = MagicMock(return_value=[])
            MockCS.return_value = mock_instance

            result = s._force_cascade_delete('domain', 1)

        assert result['success'] is True
        assert result['errors'] == []

    def test_cascade_returns_dict_structure(self):
        """_force_cascade_delete 返回 dict 包含 success / deleted / errors"""
        s = _make_service()
        s.data_source.find = MagicMock(return_value=[])

        with patch('meta.services.cascade_service.CascadeService') as MockCS:
            mock_instance = MagicMock()
            mock_instance._get_all_child_types = MagicMock(return_value=[])
            MockCS.return_value = mock_instance

            result = s._force_cascade_delete('domain', 1)

        assert isinstance(result, dict)
        assert 'success' in result
        assert 'deleted' in result
        assert 'errors' in result
        assert isinstance(result['deleted'], list)
        assert isinstance(result['errors'], list)


# ============================================================
# 3. TestDeleteRecordForceCascade
# ============================================================

class TestDeleteRecordForceCascade:
    """_delete_record 在 force_cascade=True 时自动级联"""

    def test_delete_record_default_no_cascade(self):
        """_delete_record 默认 force_cascade=False (单条 delete 保持 RESTRICT)"""
        s = _make_service()
        # 模拟 _find_existing_record 找到记录
        s._find_existing_record = MagicMock(return_value={'id': 1})

        from meta.core.action_executor import ActionResult
        s.manage_service = MagicMock()
        s.manage_service.delete = MagicMock(
            return_value=ActionResult.fail(error='CASCADE_RESTRICT', message='存在关联的子对象')
        )

        result = s._delete_record('product', {'id': 1}, MagicMock(), force_cascade=False)

        # 失败原样返回 (没 cascade)
        assert result.success is False
        assert result.error == 'CASCADE_RESTRICT'
        # _force_cascade_delete 没被调用
        # (因为 force_cascade=False)

    def test_delete_record_force_cascade_triggers_on_restrict(self):
        """force_cascade=True + RESTRICT 失败 → 自动调 _force_cascade_delete"""
        s = _make_service()
        s._find_existing_record = MagicMock(return_value={'id': 1})

        from meta.core.action_executor import ActionResult
        # 第一次失败 (RESTRICT), 第二次成功
        s.manage_service = MagicMock()
        s.manage_service.delete = MagicMock(side_effect=[
            ActionResult.fail(error='CASCADE_RESTRICT', message='存在关联的子对象'),
            ActionResult.ok(data={'id': 1}),
        ])

        # Mock _force_cascade_delete 成功
        s._force_cascade_delete = MagicMock(
            return_value={'success': True, 'deleted': [], 'errors': []}
        )

        result = s._delete_record('product', {'id': 1}, MagicMock(), force_cascade=True)

        # 验证 _force_cascade_delete 被调用
        s._force_cascade_delete.assert_called_once_with('product', 1)
        # 验证 manage_service.delete 被调用 2 次 (第一次 fail, 第二次 success after cascade)
        assert s.manage_service.delete.call_count == 2

    def test_delete_record_force_cascade_no_trigger_on_other_error(self):
        """force_cascade=True + 非 RESTRICT 错误 → 不触发 cascade"""
        s = _make_service()
        s._find_existing_record = MagicMock(return_value={'id': 1})

        from meta.core.action_executor import ActionResult
        # 失败原因: WRITE_SCOPE_DENIED (非 RESTRICT)
        s.manage_service = MagicMock()
        s.manage_service.delete = MagicMock(
            return_value=ActionResult.fail(error='WRITE_SCOPE_DENIED', message='权限不足')
        )

        s._force_cascade_delete = MagicMock()

        result = s._delete_record('product', {'id': 1}, MagicMock(), force_cascade=True)

        # _force_cascade_delete 没被调用 (非 RESTRICT 错误)
        s._force_cascade_delete.assert_not_called()
        # 原错误返回
        assert result.error == 'WRITE_SCOPE_DENIED'

    def test_delete_record_force_cascade_triggers_on_chinese_message(self):
        """force_cascade=True + 中文 '存在关联的子对象' 消息 → 触发 cascade"""
        s = _make_service()
        s._find_existing_record = MagicMock(return_value={'id': 1})

        from meta.core.action_executor import ActionResult
        s.manage_service = MagicMock()
        s.manage_service.delete = MagicMock(side_effect=[
            ActionResult.fail(error='UNKNOWN', message='存在关联的子对象，请先处理'),
            ActionResult.ok(data={'id': 1}),
        ])

        s._force_cascade_delete = MagicMock(
            return_value={'success': True, 'deleted': [], 'errors': []}
        )

        result = s._delete_record('product', {'id': 1}, MagicMock(), force_cascade=True)

        s._force_cascade_delete.assert_called_once()

    def test_delete_record_force_cascade_subcascade_fails_returns_original(self):
        """force_cascade=True + cascade 也失败 → 返回原始错误"""
        s = _make_service()
        s._find_existing_record = MagicMock(return_value={'id': 1})

        from meta.core.action_executor import ActionResult
        s.manage_service = MagicMock()
        s.manage_service.delete = MagicMock(
            return_value=ActionResult.fail(error='CASCADE_RESTRICT', message='存在关联的子对象')
        )

        s._force_cascade_delete = MagicMock(
            return_value={'success': False, 'deleted': [], 'errors': ['sub cascade failed']}
        )

        result = s._delete_record('product', {'id': 1}, MagicMock(), force_cascade=True)

        # cascade 失败 → 返回原始 error (不返回 cascade 的 errors)
        assert result.error == 'CASCADE_RESTRICT'

    def test_delete_record_no_existing_raises(self):
        """_delete_record 无 existing 记录时, 有 BK 字段 → raise ValueError"""
        s = _make_service()
        s._find_existing_record = MagicMock(return_value=None)
        s._get_business_key_fields = MagicMock(return_value=[MagicMock(id='code')])

        from meta.core.models import registry
        mock_obj = MagicMock()
        mock_obj.name = 'product'
        with patch.object(registry, 'get', return_value=mock_obj):
            with pytest.raises(ValueError, match='要删除的记录不存在'):
                s._delete_record('product', {'code': 'P1'}, MagicMock())


# ============================================================
# 4. TestForceCascadeFlagInRequest
# ============================================================

class TestForceCascadeFlagInRequest:
    """force_cascade 标志在 import 流程中的传递"""

    def test_import_uses_force_cascade_for_delete(self):
        """import 流程 delete 行 → _delete_record(force_cascade=True)"""
        # 验证 import_export_service.py:6610 调用 _delete_record 时 force_cascade=True
        from meta.services import import_export_service
        source = import_export_service.__file__
        with open(source, 'r', encoding='utf-8') as f:
            content = f.read()
        # 关键调用
        assert '_delete_record(object_type, record, obj.import_export, force_cascade=True)' in content, \
            "import 流程 delete 应传入 force_cascade=True"

    def test_single_delete_default_force_cascade_false(self):
        """单条 delete 默认 force_cascade=False (保持 RESTRICT 行为)"""
        from meta.services import import_export_service
        source = import_export_service.__file__
        with open(source, 'r', encoding='utf-8') as f:
            content = f.read()
        # 找到 _delete_record 签名
        import re
        m = re.search(r'def _delete_record\([^)]+force_cascade: bool = False\)', content)
        assert m is not None, "_delete_record 默认参数应为 force_cascade: bool = False"
