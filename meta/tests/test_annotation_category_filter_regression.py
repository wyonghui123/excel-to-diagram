# -*- coding: utf-8 -*-
"""
[REGRESSION] annotation category filter 备注过滤守卫回归测试

## 背景

2026-06-30 修复 (commit 23dedbd / 5567e29):
"配置阶段不选备注类型时图表不展示任何备注"

用户反馈两个问题:
1. 配置阶段不选备注类型时, 图表中仍展示所有备注 (期望: 不展示任何备注)
2. 连线标签 tooltip 仍展示所有备注 (期望: 只展示过滤后的备注)

## 根因

- useAnnotation.parseAnnotationsFromData 无 filter 参数, hard-code 返回所有 annotation
- useTooltip.formatTooltipText 无 annotationFilter 参数, hard-code 拼接所有 annotationContent
- useTooltip.addMouseOverTooltips 无 annotationFilter 透传机制

## 修复 (commit 23dedbd)

1. useAnnotation.parseAnnotationsFromData (L30-136):
   - 接受 options.filter 参数
   - L130-132: 应用 category 过滤
     - filter = [] (用户未选) => 返回空数组 (不展示任何备注)
     - filter 非空 => 只保留 category 在 filter 中的 annotation

2. useTooltip.formatTooltipText (L184-255):
   - 接受 annotationFilter 参数
   - L231-248: 三分支逻辑
     - undefined (未传): 老逻辑 (单测兼容, 用 relation.annotationContent)
     - [] (空数组): 不展示备注行
     - 非空数组: 按 category 过滤

3. useTooltip.addMouseOverTooltips (L736):
   - 接受 annotationFilter = [] 参数 (默认空数组)
   - 透传到 setupLabelEvents (L753) 和 setupPathEvents (L757)
   - 调用 formatTooltipText(relation, annotationFilter)

## 复发风险

修复涉及 3 个守卫点, 任一被回退都会导致 BUG 复发:
- 守卫 1: parseAnnotationsFromData 的 filter 参数 + 三分支过滤逻辑
- 守卫 2: formatTooltipText 的 annotationFilter 参数 + 三分支逻辑
- 守卫 3: addMouseOverTooltips 透传 annotationFilter 到 setupLabelEvents/setupPathEvents

## 本文件覆盖

| ID | 测试 | 防止复发的守卫 |
|---|---|---|
| ANN-T1 | test_parse_annotations_accepts_filter_param | 守卫 1: parseAnnotationsFromData 接受 filter 参数 |
| ANN-T2 | test_parse_annotations_filter_empty_returns_empty | 守卫 1: filter=[] 返回空数组 |
| ANN-T3 | test_parse_annotations_filter_nonempty_filters_by_category | 守卫 1: filter 非空按 category 过滤 |
| ANN-T4 | test_format_tooltip_accepts_annotation_filter_param | 守卫 2: formatTooltipText 接受 annotationFilter 参数 |
| ANN-T5 | test_format_tooltip_undefined_fallback_old_logic | 守卫 2: undefined 走老逻辑 (向后兼容) |
| ANN-T6 | test_format_tooltip_empty_array_no_annotation | 守卫 2: [] 不展示备注 |
| ANN-T7 | test_format_tooltip_nonempty_filter_by_category | 守卫 2: 非空按 category 过滤 |
| ANN-T8 | test_add_mouse_over_tooltips_passes_annotation_filter | 守卫 3: addMouseOverTooltips 透传 annotationFilter |

## 测试策略

- 前端 JS: 源码字符串模式匹配 (无 JS runtime, 不执行 JS)
- 验证关键参数、三分支逻辑、透传机制存在

注意: annotation category filter 是纯前端逻辑, 无法通过 HTTP API 验证.
改用源码模式匹配 + 行为断言 (与 V033 相同策略).

参考:
- commit 23dedbd fix(object-scope): 修复树勾选级联 + 树收起 + 表格联动 + 备注过滤
- commit 5567e29 fix(object-scope): 修复树勾选级联 + 树收起 + 表格联动 + 备注过滤
- meta/docs/BUG_FIX_RECORD_20260630.md
- meta/verify_annotation_filter.js (JS 行为验证脚本)
"""

