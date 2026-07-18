# -*- coding: utf-8 -*-
"""
[REGRESSION V033] archDataConverter 反查 name 映射回归测试

## 背景

BUG-V033 用户报告:
- 架构图过滤时, "可用子领域/领域" 列表为空 (availableSubDomains/Domains 返回空数组)
- "可用服务模块" 显示编码 (如 INV) 而非中文名 (如 "库存管理")

## 根因

V863 历史 BO/SM 的冗余列 domain_name/sub_domain_name/service_module_name 全是 NULL
(这些列只在 INSERT 时由 trigger 维护, 历史 2850 条 BO 全是 NULL).

archDataConverter.js 三个函数直接读冗余列作为主数据源:
1. buildDomainProducts: 读 bo.domain_name/sub_domain_name
2. buildServiceModules: 读 sm.sub_domain_name/domain_name
3. buildPreviewDataFromArchData: 读 bo.domain_name/sub_domain_name

导致前端 availableSubDomains/Domains 因 falsy 过滤返回空数组,
availableServiceModules fallback 到编码 (INV) 而非中文名 (库存管理).

## 修复 (commit 8a21db4)

修复策略: **反查 name 映射, 不依赖冗余列**

1. buildDomainProducts (L50-152):
   - 新增 smNameMap, sdNameMap, dNameMap 三个 Map
   - BO 处理时若 sdName/dName 为空, 通过 serviceModuleMap 反查 sd, 再反查 d

2. buildServiceModules (L154-181):
   - 新增 sdMap, dMap 反查 Map
   - subDomain/domain 字段: `sd?.name || sm.sub_domain_name || ''` (反查优先, 冗余列兜底)

3. buildPreviewDataFromArchData (L219-300):
   - 新增 smCodeMap, smNameMap, sdMap, dMap 反查 Map
   - BO 处理时多层 fallback: 通过 smId 反查 sd, 通过 sdId 反查 d

## 复发风险

V033 修复涉及 3 个函数的反查逻辑, 任一被回退都会导致 BUG 复发:
- 守卫 1: buildDomainProducts 的 smNameMap/sdNameMap/dNameMap + BO 反查
- 守卫 2: buildServiceModules 的 sdMap/dMap + 反查优先 fallback
- 守卫 3: buildPreviewDataFromArchData 的 smCodeMap/smNameMap/sdMap/dMap + 多层 fallback

## 本文件覆盖

| ID | 测试 | 防止复发的守卫 |
|---|---|---|
| V033-T1 | test_build_domain_products_has_name_maps | 守卫 1: smNameMap/sdNameMap/dNameMap 存在 |
| V033-T2 | test_build_domain_products_bo_fallback_lookup | 守卫 1: BO 反查逻辑 (sdName/dName 空时通过 serviceModuleMap) |
| V033-T3 | test_build_service_modules_has_sd_d_maps | 守卫 2: sdMap/dMap 反查 Map 存在 |
| V033-T4 | test_build_service_modules_fallback_order | 守卫 2: sd?.name || sm.sub_domain_name 反查优先 |
| V033-T5 | test_build_preview_data_has_name_maps | 守卫 3: smCodeMap/smNameMap/sdMap/dMap 存在 |
| V033-T6 | test_build_preview_data_bo_fallback_lookup | 守卫 3: BO 多层 fallback 反查逻辑 |
| V033-T7 | test_no_direct_redundant_column_as_primary | 守卫 4: 不应直接读 bo.domain_name 作为主数据源 |

## 测试策略

- 前端 JS: 源码字符串模式匹配 (无 JS runtime, 不执行 JS)
- 验证关键 Map 变量、反查逻辑、fallback 顺序存在

参考:
- commit 8a21db4 fix(fe): BUG-V033 archDataConverter 反查 name 映射 (不依赖冗余列)
- commit e564c7c fix(diagram): BUG-V033 中心+关系范围合并显示 (调试暴露)
"""

import os
import re
import sys
from pathlib import Path

import pytest

# ─── 路径设置 ─────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

