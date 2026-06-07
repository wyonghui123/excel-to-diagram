# -*- coding: utf-8 -*-
"""
Feature Gap Analyzer (L1) - 反向识别 E2E 测试 case 缺口

三步流程:
  1. 扫项目代码 (src/components + src/composables)  → 提取功能矩阵
  2. 扫现有 spec (e2e/features/*.spec.js)         → 提取覆盖矩阵
  3. 矩阵对比                                     → 输出 gap 清单 + 优先级 + test case 描述

执行:  python scripts/feature_gap_analyzer.py
输出:  reports/feature_gap.md  +  reports/feature_gap.json
"""
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
SPECS_DIR = PROJECT_ROOT / "e2e" / "features"
REPORTS_DIR = PROJECT_ROOT / "reports"

# ==================== 1. 功能分类法 (Feature Taxonomy) ====================

# 11 大类核心功能 (来自项目实际代码 + 业务需求)
FEATURE_CATEGORIES = {
    "sort": {
        "label": "排序 (Sort)",
        "variants": ["single_column", "multi_column", "calculated_field", "asc_desc", "with_null", "default_sort"],
    },
    "filter": {
        "label": "过滤 (Filter)",
        "variants": ["text_search", "exact_match", "date_range", "date_relative", "number_range",
                     "multi_select", "calculated_field", "single_criteria", "multi_criteria_AND", "multi_criteria_OR"],
    },
    "filter_combination": {
        "label": "组合过滤 (Filter Combination)",
        "variants": ["multi_select_plus_text_plus_sort", "cascading_filters", "saved_filter_variant"],
    },
    "inline_edit": {
        "label": "内联编辑 (Inline Edit)",
        "variants": ["create_row", "edit_row", "delete_row", "save_row", "cancel_row",
                     "visibility_logic", "readonly_logic", "quick_mode", "direct_mode",
                     "validation_inline", "tab_navigation"],
    },
    "batch_ops": {
        "label": "批量操作 (Batch Ops)",
        "variants": ["batch_add", "batch_delete", "batch_update", "select_all", "select_page", "selection_count"],
    },
    "deep_insert": {
        "label": "深插入 (Deep Insert)",
        "variants": ["create_with_children", "cascade_save", "rollback_on_child_error"],
    },
    "calculated_field": {
        "label": "计算字段 (Calculated Field)",
        "variants": ["auto_compute", "sort_by_calc", "filter_by_calc", "display_in_table", "display_in_form"],
    },
    "pagination": {
        "label": "分页 (Pagination)",
        "variants": ["page_size", "jump_to_page", "first_last_page", "total_count"],
    },
    "export_import": {
        "label": "导入导出 (Import/Export)",
        "variants": ["export_csv", "export_excel", "import_file", "import_validation", "import_rollback"],
    },
    "association": {
        "label": "关联 (Association)",
        "variants": ["m2m_add", "m2m_remove", "fk_select", "search_help", "recent_items",
                     "inline_create_child", "deep_link"],
    },
    "form_validation": {
        "label": "表单验证 (Form Validation)",
        "variants": ["required", "format", "range", "unique", "custom_rule",
                     "async_validation", "cross_field_validation"],
    },
    "conditional_logic": {
        "label": "条件逻辑 (Conditional Logic)",
        "variants": ["visible_when", "readonly_when", "required_when", "value_when",
                     "cascade_select", "dependent_field"],
    },
}

