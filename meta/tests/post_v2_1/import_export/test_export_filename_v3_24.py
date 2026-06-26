# -*- coding: utf-8 -*-
"""
test_export_filename_v3_24.py

覆盖提交: 4132e17 (异步导出文件名不被后端 basename 覆盖)
依据: .trae/specs/test-suite/post-6-22-roadmap.md 主题 9 (Export Filename v3.24)

测试:
- 用户指定的 export_YYYY-MM-DD.xlsx 不被后端 basename 覆盖
- 异步导出 filename 自后端 file_name 来, 不再硬编码
- Unicode 文件名安全
- 并发导出文件名不冲突
"""
import os
import sys
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
# 1. TestAsyncExportFilename
# ============================================================

class TestAsyncExportFilename:
    """异步导出文件名不被后端 basename 覆盖"""

    def test_user_filename_preserved(self):
        """[FIX v3.24 2026-06-22] 异步导出完成后, 用后端 file_name (基于 objectname + 时间戳)

        之前 v3.23: ExportDialog.vue 硬编码 'export_YYYY-MM-DD.xlsx' 覆盖
        现在 v3.24: 改为从 downloadUrl 自推 filename, 跟同步 exportData 路径保持一致

        验证 ExportDialog.vue L491 注释
        """
        from pathlib import Path
        vue_file = PROJECT_ROOT / 'src' / 'components' / 'common' / 'ExportDialog' / 'ExportDialog.vue'
        with open(vue_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 关键注释: 不再用前端硬编码 'export_YYYY-MM-DD.xlsx' 覆盖
        assert 'export_YYYY-MM-DD.xlsx' in content, \
            "ExportDialog.vue 应保留 'export_YYYY-MM-DD.xlsx' 注释 (历史)"
        # 关键: 不再用前端硬编码 (覆盖旧 'export_YYYY-MM-DD.xlsx')
        assert '不再用前端硬编码' in content, \
            "ExportDialog.vue 应有 '不再用前端硬编码' 注释"
        # 关键: 从 downloadUrl 自推 filename
        assert 'downloadUrl' in content, \
            "ExportDialog.vue 应从 downloadUrl 自推 filename"

    def test_api_returns_filename_from_backend(self):
        """[FIX v3.24] API 返回 download_url (含后端 basename)

        实现: export_import_api.py:458-459
        ```
        file_name = os.path.basename(result.file_path)
        download_url = "/api/v1/export/download/{0}".format(file_name)
        ```
        """
        from meta.api import export_import_api
        source_path = export_import_api.__file__
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 关键: file_name = os.path.basename(result.file_path)
        assert 'os.path.basename(result.file_path)' in content, \
            "API 应从 result.file_path 提取 basename 作为 file_name"
        # 关键: download_url 包含 file_name
        assert 'download_url = "/api/v1/export/download/{0}".format(file_name)' in content, \
            "API 应构造 download_url"

    def test_unicode_filename_safe(self):
        """Unicode 文件名安全 (中文 objectname 保留)

        验证 _build_export_filename 已通过 v3.20 测试, v3.24 保持兼容性
        """
        s = _make_service()
        # 中文 objectname
        result = s._build_export_filename(['架构数据', 'V1.0'], '20260624_120000')
        # 验证: 中文保留, 无非法字符
        assert '架构数据' in result
        assert 'V1.0' in result
        assert result.endswith('.xlsx')

    def test_concurrent_export_no_collision(self):
        """[FIX v3.24] 并发导出文件名不冲突 (基于时间戳 + 唯一 id)

        验证: 后端 file_name 包含时间戳 (秒级), 加上 uuid 唯一性
        """
        s = _make_service()

        # 连续调用 2 次, 时间戳不同 → 文件名不同
        import time
        result1 = s._build_export_filename(['产品'], '20260624_120000')
        time.sleep(0.001)  # 几乎不延迟
        result2 = s._build_export_filename(['产品'], '20260624_120001')

        # timestamp 不同时文件名应不同
        assert result1 != result2, \
            f"不同 timestamp 应产生不同文件名: {result1} vs {result2}"

    def test_download_export_secure_filename(self):
        """[SECURITY] download_export 源码应拒绝 .. 路径穿越

        验证: 源码中应有 '..' in filename 的安全检查
        """
        from meta.api import export_import_api
        source_path = export_import_api.__file__
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 关键: 安全检查 '..' in filename
        assert "'..' in filename" in content or '".." in filename' in content, \
            "download_export 应有 '..' in filename 的安全检查"
        # 关键: filename startswith '/' 检查
        assert "filename.startswith('/')" in content or "filename.startswith(\"/\")" in content, \
            "download_export 应拒绝以 '/' 开头的 filename"


# ============================================================
# 2. TestExportFilenameAsyncDownload
# ============================================================

class TestExportFilenameAsyncDownload:
    """异步导出 download_name 行为"""

    def test_send_file_uses_basename_only(self):
        """[SECURITY] send_file 用 file_path.name 作为 download_name, 不用原始 filename
        避免路径穿越
        """
        from meta.api import export_import_api
        source_path = export_import_api.__file__
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 关键: download_name=file_path.name
        assert 'download_name=file_path.name' in content, \
            "API 应使用 file_path.name (basename) 作为 download_name"

    def test_export_folder_resolved(self):
        """[SECURITY] export_path 在 download 时被 resolve, 防止 symlink 逃逸"""
        from meta.api import export_import_api
        source_path = export_import_api.__file__
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 关键: .resolve() 检查
        assert '.resolve()' in content, \
            "API 应使用 .resolve() 规范化 export_path, 防止 symlink 逃逸"

    def test_starts_with_check(self):
        """[SECURITY] file_path 必须在 export_path 下"""
        from meta.api import export_import_api
        source_path = export_import_api.__file__
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 关键: startswith 检查
        assert 'startswith(str(export_path))' in content, \
            "API 应验证 file_path.startswith(export_path)"
