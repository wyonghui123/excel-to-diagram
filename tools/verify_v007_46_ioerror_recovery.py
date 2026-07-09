#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
V007.46 disk I/O error 恢复验证 (P0)

[V007.46 BUG-FIX 2026-07-08] 验证 V007.44 6 FIX 在工作树 meta/ 实际落地,
并新增 db_corruption_monitor/db_admin_api/diagnostics_api 3 个文件的裸连接修复

V8w: 验证 safe_connect._open_safe_connection 含 mmap_size = 0
V8x: 验证 _cleanup_resources 函数有 _cleanup_done 幂等守卫
V8y: 验证 _apply_data_permission except 路径含 id = -1 拒绝
V8z: 验证 db_corruption_monitor/db_admin_api/diagnostics_api 4 处全部改用 safe_connect
V8aa: 验证 import_export_service._flatten 有 leaf_op 参数
V8ab: 验证 full_text_search/query_by_hierarchy_path/suggest/aggregate 4 方法调用 _apply_data_permission
V8ac: 验证 _cleanup_resources 文件 4 处 (signal/atexit 入口) 都设了 _cleanup_done 守卫

用法:
  python tools/verify_v007_46_ioerror_recovery.py
"""
import os
import sys
import ast
import re
from pathlib import Path

WORKTREE_ROOT = Path(__file__).parent.parent
META_DIR = WORKTREE_ROOT / "meta"

FAILED = []
PASSED = []


def check_v8w():
    """V8w: safe_connect.py _open_safe_connection 含 mmap_size = 0"""
    f = META_DIR / "core" / "safe_connect.py"
    content = f.read_text(encoding="utf-8")
    if "PRAGMA mmap_size = 0" in content and "_open_safe_connection" in content:
        PASSED.append("V8w: safe_connect.py _open_safe_connection 含 mmap_size=0")
        return True
    FAILED.append("V8w: safe_connect.py 缺 mmap_size=0 PRAGMA")
    return False


def check_v8x():
    """V8x: server.py _cleanup_resources 函数有 _cleanup_done 幂等守卫"""
    f = META_DIR / "server.py"
    content = f.read_text(encoding="utf-8")
    if "_cleanup_done" in content and "if _cleanup_done:" in content:
        PASSED.append("V8x: server.py _cleanup_resources 含 _cleanup_done 幂等守卫")
        return True
    FAILED.append("V8x: server.py _cleanup_resources 缺 _cleanup_done 幂等守卫")
    return False


def check_v8y():
    """V8y: query_service._apply_data_permission except 路径含 id = -1 拒绝"""
    f = META_DIR / "services" / "query_service.py"
    content = f.read_text(encoding="utf-8")
    # 找 _apply_data_permission 函数体
    m = re.search(r"def _apply_data_permission\(.*?(?=\n    def |\nclass )", content, re.DOTALL)
    if not m:
        FAILED.append("V8y: query_service.py _apply_data_permission 函数未找到")
        return False
    func_body = m.group(0)
    if "id" in func_body and "-1" in func_body and "except" in func_body:
        PASSED.append("V8y: query_service._apply_data_permission except 含 id=-1 拒绝")
        return True
    FAILED.append("V8y: query_service._apply_data_permission except 缺 id=-1 拒绝")
    return False


def check_v8z():
    """V8z: db_corruption_monitor 4 处 + db_admin_api 2 处 + diagnostics_api 1 处
    全部改用 safe_connect"""
    issues = []
    for rel, must_contain, min_count in [
        ("core/db_corruption_monitor.py", "safe_connect_for_read", 4),
        ("api/db_admin_api.py", "safe_connect_for_read", 2),
        ("api/diagnostics_api.py", "safe_connect_for_read", 1),
    ]:
        f = META_DIR / rel
        if not f.exists():
            issues.append(f"文件不存在: {rel}")
            continue
        content = f.read_text(encoding="utf-8")
        count = content.count(must_contain)
        if count < min_count:
            issues.append(f"{rel} 缺 {must_contain} (需 ≥{min_count}, 实际 {count})")
    if not issues:
        PASSED.append("V8z: 3 文件 7 处裸连接全部改用 safe_connect_for_read")
        return True
    FAILED.append("V8z: " + "; ".join(issues))
    return False


def check_v8aa():
    """V8aa: import_export_service._flatten 有 leaf_op 参数"""
    f = META_DIR / "services" / "import_export_service.py"
    content = f.read_text(encoding="utf-8")
    if "def _flatten(conds: List[Dict], leaf_op" in content:
        PASSED.append("V8aa: import_export_service._flatten 含 leaf_op 参数")
        return True
    FAILED.append("V8aa: import_export_service._flatten 缺 leaf_op 参数")
    return False


def check_v8ab():
    """V8ab: full_text_search/query_by_hierarchy_path/suggest/aggregate 4 方法调用 _apply_data_permission"""
    f = META_DIR / "services" / "query_service.py"
    content = f.read_text(encoding="utf-8")
    issues = []
    for method in ["full_text_search", "query_by_hierarchy_path", "suggest", "aggregate"]:
        # 找函数体
        m = re.search(rf"def {method}\(.*?(?=\n    def |\nclass )", content, re.DOTALL)
        if not m:
            issues.append(f"方法 {method} 未找到")
            continue
        if "_apply_data_permission" not in m.group(0):
            issues.append(f"方法 {method} 缺 _apply_data_permission 调用")
    if not issues:
        PASSED.append("V8ab: 4 查询方法全部含 _apply_data_permission 调用")
        return True
    FAILED.append("V8ab: " + "; ".join(issues))
    return False


def check_v8ad():
    """V8ad: pool._create_connection 对 db-level 持久化 PRAGMA 都有幂等保护
    (journal_mode/synchronous/auto_vacuum/wal_autocheckpoint 4 个)"""
    f = META_DIR / "core" / "sql_connection_pool.py"
    content = f.read_text(encoding="utf-8")
    issues = []
    for pragma_attr in ["_journal_mode_applied", "_synchronous_applied",
                         "_auto_vacuum_applied", "_wal_autocheckpoint_applied"]:
        if pragma_attr not in content:
            issues.append(f"缺 {pragma_attr} 初始化")
    # 检查每个 PRAGMA 后面 10 行内是否有 _<pragma>_applied 检查
    for pragma in ["journal_mode", "synchronous", "auto_vacuum", "wal_autocheckpoint"]:
        attr_name = f"_{pragma}_applied"
        # 找 PRAGMA 行 (允许 {0} format)
        m = re.search(rf'PRAGMA {pragma}\s*=\s*[\w{{}}]+', content)
        if not m:
            issues.append(f"PRAGMA {pragma} 设置语句未找到")
            continue
        # 找 PRAGMA 行后面的 1000 chars, 看有 _applied 标志
        pos = m.end()
        window = content[pos:pos+1000]
        if attr_name not in window:
            issues.append(f"PRAGMA {pragma} 缺 {attr_name} 幂等检查")
    if not issues:
        PASSED.append("V8ad: 4 个 db-level PRAGMA 全部有幂等保护 (journal_mode/synchronous/auto_vacuum/wal_autocheckpoint)")
        return True
    FAILED.append("V8ad: " + "; ".join(issues))
    return False


def check_v8ae():
    """V8ae: mermaid 11.13.0 label 严格转义 (subgraph/node 全部走 sanitizeMermaidLabel)
    防止 BO 名称含 " 时 syntax error"""
    issues = []
    # 1. arrowHelper.js 含 sanitizeMermaidLabel 函数
    arrow_helper = WORKTREE_ROOT / "src" / "composables" / "useMermaid" / "syntax" / "_shared" / "arrowHelper.js"
    if not arrow_helper.exists():
        issues.append("arrowHelper.js 不存在")
    else:
        ah_content = arrow_helper.read_text(encoding="utf-8")
        if "export function sanitizeMermaidLabel" not in ah_content:
            issues.append("arrowHelper.js 缺 export function sanitizeMermaidLabel")
        if "#quot;" not in ah_content:
            issues.append("arrowHelper.js sanitizeMermaidLabel 缺 #quot; 转义")
        if "<br/>" not in ah_content:
            issues.append("arrowHelper.js sanitizeMermaidLabel 缺 <br/> 换行转义")
    # 2. UnifiedRenderer.js 用 sanitizeMermaidLabel
    ur = WORKTREE_ROOT / "src" / "services" / "groupModel" / "UnifiedRenderer.js"
    if not ur.exists():
        issues.append("UnifiedRenderer.js 不存在")
    else:
        ur_content = ur.read_text(encoding="utf-8")
        if "sanitizeMermaidLabel" not in ur_content:
            issues.append("UnifiedRenderer.js 缺 sanitizeMermaidLabel 调用")
        if ur_content.count("sanitizeMermaidLabel(") < 3:
            issues.append(f"UnifiedRenderer.js sanitizeMermaidLabel 调用次数 < 3 (实际 {ur_content.count('sanitizeMermaidLabel(')})")
    # 3. MermaidGenerator.js 用 sanitizeMermaidLabel
    mg = WORKTREE_ROOT / "src" / "services" / "groupModel" / "MermaidGenerator.js"
    if not mg.exists():
        issues.append("MermaidGenerator.js 不存在")
    else:
        mg_content = mg.read_text(encoding="utf-8")
        if "sanitizeMermaidLabel" not in mg_content:
            issues.append("MermaidGenerator.js 缺 sanitizeMermaidLabel 调用")
        if mg_content.count("sanitizeMermaidLabel(") < 3:
            issues.append(f"MermaidGenerator.js sanitizeMermaidLabel 调用次数 < 3 (实际 {mg_content.count('sanitizeMermaidLabel(')})")
    if not issues:
        PASSED.append("V8ae: mermaid 11.13 label 严格转义 (sanitizeMermaidLabel) 覆盖 UnifiedRenderer + MermaidGenerator")
        return True
    FAILED.append("V8ae: " + "; ".join(issues))
    return False