# 关键词 → 分类 (代码 + spec 通用)
KEYWORD_TO_CATEGORY = {
    # sort
    "sort": "sort", "sortable": "sort", "sortkey": "sort", "sortorder": "sort",
    "sortinfo": "sort", "defaultsort": "sort", "@sort-change": "sort", "sortchange": "sort",
    "asc": "sort", "desc": "sort", "ascending": "sort", "descending": "sort",
    "orderby": "sort", "ordering": "sort", "getariaSort": "sort",
    # filter
    "filter": "filter", "filters": "filter", "filterable": "filter", "filtertrigger": "filter",
    "filterrule": "filter", "filterrules": "filter", "filtervariant": "filter", "filtervariants": "filter",
    "search": "filter", "searchable": "filter", "searchfields": "filter", "searchquery": "filter",
    "searchbox": "filter", "textsearch": "filter", "exactmatch": "filter",
    "daterange": "filter", "datestart": "filter", "dateend": "filter", "relativedate": "filter",
    "numberrange": "filter", "multiselect": "filter", "singlecriteria": "filter",
    "multicriteria": "filter", "criteriaand": "filter", "criteriaor": "filter",
    # filter combination
    "cascading": "filter_combination", "savedfilter": "filter_combination", "filterpreset": "filter_combination",
    # inline edit
    "inline": "inline_edit", "inlinedit": "inline_edit", "inplaceedit": "inline_edit",
    "createrow": "inline_edit", "editrow": "inline_edit", "deleterow": "inline_edit",
    "saverow": "inline_edit", "cancelrow": "inline_edit", "tabnav": "inline_edit",
    "quickmode": "inline_edit", "directmode": "inline_edit", "quick_mode": "inline_edit", "direct_mode": "inline_edit",
    # batch
    "batch": "batch_ops", "batchadd": "batch_ops", "batchdelete": "batch_ops", "batchupdate": "batch_ops",
    "selectall": "batch_ops", "selectpage": "batch_ops", "selectedrows": "batch_ops", "selectedcount": "batch_ops",
    # deep insert
    "deepinsert": "deep_insert", "deep_insert": "deep_insert", "cascade": "deep_insert", "cascadesave": "deep_insert",
    "createwithchildren": "deep_insert", "withchildren": "deep_insert",
    # calculated
    "calculated": "calculated_field", "computedfield": "calculated_field", "autocompute": "calculated_field",
    "calcfield": "calculated_field", "derived": "calculated_field", "compute": "calculated_field",
    # pagination
    "pagination": "pagination", "pagesize": "pagination", "currentpage": "pagination", "totalpage": "pagination",
    "jumpto": "pagination", "nextpage": "pagination", "prevpage": "pagination",
    # export/import
    "export": "export_import", "import": "export_import", "importfile": "export_import", "importvalidation": "export_import",
    # association
    "m2m": "association", "manytomany": "association", "onetomany": "association", "manytoone": "association",
    "searchhelp": "association", "recentitems": "association", "fkselect": "association",
    "fk": "association", "association": "association", "associations": "association",
    # form validation
    "validation": "form_validation", "validate": "form_validation", "validator": "form_validation",
    "required": "form_validation", "uniquecheck": "form_validation", "formatvalidation": "form_validation",
    # conditional
    "conditional": "conditional_logic", "visiblewhen": "conditional_logic", "readonlywhen": "conditional_logic",
    "requiredwhen": "conditional_logic", "valuewhen": "conditional_logic", "depend": "conditional_logic",
    "cascade_select": "conditional_logic", "dependentfield": "conditional_logic",
}

# 业务对象 (来自 ai_discover_e2e_gaps.py 同源)
BUSINESS_OBJECTS = [
    "business_object", "user", "role", "user_group", "product", "version",
    "relationship", "enum_type", "permission", "audit_log", "menu",
    "diagram", "import_export", "draft", "filter_variant", "change_event",
    "change_subscription", "scheduled_task", "ai_async_task",
]


# ==================== 2. 扫代码:提取功能存在 ====================

def scan_code_features():
    """扫 src/components + src/composables,提取功能出现的位置"""
    features = defaultdict(list)  # category -> [file:line]
    if not SRC_DIR.exists():
        return features

    # 扫的文件
    patterns = [
        "components/common/*.vue",
        "components/common/**/*.vue",
        "composables/*.js",
        "composables/**/*.js",
    ]
    files = []
    for p in patterns:
        files.extend(SRC_DIR.glob(p))

    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # 找每个关键词
        for kw, cat in KEYWORD_TO_CATEGORY.items():
            # 用 word boundary 避免误匹配
            pattern = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
            for m in pattern.finditer(content):
                line_no = content[: m.start()].count("\n") + 1
                rel_path = str(f.relative_to(PROJECT_ROOT))
                features[cat].append(f"{rel_path}:{line_no}")

    return features