import re
import sys
from pathlib import Path

import pytest

# ─── 路径设置 ─────────────────────────────────────────────────────────────
# meta/tests/test_annotation_category_filter_regression.py -> 项目根 2 级向上
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

USE_ANNOTATION_PATH = (
    _PROJECT_ROOT / 'src' / 'composables' / 'useMermaid'
    / 'annotation' / 'useAnnotation.js'
)
USE_TOOLTIP_PATH = (
    _PROJECT_ROOT / 'src' / 'composables' / 'useMermaid'
    / 'tooltip' / 'useTooltip.js'
)


# ─── 辅助函数 ─────────────────────────────────────────────────────────────

def _read_annotation_source():
    """读取 useAnnotation.js 源码"""
    if not USE_ANNOTATION_PATH.exists():
        pytest.skip(f"useAnnotation.js 不存在: {USE_ANNOTATION_PATH}")
    return USE_ANNOTATION_PATH.read_text(encoding='utf-8')


def _read_tooltip_source():
    """读取 useTooltip.js 源码"""
    if not USE_TOOLTIP_PATH.exists():
        pytest.skip(f"useTooltip.js 不存在: {USE_TOOLTIP_PATH}")
    return USE_TOOLTIP_PATH.read_text(encoding='utf-8')


def _strip_js_comments(src):
    """移除 JS 注释行 (// 开头) 和块注释行 (* / /* 开头)

    避免注释中的文字被正则误匹配为真实代码
    """
    lines = src.split('\n')
    code_lines = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith('//'):
            continue
        if stripped.startswith('*') or stripped.startswith('/*'):
            continue
        code_lines.append(line)
    return '\n'.join(code_lines)


def _extract_function_body(src, func_name):
    """提取指定函数的函数体 (JS function/const)

    返回 (full_match, body) 或 (None, None)
    支持:
    - function name(args) { ... }
    - const name = (args) => { ... }
    - const name = function(args) { ... }
    """
    patterns = [
        # function name(args) {
        rf'function\s+{re.escape(func_name)}\s*\([^)]*\)\s*\{{',
        # const name = (args) => {
        rf'const\s+{re.escape(func_name)}\s*=\s*\([^)]*\)\s*=>\s*\{{',
        # const name = function(args) {
        rf'const\s+{re.escape(func_name)}\s*=\s*function\s*\([^)]*\)\s*\{{',
        # const name = (args) => {  (无括号箭头函数)
        rf'const\s+{re.escape(func_name)}\s*=\s*\([^)]*\)\s*=>\s*\{{',
    ]
    for pattern in patterns:
        m = re.search(pattern, src)
        if m:
            start = m.end()
            # 找下一个顶层 const/function/export
            next_func = re.search(
                r'\n(?:export\s+)?(?:const|function|let|var)\s+',
                src[start:]
            )
            end = start + next_func.start() if next_func else len(src)
            return src[m.start():end], src[start:end]
    return None, None


# ─── 测试类: 守卫 1 - parseAnnotationsFromData filter 参数 ───────────────

