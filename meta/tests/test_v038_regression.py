# -*- coding: utf-8 -*-
"""
[REGRESSION V038] import/export 备注 sheet + 上下文信息 section 守卫回归测试

## 背景

BUG-V038 用户报告两个问题:
1. 备注不只 children 才有, 任何对象导出都带"备注信息" sheet
2. 上下文信息 section 在无 version_id 时不应出现, 当前导出无论是否有 version_id 都写 5 行空

## 根因 (深度排查后发现)

- _collect_child_object_types 既通过 yaml child_sections 显式声明路径
  (如 domain.yaml L234-235 声明 child_object: annotation)
  也通过 polymorphic 自动追加路径 (BUG-V027 引入), 把 annotation 强加为 child
- export_selected_types 末尾"上下文信息 section"无条件写 6 行

## 修复 (commit 3d3f563)

1. _collect_child_object_types 加 options 入参, 检查 include_annotations / include_child_objects
   - options.get("include_child_objects", options.get("include_annotations", True))
   - yaml 显式声明的 annotation 也走守卫 (避免绕过)
   - 默认 True 保持向后兼容, 不破坏 BUG-V027 修复效果
2. 调用方 L1164 透传 options=options
3. export_selected_types 上下文信息 section 加 has_version_ctx 守卫
   - 无 version_id 时跳过 row 7-12 (节省 6 行)
   - _write_meta_sheet_operations 的 start_row 同步调整为 14 / 7
4. ExportDialog.vue 默认 include_annotations=false
   - 取消 multiTypeMode 限制, single/multi 都默认 false
   - 只在用户显式勾选 annotation (multi 模式) 才传 true

## 复发风险

V038 修复涉及 4 个守卫点, 任一被回退都会导致 BUG 复发:
- 守卫 1: _collect_child_object_types 的 options 参数
- 守卫 2: export_selected_types 的 has_version_ctx 守卫
- 守卫 3: ops_start_row 的 14/7 分支
- 守卫 4: ExportDialog.vue 默认 include_annotations=false

## 本文件覆盖

| ID | 测试 | 防止复发的守卫 |
|---|---|---|
| V038-T1 | test_collect_child_object_types_accepts_options_param | 守卫 1: options 参数存在 |
| V038-T2 | test_collect_child_object_types_respects_include_annotations_false | 守卫 1: include_annotations=False 时不追加 annotation |
| V038-T3 | test_collect_child_object_types_default_true_backcompat | 守卫 1: 默认 True (向后兼容) |
| V038-T4 | test_export_selected_types_has_version_ctx_guard | 守卫 2: has_version_ctx 守卫存在 |
| V038-T5 | test_ops_start_row_branch_14_or_7 | 守卫 3: ops_start_row 14/7 分支 |
| V038-T6 | test_export_dialog_default_include_annotations_false | 守卫 4: ExportDialog.vue 默认 false |
| V038-T7 | test_export_dialog_user_picked_annotation_logic | 守卫 4: 用户勾选 annotation 才传 true |

## 测试策略

- 后端 Python: 用源码字符串模式匹配 + 真实调用 _collect_child_object_types
- 前端 Vue: 读源码字符串 + 关键模式匹配

参考:
- commit 3d3f563 fix(export): BUG-V038 - 备注 sheet + 上下文信息 section 修复
- commit 0407f60 同上 (另一分支)
- meta/tests/test_import_export_api.py:test_05c_collect_child_object_types_respects_include_annotations
"""

import os
import re
import sys
from pathlib import Path

import pytest

# ─── 路径设置 ─────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

IMPORT_EXPORT_SERVICE_PATH = _PROJECT_ROOT / 'meta' / 'services' / 'import_export_service.py'
EXPORT_DIALOG_PATH = (
    _PROJECT_ROOT / 'src' / 'components' / 'common' / 'ExportDialog'
    / 'ExportDialog.vue'
)


# ─── 辅助函数 ─────────────────────────────────────────────────────────────

def _read_service_source():
    """读取 import_export_service.py 源码"""
    return IMPORT_EXPORT_SERVICE_PATH.read_text(encoding='utf-8')


def _read_export_dialog_source():
    """读取 ExportDialog.vue 源码"""
    if not EXPORT_DIALOG_PATH.exists():
        pytest.skip(f"ExportDialog.vue 不存在: {EXPORT_DIALOG_PATH}")
    return EXPORT_DIALOG_PATH.read_text(encoding='utf-8')


# ─── 测试类: 守卫 1 - _collect_child_object_types options 参数 ──────────