# ==================== 3. 扫 spec:提取覆盖矩阵 ====================

def scan_spec_coverage():
    """扫 e2e/features/*.spec.js,提取覆盖的功能"""
    coverage = defaultdict(set)  # category -> set(feature_keyword)
    if not SPECS_DIR.exists():
        return coverage

    for f in SPECS_DIR.glob("*.spec.js"):
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for kw, cat in KEYWORD_TO_CATEGORY.items():
            pattern = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
            if pattern.search(content):
                coverage[cat].add(kw)

    return coverage


# ==================== 4. 业务对象 × 功能 矩阵 ====================

def scan_object_feature_in_code():
    """扫代码,识别 (object, feature) 对应关系"""
    pairs = defaultdict(set)  # (object, feature) -> [evidence]
    if not SRC_DIR.exists():
        return pairs

    files = list(SRC_DIR.glob("components/**/*.vue")) + list(SRC_DIR.glob("composables/**/*.js"))
    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore").lower()
        except Exception:
            continue
        rel = str(f.relative_to(PROJECT_ROOT)).lower()
        # 找代码中提及的 object
        for obj in BUSINESS_OBJECTS:
            obj_patterns = [obj, obj.replace("_", ""), obj.replace("_", "-")]
            obj_in_file = any(p in rel or p in content for p in obj_patterns)
            if not obj_in_file:
                continue
            # 找代码中提及的 feature keyword
            for kw, cat in KEYWORD_TO_CATEGORY.items():
                if re.search(r"\b" + re.escape(kw) + r"\b", content, re.IGNORECASE):
                    pairs[(obj, cat)].add(f"{f.name}#{kw}")

    return pairs


# ==================== 5. 渲染 Gap 报告 ====================

# 业务价值评分 (来自实际业务场景)
PRIORITY_MAP = {
    "inline_edit": ("P0", "核心产品能力,影响所有 BO 编辑"),
    "batch_ops": ("P0", "数据导入/批量管理必备"),
    "sort": ("P1", "高频功能,影响 UX"),
    "filter": ("P1", "高频功能,影响 UX"),
    "filter_combination": ("P2", "高级用户需求"),
    "deep_insert": ("P1", "嵌套数据建模关键"),
    "calculated_field": ("P1", "数据展示核心"),
    "association": ("P1", "M2M 是核心数据模型"),
    "pagination": ("P2", "基础功能,但实现简单"),
    "export_import": ("P1", "运营必备"),
    "form_validation": ("P0", "数据正确性底线"),
    "conditional_logic": ("P1", "业务规则核心"),
}


