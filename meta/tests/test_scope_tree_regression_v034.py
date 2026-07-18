# -*- coding: utf-8 -*-
"""
[REGRESSION V034] RelationScopeTree 5 个连续 Bug 回归测试

## 背景

BUG-V034 是 RelationScopeTree（对象范围树）组件的 5 个相互纠缠的 Bug，
共复发 3 次（v1/v2/v3 + 后续 fix），是 30 天迭代中复发次数最多的 BUG。

## 5 个 Bug 根因

| # | 现象 | 根因 |
|---|------|------|
| 1 | 点击 RSS 树自动折叠 | installStoreSetDataHook 在 USE_FILTERSOURCE 模式下被 `if (USE_FILTERSOURCE) return` 提前返回 |
| 2 | 同服务模块(9) > 付款计划 显示 4 条而非 2 条 | init_and_seed.py 中 16 个 service_module 全部映射到 sub_domain_id=1 |
| 3 | 范围外节点无法反勾选 | el-tree 2.15+ 移除了 setCheckedKeys/setExpandedKeys 的某些签名 |
| 4 | 范围内节点"展开又快速合上"（flash） | filter() 调用副作用：自动展开所有可见非叶节点 |
| 5 | 修复 flash 后节点选中后自动折叠 | setData 触发链中 user state 丢失 |

## 3 次复发时间线（git log）

- b81e639 fix(scope-tree): BUG-V034 v1 修复对象范围树自动全展开
- eec582e fix(scope-tree): BUG-V034 v2 默认不展开 1 级节点 (避免 971 domain 全展开卡顿)
- 97d0596 fix(scope-tree): BUG-V034 v3 跨重建持久化用户展开状态 (修复勾选后树收起)
- 5567e29 / 23dedbd fix(object-scope): 修复树勾选级联 + 树收起 + 表格联动 + 备注过滤

## 本文件覆盖

| ID | 测试 | 防止复发的根因 |
|---|---|---|
| V034-T1 | test_init_and_seed_module_importable | init_and_seed.py 模块可导入 |
| V034-T2 | test_service_modules_count_is_16 | 16 个 SM（防结构退化） |
| V034-T3 | test_sub_domains_count_is_8 | 8 个 SD（防结构变更） |
| V034-T4 | test_sm_distribution_2_per_sd | 每个 SD 恰好 2 个 SM（防 V034-2 复发） |
| V034-T5 | test_sm_not_all_mapped_to_single_sd | SM 不能全部映射到同一个 SD（V034-2 直接根因） |
| V034-T6 | test_bo_req_maps_to_proc_req_mng | BO_REQ→PROC_REQ_MNG（V034-3 修复点） |
| V034-T7 | test_bo_sales_inv_maps_to_ar_invoice | BO_SALES_INV→AR_INVOICE（V034-3 修复点） |
| V034-T8 | test_bo_to_sm_map_covers_all_25_bos | 25 个 BO 都有 SM 映射 |
| V034-T9 | test_relationships_table_no_virtual_columns_physicalized | relationships 表 14 列（V034-5 单事实源） |
| V034-T10 | test_install_store_set_data_hook_no_use_filtersource_early_return | installStoreSetDataHook 无 USE_FILTERSOURCE 提前返回（V034-1 根因） |
| V034-T11 | test_no_tree_filter_call_in_vue | 不调用 `tree.filter()`（V034-4 flash 根因） |
| V034-T12 | test_no_setExpandedKeys_call | 不调用废弃的 `setExpandedKeys`（V034-3 el-tree 2.15+ 兼容） |

## 测试策略

- 后端 Python 层：用 AST 静态解析 init_and_seed.py 源代码，提取关键数据结构
  （service_modules 列表、sm_code_map 字典），不执行 DB 操作
- 前端 Vue 层：读源码字符串 + 关键模式匹配，验证 V034-1/3/4 根因已修复

参考:
- docs/retrospectives/2026-06-04-relation-scope-tree-bug.md (5 Bug 复盘)
- tests/diagnostics/verify_bug_v034.py (Playwright e2e 验证)
- tests/diagnostics/repro_bug_v034_collapse.py (Playwright 复现脚本)
"""

import ast
import os
import sys
import re
from pathlib import Path

import pytest

# ─── 路径设置 ─────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

