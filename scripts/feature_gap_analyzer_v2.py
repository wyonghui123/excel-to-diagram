# -*- coding: utf-8 -*-
"""
Feature Gap Analyzer v2 - 4 数据源 × 3 分辨率

设计:
  4 数据源 (DS):
    DS1: 代码扫描     → 功能/对象 × 代码位置
    DS2: Spec 质量    → v1/v2/soft-fail/API-smoke/分
    DS3: 业务规则     → meta/api 风险标签 (SEC/COMP/DATA/UX)
    DS4: UI 模式      → Element UI 组件使用

  3 分辨率 (L):
    L1-c: Category 覆盖度 (12 categories)
    L1-s: Scenario 漏测清单 (每个 category 的 variants)
    L1-r: Test case 描述 (具体步骤 + 断言)

  Auto: P0/P1 category 自动 deep-dive,无需用户问

执行:  python scripts/feature_gap_analyzer_v2.py
输出:  reports/feature_gap_v2.md  +  reports/feature_gap_v2.json
"""
import ast
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
API_DIR = PROJECT_ROOT / "meta" / "api"
SPECS_DIR = PROJECT_ROOT / "e2e" / "features"
REPORTS_DIR = PROJECT_ROOT / "reports"


# ====================== 公共:Feature Taxonomy ======================

FEATURE_CATEGORIES = {
    "sort": {
        "label": "排序 (Sort)",
        "variants": ["single_column", "multi_column", "calculated_field", "asc_desc", "with_null", "default_sort"],
        "risk": "UX",
    },
    "filter": {
        "label": "过滤 (Filter)",
        "variants": ["text_search", "exact_match", "date_range", "date_relative", "number_range",
                     "multi_select", "calculated_field", "single_criteria", "multi_criteria_AND", "multi_criteria_OR"],
        "risk": "UX",
    },
    "filter_combination": {
        "label": "组合过滤 (Filter Combination)",
        "variants": ["multi_select_plus_text_plus_sort", "cascading_filters", "saved_filter_variant"],
        "risk": "UX",
    },
    "inline_edit": {
        "label": "内联编辑 (Inline Edit)",
        "variants": ["create_row", "edit_row", "delete_row", "save_row", "cancel_row",
                     "visibility_logic", "readonly_logic", "quick_mode", "direct_mode",
                     "validation_inline", "tab_navigation"],
        "risk": "DATA",
    },
    "batch_ops": {
        "label": "批量操作 (Batch Ops)",
        "variants": ["batch_add", "batch_delete", "batch_update", "select_all", "select_page", "selection_count"],
        "risk": "DATA",
    },
    "deep_insert": {
        "label": "深插入 (Deep Insert)",
        "variants": ["create_with_children", "cascade_save", "rollback_on_child_error"],
        "risk": "DATA",
    },
    "calculated_field": {
        "label": "计算字段 (Calculated Field)",
        "variants": ["auto_compute", "sort_by_calc", "filter_by_calc", "display_in_table", "display_in_form"],
        "risk": "DATA",
    },
    "pagination": {
        "label": "分页 (Pagination)",
        "variants": ["page_size", "jump_to_page", "first_last_page", "total_count"],
        "risk": "UX",
    },
    "export_import": {
        "label": "导入导出 (Import/Export)",
        "variants": ["export_csv", "export_excel", "import_file", "import_validation", "import_rollback"],
        "risk": "DATA",
    },
    "association": {
        "label": "关联 (Association)",
        "variants": ["m2m_add", "m2m_remove", "fk_select", "search_help", "recent_items",
                     "inline_create_child", "deep_link", "batch_add", "batch_remove", "validation"],
        "risk": "DATA",
    },
    "form_validation": {
        "label": "表单验证 (Form Validation)",
        "variants": ["required", "format", "range", "unique", "custom_rule",
                     "async_validation", "cross_field_validation"],
        "risk": "DATA",
    },
    "conditional_logic": {
        "label": "条件逻辑 (Conditional Logic)",
        "variants": ["visible_when", "readonly_when", "required_when", "value_when",
                     "cascade_select", "dependent_field", "permission_based_visibility"],
        "risk": "COMP",  # 合规/权限相关
    },
}

# 风险等级映射
RISK_LEVELS = {
    "SEC": {"label": "安全 (Security)", "color": "🔴", "priority": "P0"},
    "COMP": {"label": "合规 (Compliance)", "color": "🔴", "priority": "P0"},
    "DATA": {"label": "数据 (Data Integrity)", "color": "🟡", "priority": "P1"},
    "UX": {"label": "UX", "color": "🟢", "priority": "P2"},
}

