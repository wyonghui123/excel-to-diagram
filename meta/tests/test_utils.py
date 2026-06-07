import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
测试工具模块
提供测试所需的通用工具函数和规范
"""

import os
import sys

# ==============================================================================
# 数据库路径规范
# ==============================================================================
#
# 重要：禁止在测试代码中硬编码数据库路径！
#
# 错误示例：
#   get_data_source("sqlite", database="architecture.db")
#   get_data_source("sqlite", database="meta/architecture.db")
#
# 正确示例：
#   get_data_source("sqlite", database=get_test_db_path())
#
# 原因：
# - 相对路径在不同工作目录下解析到不同位置
# - API 使用 server.py 所在目录的数据库，即 meta/architecture.db
# - 测试应使用与 API 相同的数据库以确保一致性
#
# ==============================================================================

def get_meta_db_path():
    """
    获取 meta 模块数据库的绝对路径

    API 使用 server.py 所在目录的 architecture.db
    即 {project_root}/meta/architecture.db

    Returns:
        str: 数据库文件的绝对路径
    """
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')


def get_test_db_path():
    """
    获取测试数据库的绝对路径

    优先使用 SQLITE_DB_PATH 环境变量（test.py 快照路径），
    避免 fixture 查询生产 DB 但 API 访问快照导致的 ID 不匹配问题。

    Returns:
        str: 数据库文件的绝对路径
    """
    env_path = os.environ.get('SQLITE_DB_PATH')
    if env_path:
        return env_path
    return get_meta_db_path()


def get_data_source_for_test():
    """
    获取测试用数据源（使用统一路径）

    Returns:
        DataSource: 数据源实例
    """
    from meta.core.datasource import get_data_source
    return get_data_source("sqlite", database=get_test_db_path())


# ==============================================================================
# Excel 文件测试工具
# ==============================================================================

def create_test_workbook(child_type='annotation', data=None):
    """
    创建测试用子对象 Sheet 的 Workbook（纯内存，不写磁盘）

    用法：
        wb, meta = create_test_workbook('annotation')
        ws = wb.worksheets[0]
        assert ws.cell(row=1, column=1).fill.start_color.rgb == "004472C4"

    Args:
        child_type: 子对象类型（如 'annotation'）
        data: 测试数据列表，None 则使用默认数据

    Returns:
        tuple: (openpyxl.Workbook, MetaObject) 工作簿和元模型
    """
    from meta.core.models import registry
    from meta.core.datasource import get_data_source
    from meta.services.manage_service import ManageService
    from meta.services.query_service import QueryService
    from meta.services.import_export_service import ImportExportService
    from openpyxl import Workbook

    child_meta = registry.get(child_type)
    if not child_meta:
        raise ValueError(f"找不到 {child_type} 元模型")

    if data is None:
        data = [{
            'id': 1,
            'target_type': 'domain',
            'target_id': 10,
            'target_code': 'DM001',
            'target_name': '测试领域',
            'category': 'important',
            'content': '测试备注内容',
            'category_label': '重要',
        }]

    ds = get_data_source('sqlite', database=get_test_db_path())
    ie_service = ImportExportService(ds, ManageService(ds), QueryService(ds))

    wb = Workbook()
    wb.remove(wb.active)
    sheets_info = []
    ie_service._write_child_sheet(wb, child_type, child_meta, data, sheets_info)
    return wb, child_meta


def get_cell_fill_rgb(cell):
    """
    获取单元格填充色的 RGB 字符串（6位，不含 alpha 前缀）

    openpyxl 的 cell.fill.start_color.rgb 返回 8 位字符串（如 "00E0E0E0"），
    此函数返回后 6 位（如 "E0E0E0"），便于与 CSS 颜色值比较。

    Args:
        cell: openpyxl Cell 对象

    Returns:
        str: 6 位 RGB 字符串（如 "E0E0E0"），无填充时返回 None
    """
    if not cell.fill or not cell.fill.start_color:
        return None
    rgb = cell.fill.start_color.rgb
    if rgb and len(rgb) == 8:
        return rgb[2:]
    return rgb


def assert_cell_fill(cell, expected_rgb6, msg=None):
    """
    断言单元格填充色匹配预期（6位 RGB，如 "E0E0E0"）

    Args:
        cell: openpyxl Cell 对象
        expected_rgb6: 6 位 RGB 字符串（如 "E0E0E0"）
        msg: 断言失败时的附加信息
    """
    actual = get_cell_fill_rgb(cell)
    default_msg = f"填充色应为 {expected_rgb6}，实际: {actual}"
    assert actual == expected_rgb6, msg or default_msg
