"""
ImportExportFactory (Phase 4 业务特定)
======================================

导入导出工厂: 用于 Excel/CSV 导入测试
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class ImportExportFactory(BaseFactory):
    """导入导出任务工厂"""

    _OBJECT_TYPE = 'import_export_task'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        suffix = unique_str(4)
        return {
            'task_type': 'import',
            'format': 'xlsx',
            'object_type': 'business_object',
            'filename': f'test_import_{n}_{suffix}.xlsx',
            'status': 'pending',
        }

    @classmethod
    def create_export(cls, cookie=None, **overrides) -> Dict[str, Any]:
        """创建导出任务"""
        return cls.create(cookie=cookie, task_type='export', **overrides)