# 关键词 → 分类 + 风险
KEYWORD_TO_CATEGORY = {
    # sort (UX)
    "sort": "sort", "sortable": "sort", "sortkey": "sort", "sortorder": "sort",
    "defaultsort": "sort", "@sort-change": "sort", "ascending": "sort", "descending": "sort",
    "orderby": "sort", "ordering": "sort",
    # filter (UX)
    "filter": "filter", "filterable": "filter", "filtertrigger": "filter",
    "filterrule": "filter", "filtervariant": "filter", "searchable": "filter",
    "searchfields": "filter", "textsearch": "filter", "exactmatch": "filter",
    "daterange": "filter", "relativedate": "filter", "numberrange": "filter",
    "multiselect": "filter", "singlecriteria": "filter", "multicriteria": "filter",
    # filter combination
    "cascading": "filter_combination", "savedfilter": "filter_combination", "filterpreset": "filter_combination",
    # inline edit (DATA)
    "inline": "inline_edit", "inlinedit": "inline_edit", "inplaceedit": "inline_edit",
    "createrow": "inline_edit", "editrow": "inline_edit", "deleterow": "inline_edit",
    "saverow": "inline_edit", "cancelrow": "inline_edit", "tabnav": "inline_edit",
    "quickmode": "inline_edit", "directmode": "inline_edit", "visibility_logic": "inline_edit",
    "readonly_logic": "inline_edit",
    # batch (DATA)
    "batch": "batch_ops", "batchadd": "batch_ops", "batchdelete": "batch_ops", "batchupdate": "batch_ops",
    "selectall": "batch_ops", "selectpage": "batch_ops", "selectedrows": "batch_ops", "selectedcount": "batch_ops",
    # deep insert (DATA)
    "deepinsert": "deep_insert", "cascade": "deep_insert", "cascadesave": "deep_insert",
    "createwithchildren": "deep_insert", "withchildren": "deep_insert",
    # calculated (DATA)
    "calculated": "calculated_field", "computedfield": "calculated_field", "autocompute": "calculated_field",
    "calcfield": "calculated_field", "derived": "calculated_field",
    # pagination (UX)
    "pagination": "pagination", "pagesize": "pagination", "currentpage": "pagination", "totalpage": "pagination",
    "jumpto": "pagination", "nextpage": "pagination", "prevpage": "pagination",
    # export/import (DATA)
    "export": "export_import", "import": "export_import", "importfile": "export_import", "importvalidation": "export_import",
    # association (DATA)
    "m2m": "association", "manytomany": "association", "onetomany": "association", "manytoone": "association",
    "searchhelp": "association", "recentitems": "association", "fkselect": "association",
    "association": "association", "associations": "association",
    # form validation (DATA)
    "validation": "form_validation", "validate": "form_validation", "validator": "form_validation",
    "required": "form_validation", "uniquecheck": "form_validation", "formatvalidation": "form_validation",
    # conditional logic (COMP - 合规/权限)
    "conditional": "conditional_logic", "visiblewhen": "conditional_logic", "readonlywhen": "conditional_logic",
    "requiredwhen": "conditional_logic", "valuewhen": "conditional_logic", "depend": "conditional_logic",
    "cascade_select": "conditional_logic", "dependentfield": "conditional_logic",
    "permission_based_visibility": "conditional_logic",
}

# 业务对象
BUSINESS_OBJECTS = [
    "business_object", "user", "role", "user_group", "product", "version",
    "relationship", "enum_type", "permission", "audit_log", "menu",
    "diagram", "import_export", "draft", "filter_variant", "change_event",
    "change_subscription", "scheduled_task", "ai_async_task",
]


# ====================== DS1: 代码扫描 ======================

def ds1_code_scan():
    """扫 src/ 提取功能 + (object, feature) 对"""
    features = defaultdict(list)
    obj_feature_pairs = defaultdict(set)
    files = list(SRC_DIR.glob("components/**/*.vue")) + list(SRC_DIR.glob("composables/**/*.js")) if SRC_DIR.exists() else []

    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = str(f.relative_to(PROJECT_ROOT))
        content_lower = content.lower()
        rel_lower = rel.lower()

        for kw, cat in KEYWORD_TO_CATEGORY.items():
            pattern = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
            for m in pattern.finditer(content):
                line_no = content[:m.start()].count("\n") + 1
                features[cat].append(f"{rel}:{line_no}")

        for obj in BUSINESS_OBJECTS:
            obj_patterns = [obj, obj.replace("_", ""), obj.replace("_", "-")]
            if any(p in rel_lower or p in content_lower for p in obj_patterns):
                for kw, cat in KEYWORD_TO_CATEGORY.items():
                    if re.search(r"\b" + re.escape(kw) + r"\b", content, re.IGNORECASE):
                        obj_feature_pairs[(obj, cat)].add(f.name)

    return {"features": features, "obj_feature_pairs": obj_feature_pairs}


