# -*- coding: utf-8 -*-
"""
[NEW v3.20 2026-06-19] 文件名生成单元测试

覆盖场景：
1. _build_export_filename: 中文 + ASCII + 非法字符
2. _resolve_cascade_prefix: arch-data 走"架构数据", 其他走 objectname
3. _resolve_object_names: 多 object_type → 多中文名
4. GLOBAL_MENU_PREFIX_MAP: 全局菜单前缀映射

这些 helper 是 export_cascade / export_selected_types / export_template 文件名生成的 SSOT。
不测完整 export 流程（避免依赖 DB 快照），仅测纯函数 + mock registry。
"""

import sys
import os
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
))

from meta.services.import_export_service import (
    GLOBAL_MENU_PREFIX_MAP,
    ImportExportService,
)


# ===== fixture: 构造一个 minimal service, 不连 DB =====

def _make_service():
    """构造一个无 DB 依赖的 ImportExportService 实例用于 helper 测试"""
    service = ImportExportService.__new__(ImportExportService)
    service.data_source = MagicMock()
    return service


# ===== _build_export_filename =====

class TestBuildExportFilename:
    """SSOT 文件名生成：支持中文 + 非法字符清理"""

    def test_pure_ascii(self):
        s = _make_service()
        result = s._build_export_filename(["ProductA", "v1.0"], "20260619_143012")
        assert result == "ProductA_v1.0_20260619_143012.xlsx"

    def test_chinese_objectname(self):
        """[核心] 中文 objectname 保留 - 这是用户 v3.20 新需求"""
        s = _make_service()
        result = s._build_export_filename(["架构数据"], "20260619_143012")
        assert result == "架构数据_20260619_143012.xlsx"

    def test_mixed_chinese_and_ascii(self):
        s = _make_service()
        result = s._build_export_filename(["域", "子域", "template"], "20260619_143012")
        assert result == "域_子域_template_20260619_143012.xlsx"

    def test_invalid_chars_replaced(self):
        """Windows 非法字符 < > : " / \\ | ? * 替换为 _"""
        s = _make_service()
        result = s._build_export_filename(["a<b>c:d"], "20260619_143012")
        # < > : 都替换为 _, 然后合并连续 _
        assert "_" in result
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert result.endswith("_20260619_143012.xlsx")

    def test_empty_parts_skipped(self):
        s = _make_service()
        result = s._build_export_filename(["", None, "产品A"], "20260619_143012")
        assert result == "产品A_20260619_143012.xlsx"

    def test_default_timestamp(self):
        """不传 timestamp → 自动生成（格式: YYYYMMDD_HHMMSS）"""
        s = _make_service()
        result = s._build_export_filename(["域"])
        # 不强比较具体时间, 只验证格式
        assert result.startswith("域_")
        assert result.endswith(".xlsx")
        # timestamp 格式: 8位日期 + _ + 6位时间 = "YYYYMMDD_HHMMSS"
        import re
        assert re.search(r"_\d{8}_\d{6}\.xlsx$", result), f"unexpected: {result}"

    def test_no_parts_returns_just_timestamp(self):
        s = _make_service()
        result = s._build_export_filename([], "20260619_143012")
        assert result == "20260619_143012.xlsx"


# ===== _resolve_cascade_prefix =====

class TestResolveCascadePrefix:
    """级联导出前缀: arch-data 走"架构数据", 其他走 objectname"""

    def test_arch_data_menu_returns_global_prefix(self):
        """[核心] menu_code=arch-data → "架构数据" 前缀（用户 v3.20 新需求）"""
        s = _make_service()
        result = s._resolve_cascade_prefix("domain", menu_code="arch-data")
        assert result == "架构数据"

    def test_other_menu_uses_objectname(self):
        """非 arch-data 菜单 → 走起始对象的 objectname"""
        s = _make_service()
        # mock registry
        from meta.core import models as m_models
        original_get = m_models.registry.get
        try:
            mock_meta = MagicMock()
            mock_meta.name = "域"
            m_models.registry.get = MagicMock(return_value=mock_meta)
            result = s._resolve_cascade_prefix("domain", menu_code="some-other-menu")
            assert result == "域"
        finally:
            m_models.registry.get = original_get

    def test_no_menu_code_uses_objectname(self):
        s = _make_service()
        from meta.core import models as m_models
        original_get = m_models.registry.get
        try:
            mock_meta = MagicMock()
            mock_meta.name = "子域"
            m_models.registry.get = MagicMock(return_value=mock_meta)
            result = s._resolve_cascade_prefix("sub_domain", menu_code=None)
            assert result == "子域"
        finally:
            m_models.registry.get = original_get

    def test_unknown_object_falls_back_to_id(self):
        """registry 找不到 → 用 object_type 字符串"""
        s = _make_service()
        from meta.core import models as m_models
        original_get = m_models.registry.get
        try:
            m_models.registry.get = MagicMock(return_value=None)
            result = s._resolve_cascade_prefix("unknown_obj")
            assert result == "unknown_obj"
        finally:
            m_models.registry.get = original_get


# ===== _resolve_object_names =====

class TestResolveObjectNames:
    """多对象文件名前缀: object_type → 中文名列表"""

    def test_multiple_known_types(self):
        s = _make_service()
        from meta.core import models as m_models
        original_get = m_models.registry.get
        try:
            def fake_get(ot):
                m = MagicMock()
                m.name = {"domain": "域", "sub_domain": "子域"}.get(ot)
                return m
            m_models.registry.get = MagicMock(side_effect=fake_get)
            result = s._resolve_object_names(["domain", "sub_domain"])
            assert result == ["域", "子域"]
        finally:
            m_models.registry.get = original_get

    def test_mixed_known_and_unknown(self):
        """known → 中文, unknown → 原 ID 字符串"""
        s = _make_service()
        from meta.core import models as m_models
        original_get = m_models.registry.get
        try:
            def fake_get(ot):
                if ot == "domain":
                    m = MagicMock()
                    m.name = "域"
                    return m
                return None
            m_models.registry.get = MagicMock(side_effect=fake_get)
            result = s._resolve_object_names(["domain", "unknown_xyz"])
            assert result == ["域", "unknown_xyz"]
        finally:
            m_models.registry.get = original_get

    def test_skip_empty_values(self):
        s = _make_service()
        result = s._resolve_object_names(["", None, "domain"])
        # 空值被跳过, domain 会 fallback 到 ID（mock registry 返回 None）
        from meta.core import models as m_models
        original_get = m_models.registry.get
        try:
            m_models.registry.get = MagicMock(return_value=None)
            result = s._resolve_object_names(["", None, "domain"])
            assert result == ["domain"]
        finally:
            m_models.registry.get = original_get

    def test_empty_list_returns_empty(self):
        s = _make_service()
        assert s._resolve_object_names([]) == []
        assert s._resolve_object_names(None) == []


# ===== GLOBAL_MENU_PREFIX_MAP =====

class TestGlobalMenuPrefixMap:
    """全局菜单 → 文件名前缀的 SSOT 映射"""

    def test_arch_data_mapped(self):
        assert "arch-data" in GLOBAL_MENU_PREFIX_MAP
        assert GLOBAL_MENU_PREFIX_MAP["arch-data"] == "架构数据"

    def test_other_menus_not_present(self):
        """当前只有 arch-data, 后续新全局菜单要手动加"""
        assert "user-management" not in GLOBAL_MENU_PREFIX_MAP
        assert "system-admin" not in GLOBAL_MENU_PREFIX_MAP