def render_report(code_features, spec_coverage, obj_feature_pairs):
    """渲染 Markdown 报告"""
    lines = []
    lines.append("# E2E 功能层 Gap 分析报告 (L1)")
    lines.append("")
    lines.append(f"> **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"> **生成工具**: scripts/feature_gap_analyzer.py")
    lines.append(f"> **核心问题**: 11 个业务能力点的详细 case 是否覆盖?")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 1. 总览
    lines.append("## 一、总览")
    lines.append("")
    lines.append("| 维度 | 数字 |")
    lines.append("|------|------|")
    lines.append(f"| 功能分类数 | {len(FEATURE_CATEGORIES)} |")
    lines.append(f"| 代码中存在的功能 (category) | {len(code_features)} |")
    lines.append(f"| 现有 spec 覆盖的功能 (category) | {len(spec_coverage)} |")
    lines.append(f"| 业务对象数 | {len(BUSINESS_OBJECTS)} |")
    lines.append(f"| 代码中 (object, feature) 对 | {len(obj_feature_pairs)} |")
    covered_cats = set(code_features.keys()) & set(spec_coverage.keys())
    missing_cats = set(code_features.keys()) - set(spec_coverage.keys())
    lines.append(f"| 代码有但 spec 完全没测的功能 | **{len(missing_cats)}** |")
    if code_features:
        cov_pct = len(covered_cats) / len(code_features) * 100
        lines.append(f"| 功能层覆盖度 (粗) | **{cov_pct:.1f}%** |")
    lines.append("")

    # 2. 12 大功能 × 是否在代码 + spec 出现
    lines.append("## 二、12 大功能 × 存在性矩阵")
    lines.append("")
    lines.append("| 功能 | 代码中存在 | spec 覆盖 | 业务优先级 | 缺口状态 |")
    lines.append("|------|----------|---------|----------|---------|")
    for cat, info in FEATURE_CATEGORIES.items():
        in_code = "[OK]" if cat in code_features else "[--]"
        in_spec = "[OK]" if cat in spec_coverage else "[--]"
        prio, desc = PRIORITY_MAP.get(cat, ("P3", "未评级"))
        if cat in missing_cats:
            status = "[CRITICAL] 完全没测"
        elif cat in covered_cats and len(spec_coverage.get(cat, set())) < 3:
            status = "[WARN] 覆盖薄"
        else:
            status = "[OK] 覆盖"
        lines.append(f"| {info['label']} | {in_code} | {in_spec} | {prio} | {status} |")
    lines.append("")

    # 3. 业务对象 × 功能 矩阵
    lines.append("## 三、业务对象 × 功能 矩阵")
    lines.append("")
    lines.append("只显示代码中存在 (object, feature) 对。✅=已测 ⚠️=薄 ❌=完全没测")
    lines.append("")
    # 表头
    cats = list(FEATURE_CATEGORIES.keys())
    header = "| 对象 \\ 功能 | " + " | ".join(c[:6] for c in cats) + " |"
    sep = "|" + "---|" * (len(cats) + 1)
    lines.append(header)
    lines.append(sep)
    for obj in BUSINESS_OBJECTS:
        row = [f"`{obj}`"]
        for cat in cats:
            if (obj, cat) in obj_feature_pairs:
                # 简化判断: 是否在 spec 出现
                in_spec = cat in spec_coverage
                row.append("⚠️" if in_spec else "❌")
            else:
                row.append("·")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("图例: ✅ 已测 | ⚠️ 代码有但 spec 只间接提 | ❌ 代码有 spec 完全没 | · 代码无此组合")
    lines.append("")

    # 4. P0/P1 详细缺口 + 建议的 test cases
    lines.append("## 四、详细缺口清单 + 建议 test cases")
    lines.append("")
    lines.append("按业务优先级排序:")
    lines.append("")

    sorted_cats = sorted(
        FEATURE_CATEGORIES.items(),
        key=lambda x: {"P0": 0, "P1": 1, "P2": 2, "P3": 3}[PRIORITY_MAP.get(x[0], ("P3", ""))[0]],
    )

    for cat, info in sorted_cats:
        prio, desc = PRIORITY_MAP.get(cat, ("P3", "未评级"))
        is_missing = cat not in spec_coverage
        is_thin = cat in spec_coverage and len(spec_coverage.get(cat, set())) < 3
        if not (is_missing or is_thin):
            continue

        lines.append(f"### {prio} {info['label']}")
        lines.append(f"_{desc}_")
        lines.append("")
        if is_missing:
            lines.append(f"**状态**: [CRITICAL] 完全没测 (代码中 {len(code_features.get(cat, []))} 处实现)")
            if code_features.get(cat):
                lines.append(f"**代码位置 (前 5)**:")
                for loc in code_features[cat][:5]:
                    lines.append(f"- `{loc}`")
        else:
            lines.append(f"**状态**: [WARN] 覆盖薄 (spec 仅 {len(spec_coverage.get(cat, set()))} 处提及)")
            lines.append(f"**已测关键词**: {', '.join(sorted(spec_coverage.get(cat, set())))}")
        lines.append("")
        lines.append(f"**建议 test cases** ({len(info['variants'])} 个 variant):")
        lines.append("")
        for v in info["variants"]:
            lines.append(f"- [ ] **{v}**: {v.replace('_', ' ')} 场景验证")
        lines.append("")

    # 5. 高 ROI 推荐
    lines.append("## 五、推荐执行顺序 (按 ROI)")
    lines.append("")
    lines.append("| 优先级 | 功能 | 推荐场景数 | 业务价值 | 实施难度 |")
    lines.append("|-------|------|----------|---------|---------|")
    recs = [
        ("P0", "form_validation", 5, "高 (数据正确性)", "中 (需新 spec)"),
        ("P0", "inline_edit", 6, "高 (核心编辑能力)", "高 (新建 spec)"),
        ("P0", "batch_ops", 4, "高 (批量管理)", "中 (可基于现有 spec 扩展)"),
        ("P1", "sort", 4, "高 (UX)", "低 (可在现有 spec 加 test)"),
        ("P1", "filter", 6, "高 (UX)", "低 (可扩展现有 fk-filter)"),
        ("P1", "association", 5, "高 (M2M)", "中 (需 spec)"),
        ("P1", "export_import", 4, "中", "低 (import-export.spec 已存在)"),
        ("P2", "filter_combination", 3, "中", "高 (复杂场景)"),
    ]
    for prio, cat, n, val, diff in recs:
        info = FEATURE_CATEGORIES[cat]
        lines.append(f"| {prio} | {info['label']} | {n} | {val} | {diff} |")
    lines.append("")

    # 6. 下一步
    lines.append("## 六、下一步 (推荐)")
    lines.append("")
    lines.append("### L2: 生成 test skeleton (3-4 小时)")
    lines.append("- 用 L3 工具 (`auto_gen_v2_spec.py`) 为每个 P0/P1 功能生成 spec 骨架")
    lines.append("- 用 `dataFinder` + `isolation` 自动构造测试数据")
    lines.append("- 11 个 spec × 5-10 test = 55-110 test")
    lines.append("")
    lines.append("### L3: 闭环 (1 天)")
    lines.append("- feature_gap_analyzer.py 集成到 CI")
    lines.append("- 每周自动跑")
    lines.append("- 输出覆盖率趋势 + PR 评论")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_本报告由 scripts/feature_gap_analyzer.py 自动生成_")

    return "\n".join(lines) + "\n"


# ==================== 6. 入口 ====================

def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    print("[1/3] 扫代码提取功能存在性...")
    code_features = scan_code_features()
    print(f"  发现 {sum(len(v) for v in code_features.values())} 个功能出现位置")
    print(f"  覆盖 {len(code_features)}/{len(FEATURE_CATEGORIES)} 个 category")

    print()
    print("[2/3] 扫 spec 提取覆盖...")
    spec_coverage = scan_spec_coverage()
    print(f"  现有 spec 覆盖 {len(spec_coverage)} 个 category")
    for cat, kws in sorted(spec_coverage.items(), key=lambda x: -len(x[1])):
        print(f"    {cat}: {len(kws)} keywords")

    print()
    print("[3/3] 扫代码 (object × feature) 对...")
    obj_feature_pairs = scan_object_feature_in_code()
    print(f"  发现 {len(obj_feature_pairs)} 个 (object, feature) 对")

    print()
    print("[4/4] 渲染报告...")
    md = render_report(code_features, spec_coverage, obj_feature_pairs)
    md_path = REPORTS_DIR / "feature_gap.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"  [OK] {md_path}")

    json_path = REPORTS_DIR / "feature_gap.json"
    json_path.write_text(
        json.dumps(
            {
                "code_features": {k: v for k, v in code_features.items()},
                "spec_coverage": {k: sorted(v) for k, v in spec_coverage.items()},
                "obj_feature_pairs": {f"{o}|{f}": sorted(v) for (o, f), v in obj_feature_pairs.items()},
                "summary": {
                    "total_categories": len(FEATURE_CATEGORIES),
                    "code_categories": len(code_features),
                    "spec_categories": len(spec_coverage),
                    "missing_categories": list(set(code_features.keys()) - set(spec_coverage.keys())),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  [OK] {json_path}")

    # 关键数字
    print()
    print("=" * 60)
    print("关键发现:")
    print(f"  代码有但 spec 完全没测的 category: {len(set(code_features.keys()) - set(spec_coverage.keys()))}")
    print(f"  代码有但 spec 覆盖薄的: {sum(1 for c in code_features if c in spec_coverage and len(spec_coverage.get(c, set())) < 3)}")
    print(f"  覆盖率: {len(set(code_features.keys()) & set(spec_coverage.keys())) / max(len(code_features), 1) * 100:.1f}%")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