ARCH_DATA_CONVERTER_PATH = (
    _PROJECT_ROOT / 'src' / 'services' / 'archDataConverter.js'
)


# ─── 辅助函数 ─────────────────────────────────────────────────────────────

def _read_converter_source():
    """读取 archDataConverter.js 源码"""
    if not ARCH_DATA_CONVERTER_PATH.exists():
        pytest.skip(f"archDataConverter.js 不存在: {ARCH_DATA_CONVERTER_PATH}")
    return ARCH_DATA_CONVERTER_PATH.read_text(encoding='utf-8')


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
    """提取指定函数的函数体 (从 def 到下一个同级 def 或文件末尾)

    返回 (full_match, body) 或 (None, None)
    """
    # 匹配 function name(...) { ... } 或 export function name(...) { ... }
    # JS 函数定义: function name(args) {
    pattern = rf'(?:export\s+)?function\s+{re.escape(func_name)}\s*\([^)]*\)\s*\{{'
    m = re.search(pattern, src)
    if not m:
        return None, None
    start = m.end()
    # 找到匹配的 } (简单版: 找下一个顶层 function 或文件末尾)
    # 实际 JS 嵌套 {} 较复杂, 这里用启发式: 找下一个 "^function " 或 "^export function"
    next_func = re.search(r'\n(?:export\s+)?function\s+', src[start:])
    end = start + next_func.start() if next_func else len(src)
    return src[m.start():end], src[start:end]


# ─── 测试类: 守卫 1 - buildDomainProducts 反查 name 映射 ─────────────────

class TestBuildDomainProductsNameMaps:
    """V033-T1/T2: 防止 buildDomainProducts 的反查 name 映射被移除

    V033 修复前: 直接读 bo.domain_name/sub_domain_name (冗余列, V863 全 NULL)
    V033 修复后: 新增 smNameMap/sdNameMap/dNameMap, 通过 ID 反查主表
    """

    def test_build_domain_products_has_name_maps(self):
        """[V033-T1] buildDomainProducts 中 smNameMap/sdNameMap/dNameMap 存在

        防止: 有人删除这三个 Map, 导致 BO 反查 name 逻辑失效
        """
        src = _read_converter_source()
        full, body = _extract_function_body(src, 'buildDomainProducts')
        assert full, "buildDomainProducts 函数未找到"

        # 验证三个 Map 都存在
        for map_name in ('smNameMap', 'sdNameMap', 'dNameMap'):
            pattern = rf'const\s+{map_name}\s*=\s*new\s+Map\s*\('
            assert re.search(pattern, body), (
                f"V033 守卫 1 复发! buildDomainProducts 缺少 {map_name}. "
                f"修复: 新增 const {map_name} = new Map() 用于反查 name"
            )

    def test_build_domain_products_bo_fallback_lookup(self):
        """[V033-T2] buildDomainProducts 中 BO 反查逻辑存在

        防止: 有人删除 "若 sdName/dName 为空, 通过 serviceModuleMap 反查" 逻辑
        """
        src = _read_converter_source()
        full, body = _extract_function_body(src, 'buildDomainProducts')
        assert full, "buildDomainProducts 函数未找到"

        # 验证 fallback 逻辑: if (!sdName || !dName) { ... serviceModuleMap ... }
        # 修复代码 L94-104
        fallback_pattern = r'if\s*\(\s*!sdName\s*\|\|\s*!dName\s*\)\s*\{'
        assert re.search(fallback_pattern, body), (
            "V033 守卫 1 复发! buildDomainProducts 缺少 'if (!sdName || !dName)' 反查逻辑. "
            "修复: 当 BO 的 sdName/dName 冗余列为空时, 通过 serviceModuleMap 反查 sd, 再反查 d"
        )

        # 验证反查后赋值 sdName/dName (不是只读不写)
        assign_pattern = r'sdName\s*=\s*sd\.name'
        assert re.search(assign_pattern, body), (
            "V033 守卫 1 复发! buildDomainProducts 反查后未赋值 sdName = sd.name. "
            "修复: 反查到 sd 后, 赋值 sdName = sd.name, dName = dNameMap.get(dId)"
        )

        assign_d_pattern = r'dName\s*=\s*dNameMap\.get\s*\('
        assert re.search(assign_d_pattern, body), (
            "V033 守卫 1 复发! buildDomainProducts 反查后未用 dNameMap.get(dId) 赋值 dName. "
            "修复: 反查到 sd 后, 用 dName = dNameMap.get(dId) 获取 domain name"
        )