# ====================== DS2: Spec 质量 ======================

def ds2_spec_quality():
    """扫 e2e/features/ 输出每 spec 的质量分数"""
    specs = []
    if not SPECS_DIR.exists():
        return {"specs": specs, "summary": {}}

    for f in sorted(SPECS_DIR.glob("*.spec.js")):
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        # 基础指标
        tests = len(re.findall(r"^\s*test\(", content, re.MULTILINE))
        descs = len(re.findall(r"test\.describe\(", content))
        v1 = "login(" in content and "setAdminPermissions(" in content
        v2 = "auto-fixtures.js" in content

        # 质量指标
        soft_fail = bool(re.search(r"WARN[(\s]|软失败|soft.*fail|console\.warn", content, re.IGNORECASE))
        has_skip = "test.skip(" in content
        # API smoke: 只调用 API,不点 UI
        api_calls = len(re.findall(r"requests\.(post|get|put|delete)|fetch\(|axios\.", content))
        ui_actions = len(re.findall(r"page\.(click|fill|type|select|check|hover|press|locator)|getByRole|getByText|getByPlaceholder|getByTestId", content))
        is_api_smoke = api_calls > 0 and ui_actions == 0
        # data 隔离
        has_isolation = "isolation" in content or "auto-fixtures" in content
        has_withStep = "withStep" in content
        has_dataFinder = "dataFinder" in content or "findOrCreate" in content
        # 隔离 + trace
        has_trace = "TraceId" in content or "trace_id" in content

        # 评分 (0-100)
        score = 0
        if v2: score += 30
        elif v1: score += 10
        if not soft_fail: score += 20
        if not has_skip: score += 10
        if not is_api_smoke: score += 20
        if has_isolation: score += 5
        if has_withStep: score += 5
        if has_dataFinder: score += 5
        if has_trace: score += 5
        if tests >= 10: score += 5
        elif tests >= 5: score += 3
        elif tests >= 1: score += 1

        # 提取覆盖的功能 (跟 v1 一样)
        covered_cats = set()
        for kw, cat in KEYWORD_TO_CATEGORY.items():
            if re.search(r"\b" + re.escape(kw) + r"\b", content, re.IGNORECASE):
                covered_cats.add(cat)

        specs.append({
            "file": f.name,
            "tests": tests,
            "descs": descs,
            "v1": v1,
            "v2": v2,
            "soft_fail": soft_fail,
            "has_skip": has_skip,
            "is_api_smoke": is_api_smoke,
            "api_calls": api_calls,
            "ui_actions": ui_actions,
            "has_isolation": has_isolation,
            "has_withStep": has_withStep,
            "has_dataFinder": has_dataFinder,
            "has_trace": has_trace,
            "score": min(score, 100),
            "covered_cats": sorted(covered_cats),
        })

    # 汇总
    summary = {
        "total_specs": len(specs),
        "v1_count": sum(1 for s in specs if s["v1"]),
        "v2_count": sum(1 for s in specs if s["v2"]),
        "soft_fail_count": sum(1 for s in specs if s["soft_fail"]),
        "api_smoke_count": sum(1 for s in specs if s["is_api_smoke"]),
        "avg_score": sum(s["score"] for s in specs) / max(len(specs), 1),
        "low_score_count": sum(1 for s in specs if s["score"] < 50),
    }
    return {"specs": specs, "summary": summary}


# ====================== DS3: 业务规则 (meta/api) ======================