# 被测源码路径
INIT_AND_SEED_PATH = _PROJECT_ROOT / 'meta' / 'scripts' / 'init_and_seed.py'
RELATION_SCOPE_SECTION_PATH = (
    _PROJECT_ROOT / 'src' / 'components' / 'common' / 'RelationScopeTree'
    / 'RelationScopeSection.vue'
)


# ─── 辅助函数 ─────────────────────────────────────────────────────────────

def _parse_init_and_seed_ast():
    """解析 init_and_seed.py 为 AST，返回 module 节点"""
    src = INIT_AND_SEED_PATH.read_text(encoding='utf-8')
    return ast.parse(src)


def _extract_service_modules_list(module_ast):
    """从 AST 提取 service_modules 列表（list of tuple）

    返回: [(sm_name, sm_code, sd_key), ...]
    """
    for node in ast.walk(module_ast):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'service_modules':
                    if isinstance(node.value, ast.List):
                        result = []
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Tuple) and len(elt.elts) == 3:
                                name = ast.literal_eval(elt.elts[0])
                                code = ast.literal_eval(elt.elts[1])
                                sd_key = ast.literal_eval(elt.elts[2])
                                result.append((name, code, sd_key))
                        return result
    return []


def _extract_sub_domains_list(module_ast):
    """从 AST 提取 sub_domains 列表

    返回: [(domain_name, sd_name, code, desc), ...]
    """
    for node in ast.walk(module_ast):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'sub_domains':
                    if isinstance(node.value, ast.List):
                        result = []
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Tuple) and len(elt.elts) == 4:
                                result.append(tuple(ast.literal_eval(e) for e in elt.elts))
                        return result
    return []


def _extract_sm_code_map(module_ast):
    """从 AST 提取 sm_code_map 字典

    返回: {bo_code: sm_code, ...}
    """
    for node in ast.walk(module_ast):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'sm_code_map':
                    if isinstance(node.value, ast.Dict):
                        result = {}
                        for key, val in zip(node.value.keys, node.value.values):
                            k = ast.literal_eval(key)
                            v = ast.literal_eval(val)
                            result[k] = v
                        return result
    return {}


def _extract_business_objects_list(module_ast):
    """从 AST 提取 business_objects 列表

    返回: [(name, code, desc), ...]
    """
    for node in ast.walk(module_ast):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'business_objects':
                    if isinstance(node.value, ast.List):
                        result = []
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Tuple) and len(elt.elts) == 3:
                                result.append(tuple(ast.literal_eval(e) for e in elt.elts))
                        return result
    return []


def _extract_relationships_create_columns(module_ast):
    """从 AST 提取 relationships CREATE TABLE 的列名列表"""
    # 直接从源码字符串提取，比 AST 解析 SQL 字符串更可靠
    src = INIT_AND_SEED_PATH.read_text(encoding='utf-8')
    # 匹配 CREATE TABLE IF NOT EXISTS relationships ( ... );
    # 注意: 用 \n        \) 匹配表结束的 ) (新行+8空格+闭括号)
    # 避免 non-greedy .*? 误匹配到注释中的 ) (如 "storage: virtual (Type-B 虚拟冗余)")
    m = re.search(
        r'CREATE TABLE IF NOT EXISTS relationships \((.*?)\n        \)',
        src, re.DOTALL
    )
    if not m:
        return []
    body = m.group(1)
    # 提取列名（跳过 -- 注释行和 FOREIGN KEY 等约束）
    columns = []
    for line in body.split('\n'):
        line = line.strip().rstrip(',')
        # 跳过空行 / 注释行 / 约束
        if not line or line.startswith('--') or line.startswith('FOREIGN KEY'):
            continue
        # 列名是第一个 token
        col_name = line.split()[0]
        if col_name and col_name.isidentifier():
            columns.append(col_name)
    return columns


# ─── 测试类: 模块结构 ────────────────────────────────────────────────────

class TestInitAndSeedStructure:
    """V034-T1: init_and_seed.py 模块结构稳定性"""

    def test_init_and_seed_module_importable(self):
        """[V034-T1] init_and_seed.py 模块可导入（无语法错误）

        防止：init_and_seed.py 因为某次修改引入语法错误
        """
        assert INIT_AND_SEED_PATH.exists(), f"init_and_seed.py 不存在: {INIT_AND_SEED_PATH}"
        # 静态解析 AST（不执行模块代码）
        try:
            ast.parse(INIT_AND_SEED_PATH.read_text(encoding='utf-8'))
        except SyntaxError as e:
            pytest.fail(f"init_and_seed.py 语法错误: {e}")

    def test_relation_scope_section_vue_exists(self):
        """[V034-T1b] RelationScopeSection.vue 文件存在"""
        assert RELATION_SCOPE_SECTION_PATH.exists(), (
            f"RelationScopeSection.vue 不存在: {RELATION_SCOPE_SECTION_PATH}"
        )


