# -*- coding: utf-8 -*-
"""meta 包初始化"""

# 导出常用符号
from meta.core.yaml_loader import get_meta_object, load_meta_object

# [FIX 2026-06-12] 导出 registry 以兼容旧测试代码
from meta.core.models import registry as registry

__all__ = ['get_meta_object', 'load_meta_object', 'registry']