def ds3_business_rules():
    """扫 meta/api 提取风险标签 endpoint"""
    endpoints = []
    if not API_DIR.exists():
        return {"endpoints": endpoints, "summary": {}}

    # 风险关键词 → 标签
    risk_patterns = [
        ("permission", "SEC", "权限校验"),
        ("role", "SEC", "角色管理"),
        ("menu_permission", "SEC", "菜单权限"),
        ("data_permission", "COMP", "数据权限"),
        ("owner", "DATA", "所有者"),
        ("owner_transfer", "DATA", "所有者转移"),
        ("audit", "COMP", "审计"),
        ("permission_audit", "COMP", "权限审计"),
        ("scope", "COMP", "数据范围"),
        ("filter_variant", "UX", "过滤变体"),
        ("search_help", "UX", "搜索帮助"),
        ("value_help", "UX", "值帮助"),
        ("association", "DATA", "关联"),
        ("association_api", "DATA", "关联 API"),
        ("m2m", "DATA", "多对多"),
        ("batch", "DATA", "批量"),
        ("cascade", "DATA", "级联"),
        ("import_export", "DATA", "导入导出"),
        ("scheduled", "DATA", "定时任务"),
        ("ai_async", "DATA", "AI 异步"),
        ("login", "SEC", "登录"),
        ("auth", "SEC", "认证"),
    ]

    for f in API_DIR.glob("*.py"):
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        fname = f.stem.lower()
        # 找这个文件的风险标签
        file_risks = []
        for kw, risk, desc in risk_patterns:
            if kw in fname or re.search(r"\b" + re.escape(kw) + r"\b", content, re.IGNORECASE):
                file_risks.append((risk, desc, kw))
        if not file_risks:
            continue
        # 提取 endpoint (粗略: 找 @xxx.route 或 @api.route)
        routes = re.findall(r"@\w+\.(?:route|get|post|put|delete|patch)\(['\"]([^'\"]+)", content)
        endpoint_count = len(routes) if routes else content.count("def ")

        # 主风险 (最高级)
        risk_priority = {"SEC": 4, "COMP": 3, "DATA": 2, "UX": 1}
        main_risk = max(file_risks, key=lambda x: risk_priority[x[0]])

        endpoints.append({
            "file": f.name,
            "main_risk": main_risk[0],
            "main_risk_label": main_risk[1],
            "all_risks": [r[1] for r in file_risks],
            "endpoint_count": endpoint_count,
            "routes_sample": routes[:5],
        })

    # 汇总
    risk_count = defaultdict(int)
    for e in endpoints:
        risk_count[e["main_risk"]] += 1
    summary = {
        "total_api_files": len(endpoints),
        "by_risk": dict(risk_count),
    }
    return {"endpoints": endpoints, "summary": summary}


# ====================== DS4: UI 模式 (Element UI 组件) ======================

def ds4_ui_patterns():
    """扫 src/ 提取 Element UI 组件使用模式"""
    patterns = defaultdict(int)
    pattern_locations = defaultdict(list)
    if not SRC_DIR.exists():
        return {"patterns": dict(patterns), "locations": dict(pattern_locations)}

    # 关键 Element UI 组件
    ui_components = {
        "el-table": "表格 (List/Table)",
        "el-form": "表单 (Form)",
        "el-dialog": "弹窗 (Dialog)",
        "el-drawer": "抽屉 (Drawer)",
        "el-tabs": "标签页 (Tabs)",
        "el-select": "下拉选择 (Select)",
        "el-cascader": "级联选择 (Cascader)",
        "el-date-picker": "日期选择 (DatePicker)",
        "el-tree": "树形 (Tree)",
        "el-upload": "上传 (Upload)",
        "el-pagination": "分页 (Pagination)",
        "el-checkbox-group": "多选框组 (CheckboxGroup)",
        "el-radio-group": "单选框组 (RadioGroup)",
        "el-input": "输入框 (Input)",
        "el-button": "按钮 (Button)",
        "el-menu": "菜单 (Menu)",
    }

    files = list(SRC_DIR.glob("components/**/*.vue")) + list(SRC_DIR.glob("views/**/*.vue"))
    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for comp, label in ui_components.items():
            count = content.count(f"<{comp}")
            if count > 0:
                patterns[comp] += count
                pattern_locations[comp].append(f"{f.name} ({count})")

    return {
        "patterns": dict(patterns),
        "locations": {k: v[:5] for k, v in pattern_locations.items()},  # 取前 5
    }


# ====================== 3 分辨率: 矩阵 + Scenario + Test Case ======================

