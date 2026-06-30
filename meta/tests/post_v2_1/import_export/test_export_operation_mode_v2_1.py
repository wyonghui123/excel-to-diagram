# -*- coding: utf-8 -*-
"""
test_export_operation_mode_v2_1.py

覆盖提交: 本会话修复 (BUG-V019 + ExportDialog frontend default)
依据: 用户报告 6月26日截图 + 反馈

测试:
- 操作模式列在第 1 列 (最左), 与历史用户原始模板一致
- 数据写入循环跳过操作模式列 (column=2 起)
- ExportDialog.vue 默认模式改为 'cascade'
- MetaListPage.vue / MultiObjectManagementPage.vue 不再传 :show-export-mode="true"
"""
import os
import sys
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = [
    pytest.mark.post_v2_1,
    pytest.mark.import_export,
]


# ============================================================
# 1. TestOperationModeColumnPosition  (BUG-V019)
# ============================================================

class TestOperationModeColumnPosition:
    """[FIX 2026-06-26 BUG-V019] 操作模式列在最左 (column=1)"""

    def test_op_cell_written_to_column_1(self):
        """操作模式 cell 写到 column=1 (最左), 不是 column=len(headers) (最右)"""
        from meta.services import import_export_service as ies_module
        source_path = ies_module.__file__

        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 关键: 操作模式 cell 用 column=1 写
        pattern = r'ws\.cell\(row=row_idx,\s*column=1,\s*value=["\']update - 更新["\']\)'
        matches = re.findall(pattern, content)
        assert len(matches) >= 1, \
            f"应至少 1 处操作模式 cell 写到 column=1, 实际: {len(matches)} 处\n" \
            f"查找模式: {pattern}"

        # 反向: 不应再有 column=len(headers) 的 op_cell 写入
        buggy_pattern = r'ws\.cell\(row=row_idx,\s*column=len\(headers\),\s*value=["\'](update|create)'
        buggy_matches = re.findall(buggy_pattern, content)
        assert len(buggy_matches) == 0, \
            f"不应再有 op_cell 写到 column=len(headers) (BUG-V019 已修复), 实际: {len(buggy_matches)} 处"

    def test_op_cell_write_in_create_branch(self):
        """create 行 (新增) 的操作模式 cell 也写到 column=1"""
        from meta.services import import_export_service as ies_module
        source_path = ies_module.__file__

        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        pattern = r'ws\.cell\(row=row_idx,\s*column=1,\s*value=["\']create - 新增["\']\)'
        matches = re.findall(pattern, content)
        assert len(matches) >= 1, \
            f"应至少 1 处 create 操作模式 cell 写到 column=1, 实际: {len(matches)} 处"

    def test_data_cycle_skips_operation_mode_column(self):
        """数据写入循环从 column=2 起始, 跳过 column=1 (操作模式列)"""
        from meta.services import import_export_service as ies_module
        source_path = ies_module.__file__

        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 关键: 主 sheet 数据循环使用 'headers[1:]' + start=2
        pattern = r'enumerate\(headers\[1:\]\s+if\s+include_operation_mode\s+else\s+headers,\s*2\s+if\s+include_operation_mode\s+else\s*1\)'
        matches = re.findall(pattern, content)
        assert len(matches) >= 1, \
            f"主 sheet 数据循环应使用 'headers[1:]' 跳过操作模式列, 实际: {len(matches)} 处"

    def test_actual_col_idx_offsets_by_operation_mode(self):
        """actual_col_idx 计算考虑 include_operation_mode 偏移"""
        from meta.services import import_export_service as ies_module
        source_path = ies_module.__file__

        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        pattern = r'actual_col_idx\s*=\s*col_idx\s*-\s*1\s*-\s*\(1\s+if\s+include_operation_mode\s+else\s*0\)'
        matches = re.findall(pattern, content)
        assert len(matches) >= 1, \
            f"actual_col_idx 应考虑 include_operation_mode 偏移, 实际: {len(matches)} 处"


# ============================================================
# 2. TestExportDialogFrontendDefault  (前端 ExportDialog)
# ============================================================

class TestExportDialogFrontendDefault:
    """[FIX 2026-06-26] ExportDialog 默认模式改为 'cascade'"""

    def test_export_dialog_default_cascade(self):
        """ExportDialog.vue 默认值是 'cascade', 不是 'single'"""
        export_dialog = PROJECT_ROOT / 'src' / 'components' / 'common' / 'ExportDialog' / 'ExportDialog.vue'
        with open(export_dialog, 'r', encoding='utf-8') as f:
            content = f.read()

        # 关键: localExportMode 默认值是 'cascade'
        pattern = r"localExportMode\s*=\s*ref\(props\.defaultExportMode\s*\|\|\s*['\"]cascade['\"]\)"
        matches = re.findall(pattern, content)
        assert len(matches) >= 1, \
            f"ExportDialog.vue 默认 localExportMode 应为 'cascade', 实际: {len(matches)} 处匹配"

    def test_export_dialog_default_cascade_in_reset(self):
        """ExportDialog.vue 的 resetState() 默认也使用 'cascade'"""
        export_dialog = PROJECT_ROOT / 'src' / 'components' / 'common' / 'ExportDialog' / 'ExportDialog.vue'
        with open(export_dialog, 'r', encoding='utf-8') as f:
            content = f.read()

        pattern = r"localExportMode\.value\s*=\s*props\.defaultExportMode\s*\|\|\s*['\"]cascade['\"]"
        matches = re.findall(pattern, content)
        assert len(matches) >= 1, \
            f"ExportDialog.vue resetState 应使用 'cascade', 实际: {len(matches)} 处匹配"

    def test_meta_list_page_no_show_export_mode(self):
        """MetaListPage.vue 不再传 :show-export-mode='true' (避免显示单对象/级联选择)"""
        meta_list = PROJECT_ROOT / 'src' / 'components' / 'common' / 'MetaListPage' / 'MetaListPage.vue'
        with open(meta_list, 'r', encoding='utf-8') as f:
            content = f.read()

        pattern = r':show-export-mode=["\']true["\']'
        matches = re.findall(pattern, content)
        assert len(matches) == 0, \
            f"MetaListPage.vue 不应再传 :show-export-mode='true', 实际: {len(matches)} 处"

    def test_multi_object_management_page_no_show_export_mode(self):
        """MultiObjectManagementPage.vue 不再传 :show-export-mode='true'"""
        multi_obj = PROJECT_ROOT / 'src' / 'components' / 'common' / 'MultiObjectManagementPage' / 'MultiObjectManagementPage.vue'
        with open(multi_obj, 'r', encoding='utf-8') as f:
            content = f.read()

        pattern = r':show-export-mode=["\']true["\']'
        matches = re.findall(pattern, content)
        assert len(matches) == 0, \
            f"MultiObjectManagementPage.vue 不应再传 :show-export-mode='true', 实际: {len(matches)} 处"