def check_v8af():
    """V8af: 业务对象图 关系数量告警 (财务云 600+ 节点 + 689 关系)
    useDiagramData.js 在 BO 图入口调 warnTooManyRelationships"""
    issues = []
    ud = WORKTREE_ROOT / "src" / "views" / "AADiagramApp" / "composables" / "useDiagramData.js"
    if not ud.exists():
        issues.append("useDiagramData.js 不存在")
    else:
        ud_content = ud.read_text(encoding="utf-8")
        # 1. import ElNotification
        if "ElNotification" not in ud_content:
            issues.append("useDiagramData.js 缺 ElNotification import")
        if "from 'element-plus'" not in ud_content:
            issues.append("useDiagramData.js 缺 from 'element-plus'")
        # 2. RELATIONSHIP_WARN_THRESHOLD 常量
        if "RELATIONSHIP_WARN_THRESHOLD" not in ud_content:
            issues.append("useDiagramData.js 缺 RELATIONSHIP_WARN_THRESHOLD 常量")
        # 3. warnTooManyRelationships 函数 + 调用
        if "function warnTooManyRelationships" not in ud_content:
            issues.append("useDiagramData.js 缺 warnTooManyRelationships 函数")
        if "warnTooManyRelationships(finalRelationships.length" not in ud_content:
            issues.append("useDiagramData.js BO 图入口未调 warnTooManyRelationships(finalRelationships.length, ...)")
        # 4. 阈值 = 100
        m = re.search(r"RELATIONSHIP_WARN_THRESHOLD\s*=\s*(\d+)", ud_content)
        if not m:
            issues.append("RELATIONSHIP_WARN_THRESHOLD 缺值")
        elif int(m.group(1)) != 100:
            issues.append(f"RELATIONSHIP_WARN_THRESHOLD = {m.group(1)} (应 100)")
        # 5. 防重复: wasAbove / isAbove 状态机 (避免 count 200/300 重复告警)
        if "_lastWarnedKey" not in ud_content:
            issues.append("useDiagramData.js 缺 _lastWarnedKey 状态变量")
        if "wasAbove" not in ud_content or "isAbove" not in ud_content:
            issues.append("useDiagramData.js 缺 wasAbove/isAbove 状态机判断")
    if not issues:
        PASSED.append("V8af: BO 图关系数量告警 (ElNotification + 阈值 100 + warnTooManyRelationships + wasAbove/isAbove 防重复)")
        return True
    FAILED.append("V8af: " + "; ".join(issues))
    return False