def build_category_matrix(ds1, ds2, ds3, ds4):
    """L1-c: 12 category × 4 data source 矩阵"""
    matrix = {}
    for cat, info in FEATURE_CATEGORIES.items():
        ds1_count = len(ds1["features"].get(cat, []))
        ds1_in_code = ds1_count > 0

        # DS2: 该 category 在哪些 spec 被覆盖,质量如何
        covered_specs = [s for s in ds2["specs"] if cat in s["covered_cats"]]
        # 质量分数 = 平均分
        if covered_specs:
            avg_score = sum(s["score"] for s in covered_specs) / len(covered_specs)
            best_spec = max(covered_specs, key=lambda s: s["score"])
        else:
            avg_score = 0
            best_spec = None

        # DS3: 该 category 关联的 API 风险
        risk_apis = []
        for e in ds3["endpoints"]:
            cat_keywords = [k for k, c in KEYWORD_TO_CATEGORY.items() if c == cat]
            fname_lower = e["file"].lower()
            for kw in cat_keywords:
                if kw in fname_lower or kw in e["main_risk_label"].lower():
                    risk_apis.append(e["file"])
                    break

        # DS4: 该 category 关联的 UI 组件 (粗略)
        ui_pattern = ""
        if cat in ("sort", "filter", "filter_combination", "pagination"):
            ui_pattern = "el-table / el-pagination"
        elif cat in ("inline_edit",):
            ui_pattern = "el-table (inline cell)"
        elif cat in ("association",):
            ui_pattern = "el-dialog / el-cascader / search-help"
        elif cat in ("form_validation", "conditional_logic"):
            ui_pattern = "el-form / el-select"
        elif cat in ("export_import",):
            ui_pattern = "el-upload"
        elif cat in ("deep_insert",):
            ui_pattern = "ObjectChildSection"
        else:
            ui_pattern = "通用 Element UI"

        # 风险评估
        risk = info.get("risk", "UX")
        is_critical = risk in ("SEC", "COMP")
        is_covered = len(covered_specs) > 0 and avg_score >= 60

        matrix[cat] = {
            "label": info["label"],
            "risk": risk,
            "is_critical": is_critical,
            "ds1_in_code": ds1_in_code,
            "ds1_count": ds1_count,
            "ds2_covered_specs": len(covered_specs),
            "ds2_avg_score": round(avg_score, 1),
            "ds2_best_spec": best_spec["file"] if best_spec else None,
            "ds3_risk_apis": risk_apis[:3],
            "ds4_ui_pattern": ui_pattern,
            "is_covered": is_covered,
            "status": "covered" if is_covered else ("thin" if covered_specs else "missing"),
        }
    return matrix


def auto_deep_dive(cat, matrix_entry, ds1, ds2, ds3, ds4):
    """对 P0/P1 category 自动 deep-dive: 列出 scenarios + test cases"""
    info = FEATURE_CATEGORIES[cat]
    risk = info.get("risk", "UX")
    if risk not in ("SEC", "COMP") and matrix_entry["status"] != "missing":
        # 只对 P0/P1 (SEC/COMP risk) 或完全没测的 category 做 deep-dive
        if matrix_entry["ds2_covered_specs"] >= 1 and matrix_entry["ds2_avg_score"] >= 70:
            return None  # 充分覆盖,不需要 deep-dive

    # 列出 scenarios
    scenarios = []
    for v in info["variants"]:
        # 检查代码中是否有 (粗略)
        code_locs = [loc for loc in ds1["features"].get(cat, []) if v.replace("_", "") in loc.lower() or v in loc.lower()]
        # 检查现有 spec 是否提到
        spec_mentions = []
        for s in ds2["specs"]:
            if v in s["file"].lower() or v.replace("_", " ") in s["file"].lower():
                spec_mentions.append(s["file"])
        scenarios.append({
            "name": v,
            "code_has": len(code_locs) > 0,
            "code_locs": code_locs[:2],
            "spec_mentions": spec_mentions,
            "is_covered": len(spec_mentions) > 0,
        })

    # 推荐 test cases (按 scenario 状态生成)
    test_cases = []
    for s in scenarios:
        if s["is_covered"]:
            continue
        # 业务风险高的, 必测
        priority = "P0" if risk in ("SEC", "COMP") else "P1"
        test_cases.append({
            "scenario": s["name"],
            "priority": priority,
            "description": f"验证 {info['label']} 的 {s['name']} 场景",
            "code_evidence": s["code_locs"][:1] if s["code_locs"] else [],
        })

    return {
        "category": cat,
        "label": info["label"],
        "risk": risk,
        "status": matrix_entry["status"],
        "ds1_in_code": matrix_entry["ds1_in_code"],
        "ds1_count": matrix_entry["ds1_count"],
        "ds2_covered_specs": matrix_entry["ds2_covered_specs"],
        "ds2_avg_score": matrix_entry["ds2_avg_score"],
        "ds3_risk_apis": matrix_entry["ds3_risk_apis"],
        "ds4_ui_pattern": matrix_entry["ds4_ui_pattern"],
        "scenarios": scenarios,
        "recommended_test_cases": test_cases,
    }


# ====================== 渲染报告 ======================

