# -*- coding: utf-8 -*-
"""
test_bug_v027_annotation_child_sheet.py

覆盖 BUG-V027: 导出时"备注信息" (annotation) sheet 缺失

根因:
  - `_collect_child_object_types` 只从 yaml 的 `child_sections` 配置收集,
    但 product.yaml / version.yaml 等历史从未显式声明 `child_object: annotation`
  - annotation 是 polymorphic 关联 (target_type/target_id), 不走 parent_object 链
  - 导致 export 时 child_parent_map 不包含 annotation, 备注信息 sheet 缺失

修复:
  - `import_export_service._collect_child_object_types` 自动追加 polymorphic child: annotation
  - 任意 selected_types 都会把 annotation 加入 child_parent_map, 由 _query_child_object
    通过 polymorphic subquery 查询 (line 2813: 'annotation' → _query_annotations_impl)

依据:
  .trae/specs/test-suite/post-6-22-roadmap.md 主题 1 (Import/Export)
  fix 提交: BUG-V027
"""
import pytest
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def _ensure_registry():
    """确保 meta registry 加载了"""
    from meta.core.models import registry
    if registry.get('product') is None:
        from meta.core.yaml_loader import register_from_directory
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        register_from_directory(schemas_dir)


class TestBugV027AnnotationChildSheet:
    """BUG-V027: 导出时 annotation (备注信息) sheet 必须自动出现"""

    def test_collect_child_object_types_includes_annotation(self):
        """_collect_child_object_types 必须自动包含 annotation (即使 yaml 没配 child_sections)"""
        _ensure_registry()
        from meta.core.models import registry
        from meta.services.import_export_service import ImportExportService

        if registry.get('annotation') is None:
            pytest.skip('annotation schema not loaded')

        ie = ImportExportService(data_source=None)
        selected_types = ['product']
        result = ie._collect_child_object_types(selected_types)
        assert 'annotation' in result, \
            f"_collect_child_object_types 必须自动包含 annotation, 实际: {result}"
        assert 'product' in result['annotation'], \
            f"annotation 必须能关联到 product, 实际: {result}"

    def test_collect_child_object_types_version_includes_annotation(self):
        """version 也必须包含 annotation"""
        _ensure_registry()
        from meta.core.models import registry
        from meta.services.import_export_service import ImportExportService

        if registry.get('annotation') is None:
            pytest.skip('annotation schema not loaded')

        ie = ImportExportService(data_source=None)
        result = ie._collect_child_object_types(['version'])
        assert 'annotation' in result
        assert 'version' in result['annotation']

    def test_query_child_object_routes_annotation_to_polymorphic(self):
        """_query_child_object 对 annotation 应该走 polymorphic 路径"""
        _ensure_registry()
        from meta.core.models import registry
        from meta.services.import_export_service import ImportExportService

        if registry.get('annotation') is None:
            pytest.skip('annotation schema not loaded')

        ie = ImportExportService(data_source=None)
        # 模拟 _query_annotations_impl 已被替换, 验证路由正确
        called = []

        def fake_query(parent_types, filters=None):
            called.append(parent_types)
            return [{'id': 1, 'category': 'test', 'content': 'fake'}]

        ie._query_annotations_impl = fake_query
        result = ie._query_child_object('annotation', ['product'], None)
        assert result == [{'id': 1, 'category': 'test', 'content': 'fake'}]
        assert called == [['product']], \
            f"annotation 必须通过 _query_annotations_impl 调用, parent_types={called}"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])