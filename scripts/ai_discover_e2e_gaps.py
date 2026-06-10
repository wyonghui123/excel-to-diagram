# -*- coding: utf-8 -*-
"""
E2E 覆盖率 Gap 报告生成器
==========================

扫描元数据 schemas 与现有 E2E specs,生成覆盖率 gap 报告。

数据源:
  - meta/schemas/*.yaml           (元数据对象,排除 _ 开头)
  - e2e/features/*.spec.js        (功能测试)
  - e2e/smoke/*.smoke.spec.js     (冒烟测试)

输出:
  - scripts/e2e_coverage_gap.json     (机器可读)
  - 控制台打印 Markdown 报告

使用:
  python scripts/ai_discover_e2e_gaps.py
  python scripts/ai_discover_e2e_gaps.py --output reports/e2e_gap.md
  python scripts/ai_discover_e2e_gaps.py --json reports/e2e_gap.json
"""
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[ERR] PyYAML 未安装,请运行: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


# ==================== 路径配置 ====================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = PROJECT_ROOT / "meta" / "schemas"
E2E_DIRS = [
    PROJECT_ROOT / "e2e" / "features",
    PROJECT_ROOT / "e2e" / "smoke",
]
ROUTER_FILE = PROJECT_ROOT / "src" / "router" / "index.js"
MENU_FILE = PROJECT_ROOT / "src" / "config" / "menuConfig.js"

# 业务优先级映射 (基于 docs/需求文档.md)
PRIORITY_MAP = {
    # P0: 核心业务
    "user": "P0", "user_group": "P0", "user_group_member": "P0",
    "role": "P0", "permission": "P0", "menu": "P0",
    "product": "P0", "version": "P0",
    "domain": "P0", "sub_domain": "P0", "service_module": "P0",
    "business_object": "P0", "relationship": "P0",
    "audit_log": "P0",
    # P1: 重要配置
    "enum_type": "P1", "enum_value": "P1",
    "annotation": "P1",
    "data_permission": "P1", "group_data_permission": "P1",
    "role_data_permission": "P1", "role_permission": "P1",
    "permission_rule": "P1", "permission_bundle": "P1",
    "menu_permission": "P1", "role_dimension_scope": "P1",
    "employee_data_scope": "P1", "filter_variant": "P1",
    # P2: 辅助/运维
    "change_subscription": "P2", "change_event": "P2",
    "scheduled_task": "P2", "task_queue": "P2",
    "task_execution": "P2", "ai_async_task": "P2",
}


# ==================== 元数据扫描 ====================

def scan_schemas():
    """扫描所有 YAML schemas,提取业务对象元数据"""
    objects = []
    if not SCHEMAS_DIR.exists():
        print(f"[WARN] Schemas 目录不存在: {SCHEMAS_DIR}", file=sys.stderr)
        return objects

    for yaml_file in sorted(SCHEMAS_DIR.glob("*.yaml")):
        # 排除内部文件 (以下划线开头)
        if yaml_file.name.startswith("_"):
            continue
        try:
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            print(f"[WARN] YAML 解析失败: {yaml_file.name} - {e}", file=sys.stderr)
            continue

        obj_id = data.get("id")
        if not obj_id:
            continue

        # 推断能力
        aspects = data.get("aspects", []) or []
        has_audit = "audit_aspect" in aspects
        has_hierarchy = "hierarchy_aspect" in aspects

        objects.append({
            "id": obj_id,
            "name": data.get("name", obj_id),
            "table": data.get("table_name", ""),
            "parent": data.get("parent_object", ""),
            "aspects": aspects,
            "has_audit": has_audit,
            "has_hierarchy": has_hierarchy,
            "has_crud": all(k in data for k in ("list", "detail")),
            "field_count": len(data.get("fields", []) or []),
            "action_count": len(data.get("actions", []) or []),
            "priority": PRIORITY_MAP.get(obj_id, "P2"),
            "file": yaml_file.name,
        })
    return objects


# ==================== E2E 测试扫描 ====================