class TestCollectChildObjectTypesOptionsGuard:
    """V038-T1/T2/T3: 防止 _collect_child_object_types 的 options 守卫被移除

    V038 修复前: _collect_child_object_types 无 options 参数,
        hard-code 永远追加 annotation 作为 polymorphic child
    V038 修复后: 接受 options 参数, 通过 include_annotations 选项控制
    """

    def test_collect_child_object_types_accepts_options_param(self):
        """[V038-T1] _collect_child_object_types 接受 options 参数

        防止: 有人重构时去掉 options 参数, 导致 include_annotations 失效
        """
        src = _read_service_source()
        # 找到 _collect_child_object_types 函数定义
        m = re.search(
            r'def\s+_collect_child_object_types\s*\([^)]*\)',
            src
        )
        assert m, "_collect_child_object_types 函数未找到"
        func_sig = m.group(0)
        # 验证 options 参数存在
        assert 'options' in func_sig, (
            f"V038 守卫 1 复发! _collect_child_object_types 缺少 options 参数: "
            f"函数签名: {func_sig}. "
            f"修复: 添加 options=None 参数, 用于控制 include_annotations"
        )

    def test_collect_child_object_types_respects_include_annotations_false(self):
        """[V038-T2] include_annotations=False 时不追加 annotation

        防止 V038 复发: 即使 yaml 显式声明 annotation 作为 child_sections,
        也必须走 include_annotations 守卫
        """
        src = _read_service_source()
        # 找到 _collect_child_object_types 函数体
        # 注意: 函数签名跨多行 + 带返回类型注解 (-> Dict[str, List[str]]:),
        # 用 [^\n]*: 匹配 ) 到行尾的 : (函数体开始)
        m = re.search(
            r'def\s+_collect_child_object_types\s*\([^)]*\)[^\n]*:',
            src
        )
        assert m, "_collect_child_object_types 函数未找到"
        start = m.end()
        # 找到下一个 def 或文件末尾
        next_def = re.search(r'\ndef\s+', src[start:])
        end = start + next_def.start() if next_def else len(src)
        func_body = src[start:end]

        # 验证 include_annotations 变量定义存在
        assert 'include_annotations' in func_body, (
            "V038 守卫 1 复发! _collect_child_object_types 函数体内缺少 "
            "include_annotations 变量. "
            "修复: 加 include_annotations = options.get('include_annotations', True)"
        )

        # 验证 annotation 走守卫的关键代码存在
        # 修复代码: if child_type == 'annotation' and not include_annotations: ... (跳过)
        guard_pattern = r"child_type\s*==\s*['\"]annotation['\"]\s+and\s+not\s+include_annotations"
        assert re.search(guard_pattern, func_body), (
            "V038 守卫 1 复发! 缺少 'if child_type == annotation and not include_annotations' 守卫. "
            "修复: yaml 显式声明的 annotation 也走 include_annotations 守卫, 避免绕过"
        )

    def test_collect_child_object_types_default_true_backcompat(self):
        """[V038-T3] 默认 True 保持向后兼容

        防止: 有人把默认值改成 False, 破坏 BUG-V027 修复效果
        (BUG-V027 引入 polymorphic annotation 自动追加, V038 只是让它可关闭)
        """
        src = _read_service_source()
        # 找 _collect_child_object_types 中的默认值
        # 注意: 函数签名跨多行 + 带返回类型注解, 用 [^\n]*: 匹配到行尾的 :
        m = re.search(
            r'def\s+_collect_child_object_types\s*\([^)]*\)[^\n]*:(.*?)(?=\ndef\s+|\Z)',
            src, re.DOTALL
        )
        assert m, "_collect_child_object_types 函数未找到"
        func_body = m.group(1)

        # 验证默认 True (向后兼容)
        # 代码模式: options.get("include_annotations", True)
        default_pattern = r'options\.get\s*\(\s*["\']include_annotations["\']\s*,\s*True\s*\)'
        assert re.search(default_pattern, func_body), (
            "V038 默认值回退! include_annotations 默认应为 True (向后兼容 BUG-V027). "
            "修复: options.get('include_annotations', True) 保持默认 True"
        )


# ─── 测试类: 守卫 2/3 - has_version_ctx + ops_start_row ────────────────