class TestParseAnnotationsFilterGuard:
    """ANN-T1/T2/T3: 防止 parseAnnotationsFromData 的 filter 守卫被移除

    修复前: 无 filter 参数, hard-code 返回所有 annotation
    修复后: 接受 options.filter, 三分支逻辑 (空数组/非空数组)
    """

    def test_parse_annotations_accepts_filter_param(self):
        """[ANN-T1] parseAnnotationsFromData 接受 filter 参数

        防止: 有人重构时去掉 filter 参数, 导致 category 过滤失效
        """
        src = _read_annotation_source()
        full, body = _extract_function_body(src, 'parseAnnotationsFromData')
        assert full, "parseAnnotationsFromData 函数未找到"

        # 验证 options 参数存在 (filter 从 options 解构)
        # 函数签名: (data, diagramType, options = {})
        sig_pattern = r'parseAnnotationsFromData\s*=\s*\([^)]*options[^)]*\)'
        assert re.search(sig_pattern, full), (
            "ANN 守卫 1 复发! parseAnnotationsFromData 缺少 options 参数. "
            "修复: 加 options = {} 参数, 从 options.filter 取过滤条件"
        )

        # 验证 filter 解构: const { filter = [] } = options
        destructure_pattern = r"const\s*\{\s*filter\s*=\s*\[\]\s*\}\s*=\s*options"
        assert re.search(destructure_pattern, body), (
            "ANN 守卫 1 复发! 缺少 'const { filter = [] } = options' 解构. "
            "修复: 从 options 解构 filter, 默认空数组 (用户未选)"
        )

    def test_parse_annotations_filter_empty_returns_empty(self):
        """[ANN-T2] filter=[] 时返回空数组

        防止: 有人把 'filter = [] => 返回空' 改成 'filter = [] => 返回所有',
        导致用户不选备注类型时仍展示所有备注
        """
        src = _read_annotation_source()
        full, body = _extract_function_body(src, 'parseAnnotationsFromData')
        assert full, "parseAnnotationsFromData 函数未找到"

        # 验证三分支逻辑: (Array.isArray(filter) && filter.length > 0) ? 过滤 : []
        # 关键: filter.length > 0 为 false 时 (即 filter=[]), 返回 []
        empty_pattern = r'filter\.length\s*>\s*0\s*\)\s*\?\s*result\.filter[^:]*:\s*\[\]'
        assert re.search(empty_pattern, body), (
            "ANN 守卫 1 复发! filter=[] 时未返回空数组. "
            "修复: (Array.isArray(filter) && filter.length > 0) ? result.filter(...) : []"
        )

    def test_parse_annotations_filter_nonempty_filters_by_category(self):
        """[ANN-T3] filter 非空时按 category 过滤

        防止: 有人把过滤条件从 'category 在 filter 中' 改成 'true' (恒通过),
        导致选一个 category 时所有备注都展示
        """
        src = _read_annotation_source()
        full, body = _extract_function_body(src, 'parseAnnotationsFromData')
        assert full, "parseAnnotationsFromData 函数未找到"

        # 验证过滤条件: ann.category && filter.includes(ann.category)
        # 关键: 必须检查 ann.category 在 filter 中, 不是恒 true
        filter_pattern = r'result\.filter\s*\(\s*ann\s*=>\s*ann\.category\s*&&\s*filter\.includes\s*\(\s*ann\.category\s*\)\s*\)'
        assert re.search(filter_pattern, body), (
            "ANN 守卫 1 复发! 过滤条件未用 'ann.category && filter.includes(ann.category)'. "
            "修复: result.filter(ann => ann.category && filter.includes(ann.category))"
        )


# ─── 测试类: 守卫 2 - formatTooltipText annotationFilter 参数 ─────────────

