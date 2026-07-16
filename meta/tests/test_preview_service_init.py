"""测试 preview_service 模块加载"""
import pytest


def test_preview_service_module_imports():
    """preview_service 模块应能正常导入"""
    from meta.services import preview_service
    assert preview_service is not None


def test_preview_service_has_aggregate_annotations():
    """preview_service 应包含 aggregate_annotations_for_targets 函数"""
    from meta.services.preview_service import aggregate_annotations_for_targets
    assert callable(aggregate_annotations_for_targets)