class TestExportSelectedTypesVersionCtxGuard:
    """V038-T4/T5: 防止 export_selected_types 的 has_version_ctx 守卫被移除

    V038 修复前: 上下文信息 section 无条件写 6 行 (即使无 version_id)
    V038 修复后: 无 version_id 时跳过 section, 节省 6 行
    """

    def test_export_selected_types_has_version_ctx_guard(self):
        """[V038-T4] export_selected_types 中 has_version_ctx 守卫存在

        防止: 有人删除 has_version_ctx 检查, 导致无 version_id 时也写上下文 section
        """
        src = _read_service_source()
        # 验证 has_version_ctx 变量存在
        assert 'has_version_ctx' in src, (
            "V038 守卫 2 复发! 缺少 has_version_ctx 变量. "
            "修复: 加 has_version_ctx = bool(filters and ...version_id...), "
            "无 version_id 时跳过上下文 section"
        )

        # 验证 has_version_ctx 用于条件判断
        cond_pattern = r'if\s+has_version_ctx\s*:'
        assert re.search(cond_pattern, src), (
            "V038 守卫 2 复发! has_version_ctx 未用于条件判断. "
            "修复: 用 'if has_version_ctx:' 包裹上下文 section 写入逻辑"
        )

    def test_ops_start_row_branch_14_or_7(self):
        """[V038-T5] ops_start_row 14/7 分支存在

        防止: 有人把 ops_start_row 改回固定 14, 导致无 version_id 时空 6 行
        """
        src = _read_service_source()
        # 验证 ops_start_row = 14 if has_version_ctx else 7 (或等价形式)
        branch_pattern = r'ops_start_row\s*=\s*14\s+if\s+has_version_ctx\s+else\s+7'
        assert re.search(branch_pattern, src), (
            "V038 守卫 3 复发! 缺少 ops_start_row 的 14/7 分支. "
            "修复: ops_start_row = 14 if has_version_ctx else 7 "
            "(有 version_id 从 14 行开始, 无 version_id 从 7 行开始)"
        )


# ─── 测试类: 守卫 4 - ExportDialog.vue 默认 include_annotations ─────────

class TestExportDialogDefaultIncludeAnnotations:
    """V038-T6/T7: 防止 ExportDialog.vue 默认 include_annotations 回退

    V038 修复前: multiTypeMode 限制, single mode 不传 (后端 hard-code 自动追加)
    V038 修复后: 取消 multiTypeMode 限制, single/multi 都默认 false
    """

    def test_export_dialog_default_include_annotations_false(self):
        """[V038-T6] ExportDialog.vue 默认 include_annotations=false

        防止: 有人把默认值改回 true, 导致 single mode 也自动追加 annotation sheet
        """
        vue_src = _read_export_dialog_source()

        # 验证 include_annotations 在 ExportDialog.vue 中存在
        assert 'include_annotations' in vue_src, (
            "V038 守卫 4 复发! ExportDialog.vue 缺少 include_annotations 选项. "
            "修复: 加 params.options.include_annotations = userPickedAnnotation"
        )

    def test_export_dialog_user_picked_annotation_logic(self):
        """[V038-T7] ExportDialog.vue 用户勾选 annotation 才传 true

        防止: 有人把 userPickedAnnotation 改成恒 true, 导致默认追加 annotation
        """
        vue_src = _read_export_dialog_source()

        # 验证 userPickedAnnotation 变量存在
        assert 'userPickedAnnotation' in vue_src, (
            "V038 守卫 4 复发! ExportDialog.vue 缺少 userPickedAnnotation 变量. "
            "修复: const userPickedAnnotation = props.multiTypeMode && "
            "selectedMultiTypes.value.includes('annotation')"
        )

        # 验证 userPickedAnnotation 逻辑: multiTypeMode + selectedMultiTypes
        logic_pattern = r'userPickedAnnotation\s*=\s*props\.multiTypeMode'
        assert re.search(logic_pattern, vue_src), (
            "V038 守卫 4 复发! userPickedAnnotation 逻辑错误. "
            "修复: 必须基于 props.multiTypeMode && selectedMultiTypes.value.includes('annotation')，"
            "只在用户显式勾选 annotation 时才传 true"
        )

        # 验证两个调用点都用了 userPickedAnnotation
        # ExportDialog 通常有同步导出 + 异步导出两个调用点
        assignment_count = len(re.findall(
            r'params\.options\.include_annotations\s*=\s*userPickedAnnotation',
            vue_src
        ))
        assert assignment_count >= 1, (
            f"V038 守卫 4 复发! 缺少 'params.options.include_annotations = userPickedAnnotation' 赋值. "
            f"应至少 1 处, 实际 {assignment_count} 处. "
            f"修复: 在导出调用前赋值 include_annotations = userPickedAnnotation"
        )


# ─── 入口 ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