# ─── 测试类: 守卫 2 - buildServiceModules 反查 name 映射 ──────────────────

class TestBuildServiceModulesFallback:
    """V033-T3/T4: 防止 buildServiceModules 的反查 name 映射被移除

    V033 修复前: 直接读 sm.sub_domain_name/domain_name (冗余列, V863 全 NULL)
    V033 修复后: 新增 sdMap/dMap, 反查优先, 冗余列兜底
    """

    def test_build_service_modules_has_sd_d_maps(self):
        """[V033-T3] buildServiceModules 中 sdMap/dMap 反查 Map 存在

        防止: 有人删除 sdMap/dMap, 导致 sm 反查 name 逻辑失效
        """
        src = _read_converter_source()
        full, body = _extract_function_body(src, 'buildServiceModules')
        assert full, "buildServiceModules 函数未找到"

        # 验证 sdMap 存在 (用 subDomains 构造)
        sd_pattern = r'sdMap\s*=\s*new\s+Map\s*\(\s*\(?subDomains'
        assert re.search(sd_pattern, body), (
            "V033 守卫 2 复发! buildServiceModules 缺少 sdMap = new Map(subDomains...). "
            "修复: 新增 const sdMap = new Map((subDomains || []).map(sd => [sd.id, sd]))"
        )

        # 验证 dMap 存在 (用 domains 构造)
        d_pattern = r'dMap\s*=\s*new\s+Map\s*\(\s*\(?domains'
        assert re.search(d_pattern, body), (
            "V033 守卫 2 复发! buildServiceModules 缺少 dMap = new Map(domains...). "
            "修复: 新增 const dMap = new Map((domains || []).map(d => [d.id, d]))"
        )

    def test_build_service_modules_fallback_order(self):
        """[V033-T4] buildServiceModules 中 subDomain/domain 字段反查优先

        防止: 有人把 'sd?.name || sm.sub_domain_name' 改回 'sm.sub_domain_name' 优先,
        导致冗余列 NULL 时 fallback 失效
        """
        src = _read_converter_source()
        full, body = _extract_function_body(src, 'buildServiceModules')
        assert full, "buildServiceModules 函数未找到"

        # 验证 subDomain 字段反查优先: sd?.name || sm.sub_domain_name || ''
        # 顺序很重要: 反查 (sd?.name) 在前, 冗余列 (sm.sub_domain_name) 兜底
        sub_domain_pattern = r"subDomain\s*:\s*sd\?\.name\s*\|\|\s*sm\.sub_domain_name"
        assert re.search(sub_domain_pattern, body), (
            "V033 守卫 2 复发! subDomain 字段未用 'sd?.name || sm.sub_domain_name' 反查优先. "
            "修复: subDomain: sd?.name || sm.sub_domain_name || '' (反查优先, 冗余列兜底)"
        )

        # 验证 domain 字段反查优先: d?.name || sm.domain_name
        domain_pattern = r"domain\s*:\s*d\?\.name\s*\|\|\s*sm\.domain_name"
        assert re.search(domain_pattern, body), (
            "V033 守卫 2 复发! domain 字段未用 'd?.name || sm.domain_name' 反查优先. "
            "修复: domain: d?.name || sm.domain_name || '' (反查优先, 冗余列兜底)"
        )


# ─── 测试类: 守卫 3 - buildPreviewDataFromArchData 反查 name 映射 ────────