# ─── 测试类: V034-2 根因 (SM→SD 映射) ──────────────────────────────────

class TestSmToSdMapping:
    """V034-T2/T3/T4/T5: 防止 V034-2 复发（SM 全部映射到 sd_id=1）

    V034-2 根因：init_and_seed.py 原 bug 代码
        for sm_name, sm_code in service_modules:
            for sd_key, (sd_name, sd_code) in [...]:  # 硬编码 4 个 sd
                sd_id = sub_domain_ids.get(sd_key)
                if sd_id:
                    # (此处原代码向 service_modules 表插入记录)
                    cursor.execute("... service_modules ...")
                    break  # ← 每次都只插第一个匹配的 sd

    修复后：service_modules 列表每项显式指定 sd_key
        ('采购需求', 'PROC_REQ_MNG', '采购管理.采购需求'),
        ...
    """

    @pytest.fixture(scope='class')
    def service_modules(self):
        return _extract_service_modules_list(_parse_init_and_seed_ast())

    @pytest.fixture(scope='class')
    def sub_domains(self):
        return _extract_sub_domains_list(_parse_init_and_seed_ast())

    def test_service_modules_count_is_16(self, service_modules):
        """[V034-T2] 16 个 service_module（防结构退化）

        业务约束：4 domains × 2 sub_domains × 2 service_modules = 16
        """
        assert len(service_modules) == 16, (
            f"service_modules 应有 16 项, 实际 {len(service_modules)}: {service_modules}"
        )

    def test_sub_domains_count_is_8(self, sub_domains):
        """[V034-T3] 8 个 sub_domain（防结构变更）

        业务约束：4 domains × 2 sub_domains = 8
        """
        assert len(sub_domains) == 8, (
            f"sub_domains 应有 8 项, 实际 {len(sub_domains)}: {sub_domains}"
        )

    def test_sm_distribution_2_per_sd(self, service_modules, sub_domains):
        """[V034-T4] 每个 sub_domain 恰好 2 个 service_module

        防止 V034-2 复发：原 bug 是 16 个 SM 全部映射到 sd_id=1
        修复后：每个 SD 恰好 2 个 SM
        """
        # 构造合法 sd_key 集合
        valid_sd_keys = {f"{d}.{sd}" for d, sd, _, _ in sub_domains}

        # 按 sd_key 分组
        sd_to_sms = {}
        for sm_name, sm_code, sd_key in service_modules:
            assert sd_key in valid_sd_keys, (
                f"SM {sm_name}({sm_code}) 引用不存在的 sd_key={sd_key}"
            )
            sd_to_sms.setdefault(sd_key, []).append(sm_code)

        # 每个 SD 恰好 2 个 SM
        for sd_key, sms in sd_to_sms.items():
            assert len(sms) == 2, (
                f"SD {sd_key} 应有 2 个 SM, 实际 {len(sms)}: {sms}"
            )

    def test_sm_not_all_mapped_to_single_sd(self, service_modules):
        """[V034-T5] SM 不能全部映射到同一个 SD（V034-2 直接根因）

        这是 V034-2 的直接检测：如果所有 SM 都映射到同一个 sd_key，
        说明 V034-2 bug 复发。
        """
        sd_keys = {sd_key for _, _, sd_key in service_modules}
        assert len(sd_keys) > 1, (
            f"V034-2 复发! 所有 SM 都映射到同一个 SD: {sd_keys}. "
            f"应分布到至少 2 个 SD, 期望 8 个 SD."
        )


# ─── 测试类: V034-3 根因 (BO→SM 映射) ──────────────────────────────────