def extract_test_keywords(content):
    """从 spec 文件提取被测对象关键词"""
    keywords = set()

    # 1. 提取 test('C01: ...') 描述
    test_descs = re.findall(r"test\(['\"]([CMSAF]\d+):\s*([^'\"]+)['\"]", content)
    for tid, desc in test_descs:
        keywords.add(tid)
        keywords.add(desc.lower())

    # 2. 提取路由 path
    routes = re.findall(r"['\"`](/[a-z][a-z\-/]+)['\"`]", content, re.IGNORECASE)
    keywords.update(r.lower() for r in routes)

    # 3. 提取常见的 object 关键词 (来自元数据)
    known_objects = [
        "user", "users", "role", "roles", "user_group", "user-group",
        "permission", "permissions", "menu", "menus",
        "product", "products", "version", "versions",
        "domain", "sub_domain", "sub-domain", "service_module", "service-module",
        "business_object", "business-object", "businessObject",
        "relationship", "relationships",
        "enum_type", "enum-type", "enumType", "enum_value", "enum-value",
        "annotation", "annotations", "audit_log", "audit-log", "auditLog",
        "diagram", "archdata",
    ]
    for kw in known_objects:
        if re.search(r"\b" + re.escape(kw) + r"\b", content, re.IGNORECASE):
            keywords.add(kw.lower().replace("-", "_"))

    return keywords


def scan_e2e_specs():
    """扫描所有 E2E specs,提取覆盖关键词"""
    specs = []
    for e2e_dir in E2E_DIRS:
        if not e2e_dir.exists():
            continue
        # features/ 和 smoke/ 都可能含 *.spec.js
        for pattern in ("*.spec.js", "*.smoke.spec.js"):
            for spec_file in sorted(e2e_dir.glob(pattern)):
                try:
                    with open(spec_file, encoding="utf-8") as f:
                        content = f.read()
                except UnicodeDecodeError:
                    print(f"[WARN] 编码失败: {spec_file}", file=sys.stderr)
                    continue

                keywords = extract_test_keywords(content)
                specs.append({
                    "file": str(spec_file.relative_to(PROJECT_ROOT)),
                    "test_count": len(re.findall(r"^\s*test\s*\(", content, re.MULTILINE)),
                    "keywords": keywords,
                })
    return specs


# ==================== 路由扫描 ====================

