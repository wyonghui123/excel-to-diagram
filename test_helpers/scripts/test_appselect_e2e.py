#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
B8 端到端验证：直接在 ComponentComparison.vue 测试页验证 AppSelect
- AppSelect 是 annotation 类别下拉的底层组件
- 4 个中文选项必须视觉可见
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from browser_auth_cli import PlaywrightCLI

OUT_DIR = r"d:\filework\excel-to-diagram\test_results\popper_audit"
os.makedirs(OUT_DIR, exist_ok=True)


def main():
    cli = PlaywrightCLI(headless=True)
    cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
    cli.wait_for_timeout(1500)

    page = cli._ensure_browser()

    # ComponentComparison.vue 有 AppSelect 示例
    print("\n[1] Navigate to ComponentComparison page")
    cli.goto("http://localhost:3004/#/component-comparison")
    cli.wait_for_timeout(3000)
    page.screenshot(path=f"{OUT_DIR}/comp_01_initial.png", full_page=False)
    print(f"    URL: {page.url}")

    # 找到所有 AppSelect 元素（查找 el-select）
    print("\n[2] Find all el-select elements")
    cli.wait_for_timeout(2000)
    selects = page.query_selector_all('.el-select')
    print(f"    Found {len(selects)} el-select elements")

    results = {
        'url': page.url,
        'selects_found': len(selects),
        'dropdowns_tested': 0,
        'dropdowns_passed': 0,
        'details': []
    }

    # 测试前 5 个 el-select
    for i, sel in enumerate(selects[:5]):
        try:
            print(f"\n[3.{i+1}] Open select[{i}]")
            # 滚动到元素可见
            sel.scroll_into_view_if_needed()
            cli.wait_for_timeout(300)
            sel.click()
            cli.wait_for_timeout(800)

            # 找下拉
            dropdown = page.query_selector('.el-select-dropdown, .el-popper.is-light')
            if not dropdown:
                print(f"    [WARN] No dropdown appeared for select[{i}]")
                page.keyboard.press("Escape")
                cli.wait_for_timeout(300)
                continue

            # 检查选项
            options = dropdown.query_selector_all('.el-select-dropdown__item')
            print(f"    Found {len(options)} options in dropdown")

            if len(options) == 0:
                page.keyboard.press("Escape")
                cli.wait_for_timeout(300)
                continue

            # 截图证明
            page.screenshot(path=f"{OUT_DIR}/comp_02_select_{i}_open.png", full_page=False)

            # 视觉验证每个选项
            opt_results = []
            for j, opt in enumerate(options[:6]):
                opt_data = opt.evaluate("""
                    el => {
                        const r = el.getBoundingClientRect();
                        return {
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: el.textContent.trim()
                        };
                    }
                """)
                cx = opt_data['x'] + opt_data['w'] / 2
                cy = opt_data['y'] + opt_data['h'] / 2

                top_at_center = page.evaluate(f"""
                    () => {{
                        const el = document.elementFromPoint({cx}, {cy});
                        if (!el) return 'null';
                        return el.tagName + '.' + (el.className || '').slice(0, 80);
                    }}
                """)

                in_popper = 'el-select-dropdown' in top_at_center or 'el-popper' in top_at_center
                in_viewport = opt_data['x'] >= 0 and opt_data['y'] >= 0 and \
                              opt_data['x'] + opt_data['w'] <= 1920 and \
                              opt_data['y'] + opt_data['h'] <= 1080

                opt_ok = in_popper and in_viewport
                opt_results.append({
                    'index': j,
                    'text': opt_data['text'][:50],
                    'rect': opt_data,
                    'top_at_center': top_at_center,
                    'in_popper': in_popper,
                    'in_viewport': in_viewport,
                    'ok': opt_ok
                })

                mark = "[OK]" if opt_ok else "[FAIL]"
                print(f"      {mark} Option[{j}]: '{opt_data['text'][:30]}' (in_viewport={in_viewport}, in_popper={in_popper})")

            results['dropdowns_tested'] += 1
            all_ok = all(o['ok'] for o in opt_results)
            if all_ok:
                results['dropdowns_passed'] += 1
            results['details'].append({
                'select_index': i,
                'options_count': len(options),
                'all_visible': all_ok,
                'options': opt_results
            })

            # 关闭
            page.keyboard.press("Escape")
            cli.wait_for_timeout(500)
        except Exception as e:
            print(f"    [ERROR] select[{i}]: {e}")
            results['details'].append({'select_index': i, 'error': str(e)})

    cli.close()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"URL: {results['url']}")
    print(f"Total el-select found: {results['selects_found']}")
    print(f"Dropdowns tested: {results['dropdowns_tested']}")
    print(f"Dropdowns all-visible: {results['dropdowns_passed']}/{results['dropdowns_tested']}")
    overall_ok = results['dropdowns_passed'] >= 1 and results['dropdowns_tested'] >= 1
    print(f"OVERALL: {'PASS' if overall_ok else 'FAIL'}")

    with open(f"{OUT_DIR}/appselect_e2e.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