class TestBoToSmMapping:
    """V034-T6/T7/T8: 防止 V034-3 复发（BO→SM 映射错误）

    V034-3 修复点（init_and_seed.py）:
        - BO_REQ → PROC_REQ_MNG (采购需求, 不是采购订单)
        - BO_SALES_INV → AR_INVOICE (销售发票创建应收, 不是 ORDER_MNG)
    """

    @pytest.fixture(scope='class')
    def sm_code_map(self):
        return _extract_sm_code_map(_parse_init_and_seed_ast())

    @pytest.fixture(scope='class')
    def business_objects(self):
        return _extract_business_objects_list(_parse_init_and_seed_ast())

    def test_bo_req_maps_to_proc_req_mng(self, sm_code_map):
        """[V034-T6] BO_REQ → PROC_REQ_MNG

        业务含义：采购申请属于"采购需求"模块
        历史错误：曾错误映射到 PROC_ORDER (采购订单)
        """
        assert 'BO_REQ' in sm_code_map, "sm_code_map 必须包含 BO_REQ"
        assert sm_code_map['BO_REQ'] == 'PROC_REQ_MNG', (
            f"BO_REQ 应映射到 PROC_REQ_MNG, 实际映射到 {sm_code_map['BO_REQ']}"
        )

    def test_bo_sales_inv_maps_to_ar_invoice(self, sm_code_map):
        """[V034-T7] BO_SALES_INV → AR_INVOICE

        业务含义：销售发票创建应收账款，所以属于"应收发票"模块
        历史错误：曾错误映射到 ORDER_MNG (订单管理)
        """
        assert 'BO_SALES_INV' in sm_code_map, "sm_code_map 必须包含 BO_SALES_INV"
        assert sm_code_map['BO_SALES_INV'] == 'AR_INVOICE', (
            f"BO_SALES_INV 应映射到 AR_INVOICE, 实际映射到 {sm_code_map['BO_SALES_INV']}. "
            f"业务原因: 销售发票创建应收账款，应属应收发票模块"
        )

    def test_bo_to_sm_map_covers_all_25_bos(self, sm_code_map, business_objects):
        """[V034-T8] 所有 BO 都有 SM 映射

        防止：新增 BO 但忘记加 sm_code_map 项，导致 fallback 'ORDER_MNG'
        """
        bo_codes = {code for _, code, _ in business_objects}
        missing = bo_codes - set(sm_code_map.keys())
        assert not missing, (
            f"{len(missing)} 个 BO 缺少 sm_code_map 映射: {sorted(missing)}. "
            f"未映射的 BO 会 fallback 到 'ORDER_MNG', 导致 scope-tree 分类错误"
        )

    def test_all_sm_codes_in_map_exist_in_service_modules(self, sm_code_map, business_objects):
        """[V034-T8b] sm_code_map 引用的 SM code 都存在于 service_modules 列表

        防止：sm_code_map 引用了不存在的 SM code
        """
        service_modules = _extract_service_modules_list(_parse_init_and_seed_ast())
        valid_sm_codes = {sm_code for _, sm_code, _ in service_modules}
        invalid_refs = set(sm_code_map.values()) - valid_sm_codes
        # ORDER_MNG 是 fallback, 允许存在
        invalid_refs.discard('ORDER_MNG')
        assert not invalid_refs, (
            f"sm_code_map 引用了不存在的 SM code: {invalid_refs}. "
            f"合法 SM codes: {sorted(valid_sm_codes)}"
        )


# ─── 测试类: V034-5 根因 (单事实源) ─────────────────────────────────────