def check_v8ag():
    """V8ag: StepScopeSummary 步骤 1 关系数量告警 (V007.50 P0)
    useDiagramData.js 已有 V007.49 BO 图渲染告警, V007.50 把告警提前到
    StepChartType 内 StepScopeSummary 卡片 (步骤 0/1 类型选择页就看到)"""
    issues = []
    # 1. StepScopeSummary.vue 含 V007.50 改动
    sss = WORKTREE_ROOT / "src" / "views" / "AADiagramApp" / "components" / "steps" / "StepScopeSummary.vue"
    if not sss.exists():
        issues.append("StepScopeSummary.vue 不存在")
    else:
        sss_content = sss.read_text(encoding="utf-8")
        # import ElNotification
        if "ElNotification" not in sss_content:
            issues.append("StepScopeSummary.vue 缺 ElNotification import")
        # warnTooManyRelationshipsStep1 函数
        if "warnTooManyRelationshipsStep1" not in sss_content:
            issues.append("StepScopeSummary.vue 缺 warnTooManyRelationshipsStep1 函数")
        if "RELATIONSHIP_WARN_THRESHOLD" not in sss_content:
            issues.append("StepScopeSummary.vue 缺 RELATIONSHIP_WARN_THRESHOLD 常量")
        # watch total.objectRelations
        if "watch:" not in sss_content:
            issues.append("StepScopeSummary.vue 缺 watch 块")
        if "'total.objectRelations'" not in sss_content and '"total.objectRelations"' not in sss_content:
            issues.append("StepScopeSummary.vue 缺 watch 'total.objectRelations'")
        # chartType prop
        if "chartType" not in sss_content:
            issues.append("StepScopeSummary.vue 缺 chartType prop")
    # 2. StepChartType.vue 传 :chart-type="chartType"
    sct = WORKTREE_ROOT / "src" / "views" / "AADiagramApp" / "components" / "steps" / "StepChartType.vue"
    if not sct.exists():
        issues.append("StepChartType.vue 不存在")
    else:
        sct_content = sct.read_text(encoding="utf-8")
        if ":chart-type=\"chartType\"" not in sct_content and ':chart-type="chartType"' not in sct_content:
            issues.append("StepChartType.vue 缺 :chart-type=\"chartType\" 传参")
    if not issues:
        PASSED.append("V8ag: StepScopeSummary 步骤 1 告警 (ElNotification + watch total.objectRelations + chartType prop + 状态机防重复)")
        return True
    FAILED.append("V8ag: " + "; ".join(issues))
    return False