class TestBuildPreviewDataNameMaps:
    """V033-T5/T6: 防止 buildPreviewDataFromArchData 的反查 name 映射被移除

    V033 修复前: BO 直接读 bo.domain_name/sub_domain_name (冗余列, V863 全 NULL)
    V033 修复后: 新增 smCodeMap/smNameMap/sdMap/dMap, 多层 fallback 反查
    """

    def test_build_preview_data_has_name_maps(self):
        """[V033-T5] buildPreviewDataFromArchData 中四个反查 Map 存在

        防止: 有人删除 smCodeMap/smNameMap/sdMap/dMap, 导致 BO 反查 name 逻辑失效
        """
        src = _read_converter_source()
        full, body = _extract_function_body(src, 'buildPreviewDataFromArchData')
        assert full, "buildPreviewDataFromArchData 函数未找到"

        # 验证 smCodeMap 和 smNameMap 存在
        for map_name in ('smCodeMap', 'smNameMap'):
            pattern = rf'const\s+{map_name}\s*=\s*new\s+Map\s*\('
            assert re.search(pattern, body), (
                f"V033 守卫 3 复发! buildPreviewDataFromArchData 缺少 {map_name}. "
                f"修复: 新增 const {map_name} = new Map() 用于反查 SM"
            )

        # 验证 sdMap 和 dMap 存在 (用 subDomains/domains 构造)
        sd_pattern = r'sdMap\s*=\s*new\s+Map\s*\(\s*subDomains'
        assert re.search(sd_pattern, body), (
            "V033 守卫 3 复发! buildPreviewDataFromArchData 缺少 sdMap = new Map(subDomains...). "
            "修复: 新增 const sdMap = new Map(subDomains.map(sd => [sd.id, sd]))"
        )

        d_pattern = r'dMap\s*=\s*new\s+Map\s*\(\s*domains'
        assert re.search(d_pattern, body), (
            "V033 守卫 3 复发! buildPreviewDataFromArchData 缺少 dMap = new Map(domains...). "
            "修复: 新增 const dMap = new Map(domains.map(d => [d.id, d]))"
        )

    def test_build_preview_data_bo_fallback_lookup(self):
        """[V033-T6] buildPreviewDataFromArchData 中 BO 多层 fallback 反查逻辑

        防止: 有人删除 "若 sdName/dName/sdId 为空, 通过 smId 反查 sd, 再反查 d" 逻辑
        """
        src = _read_converter_source()
        full, body = _extract_function_body(src, 'buildPreviewDataFromArchData')
        assert full, "buildPreviewDataFromArchData 函数未找到"

        # 验证多层 fallback 入口: if (!sdName || !dName || !sdId)
        # 修复代码 L251
        fallback_pattern = r'if\s*\(\s*!sdName\s*\|\|\s*!dName\s*\|\|\s*!sdId\s*\)'
        assert re.search(fallback_pattern, body), (
            "V033 守卫 3 复发! buildPreviewDataFromArchData 缺少多层 fallback 入口. "
            "修复: if (!sdName || !dName || !sdId) { 通过 smId 反查 sd, 再反查 d }"
        )

        # 验证通过 smId 反查 sd 的逻辑: serviceModules.find(s => s.id === smId)
        find_pattern = r'serviceModules\.find\s*\(\s*s\s*=>\s*s\.id\s*===\s*smId\s*\)'
        assert re.search(find_pattern, body), (
            "V033 守卫 3 复发! 缺少 'serviceModules.find(s => s.id === smId)' 反查 SM 逻辑. "
            "修复: 通过 smId 在 serviceModules 中反查 sm, 再用 sm.sub_domain_id 反查 sd"
        )

        # 验证反查 sd 后用 sdMap 查找: sdMap.get(matchedSdId)
        sdmap_get_pattern = r'sdMap\.get\s*\(\s*matchedSdId\s*\)'
        assert re.search(sdmap_get_pattern, body), (
            "V033 守卫 3 复发! 缺少 'sdMap.get(matchedSdId)' 反查 sd 逻辑. "
            "修复: 用 sdMap.get(matchedSdId) 获取 sd, 再赋值 sdName = sd.name"
        )

        # 验证反查 d 后用 dMap 查找: dMap.get(dId)?.name
        dmap_get_pattern = r'dMap\.get\s*\(\s*dId\s*\)\?\.name'
        assert re.search(dmap_get_pattern, body), (
            "V033 守卫 3 复发! 缺少 'dMap.get(dId)?.name' 反查 d name 逻辑. "
            "修复: 用 dMap.get(dId)?.name 获取 domain name 并赋值给 dName"
        )