class TestSingleSourceOfTruth:
    """V034-T9: 防止 V034-5 复发（17 个虚拟字段被物理化）

    V034-5 根因：违反 YAML schema 的 storage: virtual 契约
        relationship.yaml 中 17 个字段标记为 storage: virtual (Type-B 虚拟冗余)
        但 V034 修复前在 CREATE TABLE 中建成了物理列

    修复：从 relationships CREATE TABLE 移除 17 列，让 computed_utils.py
        在查询时通过 JOIN 实时计算

    防止复发：检测 relationships 表列数应为 14（不含 17 虚拟字段）
    """

    EXPECTED_COLUMNS = {
        'id', 'version_id', 'source_bo_id', 'target_bo_id',
        'source_code', 'target_code', 'code', 'relation_code',
        'relation_type', 'relation_desc',
        'created_at', 'created_by', 'updated_by',
    }

    # 17 个虚拟字段（V034-5 修复时移除）- 防止重新引入
    VIRTUAL_FIELDS_REMOVED = {
        'source_bo_name', 'source_domain_id', 'source_sub_domain_id',
        'source_service_module_id', 'source_service_module_name',
        'source_sub_domain_name', 'source_domain_name',
        'target_bo_name', 'target_domain_id', 'target_sub_domain_id',
        'target_service_module_id', 'target_service_module_name',
        'target_sub_domain_name', 'target_domain_name',
        'module_relation', 'cross_module_relation', 'child_count',
    }

    def test_relationships_table_no_virtual_columns_physicalized(self):
        """[V034-T9] relationships 表不能物理化 17 个虚拟字段

        防止 V034-5 复发：如果检测到虚拟字段被重新引入为物理列，立即失败
        """
        module_ast = _parse_init_and_seed_ast()
        columns = _extract_relationships_create_columns(module_ast)
        column_set = set(columns)

        # 1. 验证期望的 14 列都存在
        missing = self.EXPECTED_COLUMNS - column_set
        assert not missing, (
            f"relationships 表缺少期望列: {missing}. "
            f"实际列: {sorted(column_set)}"
        )

        # 2. 验证 17 个虚拟字段没有被重新引入
        re_introduced = self.VIRTUAL_FIELDS_REMOVED & column_set
        assert not re_introduced, (
            f"V034-5 复发! relationships 表物理化了虚拟字段: {sorted(re_introduced)}. "
            f"这些字段在 relationship.yaml 中标记为 storage: virtual, "
            f"应由 computed_utils.py 在查询时通过 JOIN 实时计算, 不应物理化."
        )

        # 3. 验证总列数（14 列，允许略多但必须小于 20）
        assert len(column_set) <= 20, (
            f"relationships 表列数 {len(column_set)} 过多, "
            f"可能重新引入了虚拟字段. 实际列: {sorted(column_set)}"
        )


# ─── 测试类: V034-1/3/4 根因 (Vue 组件) ────────────────────────────────