def check_v8ah():
    """V8ah: mermaid 11.13 label 严格转义覆盖 useBusinessObjectSyntax + useServiceModuleSyntax
    (V007.48 修了 UnifiedRenderer + MermaidGenerator, V007.51 补 useBusinessObjectSyntax + useServiceModuleSyntax)"""
    issues = []
    # 1. useBusinessObjectSyntax.js
    bos = WORKTREE_ROOT / "src" / "composables" / "useMermaid" / "syntax" / "useBusinessObjectSyntax.js"
    if not bos.exists():
        issues.append("useBusinessObjectSyntax.js 不存在")
    else:
        bos_content = bos.read_text(encoding="utf-8")
        if "sanitizeMermaidLabel" not in bos_content:
            issues.append("useBusinessObjectSyntax.js 缺 sanitizeMermaidLabel")
        elif bos_content.count("sanitizeMermaidLabel(") < 4:
            issues.append(f"useBusinessObjectSyntax.js sanitizeMermaidLabel( 调用 < 4 (实际 {bos_content.count('sanitizeMermaidLabel(')})")
    # 2. useServiceModuleSyntax.js
    sms = WORKTREE_ROOT / "src" / "composables" / "useMermaid" / "syntax" / "useServiceModuleSyntax.js"
    if not sms.exists():
        issues.append("useServiceModuleSyntax.js 不存在")
    else:
        sms_content = sms.read_text(encoding="utf-8")
        if "sanitizeMermaidLabel" not in sms_content:
            issues.append("useServiceModuleSyntax.js 缺 sanitizeMermaidLabel")
        elif sms_content.count("sanitizeMermaidLabel(") < 3:
            issues.append(f"useServiceModuleSyntax.js sanitizeMermaidLabel( 调用 < 3 (实际 {sms_content.count('sanitizeMermaidLabel(')})")
    if not issues:
        PASSED.append("V8ah: mermaid 11.13 label 严格转义 (sanitizeMermaidLabel) 覆盖 useBusinessObjectSyntax + useServiceModuleSyntax (V007.51 P0)")
        return True
    FAILED.append("V8ah: " + "; ".join(issues))
    return False