class TestFormatTooltipAnnotationFilterGuard:
    """ANN-T4/T5/T6/T7: 防止 formatTooltipText 的 annotationFilter 守卫被移除

    修复前: 无 annotationFilter 参数, hard-code 拼接所有 annotationContent
    修复后: 接受 annotationFilter, 三分支逻辑 (undefined/[]/非空)
    """

    def test_format_tooltip_accepts_annotation_filter_param(self):
        """[ANN-T4] formatTooltipText 接受 annotationFilter 参数

        防止: 有人重构时去掉 annotationFilter 参数, 导致 tooltip 过滤失效
        """
        src = _read_tooltip_source()
        full, body = _extract_function_body(src, 'formatTooltipText')
        assert full, "formatTooltipText 函数未找到"

        # 验证函数签名包含 annotationFilter 参数
        # const formatTooltipText = (relation, annotationFilter) => {
        sig_pattern = r'formatTooltipText\s*=\s*\(\s*relation\s*,\s*annotationFilter\s*\)'
        assert re.search(sig_pattern, full), (
            "ANN 守卫 2 复发! formatTooltipText 缺少 annotationFilter 参数. "
            "修复: 加 annotationFilter 参数, 用于按 category 过滤备注"
        )

    def test_format_tooltip_undefined_fallback_old_logic(self):
        """[ANN-T5] annotationFilter=undefined 走老逻辑 (向后兼容)

        防止: 有人删除 undefined 分支, 导致单测 (用 relation.annotationContent) 失败
        """
        src = _read_tooltip_source()
        full, body = _extract_function_body(src, 'formatTooltipText')
        assert full, "formatTooltipText 函数未找到"

        # 验证 undefined 分支: if (annotationFilter === undefined) { 走老逻辑 }
        undefined_pattern = r'if\s*\(\s*annotationFilter\s*===\s*undefined\s*\)'
        assert re.search(undefined_pattern, body), (
            "ANN 守卫 2 复发! 缺少 'if (annotationFilter === undefined)' 分支. "
            "修复: undefined 时走老逻辑 (relation.annotationContent), 向后兼容单测"
        )

        # 验证老逻辑: annotationLine = relation.annotationContent || ''
        old_logic_pattern = r'annotationLine\s*=\s*relation\.annotationContent\s*\|\|\s*[\'"]{2}'
        assert re.search(old_logic_pattern, body), (
            "ANN 守卫 2 复发! undefined 分支未用 'relation.annotationContent || \"\"'. "
            "修复: 老逻辑用 annotationLine = relation.annotationContent || '' (向后兼容)"
        )

    def test_format_tooltip_empty_array_no_annotation(self):
        """[ANN-T6] annotationFilter=[] 时不展示备注

        防止: 有人把 [] 分支改成展示所有备注, 导致用户不选类型时 tooltip 仍展示备注
        """
        src = _read_tooltip_source()
        full, body = _extract_function_body(src, 'formatTooltipText')
        assert full, "formatTooltipText 函数未找到"

        # 验证三分支结构: undefined / 非空数组 / (默认 [] 走空字符串)
        # 关键: annotationFilter === [] 时, 不进入 undefined 分支, 也不进入非空分支
        #        annotationLine 保持空字符串
        # 检测: else if (Array.isArray(annotationFilter) && annotationFilter.length > 0)
        nonempty_branch = r'else\s+if\s*\(\s*Array\.isArray\s*\(\s*annotationFilter\s*\)\s*&&\s*annotationFilter\.length\s*>\s*0\s*\)'
        assert re.search(nonempty_branch, body), (
            "ANN 守卫 2 复发! 缺少 'else if (Array.isArray(annotationFilter) && annotationFilter.length > 0)' 分支. "
            "修复: [] 时跳过此分支, annotationLine 保持空字符串 (不展示备注)"
        )

        # 验证: 仅在 annotationLine 非空时拼接 '备注:'
        # if (annotationLine) { text += '\\n备注: ' + annotationLine }
        append_pattern = r'if\s*\(\s*annotationLine\s*\)\s*\{[^}]*备注'
        assert re.search(append_pattern, body), (
            "ANN 守卫 2 复发! 缺少 'if (annotationLine)' 守卫, 导致空字符串也拼接 '备注:'. "
            "修复: 仅在 annotationLine 非空时拼接 '备注: ' + annotationLine"
        )

    def test_format_tooltip_nonempty_filter_by_category(self):
        """[ANN-T7] annotationFilter 非空时按 category 过滤

        防止: 有人把过滤条件改成恒 true, 导致选一个 category 时所有备注都展示
        """
        src = _read_tooltip_source()
        full, body = _extract_function_body(src, 'formatTooltipText')
        assert full, "formatTooltipText 函数未找到"

        # 验证过滤逻辑: .filter(item => item.content && item.category && annotationFilter.includes(item.category))
        filter_pattern = r'\.filter\s*\(\s*item\s*=>\s*item\.content\s*&&\s*item\.category\s*&&\s*annotationFilter\.includes\s*\(\s*item\.category\s*\)\s*\)'
        assert re.search(filter_pattern, body), (
            "ANN 守卫 2 复发! 非空 filter 分支未按 category 过滤. "
            "修复: .filter(item => item.content && item.category && annotationFilter.includes(item.category))"
        )