def scan_routes():
    """从 router/index.js 提取路由表"""
    routes = []
    if not ROUTER_FILE.exists():
        return routes
    try:
        with open(ROUTER_FILE, encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        return routes

    # 匹配 path: '/xxx' 模式
    path_matches = re.findall(r"path:\s*['\"`](/[^'\"`]*)['\"`]", content)
    for p in path_matches:
        routes.append(p)
    return routes


# ==================== 组件扫描 ====================

COMPONENTS_DIR = PROJECT_ROOT / "src" / "components" / "common"

def scan_components():
    """扫描 src/components/common/ 下的 Vue 组件,提取组件名清单。

    用途: 在 gap 报告中列出项目已具备的通用组件,作为 v2 POM 选型参考。
    """
    components = []
    if not COMPONENTS_DIR.exists():
        print(f"[WARN] Components 目录不存在: {COMPONENTS_DIR}", file=sys.stderr)
        return components

    for vue_file in sorted(COMPONENTS_DIR.glob("*.vue")):
        try:
            with open(vue_file, encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            continue
        # 提取 name: 'Xxx' (Vue SFC name)
        m = re.search(r"name:\s*['\"`](\w+)['\"`]", content)
        comp_name = m.group(1) if m else vue_file.stem
        # 推断组件类型标签 (简单启发式)
        lower = vue_file.name.lower()
        if 'list' in lower:
            comp_type = 'list'
        elif 'form' in lower or 'editor' in lower:
            comp_type = 'form'
        elif 'filter' in lower or 'search' in lower:
            comp_type = 'filter'
        elif 'modal' in lower or 'dialog' in lower or 'drawer' in lower:
            comp_type = 'modal'
        elif 'select' in lower or 'enum' in lower or 'value' in lower:
            comp_type = 'selector'
        else:
            comp_type = 'misc'
        components.append({
            "name": comp_name,
            "file": str(vue_file.relative_to(PROJECT_ROOT)),
            "type": comp_type,
        })
    return components


# ==================== Gap 分析 ====================

OBJECT_KEYWORDS = {
    "user": ["user", "users"],
    "user_group": ["user-group", "user_group", "usergroup"],
    "user_group_member": ["user-group-member", "user_group_member", "member"],
    "role": ["role", "roles"],
    "permission": ["permission", "permissions"],
    "menu": ["menu", "menus"],
    "product": ["product", "products"],
    "version": ["version", "versions"],
    "domain": ["domain", "domains"],
    "sub_domain": ["sub-domain", "sub_domain", "subdomain"],
    "service_module": ["service-module", "service_module", "servicemodule"],
    "business_object": ["business-object", "business_object", "businessobject", "archdata"],
    "relationship": ["relationship", "relationships"],
    "enum_type": ["enum-type", "enum_type", "enum-management", "enummanagement"],
    "enum_value": ["enum-value", "enum_value"],
    "annotation": ["annotation", "annotations"],
    "audit_log": ["audit-log", "audit_log", "auditlog"],
    "scheduled_task": ["scheduled-task", "scheduled_task", "task-management"],
    "task_queue": ["task-queue", "task_queue"],
    "task_execution": ["task-execution", "task_execution"],
    "ai_async_task": ["ai-async-task", "ai_async_task", "ai-task"],
}


def compute_gap(objects, specs):
    """计算每个对象的覆盖度"""
    # 收集所有 spec 的关键词 (转换为统一的 set)
    all_kws = set()
    spec_map = defaultdict(list)  # keyword -> [spec files]
    for spec in specs:
        for kw in spec["keywords"]:
            all_kws.add(kw)
            spec_map[kw].append(spec["file"])

    gaps = []
    for obj in objects:
        obj_id = obj["id"]
        # 找出此对象可能匹配的关键词
        kws_to_check = OBJECT_KEYWORDS.get(obj_id, [obj_id, obj_id.replace("_", "-")])
        matched_specs = set()
        for kw in kws_to_check:
            for spec_kw, spec_files in spec_map.items():
                if kw in spec_kw or spec_kw in kw:
                    matched_specs.update(spec_files)

        covered = len(matched_specs) > 0
        gaps.append({
            "id": obj_id,
            "name": obj["name"],
            "priority": obj["priority"],
            "has_audit": obj["has_audit"],
            "has_hierarchy": obj["has_hierarchy"],
            "has_crud": obj["has_crud"],
            "parent": obj["parent"],
            "field_count": obj["field_count"],
            "action_count": obj["action_count"],
            "covered": covered,
            "covering_specs": sorted(matched_specs),
            "coverage_count": len(matched_specs),
        })

    return gaps


# ==================== 路由 Gap ====================

def compute_route_gap(routes, gaps):
    """从 routes 角度补充 gap (找未在元数据中或缺测试的路由)"""
    # 关键路由 -> schema id 映射
    # (key 必须用 schema 的 id,不要用别名,以便和 gaps[].id 对齐)
    route_obj_map = {
        "/": ("workspace", "工作台 (Workspace)"),  # 无 schema,仅作标签
        "/diagram": ("diagram", "架构图生成器"),
        "/system/archdata": ("business_object", "架构数据管理"),
        "/system/admin": ("audit_log", "系统管理 (日志)"),
        "/system/user": ("user", "用户管理"),
        "/user-permission": ("user", "用户/角色/用户组"),  # 主用户页
        "/system/role": ("role", "角色管理"),
        "/system/role-detail": ("role", "角色详情"),
        "/system/user-group": ("user_group", "用户组管理"),
        "/product-management": ("product", "产品版本管理"),
        "/product-detail": ("product", "产品详情"),
        "/business-config": ("enum_type", "业务配置 (枚举)"),
        "/system/task-management": ("scheduled_task", "任务调度"),
        "/account": ("account", "账户设置"),  # 无 schema
    }

    route_gaps = []
    for route in routes:
        # 找最长匹配
        matched = None
        for prefix, (key, label) in route_obj_map.items():
            if route == prefix or route.startswith(prefix + "/") or route.startswith(prefix + "-"):
                matched = (key, label, prefix)
                break
        if matched:
            key, label, prefix = matched
            # 找是否在 gap 中已标记
            has_covered_gap = any(g["id"] == key and g["covered"] for g in gaps)
            route_gaps.append({
                "route": route,
                "label": label,
                "key": key,
                "covered_in_e2e": has_covered_gap,
            })
    return route_gaps


# ==================== 报告输出 ====================

def render_markdown_report(gaps, specs, routes, route_gaps, components=None):
    """渲染为 Markdown 报告"""
    if components is None:
        components = []
    lines = []
    lines.append("# E2E 测试覆盖率 Gap 报告")
    lines.append("")
    lines.append(f"> **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"> **项目**: excel-to-diagram / ArchWorkspace")
    lines.append(f"> **元数据对象**: {len(gaps)}")
    lines.append(f"> **E2E specs**: {len(specs)}")
    lines.append(f"> **路由数**: {len(routes)}")
    lines.append(f"> **通用组件数**: {len(components)}")
    lines.append("")

    # 总体统计
    total = len(gaps)
    covered = sum(1 for g in gaps if g["covered"])
    coverage_pct = (covered / total * 100) if total else 0
    lines.append("## 一、总体覆盖率")
    lines.append("")
    lines.append(f"- **业务对象总数**: {total}")
    lines.append(f"- **已覆盖**: {covered}")
    lines.append(f"- **未覆盖**: {total - covered}")
    lines.append(f"- **覆盖率**: **{coverage_pct:.1f}%**")
    lines.append("")

    # 按优先级分组
    by_priority = defaultdict(list)
    for g in gaps:
        by_priority[g["priority"]].append(g)

    lines.append("## 二、按优先级 Gap")
    lines.append("")
    for prio in ["P0", "P1", "P2"]:
        objs = by_priority.get(prio, [])
        if not objs:
            continue
        uncovered = [g for g in objs if not g["covered"]]
        lines.append(f"### {prio} (共 {len(objs)} 个, 未覆盖 {len(uncovered)})")
        lines.append("")
        lines.append("| 对象 | 名称 | 审计 | 层级 | CRUD | 覆盖 | 覆盖 spec | 字段数 |")
        lines.append("|------|------|------|------|------|------|-----------|--------|")
        for g in sorted(objs, key=lambda x: (x["covered"], x["id"])):
            cov_mark = "[OK]" if g["covered"] else "[GAP]"
            specs_str = ", ".join(g["covering_specs"][:2])
            if len(g["covering_specs"]) > 2:
                specs_str += f" +{len(g['covering_specs'])-2}"
            specs_str = specs_str if specs_str else "-"
            lines.append(
                f"| `{g['id']}` | {g['name']} | "
                f"{'是' if g['has_audit'] else '否'} | "
                f"{'是' if g['has_hierarchy'] else '否'} | "
                f"{'是' if g['has_crud'] else '否'} | "
                f"{cov_mark} | {specs_str} | {g['field_count']} |"
            )
        lines.append("")

    # 关键 Gap 列表 (未覆盖的 P0)
    lines.append("## 三、关键 Gap 清单 (P0 未覆盖)")
    lines.append("")
    p0_uncovered = [g for g in gaps if g["priority"] == "P0" and not g["covered"]]
    if p0_uncovered:
        lines.append("| 优先级 | 对象 | 名称 | 父对象 | 字段数 | 建议测试场景 |")
        lines.append("|--------|------|------|--------|--------|--------------|")
        for g in p0_uncovered:
            scenarios = suggest_scenarios(g)
            lines.append(
                f"| {g['priority']} | `{g['id']}` | {g['name']} | "
                f"{g['parent'] or '-'} | {g['field_count']} | {scenarios} |"
            )
    else:
        lines.append("**[OK] 全部 P0 对象已覆盖**")
    lines.append("")

    # 路由 Gap
    lines.append("## 四、路由级覆盖")
    lines.append("")
    if route_gaps:
        lines.append("| 路由 | 标签 | E2E 覆盖 |")
        lines.append("|------|------|---------|")
        for rg in route_gaps:
            mark = "[OK]" if rg["covered_in_e2e"] else "[GAP]"
            lines.append(f"| `{rg['route']}` | {rg['label']} | {mark} |")
    lines.append("")

    # E2E Spec 统计
    lines.append("## 五、E2E Spec 统计")
    lines.append("")
    total_tests = sum(s["test_count"] for s in specs)
    lines.append(f"- **Spec 文件数**: {len(specs)}")
    lines.append(f"- **测试总数**: {total_tests}")
    lines.append("")
    lines.append("### Top 10 Spec (按测试数)")
    lines.append("")
    lines.append("| 文件 | 测试数 |")
    lines.append("|------|--------|")
    for s in sorted(specs, key=lambda x: -x["test_count"])[:10]:
        lines.append(f"| `{s['file']}` | {s['test_count']} |")
    lines.append("")

    # 建议
    lines.append("## 六、行动建议")
    lines.append("")
    p0_gap = sum(1 for g in gaps if g["priority"] == "P0" and not g["covered"])
    p1_gap = sum(1 for g in gaps if g["priority"] == "P1" and not g["covered"])
    p2_gap = sum(1 for g in gaps if g["priority"] == "P2" and not g["covered"])

    lines.append("### P0 Gap (必须补)")
    if p0_gap:
        for g in [x for x in gaps if x["priority"] == "P0" and not x["covered"]]:
            lines.append(f"- [ ] **{g['id']}** ({g['name']}): CRUD + 审计 + 跨域流程")
    else:
        lines.append("- [OK] 无 P0 Gap")
    lines.append("")

    lines.append("### P1 Gap (建议补)")
    if p1_gap:
        for g in [x for x in gaps if x["priority"] == "P1" and not x["covered"]][:10]:
            lines.append(f"- [ ] **{g['id']}** ({g['name']})")
        if p1_gap > 10:
            lines.append(f"- [ ] ... 还有 {p1_gap - 10} 个 P1 Gap")
    else:
        lines.append("- [OK] 无 P1 Gap")
    lines.append("")

    lines.append("### P2 Gap (可选)")
    if p2_gap:
        for g in [x for x in gaps if x["priority"] == "P2" and not x["covered"]][:5]:
            lines.append(f"- [ ] **{g['id']}** ({g['name']})")
        if p2_gap > 5:
            lines.append(f"- [ ] ... 还有 {p2_gap - 5} 个 P2 Gap")
    else:
        lines.append("- [OK] 无 P2 Gap")
    lines.append("")

    # 通用组件清单 (新增)
    if components:
        lines.append("## 七、通用组件清单 (v2 POM 选型参考)")
        lines.append("")
        by_type = defaultdict(list)
        for c in components:
            by_type[c["type"]].append(c)
        type_labels = {
            "list": "列表型",
            "form": "表单/编辑型",
            "filter": "过滤/搜索型",
            "modal": "弹窗/抽屉型",
            "selector": "选择器/枚举型",
            "misc": "其他",
        }
        for t in ("list", "form", "filter", "modal", "selector", "misc"):
            items = by_type.get(t, [])
            if not items:
                continue
            lines.append(f"### {type_labels[t]} ({len(items)} 个)")
            lines.append("")
            for c in items:
                lines.append(f"- `{c['name']}` - {c['file']}")
            lines.append("")

    return "\n".join(lines) + "\n"


def suggest_scenarios(obj):
    """根据对象特征建议测试场景"""
    scenarios = []
    if obj["has_crud"]:
        scenarios.append("CRUD")
    if obj["has_audit"]:
        scenarios.append("审计验证")
    if obj["has_hierarchy"]:
        scenarios.append("层级关系")
    if obj["parent"]:
        scenarios.append(f"父关联({obj['parent']})")
    if obj["action_count"] > 3:
        scenarios.append(f"{obj['action_count']}个 actions")
    return ", ".join(scenarios) if scenarios else "基础场景"


# ==================== 主入口 ====================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="E2E 覆盖率 Gap 报告生成器")
    parser.add_argument("--output", "-o", help="Markdown 报告输出路径")
    parser.add_argument("--json", "-j", help="JSON 报告输出路径")
    parser.add_argument("--quiet", "-q", action="store_true", help="不打印到控制台")
    args = parser.parse_args()

    print(f"[INFO] 扫描元数据: {SCHEMAS_DIR}", file=sys.stderr)
    objects = scan_schemas()
    print(f"[INFO] 发现 {len(objects)} 个业务对象", file=sys.stderr)

    print(f"[INFO] 扫描 E2E specs: {[str(p) for p in E2E_DIRS]}", file=sys.stderr)
    specs = scan_e2e_specs()
    print(f"[INFO] 发现 {len(specs)} 个 E2E spec", file=sys.stderr)

    print(f"[INFO] 扫描路由: {ROUTER_FILE}", file=sys.stderr)
    routes = scan_routes()
    print(f"[INFO] 发现 {len(routes)} 个路由", file=sys.stderr)

    print(f"[INFO] 扫描组件: {COMPONENTS_DIR}", file=sys.stderr)
    components = scan_components()
    print(f"[INFO] 发现 {len(components)} 个组件", file=sys.stderr)

    # 计算 gap
    gaps = compute_gap(objects, specs)
    route_gaps = compute_route_gap(routes, gaps)

    # 渲染报告
    md_report = render_markdown_report(gaps, specs, routes, route_gaps, components)

    # 输出 Markdown
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_report)
        print(f"[OK] Markdown 报告已写入: {out_path}", file=sys.stderr)
    elif not args.quiet:
        print(md_report)

    # 输出 JSON
    if args.json:
        json_path = Path(args.json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_report = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_objects": len(gaps),
                "covered": sum(1 for g in gaps if g["covered"]),
                "uncovered": sum(1 for g in gaps if not g["covered"]),
                "coverage_pct": round(sum(1 for g in gaps if g["covered"]) / len(gaps) * 100, 1) if gaps else 0,
                "total_specs": len(specs),
                "total_routes": len(routes),
                "total_components": len(components),
            },
            "by_priority": {
                p: {
                    "total": sum(1 for g in gaps if g["priority"] == p),
                    "covered": sum(1 for g in gaps if g["priority"] == p and g["covered"]),
                }
                for p in ["P0", "P1", "P2"]
            },
            "gaps": gaps,
            "route_gaps": route_gaps,
            "specs": [{"file": s["file"], "test_count": s["test_count"]} for s in specs],
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_report, f, ensure_ascii=False, indent=2)
        print(f"[OK] JSON 报告已写入: {json_path}", file=sys.stderr)

    # 默认 JSON 输出到 scripts/ 目录
    if not args.json:
        default_json = PROJECT_ROOT / "scripts" / "e2e_coverage_gap.json"
        default_json.parent.mkdir(parents=True, exist_ok=True)
        json_report = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_objects": len(gaps),
                "covered": sum(1 for g in gaps if g["covered"]),
                "uncovered": sum(1 for g in gaps if not g["covered"]),
                "coverage_pct": round(sum(1 for g in gaps if g["covered"]) / len(gaps) * 100, 1) if gaps else 0,
                "total_specs": len(specs),
                "total_routes": len(routes),
                "total_components": len(components),
            },
            "gaps": gaps,
            "route_gaps": route_gaps,
            "components": components,
        }
        with open(default_json, "w", encoding="utf-8") as f:
            json.dump(json_report, f, ensure_ascii=False, indent=2)
        print(f"[OK] JSON 报告已写入: {default_json}", file=sys.stderr)

    # 简短的统计输出
    total = len(gaps)
    covered = sum(1 for g in gaps if g["covered"])
    pct = (covered / total * 100) if total else 0
    print("", file=sys.stderr)
    print(f"[SUMMARY] 业务对象: {total}, 已覆盖: {covered}, 覆盖率: {pct:.1f}%", file=sys.stderr)
    p0_gap = sum(1 for g in gaps if g["priority"] == "P0" and not g["covered"])
    p1_gap = sum(1 for g in gaps if g["priority"] == "P1" and not g["covered"])
    p2_gap = sum(1 for g in gaps if g["priority"] == "P2" and not g["covered"])
    print(f"[SUMMARY] P0 Gap: {p0_gap}, P1 Gap: {p1_gap}, P2 Gap: {p2_gap}", file=sys.stderr)

    return 0 if p0_gap == 0 else 1  # P0 全覆盖返回 0,否则返回 1


if __name__ == "__main__":
    sys.exit(main())