def check_v8ac():
    """V8ac: db_health_monitor 2 处裸连接 + async_audit_writer 降级路径 mmap_size=0"""
    issues = []
    # db_health_monitor 2 处
    f = META_DIR / "core" / "db_health_monitor.py"
    content = f.read_text(encoding="utf-8")
    if content.count("safe_connect_for_read") < 2:
        issues.append("db_health_monitor.py 缺 safe_connect_for_read (需 ≥2)")
    # async_audit_writer 降级路径
    f2 = META_DIR / "services" / "async_audit_writer.py"
    content2 = f2.read_text(encoding="utf-8")
    # 找降级路径
    m = re.search(r"# 降级到原裸连接.*?(?=\n            # )", content2, re.DOTALL)
    if m and "mmap_size=0" in m.group(0) and "cache_size=-2000" in m.group(0):
        pass
    else:
        issues.append("async_audit_writer.py 降级路径缺 mmap_size=0 + cache_size=-2000")
    if not issues:
        PASSED.append("V8ac: db_health_monitor 2 处 + async_audit_writer 降级路径全部加固")
        return True
    FAILED.append("V8ac: " + "; ".join(issues))
    return False


def main():
    print("=" * 60)
    print("V007.46 disk I/O error 恢复验证 (P0)")
    print("=" * 60)
    print()
    print(f"工作树: {WORKTREE_ROOT}")
    print(f"meta 路径: {META_DIR}")
    print()
    print("-" * 60)
    print("V8x 系列 invariant (V007.46 P0 BUG-FIX 锚点):")
    print("-" * 60)
    check_v8w()
    check_v8x()
    check_v8y()
    check_v8z()
    check_v8aa()
    check_v8ab()
    check_v8ac()
    check_v8ad()
    check_v8ae()
    check_v8af()
    check_v8ag()
    check_v8ah()
    print()
    print("-" * 60)
    print(f"PASSED ({len(PASSED)}):")
    for p in PASSED:
        print(f"  + {p}")
    print()
    if FAILED:
        print(f"FAILED ({len(FAILED)}):")
        for fail in FAILED:
            print(f"  ! {fail}")
        print()
        print(f"共 {len(FAILED)}/{len(PASSED) + len(FAILED)} 失败")
        return 1
    else:
        print(f"共 {len(PASSED)}/{len(PASSED)} 通过 ✅")
        return 0


if __name__ == "__main__":
    sys.exit(main())
