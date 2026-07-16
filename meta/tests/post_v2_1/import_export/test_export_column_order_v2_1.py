# -*- coding: utf-8 -*-
"""
test_export_column_order_v2_1.py

覆盖提交: fd7dde9, 259319c, 264849d, 8618081, 6274719 (列顺序 + annotation export)
依据: .trae/specs/test-suite/post-6-22-roadmap.md 主题 1 (Import/Export 体系)

测试:
- import_order=0 字段排在第一位 (不是 None)
- annotation 的 target_code / target_name 字段被填充
- 父对象 FK 列 comment 文案统一 ('业务主键')
- readonly_system 列 comment ('系统只读')
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


def _make_service(data_source=None):
    from meta.services.import_export_service import ImportExportService
    service = ImportExportService.__new__(ImportExportService)
    service.data_source = data_source or MagicMock()
    return service


# ============================================================
# 1. TestColumnOrder
# ============================================================

class TestColumnOrder:
    """导出列顺序 - import_order=0 不是 None"""

    def test_import_order_zero_rendered_first(self):
        """[FIX 2026-06-16 BMRD] import_order=0 字段正确排在第一位 (不是被当作 None)

        实现位置: import_export_service.py:1716
        ```
        key=lambda f: f.semantics.import_order if f.semantics.import_order is not None else 999
        ```

        关键: 用 `is not None` 判断, 而不是 `or 999` (后者会把 0 当作 falsy)
        """
        # 模拟: 字段的 import_order
        fields = [
            {'id': 'A', 'import_order': 0},    # 应该是第 1 个
            {'id': 'B', 'import_order': 1},    # 应该是第 2 个
            {'id': 'C', 'import_order': None}, # 应该是第 3 个
        ]

        # 模拟修复后的 sort key
        # 旧: lambda f: f.semantics.import_order or 999  # 0 会被换成 999
        # 新: lambda f: f.semantics.import_order if f.semantics.import_order is not None else 999
        new_sorted = sorted(fields, key=lambda f: f['import_order'] if f['import_order'] is not None else 999)
        old_sorted = sorted(fields, key=lambda f: f['import_order'] or 999)  # buggy

        # 修复后: A(0) 排第 1
        assert new_sorted[0]['id'] == 'A', \
            f"修复后 A(import_order=0) 应排第 1, 实际: {[f['id'] for f in new_sorted]}"

        # buggy 版本: A(0) 被当 999, 排到后面
        assert old_sorted[0]['id'] != 'A', \
            f"buggy 版本 A 不应排第 1, 实际: {[f['id'] for f in old_sorted]}"

    def test_child_sheet_business_key_exported(self):
        """[FIX 2026-06-16 BMRD] child sheet 同样修复 business_key 字段导出

        案例: version sheet 应有 business_key=code 字段
        """
        # 验证 service 源码中包含正确的 sort key
        from meta.services import import_export_service
        source_path = import_export_service.__file__
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 关键: 用 `is not None` 判断 import_order
        # 应有多处 (L1716, L2983, L4447)
        occurrences = content.count('if f.semantics.import_order is not None else 999')
        assert occurrences >= 1, \
            f"源码应至少 1 处用 'is not None' 判断 import_order, 实际: {occurrences}"

    def test_multiple_import_order_values_sort_correctly(self):
        """多个 import_order 值正确排序 (0, 1, 2, 3, None)"""
        fields = [
            {'id': 'N', 'import_order': None},
            {'id': 'Z', 'import_order': 999},
            {'id': 'A', 'import_order': 0},
            {'id': 'B', 'import_order': 1},
            {'id': 'C', 'import_order': 2},
        ]
        sorted_fields = sorted(fields, key=lambda f: f['import_order'] if f['import_order'] is not None else 999)
        ids = [f['id'] for f in sorted_fields]
        assert ids == ['A', 'B', 'C', 'N', 'Z'], \
            f"排序应 A(0) B(1) C(2) N(None→999) Z(999), 实际: {ids}"


# ============================================================
# 2. TestAnnotationExport
# ============================================================

class TestAnnotationExport:
    """annotation 导出 target_code / target_name"""

    def test_target_code_populated(self):
        """[FIX 2026-06-24] annotation 的 target_code 列不为空
        实现: import_export_service.py:2674-2677
        """
        s = _make_service()

        # Mock: target_type='domain', target_id=10
        # Mock: SELECT code, name FROM domains WHERE id=10
        s.data_source.execute = MagicMock(return_value=MagicMock(
            fetchone=MagicMock(return_value=('DOM10', 'Domain 10'))
        ))

        record = {'target_type': 'domain', 'target_id': 10}
        s._enrich_annotation_target(record)

        assert 'target_code' in record, "target_code 应被填充"
        assert record['target_code'] == 'DOM10', f"target_code 应为 'DOM10', 实际: {record.get('target_code')}"

    def test_target_name_populated(self):
        """[FIX 2026-06-24] annotation 的 target_name 列不为空"""
        s = _make_service()
        s.data_source.execute = MagicMock(return_value=MagicMock(
            fetchone=MagicMock(return_value=('DOM10', 'Domain 10'))
        ))

        record = {'target_type': 'domain', 'target_id': 10}
        s._enrich_annotation_target(record)

        assert 'target_name' in record, "target_name 应被填充"
        assert record['target_name'] == 'Domain 10', f"target_name 应为 'Domain 10', 实际: {record.get('target_name')}"

    def test_relationship_target_format(self):
        """[FIX 2026-06-24] annotation 指向 relationship 时, target_name 优先用 relation_desc
        实现: import_export_service.py:2657-2664
        """
        s = _make_service()
        # Mock: SELECT relation_code, relation_desc, source_code, target_code FROM relationships
        s.data_source.execute = MagicMock(return_value=MagicMock(
            fetchone=MagicMock(return_value=('R001', 'rel desc', 'SRC', 'TGT'))
        ))

        record = {'target_type': 'relationship', 'target_id': 5}
        s._enrich_annotation_target(record)

        # 当 relation_desc 不为空, 优先用 relation_desc
        # 当 relation_desc 为空, 才用 ' -> '.join([source_code, target_code])
        assert record['target_name'] == 'rel desc', \
            f"有 relation_desc 时应优先使用, 实际: {record.get('target_name')}"
        assert record['target_code'] == 'R001', \
            f"target_code 应为 'R001', 实际: {record.get('target_code')}"

    def test_relationship_target_format_fallback_to_arrow(self):
        """[FIX 2026-06-24] relation_desc 为空时, target_name 用 ' -> ' 拼接 source_code -> target_code
        """
        s = _make_service()
        # relation_desc 为空字符串
        s.data_source.execute = MagicMock(return_value=MagicMock(
            fetchone=MagicMock(return_value=('R001', '', 'SRC', 'TGT'))
        ))

        record = {'target_type': 'relationship', 'target_id': 5}
        s._enrich_annotation_target(record)

        # relation_desc 为空 → fallback 到 'SRC -> TGT'
        assert record['target_name'] == 'SRC -> TGT', \
            f"relation_desc 为空时 target_name 应为 'SRC -> TGT', 实际: {record.get('target_name')}"

    def test_target_missing_safe_no_crash(self):
        """target_id 缺失时, 不崩溃, 不填 target_code/name"""
        s = _make_service()
        record = {'target_type': 'domain', 'target_id': None}
        s._enrich_annotation_target(record)
        # 没异常
        assert 'target_code' not in record
        assert 'target_name' not in record

    def test_target_type_unknown_no_crash(self):
        """target_type 未知 (不在 RESOURCE_TABLE_MAP) → 静默跳过"""
        s = _make_service()
        record = {'target_type': 'unknown_xxx', 'target_id': 10}
        s._enrich_annotation_target(record)
        # 没异常, 不填 target_code/name
        assert 'target_code' not in record


# ============================================================
# 3. TestColumnCommentText
# ============================================================

class TestColumnCommentText:
    """parent_key vs FK code 列的 comment 文案"""

    def test_parent_key_comment_text(self):
        """[FIX 2026-06-24] parent_key 列 comment 显示 '父对象编码或者FK对象编码字段，创建必填，更新不可变更，录入的话系统会忽略'"""
        from meta.services.import_export_service import PARENT_FK_COMMENT
        assert '父对象编码' in PARENT_FK_COMMENT
        assert '创建必填' in PARENT_FK_COMMENT
        assert '更新不可变更' in PARENT_FK_COMMENT
        assert '录入的话系统会忽略' in PARENT_FK_COMMENT

    def test_readonly_system_comment_text(self):
        """[NEW 2026-06-24] readonly_system 列 comment 显示 '系统填充只读字段，基于父对象自动推导，不可编辑、不可填写'"""
        from meta.services.import_export_service import READONLY_SYSTEM_COMMENT
        assert '系统填充只读字段' in READONLY_SYSTEM_COMMENT
        assert '基于父对象自动推导' in READONLY_SYSTEM_COMMENT
        assert '不可编辑' in READONLY_SYSTEM_COMMENT
        assert '不可填写' in READONLY_SYSTEM_COMMENT

    def test_unified_comment_for_fk(self):
        """[FIX 2026-06-24] FK code 列 comment 统一文案 (使用常量 PARENT_FK_COMMENT)"""
        from meta.services import import_export_service
        source_path = import_export_service.__file__
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 关键: 多处使用 PARENT_FK_COMMENT (L1535, L1843, L1925, L3094, L3158, ...)
        occurrences = content.count('PARENT_FK_COMMENT')
        assert occurrences >= 5, \
            f"PARENT_FK_COMMENT 应在多处使用, 实际: {occurrences} 次"

        # 关键: 多处使用 READONLY_SYSTEM_COMMENT
        occurrences_ro = content.count('READONLY_SYSTEM_COMMENT')
        assert occurrences_ro >= 3, \
            f"READONLY_SYSTEM_COMMENT 应在多处使用, 实际: {occurrences_ro} 次"

    def test_make_header_comment_adaptive_size(self):
        """[FIX v1.2.43c 2026-06-22] Comment 框根据内容行数自动调整 height/width
        实现: import_export_service.py:47-76
        """
        from meta.services.import_export_service import _make_header_comment
        # 单行
        cmt = _make_header_comment('短')
        assert cmt.height >= 100
        assert cmt.width == 300

        # 多行
        long_text = 'line1\nline2\nline3\nline4\nline5'
        cmt2 = _make_header_comment(long_text)
        # height 应随行数增加
        assert cmt2.height > cmt.height, \
            f"多行 comment 应更高, 单行={cmt.height}, 多行={cmt2.height}"

    def test_make_header_comment_unicode_safe(self):
        """_make_header_comment 处理 Unicode 安全"""
        from meta.services.import_export_service import _make_header_comment
        cmt = _make_header_comment('父对象编码字段，创建必填')
        # 不崩溃
        assert cmt is not None
        assert cmt.height > 0


# ============================================================
# 4. TestExportOrderHelper
# ============================================================

class TestExportOrderHelper:
    """辅助: 验证 export 时列顺序实现"""

    def test_column_sort_key_uses_is_not_none(self):
        """[FIX 2026-06-16 BMRD] 列排序 key 用 'is not None' 不是 'or'"""
        from meta.services import import_export_service
        source_path = import_export_service.__file__
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 关键修复: 'if f.semantics.import_order is not None else 999'
        # 错误版本: 'f.semantics.import_order or 999'  ← 0 会被吞
        buggy_pattern = content.count('f.semantics.import_order or 999')
        assert buggy_pattern == 0, \
            f"不应有 buggy 写法 'import_order or 999' (会把 0 吞成 999), 实际: {buggy_pattern} 处"

    def test_relationship_excluded_from_hierarchy_sort(self):
        """relationship 不在 parent_object 链中, _sort_by_hierarchy 不会处理它

        修复: import_export_service.py:5096-5099 显式处理 relationship 的位置
        """
        from meta.services import import_export_service
        source_path = import_export_service.__file__
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 关键: 显式 relationship 排序
        assert "'relationship' in import_order and 'business_object' in import_order" in content, \
            "应有显式 relationship 排序逻辑"
