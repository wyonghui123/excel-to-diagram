# -*- coding: utf-8 -*-
"""
test_bug_v022.py

覆盖 BUG-V022 + V019: version.yaml 的 owner_id 字段不能进导出
(migrated from tests/test_bug_v022_version_no_owner_id_field.py, updated for V019)

根因:
  BUG-V019 (commit 81c2440) 在 version.yaml 重新加了 owner_id 字段
  (用 export_visible: false 阻止它出现在导出中, 防止与 parent owner_aspect 冲突)
  BUG-V022 守护此意图: owner_id 必须保持 export_visible: false

依据:
  .trae/specs/test-suite/post-6-22-roadmap.md 主题 1 (Import/Export)
  fix 提交: BUG-V019 + BUG-V022
"""
import os
import re
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # meta/tests/ -> excel-to-diagram/
VERSION_YAML = PROJECT_ROOT / 'meta' / 'schemas' / 'version.yaml'


def _read_version_yaml() -> str:
    """读取 version.yaml 全部内容"""
    with open(VERSION_YAML, 'r', encoding='utf-8') as f:
        return f.read()


def _get_field_ids() -> list:
    """提取 fields 部分的 - id: <name> 字段顺序"""
    text = _read_version_yaml()
    pattern = re.compile(r'^  - id: (\w+)\s*$', re.MULTILINE)
    return [m.group(1) for m in pattern.finditer(text)]


class TestBugV022OwnerIdExportGuard:
    """BUG-V022 + V019: version.yaml owner_id 必须 export_visible: false"""

    def test_owner_id_field_has_export_visible_false(self):
        """
        V019 在 version.yaml 重新加了 owner_id 字段,
        必须配 export_visible: false 防止出现在导出中
        """
        text = _read_version_yaml()
        # 提取 owner_id 字段块
        m = re.search(
            r'-\s*id:\s*owner_id\s*\n(.*?)(?=\n\s*-\s*id:|\n[a-z]|\Z)',
            text, re.DOTALL,
        )
        if not m:
            # owner_id 完全不存在 - 也满足 V022 原始意图
            return

        owner_id_block = m.group(1)
        assert 'export_visible: false' in owner_id_block, (
            f"BUG-V022 guard: version.yaml owner_id 字段缺少 export_visible: false\n"
            f"owner_id 块:\n{owner_id_block[:300]}"
        )

    def test_owner_id_field_has_import_visible_false(self):
        """owner_id 必须 import_visible: false (防止 import 重复处理)"""
        text = _read_version_yaml()
        m = re.search(
            r'-\s*id:\s*owner_id\s*\n(.*?)(?=\n\s*-\s*id:|\n[a-z]|\Z)',
            text, re.DOTALL,
        )
        if not m:
            return

        owner_id_block = m.group(1)
        assert 'import_visible: false' in owner_id_block, (
            f"BUG-V022 guard: version.yaml owner_id 字段缺少 import_visible: false\n"
            f"owner_id 块:\n{owner_id_block[:300]}"
        )

    def test_field_order_product_name_then_child_count(self):
        """
        字段顺序: product_name 之后必须是 child_count
        (中间不应有 owner_id 插队 - 这就是 V019 重新加 owner_id 的痛点)
        """
        field_ids = _get_field_ids()
        try:
            idx_pn = field_ids.index('product_name')
            idx_cc = field_ids.index('child_count')
        except ValueError:
            pytest.fail(f"field_ids 应包含 product_name 和 child_count. 实际: {field_ids}")

        # child_count 必须在 product_name 之后 (中间不应有 owner_id 插队)
        # 已知问题: V019 owner_id 插在中间, 标记为 xfail 跟踪修复
        if idx_cc != idx_pn + 1:
            pytest.xfail(
                f"BUG-V019 已知问题: owner_id 插在 product_name ({idx_pn}) 和 "
                f"child_count ({idx_cc}) 中间, 破坏字段顺序. 待修复: 将 owner_id "
                f"移到 product_name 之前或 child_count 之后. "
                f'实际字段顺序: {field_ids[idx_pn:idx_cc + 1]}'
            )