def render_v2_report(ds1, ds2, ds3, ds4, matrix, deep_dives):
    lines = []
    lines.append("# Feature Gap Analyzer v2 (4×3)")
    lines.append("")
    lines.append(f"> **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"> **生成工具**: scripts/feature_gap_analyzer_v2.py")
    lines.append(f"> **设计**: 4 数据源 × 3 分辨率 + Auto deep-dive")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ====== Executive Summary ======
    lines.append("## 一、Executive Summary")
    lines.append("")
    total_cats = len(matrix)
    covered = sum(1 for m in matrix.values() if m["status"] == "covered")
    thin = sum(1 for m in matrix.values() if m["status"] == "thin")
    missing = sum(1 for m in matrix.values() if m["status"] == "missing")
    critical_missing = sum(1 for m in matrix.values() if m["status"] == "missing" and m["is_critical"])
    coverage = covered / total_cats * 100

    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append(f"| **整体覆盖度** | **{coverage:.1f}%** ({covered}/{total_cats} category 充分覆盖) |")
    lines.append(f"| Critical missing (SEC/COMP) | **{critical_missing}** |")
    lines.append(f"| 薄覆盖 (thin) | {thin} |")
    lines.append(f"| 完全没测 (missing) | {missing} |")
    lines.append(f"| Spec 总数 | {ds2['summary'].get('total_specs', 0)} |")
    lines.append(f"| Spec 平均质量分 | {ds2['summary'].get('avg_score', 0):.1f} / 100 |")
    lines.append(f"| v1 spec (需迁移) | {ds2['summary'].get('v1_count', 0)} |")
    lines.append(f"| v2 spec | {ds2['summary'].get('v2_count', 0)} |")
    lines.append(f"| soft-fail spec | {ds2['summary'].get('soft_fail_count', 0)} |")
    lines.append(f"| API smoke spec (无 UI) | {ds2['summary'].get('api_smoke_count', 0)} |")
    lines.append(f"| API 风险端点 | {ds3['summary'].get('total_api_files', 0)} |")
    lines.append("")

    # ====== 二、4 数据源 (DS) ======
    lines.append("## 二、4 数据源扫描结果")
    lines.append("")

    # DS1
    lines.append("### DS1: 代码扫描")
    lines.append(f"- 扫描文件: src/components + src/composables")
    lines.append(f"- 发现功能 category: {len(ds1['features'])}")
    lines.append(f"- (object × feature) 对: {len(ds1['obj_feature_pairs'])}")
    lines.append("")

    # DS2
    lines.append("### DS2: Spec 质量评分")
    lines.append("")
    lines.append("| 评分维度 | 数量 | 占比 |")
    lines.append("|---------|------|------|")
    s = ds2["summary"]
    tot = s.get("total_specs", 1)
    lines.append(f"| v1 风格 | {s.get('v1_count', 0)} | {s.get('v1_count', 0)/tot*100:.0f}% |")
    lines.append(f"| v2 风格 | {s.get('v2_count', 0)} | {s.get('v2_count', 0)/tot*100:.0f}% |")
    lines.append(f"| soft-fail | {s.get('soft_fail_count', 0)} | {s.get('soft_fail_count', 0)/tot*100:.0f}% |")
    lines.append(f"| API smoke (无 UI) | {s.get('api_smoke_count', 0)} | {s.get('api_smoke_count', 0)/tot*100:.0f}% |")
    lines.append(f"| 质量分 < 50 | {s.get('low_score_count', 0)} | {s.get('low_score_count', 0)/tot*100:.0f}% |")
    lines.append("")
    lines.append("**Top 5 低质量 spec** (需重写/迁移):")
    lines.append("")
    low_specs = sorted(ds2["specs"], key=lambda x: x["score"])[:5]
    for s_obj in low_specs:
        flags = []
        if s_obj["v1"]: flags.append("v1")
        if s_obj["soft_fail"]: flags.append("soft-fail")
        if s_obj["is_api_smoke"]: flags.append("API-smoke")
        lines.append(f"- `{s_obj['file']}` - 分 {s_obj['score']} ({', '.join(flags) or 'ok'})")
    lines.append("")

    # DS3
    lines.append("### DS3: 业务规则 (meta/api)")
    lines.append("")
    lines.append("| 风险等级 | API 文件数 |")
    lines.append("|---------|-----------|")
    for risk, count in ds3["summary"].get("by_risk", {}).items():
        risk_info = RISK_LEVELS.get(risk, {"label": risk, "color": "·"})
        lines.append(f"| {risk_info['color']} {risk_info['label']} | {count} |")
    lines.append("")
    lines.append("**SEC/COMP 风险 API** (必须 E2E 覆盖):")
    lines.append("")
    for e in ds3["endpoints"]:
        if e["main_risk"] in ("SEC", "COMP"):
            lines.append(f"- `{e['file']}` ({e['main_risk_label']}, {e['endpoint_count']} endpoints)")
    lines.append("")

    # DS4
    lines.append("### DS4: UI 模式 (Element UI)")
    lines.append("")
    lines.append("| 组件 | 使用次数 |")
    lines.append("|------|---------|")
    sorted_patterns = sorted(ds4["patterns"].items(), key=lambda x: -x[1])
    for comp, count in sorted_patterns[:10]:
        lines.append(f"| `<{comp}>` | {count} |")
    lines.append("")

    # ====== 三、L1-c 矩阵 ======
    lines.append("## 三、L1-c: Category 覆盖度矩阵 (12 × 4 DS)")
    lines.append("")
    lines.append("| Category | 风险 | DS1代码 | DS2 spec (分) | DS3 API | DS4 UI | 状态 |")
    lines.append("|----------|------|---------|--------------|---------|--------|------|")
    for cat, m in matrix.items():
        risk_info = RISK_LEVELS.get(m["risk"], {"label": m["risk"], "color": "·", "priority": "P3"})
        status_icon = {"covered": "✅", "thin": "⚠️", "missing": "❌"}.get(m["status"], "·")
        ds1_icon = "✅" if m["ds1_in_code"] else "·"
        ds2_str = f"{m['ds2_covered_specs']} ({m['ds2_avg_score']})" if m["ds2_covered_specs"] else "·"
        ds3_str = str(len(m["ds3_risk_apis"])) if m["ds3_risk_apis"] else "·"
        lines.append(f"| {m['label']} | {risk_info['color']}{risk_info['label'][:4]} | {ds1_icon} ({m['ds1_count']}) | {ds2_str} | {ds3_str} | {m['ds4_ui_pattern'][:15]} | {status_icon} |")
    lines.append("")

    # ====== 四、Auto Deep-Dive (P0/P1) ======
    lines.append("## 四、Auto Deep-Dive (P0/P1 + missing/thin)")
    lines.append("")
    lines.append("> 每个 deep-dive 包含: 4 DS 证据 + scenarios + 推荐的 test cases")
    lines.append("")

    for dd in deep_dives:
        if not dd:
            continue
        risk_info = RISK_LEVELS.get(dd["risk"], {"label": dd["risk"], "color": "·", "priority": "P3"})
        status_icon = {"covered": "✅", "thin": "⚠️", "missing": "❌"}.get(dd["status"], "·")
        lines.append(f"### {risk_info['color']} [{risk_info['priority']}] {dd['label']} {status_icon}")
        lines.append("")
        lines.append("**4 数据源证据**:")
        lines.append(f"- DS1 代码: {dd['ds1_count']} 处" if dd['ds1_in_code'] else "- DS1 代码: ❌ 无")
        lines.append(f"- DS2 spec: {dd['ds2_covered_specs']} 个, 平均分 {dd['ds2_avg_score']}" if dd['ds2_covered_specs'] else "- DS2 spec: ❌ 完全没测")
        lines.append(f"- DS3 API: {len(dd['ds3_risk_apis'])} 个相关 ({', '.join(dd['ds3_risk_apis']) if dd['ds3_risk_apis'] else '无'})")
        lines.append(f"- DS4 UI 组件: {dd['ds4_ui_pattern']}")
        lines.append("")

        if dd["scenarios"]:
            lines.append("**Scenarios (L1-s)**:")
            lines.append("")
            for s in dd["scenarios"]:
                icon = "✅" if s["is_covered"] else ("⚙️" if s["code_has"] else "·")
                lines.append(f"- {icon} **{s['name']}**: " + (
                    f"已测 ({', '.join(s['spec_mentions'])})" if s["is_covered"]
                    else (f"代码有 ({s['code_locs'][0] if s['code_locs'] else 'N/A'})" if s["code_has"] else "未覆盖")
                ))
            lines.append("")

        if dd["recommended_test_cases"]:
            lines.append(f"**推荐 test cases (L1-r)**: {len(dd['recommended_test_cases'])} 个")
            lines.append("")
            for tc in dd["recommended_test_cases"][:8]:  # 最多显示 8 个
                lines.append(f"- [{tc['priority']}] **{tc['scenario']}**")
            if len(dd["recommended_test_cases"]) > 8:
                lines.append(f"- ... +{len(dd['recommended_test_cases']) - 8} more")
            lines.append("")

    # ====== 五、最终优先级 ======
    lines.append("## 五、最终优先级 (Risk × Coverage)")
    lines.append("")
    lines.append("| 排序 | Category | 风险 | 状态 | 推荐 ROI | 优先级 |")
    lines.append("|------|----------|------|------|---------|--------|")
    priority_list = []
    for cat, m in matrix.items():
        risk_info = RISK_LEVELS.get(m["risk"], {"label": m["risk"], "color": "·", "priority": "P3"})
        # ROI 评估
        if m["status"] == "missing" and m["is_critical"]:
            roi = "极高"
            prio = "P0"
        elif m["status"] == "missing":
            roi = "高"
            prio = "P1"
        elif m["status"] == "thin" and m["is_critical"]:
            roi = "高"
            prio = "P0"
        else:
            roi = "中"
            prio = m.get("priority", "P2")
        priority_list.append((prio, m["label"], m["risk"], m["status"], roi))

    # 排序: P0 优先, missing > thin > covered
    status_order = {"missing": 0, "thin": 1, "covered": 2}
    priority_list.sort(key=lambda x: (x[0], status_order.get(x[3], 3)))
    for i, (prio, label, risk, status, roi) in enumerate(priority_list, 1):
        risk_info = RISK_LEVELS.get(risk, {"color": "·", "label": risk})
        status_icon = {"covered": "✅", "thin": "⚠️", "missing": "❌"}.get(status, "·")
        lines.append(f"| {i} | {label} | {risk_info['color']}{risk} | {status_icon} | {roi} | {prio} |")
    lines.append("")

    # ====== 六、附录: Spec 质量详情 ======
    lines.append("## 六、附录: Spec 质量详情 (15 spec)")
    lines.append("")
    lines.append("| Spec | tests | v1/v2 | soft-fail | smoke | 分 |")
    lines.append("|------|------:|------|-----------|-------|----:|")
    for s in sorted(ds2["specs"], key=lambda x: x["score"]):
        style = "v2" if s["v2"] else ("v1" if s["v1"] else "?")
        soft = "⚠️" if s["soft_fail"] else "·"
        smoke = "⚠️" if s["is_api_smoke"] else "·"
        lines.append(f"| `{s['file']}` | {s['tests']} | {style} | {soft} | {smoke} | **{s['score']}** |")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_本报告由 scripts/feature_gap_analyzer_v2.py (4×3 设计) 自动生成_")
    lines.append("")

    return "\n".join(lines) + "\n"


# ====================== 入口 ======================

def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print("[DS1] 扫代码...")
    ds1 = ds1_code_scan()
    print(f"  功能 category: {len(ds1['features'])}, 对象×功能对: {len(ds1['obj_feature_pairs'])}")

    print("[DS2] 扫 spec 质量...")
    ds2 = ds2_spec_quality()
    s = ds2["summary"]
    print(f"  {s['total_specs']} specs, 平均分 {s['avg_score']:.1f}, v1={s['v1_count']}, v2={s['v2_count']}, soft-fail={s['soft_fail_count']}")

    print("[DS3] 扫业务规则 (meta/api)...")
    ds3 = ds3_business_rules()
    print(f"  {ds3['summary'].get('total_api_files', 0)} 个 API 文件, 风险分布: {ds3['summary'].get('by_risk', {})}")

    print("[DS4] 扫 UI 模式...")
    ds4 = ds4_ui_patterns()
    print(f"  {len(ds4['patterns'])} 个 Element UI 组件")

    print("[L1-c] 构建 category 矩阵...")
    matrix = build_category_matrix(ds1, ds2, ds3, ds4)
    print(f"  矩阵: {len(matrix)} category")

    print("[Auto Deep-Dive] 对 P0/P1 + missing/thin category...")
    deep_dives = []
    for cat in FEATURE_CATEGORIES:
        dd = auto_deep_dive(cat, matrix[cat], ds1, ds2, ds3, ds4)
        deep_dives.append(dd)
    valid_dd = [d for d in deep_dives if d]
    print(f"  {len(valid_dd)} 个 category 需要 deep-dive")

    print("[Render] 渲染报告...")
    md = render_v2_report(ds1, ds2, ds3, ds4, matrix, deep_dives)
    md_path = REPORTS_DIR / "feature_gap_v2.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"  [OK] {md_path}")

    json_path = REPORTS_DIR / "feature_gap_v2.json"
    json_path.write_text(
        json.dumps(
            {
                "ds1": {"features": {k: len(v) for k, v in ds1["features"].items()}, "obj_feature_pairs_count": len(ds1["obj_feature_pairs"])},
                "ds2_summary": ds2["summary"],
                "ds2_specs": ds2["specs"],
                "ds3_summary": ds3["summary"],
                "ds3_endpoints": ds3["endpoints"],
                "ds4_patterns": ds4["patterns"],
                "matrix": matrix,
                "deep_dives": [d for d in deep_dives if d],
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"  [OK] {json_path}")

    # 关键数字
    print()
    print("=" * 60)
    print("关键发现:")
    print(f"  整体覆盖度: {sum(1 for m in matrix.values() if m['status'] == 'covered') / len(matrix) * 100:.1f}%")
    print(f"  Critical missing (SEC/COMP): {sum(1 for m in matrix.values() if m['status'] == 'missing' and m['is_critical'])}")
    print(f"  Spec v1 (需迁移): {ds2['summary']['v1_count']}")
    print(f"  Spec soft-fail: {ds2['summary']['soft_fail_count']}")
    print(f"  API smoke (无 UI): {ds2['summary']['api_smoke_count']}")
    print(f"  Deep-dive 触发: {len(valid_dd)} category")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