class TestRelationScopeSectionVue:
    """V034-T10/T11/T12: 防止 V034-1/3/4 复发（前端 Vue 组件根因）

    这些是前端层面的检测，通过源码字符串模式匹配验证根因已修复。
    如果需要完整 e2e 验证，参考 tests/diagnostics/verify_bug_v034.py。
    """

    @pytest.fixture(scope='class')
    def vue_source(self):
        if not RELATION_SCOPE_SECTION_PATH.exists():
            pytest.skip(f"RelationScopeSection.vue 不存在: {RELATION_SCOPE_SECTION_PATH}")
        return RELATION_SCOPE_SECTION_PATH.read_text(encoding='utf-8')

    def test_install_store_set_data_hook_no_use_filtersource_early_return(self, vue_source):
        """[V034-T10] installStoreSetDataHook 不能有 USE_FILTERSOURCE 提前 return

        V034-1 根因：
            function installStoreSetDataHook() {
              if (storeSetDataHooked) return
              if (!relationTreeRef.value?.store) return
              // ❌ 缺失的检查
              if (USE_FILTERSOURCE) return  // ← 罪魁祸首
              ...
            }

        修复后：installStoreSetDataHook 在所有模式下都生效（不再提前 return）
        """
        # 提取 installStoreSetDataHook 函数体（直到下一个 function 或结束）
        m = re.search(
            r'function\s+installStoreSetDataHook\s*\([^)]*\)\s*\{',
            vue_source
        )
        assert m, "installStoreSetDataHook 函数未找到"

        # 找到匹配的 } (考虑嵌套)
        start = m.end()
        depth = 1
        end = start
        while end < len(vue_source) and depth > 0:
            if vue_source[end] == '{':
                depth += 1
            elif vue_source[end] == '}':
                depth -= 1
            end += 1

        func_body = vue_source[start:end]

        # 检查是否有 "if (USE_FILTERSOURCE) return" 或 "if (USE_FILTERSOURCE)\n  return"
        # 允许 USE_FILTERSOURCE 出现在其他上下文（如 watcher），但函数内不能有提前 return
        bad_patterns = [
            r'if\s*\(\s*USE_FILTERSOURCE\s*\)\s*return',
            r'if\s*\(\s*USE_FILTERSOURCE\s*\)\s*\n\s*return',
        ]
        for pat in bad_patterns:
            m = re.search(pat, func_body)
            assert not m, (
                f"V034-1 复发! installStoreSetDataHook 内有 USE_FILTERSOURCE 提前 return: "
                f"匹配位置: {m.group() if m else 'N/A'}. "
                f"修复: 移除 'if (USE_FILTERSOURCE) return' 这一行"
            )

    def test_no_tree_filter_call_in_vue(self, vue_source):
        """[V034-T11] 不调用 `tree.filter()` 或 `relationTreeRef.value.filter()`

        V034-4 根因：filter() 会自动展开所有可见非叶节点（flash 来源）

        修复后：用 `store.filterText = ...` 替代 filter() 调用
        """
        # 移除注释行后再检测（避免 // 注释中的 "tree.filter()" 文字误报）
        lines = vue_source.split('\n')
        code_lines = []
        for line in lines:
            stripped = line.lstrip()
            # 跳过单行注释 (// ...)
            if stripped.startswith('//'):
                continue
            # 跳过块注释 (/* ... */ 单行)
            if stripped.startswith('*') or stripped.startswith('/*'):
                continue
            code_lines.append(line)
        code_only = '\n'.join(code_lines)

        # 匹配 .filter( 调用（排除 store.filterText 赋值）
        bad_patterns = [
            r'treeRef\.value\.filter\s*\(',
            r'relationTreeRef\.value\.filter\s*\(',
            r'tree\.filter\s*\(',
        ]
        for pat in bad_patterns:
            m = re.search(pat, code_only)
            assert not m, (
                f"V034-4 复发! 调用了 el-tree 的 filter() 方法 (会触发 auto-expand 副作用): "
                f"匹配: {m.group() if m else 'N/A'}. "
                f"修复: 改用 'store.filterText = ...' 设置 filterText, "
                f"让 :filter-node-method 自动重算 node.visible"
            )

        # 验证正确做法存在（store.filterText 赋值）
        assert 'store.filterText' in vue_source or 'filterText' in vue_source, (
            "缺少 'store.filterText = ...' 赋值, "
            "V034-4 修复方案应包含 filterText 直接赋值"
        )

    def test_no_setExpandedKeys_call(self, vue_source):
        """[V034-T12] 不调用废弃的 setExpandedKeys

        V034-3 根因：el-tree 2.15+ 移除了 setExpandedKeys API
            tree.setExpandedKeys(keys)  // 静默失败

        修复后：用 `node.expand()` 逐个展开
        """
        # 移除注释行后再检测
        lines = vue_source.split('\n')
        code_lines = []
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith('//'):
                continue
            if stripped.startswith('*') or stripped.startswith('/*'):
                continue
            code_lines.append(line)
        code_only = '\n'.join(code_lines)

        # 匹配 .setExpandedKeys( 调用
        m = re.search(r'\.setExpandedKeys\s*\(', code_only)
        assert not m, (
            f"V034-3 复发! 调用了废弃的 setExpandedKeys API: "
            f"匹配位置附近: {code_only[m.start():m.start()+80] if m else 'N/A'}. "
            f"修复: el-tree 2.15+ 移除了 setExpandedKeys, "
            f"改用 'store.nodesMap[key].expand()' 逐个展开节点"
        )

        # 验证修复方案存在（node.expand() 调用）
        assert '.expand(' in vue_source, (
            "缺少 'node.expand()' 调用, "
            "V034-3 修复方案应使用 node.expand() 逐个展开"
        )

    def test_user_expanded_keys_persistence_exists(self, vue_source):
        """[V034-T13] userExpandedKeys 跨重建持久化机制存在

        V034 v3 修复：跨 setData 重建持久化用户展开状态
            const userExpandedKeys = ref(new Set())
            function onNodeExpand(data) { userExpandedKeys.value.add(...) }
            function onNodeCollapse(data) { userExpandedKeys.value.delete(...) }
        """
        assert 'userExpandedKeys' in vue_source, (
            "缺少 userExpandedKeys 变量, "
            "V034 v3 修复方案应使用 userExpandedKeys (Set) 跨 setData 重建持久化展开状态"
        )
        # 验证 onNodeExpand / onNodeCollapse 存在
        assert 'onNodeExpand' in vue_source or 'node-expand' in vue_source, (
            "缺少 onNodeExpand 处理函数, "
            "应通过 @node-expand 事件持续更新 userExpandedKeys"
        )
        assert 'onNodeCollapse' in vue_source or 'node-collapse' in vue_source, (
            "缺少 onNodeCollapse 处理函数, "
            "应通过 @node-collapse 事件持续更新 userExpandedKeys"
        )


# ─── 入口 ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