# ─── 测试类: 守卫 4 - 不应直接依赖冗余列作为主数据源 ──────────────────────

class TestNoDirectRedundantColumnDependency:
    """V033-T7: 防止 archDataConverter.js 直接依赖冗余列作为主数据源

    V033 修复前: bo.domain_name/sub_domain_name 作为主数据源 (V863 全 NULL)
    V033 修复后: 反查优先, 冗余列仅作为 fallback 兜底
    """

    def test_no_direct_redundant_column_as_primary(self):
        """[V033-T7] 不应直接读 bo.domain_name 作为主数据源

        防止: 有人把 'dName = bo.domain_name' 改回直接读 (无 fallback),
        导致 V863 历史 BO (冗余列 NULL) 渲染为空
        """
        src = _read_converter_source()
        # 移除注释, 避免注释中的字面量被误匹配
        code_only = _strip_js_comments(src)

        # 危险模式: 'dName = bo.domain_name' 后没有 || 反查
        # 正确模式: 'dName = bo.domain_name' 后跟 if (!sdName || !dName) { 反查 }
        # 这里我们检查是否有裸的 'dName = bo.domain_name' 没有 fallback
        # 实际上 V033 修复中 'let dName = bo.domain_name' 是初始化, 后面跟 fallback
        # 我们验证 fallback 逻辑存在 (已在 T2/T6 覆盖), 这里检查不退化

        # 检查 1: bo.domain_name 不应出现在 return 对象中直接作为 domain 字段值
        # 错误模式: domain: bo.domain_name (无 fallback)
        bad_pattern = r'domain\s*:\s*bo\.domain_name\s*[,}]'
        bad_match = re.search(bad_pattern, code_only)
        assert not bad_match, (
            "V033 守卫 4 复发! 发现 'domain: bo.domain_name' 直接依赖冗余列. "
            "修复: domain 字段应使用 dName 变量 (经过反查 fallback), 不是 bo.domain_name 直接读取"
        )

        # 检查 2: bo.sub_domain_name 不应直接作为 subDomain 字段值
        bad_pattern2 = r'subDomain\s*:\s*bo\.sub_domain_name\s*[,}]'
        bad_match2 = re.search(bad_pattern2, code_only)
        assert not bad_match2, (
            "V033 守卫 4 复发! 发现 'subDomain: bo.sub_domain_name' 直接依赖冗余列. "
            "修复: subDomain 字段应使用 sdName 变量 (经过反查 fallback), 不是 bo.sub_domain_name 直接读取"
        )

        # 检查 3: sm.sub_domain_name 不应直接作为 subDomain 字段值 (buildServiceModules)
        # 正确模式: sd?.name || sm.sub_domain_name || '' (反查优先)
        bad_pattern3 = r'subDomain\s*:\s*sm\.sub_domain_name\s*[,}]'
        bad_match3 = re.search(bad_pattern3, code_only)
        assert not bad_match3, (
            "V033 守卫 4 复发! 发现 'subDomain: sm.sub_domain_name' 直接依赖冗余列. "
            "修复: subDomain 字段应使用 'sd?.name || sm.sub_domain_name || '' (反查优先, 冗余列兜底)"
        )

        # 检查 4: sm.domain_name 不应直接作为 domain 字段值 (buildServiceModules)
        bad_pattern4 = r'domain\s*:\s*sm\.domain_name\s*[,}]'
        bad_match4 = re.search(bad_pattern4, code_only)
        assert not bad_match4, (
            "V033 守卫 4 复发! 发现 'domain: sm.domain_name' 直接依赖冗余列. "
            "修复: domain 字段应使用 'd?.name || sm.domain_name || '' (反查优先, 冗余列兜底)"
        )


# ─── 入口 ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
