#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自动发现并审计页面所有 popper 类元素的视觉可见性
"""
import sys
import os
import time
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from browser_auth_cli import PlaywrightCLI

OUT_DIR = r"d:\filework\excel-to-diagram\test_results\popper_audit"
os.makedirs(OUT_DIR, exist_ok=True)

PAGES = [
    {"name": "business_object_list", "url": "/#/object/business_object"},
    {"name": "business_object_detail", "url": "/#/detail/business_object/25"},
    {"name": "annotation_list", "url": "/#/object/annotation"},
    {"name": "dashboard", "url": "/#/"},
]

# 触发器规则：(css_selector, action, "type")
# type: 'select' | 'dropdown' | 'tooltip' | 'popover' | 'datepicker' | 'cascader'
TRIGGERS = [
    (".el-select", "click", "select"),
    (".el-dropdown", "click", "dropdown"),
    (".row-action-trigger", "click", "dropdown"),
    (".el-tooltip", "hover", "tooltip"),
    (".el-popover", "click", "popover"),
    (".el-date-editor", "click", "datepicker"),
    (".el-cascader", "click", "cascader"),
    (".el-color-picker", "click", "colorpicker"),
]


def discover_poppers(page) -> dict:
    """自动发现页面里所有可能产生 popper 的元素"""
    return page.evaluate("""
        () => {
            const result = {
                selects: [],
                dropdowns: [],
                tooltips: [],
                popovers: [],
                datePickers: [],
                cascaders: [],
                colorPickers: []
            };

            for (const sel of document.querySelectorAll('.el-select')) {
                const r = sel.getBoundingClientRect();
                const rect = { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
                const inViewport = r.x >= 0 && r.y >= 0 && r.x + r.width <= innerWidth && r.y + r.height <= innerHeight;
                const text = sel.textContent.trim().slice(0, 30);
                const wrapper = sel.querySelector('.el-select__wrapper');
                result.selects.push({ rect, inViewport, text, hasWrapper: !!wrapper });
            }

            for (const sel of document.querySelectorAll('.el-dropdown')) {
                const r = sel.getBoundingClientRect();
                result.dropdowns.push({ rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }, inViewport: r.x >= 0 && r.y >= 0 });
            }

            for (const sel of document.querySelectorAll('.el-tooltip')) {
                const r = sel.getBoundingClientRect();
                result.tooltips.push({ rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }, inViewport: r.x >= 0 && r.y >= 0 });
            }

            for (const sel of document.querySelectorAll('.el-popover')) {
                const r = sel.getBoundingClientRect();
                result.popovers.push({ rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }, inViewport: r.x >= 0 && r.y >= 0 });
            }

            for (const sel of document.querySelectorAll('.el-date-editor')) {
                const r = sel.getBoundingClientRect();
                result.datePickers.push({ rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }, inViewport: r.x >= 0 && r.y >= 0 });
            }

            return result;
        }
    """)


def trigger_and_check(cli, page, selector: str, action: str, kind: str) -> dict:
    """触发 popper 并检查视觉可见性"""
    try:
        if action == "hover":
            page.hover(selector)
        else:
            page.click(selector)
        page.wait_for_timeout(800)

        # 找对应的 popper 节点
        popper_map = {
            "select": ".el-select-dropdown, .el-popper",
            "dropdown": ".el-dropdown-menu, .el-popper",
            "tooltip": ".el-tooltip__popper, .el-popper",
            "popover": ".el-popper, .el-popover",
            "datepicker": ".el-picker__popper, .el-popper",
            "cascader": ".el-cascader__dropdown, .el-popper",
            "colorpicker": ".el-color-picker__panel, .el-popper",
        }
        popper_sel = popper_map.get(kind, ".el-popper")

        # 找最新出现的 popper
        result = page.evaluate("""
            (sel) => {
                const candidates = document.querySelectorAll(sel);
                let visible = [];
                for (const c of candidates) {
                    const r = c.getBoundingClientRect();
                    const s = getComputedStyle(c);
                    if (r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden' && parseFloat(s.opacity) > 0.01) {
                        visible.push({
                            rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
                            zIndex: s.zIndex,
                            position: s.position
                        });
                    }
                }
                return visible;
            }
        """, popper_sel)

        if not result:
            return {"triggered": True, "popper_visible_count": 0}

        # 检查最新出现的 popper 是否在视口内且未被遮挡
        first = result[-1]
        rect = first["rect"]
        in_viewport = rect["x"] >= 0 and rect["y"] >= 0 and rect["x"] + rect["w"] <= 1920 and rect["y"] + rect["h"] <= 1080

        obscured = False
        if in_viewport:
            top_el = page.evaluate("""
                ([x, y]) => {
                    const el = document.elementFromPoint(x, y);
                    if (!el) return null;
                    return el.tagName + '.' + String(el.className).slice(0, 80);
                }
            """, [rect["x"] + rect["w"]/2, rect["y"] + rect["h"]/2])
            # 如果 elementFromPoint 不在 popper 内（也不在 popper 容器内），认为被遮挡
            if top_el and "el-select-dropdown" not in top_el and "el-dropdown-menu" not in top_el and "el-tooltip" not in top_el and "el-popper" not in top_el:
                obscured = True

        # 关闭 popper
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        return {
            "triggered": True,
            "popper_visible_count": len(result),
            "popper_rect": rect,
            "in_viewport": in_viewport,
            "obscured": obscured,
            "top_element": top_el if obscured else None,
            "ok": in_viewport and not obscured
        }
    except Exception as e:
        return {"triggered": False, "error": str(e)[:200]}


def audit_page(cli, page_info: dict) -> dict:
    """审计一个页面"""
    page_name = page_info["name"]
    url = page_info["url"]
    print(f"\n{'='*60}")
    print(f"[{page_name}] {url}")
    print(f"{'='*60}")

    cli.goto(f"http://localhost:3004{url}")
    cli.wait_for_timeout(2000)
    page = cli._ensure_browser()

    page.screenshot(path=f"{OUT_DIR}/{page_name}_initial.png", full_page=True)

    discovered = discover_poppers(page)
    print(f"  Found: {len(discovered['selects'])} selects, {len(discovered['dropdowns'])} dropdowns, {len(discovered['tooltips'])} tooltips, {len(discovered['popovers'])} popovers, {len(discovered['datePickers'])} datePickers")

    issues = []
    tested = 0
    passed = 0

    # 测 select (最多 5 个)
    for i, sel in enumerate(discovered['selects'][:5]):
        if not sel['inViewport']:
            continue
        tested += 1
        result = trigger_and_check(cli, page, f".el-select", "click", "select")
        if result.get('ok'):
            passed += 1
        else:
            issues.append({
                "type": "select", "index": i,
                "select_text": sel.get('text', ''),
                "in_viewport": result.get('in_viewport', False),
                "obscured": result.get('obscured', False),
                "top_element": result.get('top_element', ''),
                "popper_rect": result.get('popper_rect', {}),
                "reason": "in_viewport" if not result.get('in_viewport') else ("obscured by " + str(result.get('top_element', '')) if result.get('obscured') else "no popper")
            })

    # 测 dropdown
    for i in range(min(3, len(discovered['dropdowns']))):
        if not discovered['dropdowns'][i].get('inViewport'):
            continue
        tested += 1
        result = trigger_and_check(cli, page, ".el-dropdown", "click", "dropdown")
        if result.get('ok'):
            passed += 1
        else:
            issues.append({
                "type": "dropdown", "index": i,
                "in_viewport": result.get('in_viewport', False),
                "obscured": result.get('obscured', False),
                "top_element": result.get('top_element', ''),
                "reason": "obscured" if result.get('obscured') else "no popper"
            })

    # 测 datepicker
    for i in range(min(3, len(discovered['datePickers']))):
        if not discovered['datePickers'][i].get('inViewport'):
            continue
        tested += 1
        result = trigger_and_check(cli, page, ".el-date-editor", "click", "datepicker")
        if result.get('ok'):
            passed += 1
        else:
            issues.append({
                "type": "datepicker", "index": i,
                "in_viewport": result.get('in_viewport', False),
                "obscured": result.get('obscured', False),
                "top_element": result.get('top_element', ''),
                "reason": "obscured" if result.get('obscured') else "no popper"
            })

    print(f"  Tested: {tested}, Passed: {passed}, Issues: {len(issues)}")
    for issue in issues:
        print(f"    [ISSUE] {issue['type']}[{issue['index']}]: {issue['reason']}")

    return {
        "page": page_name,
        "url": url,
        "discovered": {
            "selects": len(discovered['selects']),
            "dropdowns": len(discovered['dropdowns']),
            "tooltips": len(discovered['tooltips']),
            "popovers": len(discovered['popovers']),
            "datePickers": len(discovered['datePickers'])
        },
        "tested": tested,
        "passed": passed,
        "issues": issues
    }


def main():
    cli = PlaywrightCLI(headless=True)
    cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
    cli.wait_for_timeout(1500)

    results = []
    for page_info in PAGES:
        results.append(audit_page(cli, page_info))

    print("\n" + "=" * 60)
    print("OVERALL SUMMARY")
    print("=" * 60)
    total_tested = sum(r["tested"] for r in results)
    total_passed = sum(r["passed"] for r in results)
    print(f"Total: {total_passed}/{total_tested} poppers visually visible")
    print()
    for r in results:
        status = "OK" if r["passed"] == r["tested"] else "FAIL"
        print(f"  [{status}] {r['page']}: {r['passed']}/{r['tested']} visible ({len(r['issues'])} issues)")

    with open(f"{OUT_DIR}/report.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
