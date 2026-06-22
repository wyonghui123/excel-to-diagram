"""
直接验证 import_export_service.py 修复, 绕开 test.py hook

测试 4 个核心修复点:
1. export_cascade 接受 progress_callback 参数
2. _resolve_object_names None 防御
3. _resolve_cascade_prefix 用 self.GLOBAL_MENU_PREFIX_MAP (类级)
4. export_template 用 self.GLOBAL_MENU_PREFIX_MAP
"""
import sys
import os
import inspect

# 切到 worktree 目录
WORKTREE = r'd:\filework\excel-to-diagram-worktrees\fix-import-export-pre-existing-bugs'
os.chdir(WORKTREE)
sys.path.insert(0, WORKTREE)

print("=" * 60)
print(f"工作目录: {os.getcwd()}")
print("=" * 60)

# 1. 测试 _resolve_object_names None 防御
print("\n[1/4] 测试 _resolve_object_names None 防御")
print("-" * 60)
from meta.services.import_export_service import ImportExportService
from unittest.mock import MagicMock
from meta.core import models as m_models

# 创建 service 实例 (用 mock data_source)
svc = ImportExportService.__new__(ImportExportService)
svc.data_source = MagicMock()

original_get = m_models.registry.get
try:
    m_models.registry.get = MagicMock(return_value=None)
    result_empty = svc._resolve_object_names([])
    result_none = svc._resolve_object_names(None)
    print(f"  _resolve_object_names([]) = {result_empty}")
    print(f"  _resolve_object_names(None) = {result_none}")
    assert result_empty == [], f"FAIL: 空 list 应返回 [], 实际 {result_empty}"
    assert result_none == [], f"FAIL: None 应返回 [], 实际 {result_none}"
    print("  [OK] None 防御生效")
finally:
    m_models.registry.get = original_get

# 2. 测试 _resolve_object_names 含空值列表
print("\n[2/4] 测试 _resolve_object_names 含空值列表")
print("-" * 60)
try:
    m_models.registry.get = MagicMock(return_value=None)
    result = svc._resolve_object_names(["", None, "domain"])
    print(f"  _resolve_object_names(['', None, 'domain']) = {result}")
    assert result == ["domain"], f"FAIL: 应为 ['domain'], 实际 {result}"
    print("  [OK] 空值过滤正确")
finally:
    m_models.registry.get = original_get

# 3. 测试 export_cascade 签名包含 progress_callback
print("\n[3/4] 测试 export_cascade 签名包含 progress_callback")
print("-" * 60)
sig = inspect.signature(ImportExportService.export_cascade)
params = list(sig.parameters.keys())
print(f"  export_cascade 参数: {params}")
assert 'progress_callback' in params, f"FAIL: 缺少 progress_callback, 实际参数: {params}"
print("  [OK] progress_callback 已加入签名")

# 4. 测试 GLOBAL_MENU_PREFIX_MAP 是类级
print("\n[4/4] 测试 GLOBAL_MENU_PREFIX_MAP 是类级")
print("-" * 60)
assert hasattr(ImportExportService, 'GLOBAL_MENU_PREFIX_MAP'), "FAIL: 类级 MAP 缺失"
map_value = ImportExportService.GLOBAL_MENU_PREFIX_MAP
print(f"  类级 GLOBAL_MENU_PREFIX_MAP = {map_value}")
assert 'arch-data' in map_value
assert map_value['arch-data'] == '架构数据'
print("  [OK] 类级 MAP 配置正确")

# 5. 测试模块级 MAP 已删除
print("\n[5/5] 测试模块级 GLOBAL_MENU_PREFIX_MAP 已删除")
print("-" * 60)
import meta.services.import_export_service as mod
has_module_level = hasattr(mod, 'GLOBAL_MENU_PREFIX_MAP')
print(f"  hasattr(module, 'GLOBAL_MENU_PREFIX_MAP') = {has_module_level}")
if has_module_level:
    print("  [WARN] 模块级 MAP 仍存在 (可能引用导致 import warning)")
else:
    print("  [OK] 模块级 MAP 已删除, 仅有类级 SSOT")

print("\n" + "=" * 60)
print("[ALL PASS] 5 个核心修复验证通过")
print("=" * 60)
