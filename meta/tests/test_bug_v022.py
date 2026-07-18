# -*- coding: utf-8 -*-
"""
test_bug_v022_version_no_owner_id_field.py

覆盖 BUG-V022: version.yaml 不应有 owner_id 字段定义 (回归保护)

根因:
  BUG-V019 (commit 81c2440) 在 version.yaml 加了 owner_id 字段
  即使 export_visible: false, 字段顺序也破坏了原版 (插在 product_name 和 child_count 之间)
  owner_aspect 已经定义 owner_id, 重复定义画蛇添足

依据:
  .trae/specs/test-suite/post-6-22-roadmap.md 主题 1 (Import/Export)
  fix 提交: BUG-V022
"""
import os
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
VERSION_YAML = PROJECT_ROOT / 'meta' / 'schemas' / 'version.yaml'


def _read_version_yaml() -> str:
    """读取 version.yaml 全部内容"""
    with open(VERSION_YAML, 'r', encoding='utf-8') as f:
        return f.read()


def _get_field_ids() -> list:
    """提取所有 - id: <name> 字段顺序"""
    import re
    text = _read_version_yaml()
    # 找 fields 部分的 - id: (4 spaces indent)
    pattern = re.compile(r'^  - id: (\w+)\s*$', re.MULTILINE)
    return [m.group(1) for m in pattern.finditer(text)]


class TestBugV022NoOwnerIdField:
    """BUG-V022: version.yaml 不应定义 owner_id 字段"""

    def test_owner_id_field_not_in_yaml(self):
        """version.yaml fields 中不应有 - id: owner_id"""
        field_ids = _get_field_ids()
        assert 'owner_id' not in field_ids, (
            f"BUG-V022: version.yaml 不应定义 owner_id 字段 "
            f'(应由 owner_aspect 继承). 实际 field_ids: {field_ids}'
        )

    def test_no_owner_id_block_in_yaml(self):
        """version.yaml 不应有完整的 owner_id 字段定义块"""
        text = _read_version_yaml()
        # 找任何 owner_id 字段定义 (含类型/语义等)
        # 检查常见的 pattern: "- id: owner_id" 后跟 type: integer
        bad_pattern = "- id: owner_id"
        assert bad_pattern not in text, (
            f"BUG-V022: version.yaml 包含 {bad_pattern} 字段定义, 应删除"
        )

    def test_field_order_product_name_then_child_count(self):
        """
        字段顺序: product_name 之后必须是 child_count (不应有 owner_id 插队)
        """
        field_ids = _get_field_ids()
        try:
            idx_pn = field_ids.index('product_name')
            idx_cc = field_ids.index('child_count')
        except ValueError:
            pytest.fail(f"field_ids 应包含 product_name 和 child_count. 实际: {field_ids}")

        # child_count 必须在 product_name 之后 (中间不应有 owner_id)
        assert idx_cc == idx_pn + 1, (
            f"BUG-V022: product_name (idx {idx_pn}) 和 child_count (idx {idx_cc}) "
            f'必须相邻. 实际字段顺序: {field_ids[idx_pn:idx_cc + 1]}'
        )

    def test_no_export_visible_owner_id_block(self):
        """
        即使 export_visible: false 也不应有 owner_id 字段
        (因为 export_visible: false 仍然会破坏字段顺序)
        """
        text = _read_version_yaml()
        # 不应有 owner_id 字段相关的 export_visible 配置
        assert 'version_id_export_visible_owner_id' not in text, (
            'BUG-V022: 不应有 owner_id 字段'
        )
        # 原始检测: 是否还有 owner_id 字段 (含 export_visible: false)
        if '- id: owner_id' in text and 'export_visible: false' in text:
            # 检查这两段是同一个 owner_id 字段
            lines = text.split('\n')
            owner_id_started = False
            for i, line in enumerate(lines):
                if '- id: owner_id' in line:
                    owner_id_started = True
                    # 看接下来 15 行内是否有 export_visible: false
                    next_15 = '\n'.join(lines[i:i + 15])
                    if 'export_visible: false' in next_15:
                        pytest.fail(
                            "BUG-V022: version.yaml 仍有 owner_id 字段 (即使 export_visible: false), 应删除"
                        )
            if owner_id_started:
                pytest.fail("BUG-V022: version.yaml 仍有 owner_id 字段, 应删除")
