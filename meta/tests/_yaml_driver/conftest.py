# -*- coding: utf-8 -*-
"""
yaml_driver 包的 conftest.py

注册 pytest fixture + hook, 让 test_*.py 自动获得:
    - meta_object_id (参数化)
    - meta_object (单对象)
    - meta_registry (整个 registry)
    - constraint_specs (推导出的约束)
"""
from meta.tests._yaml_driver.pytest_plugin import (
    pytest_addoption,
    pytest_generate_tests,
    meta_registry,
    meta_object,
    constraint_specs,
)