# ============================================================
# 3. TestExportColumnLayout  (整体列布局合理性)
# ============================================================

class TestExportColumnLayout:
    """[FIX 2026-06-26] 统一列布局模板"""

    def test_headers_insert_op_mode_at_position_0(self):
        """headers.insert(0, '操作模式') - 操作模式列通过 insert 添加到第 1 列"""
        from meta.services import import_export_service as ies_module
        source_path = ies_module.__file__

        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        pattern = r'headers\.insert\(0,\s*[\'\"](?:操作模式|Operation Mode)[\'\"]'
        matches = re.findall(pattern, content)
        assert len(matches) >= 1, \
            f"应有 headers.insert(0, '操作模式') 逻辑, 实际: {len(matches)} 处"

    def test_operation_mode_header_written_first(self):
        """操作模式 header cell 写到 column=1, value='操作模式'"""
        from meta.services import import_export_service as ies_module
        source_path = ies_module.__file__

        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        pattern = r'ws\.cell\(row=1,\s*column=1,\s*value=["\']操作模式["\']\)'
        matches = re.findall(pattern, content)
        assert len(matches) >= 1, \
            f"应有 ws.cell(row=1, column=1, value='操作模式') 写 header, 实际: {len(matches)} 处"


# ============================================================
# 4. TestExportVisibleYamlSettings  (yaml 配置正确性)
# ============================================================

class TestExportVisibleYamlSettings:
    """[FIX 2026-06-26] yaml 字段 export_visible 配置"""

    def test_export_visible_false_excludes_field(self):
        """导出服务排除 export_visible=False AND import_visible=False 的字段"""
        from meta.services import import_export_service as ies_module
        source_path = ies_module.__file__
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        pattern = r'if not is_cud_required and not is_business_key and export_vis is False and import_vis is False:\s*\n\s*continue'
        matches = re.findall(pattern, content)
        assert len(matches) >= 1, \
            f"导出服务应有 export_vis=False AND import_vis=False → continue 逻辑, 实际: {len(matches)} 处"

    def test_ui_visible_true_includes_field(self):
        """ui.visible=True 的字段进入 candidates (即使 export_visible=False)"""
        from meta.services import import_export_service as ies_module
        source_path = ies_module.__file__
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        pattern = r'if is_business_key or is_export or is_import or \(hasattr\(f,\s*[\'\"]ui[\'\"]\)\s+and\s+hasattr\(f\.ui,\s*[\'\"]visible[\'\"]\)\s+and\s+f\.ui\.visible\s+is\s+True\):'
        matches = re.findall(pattern, content)
        assert len(matches) >= 1, \
            f"导出服务应有 ui.visible=True → 进入 candidates 逻辑, 实际: {len(matches)} 处"

    def test_product_yaml_owner_id_visible_in_ui(self):
        """product.yaml 的 owner_id 设置 ui.visible: true (产品线 sheet 显示负责人)"""
        product_yaml = PROJECT_ROOT / 'meta' / 'schemas' / 'product.yaml'
        with open(product_yaml, 'r', encoding='utf-8') as f:
            content = f.read()

        # 在 owner_id 字段定义附近查找 ui.visible: true
        pattern = re.compile(
            r'-\s+id:\s+owner_id\s*\n(?:\s+\S.*\n)*?\s+ui:\s*\n(?:\s+\S.*\n)*?\s+visible:\s*true',
            re.MULTILINE
        )
        match = pattern.search(content)
        assert match is not None, \
            "product.yaml 的 owner_id 应设置 ui.visible: true (产品线 sheet 显示负责人列)"

    def test_version_yaml_no_owner_id_field(self):
        """version.yaml 不应有 owner_id 字段 (产品版本不显示负责人列)"""
        version_yaml = PROJECT_ROOT / 'meta' / 'schemas' / 'version.yaml'
        with open(version_yaml, 'r', encoding='utf-8') as f:
            content = f.read()

        # 关键: 不应有 '- id: owner_id' 字段定义
        # 注意: comments 或其他位置提到 owner_id 不算
        pattern = r'^-\s+id:\s+owner_id\s*$'
        matches = re.findall(pattern, content, re.MULTILINE)
        assert len(matches) == 0, \
            f"version.yaml 不应有 '- id: owner_id' 字段定义 (产品版本不显示负责人), 实际: {len(matches)} 处"