# ─── 测试类: 守卫 3 - addMouseOverTooltips 透传 annotationFilter ──────────

class TestAddMouseOverTooltipsPassesAnnotationFilter:
    """ANN-T8: 防止 addMouseOverTooltips 的 annotationFilter 透传被移除

    修复前: 无 annotationFilter 参数, tooltip 无法过滤
    修复后: 接受 annotationFilter = [] 参数, 透传到 setupLabelEvents/setupPathEvents
    """

    def test_add_mouse_over_tooltips_passes_annotation_filter(self):
        """[ANN-T8] addMouseOverTooltips 接受并透传 annotationFilter

        防止: 有人删除 annotationFilter 参数, 导致 tooltip 无法接收过滤条件
        """
        src = _read_tooltip_source()
        full, body = _extract_function_body(src, 'addMouseOverTooltips')
        assert full, "addMouseOverTooltips 函数未找到"

        # 验证函数签名包含 annotationFilter = [] (默认空数组)
        # const addMouseOverTooltips = (svg, relationDescriptions, diagramType, hideTails = false, annotationFilter = []) => {
        sig_pattern = r'addMouseOverTooltips\s*=\s*\([^)]*annotationFilter\s*=\s*\[\]'
        assert re.search(sig_pattern, full), (
            "ANN 守卫 3 复发! addMouseOverTooltips 缺少 'annotationFilter = []' 参数. "
            "修复: 加 annotationFilter = [] 默认参数 (用户未选时不展示备注)"
        )

        # 验证透传到 setupLabelEvents
        # 关键调用: setupLabelEvents(label, index, tooltip, ..., annotationFilter)
        pass_label_pattern = r'setupLabelEvents\s*\([^)]*annotationFilter\s*\)'
        assert re.search(pass_label_pattern, body), (
            "ANN 守卫 3 复发! setupLabelEvents 调用未透传 annotationFilter. "
            "修复: setupLabelEvents(..., annotationFilter) 透传到 label 事件"
        )

        # 验证透传到 setupPathEvents
        pass_path_pattern = r'setupPathEvents\s*\([^)]*annotationFilter\s*\)'
        assert re.search(pass_path_pattern, body), (
            "ANN 守卫 3 复发! setupPathEvents 调用未透传 annotationFilter. "
            "修复: setupPathEvents(..., annotationFilter) 透传到 path 事件"
        )

        # 验证 setupLabelEvents 中调用 formatTooltipText 时传入 annotationFilter
        # tooltipText = formatTooltipText(relation, annotationFilter)
        # 注意: 此调用在 setupLabelEvents 函数内, 不在 addMouseOverTooltips 函数体内
        # 我们用全文件搜索 (源码模式匹配)
        full_src = _read_tooltip_source()
        format_call_pattern = r'formatTooltipText\s*\(\s*relation\s*,\s*annotationFilter\s*\)'
        assert re.search(format_call_pattern, full_src), (
            "ANN 守卫 3 复发! formatTooltipText 调用未传 annotationFilter. "
            "修复: formatTooltipText(relation, annotationFilter) 透传到 tooltip 渲染"
        )


# ─── 入口 ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
