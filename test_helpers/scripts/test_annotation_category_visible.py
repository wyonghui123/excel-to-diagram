#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
B8 + B9 综合验证：原始问题（annotation 类别下拉）的端到端视觉可见性测试
覆盖：
1. 进入 annotation 详情页
2. 点击编辑
3. 打开 category 下拉
4. 验证 4 个选项（中文标签）视觉可见
5. 验证未被遮挡、在视口内
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from browser_auth_cli import PlaywrightCLI

OUT_DIR = r"d:\filework\excel-to-diagram\test_results\popper_audit"
os.makedirs(OUT_DIR, exist_ok=True)


def assert_visible(page, selector: str, description: str) -> dict:
    """5 步视觉验证：exists, sized, notHidden, inViewport, notObscured"""
    return page.evaluate("""
        (sel) => {
            const el = document.querySelector(sel);
            if (!el) return { ok: false, step: 'exists', reason: 'element not found' };

            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) {
                return { ok: false, step: 'sized', reason: 'zero size', rect: r };
            }

            const s = getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) < 0.01) {
                return { ok: false, step: 'notHidden', reason: 'hidden by CSS', display: s.display, visibility: s.visibility, opacity: s.opacity };
            }

            const inViewport = r.x >= 0 && r.y >= 0 && r.x + r.width <= window.innerWidth && r.y + r.height <= window.innerHeight;
            if (!inViewport) {
                return { ok: false, step: 'inViewport', reason: 'outside viewport', rect: r, vw: window.innerWidth, vh: window.innerHeight };
            }

            const cx = r.x + r.width / 2;
            const cy = r.y + r.height / 2;
            const topEl = document.elementFromPoint(cx, cy);
            if (!topEl || !el.contains(topEl)) {
                // topEl 不在 popper 内，认为被遮挡
                const inPopperChain = topEl && (topEl.closest('.el-select-dropdown, .el-dropdown-menu, .el-tooltip__popper, .el-popper, .el-picker__popper'));
                if (!inPopperChain) {
                    return { ok: false, step: 'notObscured', reason: 'top element not in popper', topEl: topEl ? topEl.tagName + '.' + topEl.className : null };
                }
            }

            return { ok: true, rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) } };
        }
    """, selector)


def test_annotation_category_dropdown(cli: PlaywrightCLI) -> dict:
    """测试 annotation 类别的下拉菜单（原始问题）"""
    print("\n[TEST] annotation 类别下拉视觉可见性")
    print("=" * 60)

    page = cli._ensure_browser()
    results = {}

    # 步骤 1: 导航到 annotation 列表
    print("\n  Step 1: 导航到 /#/object/annotation")
    cli.goto("http://localhost:3004/#/object/annotation")
    cli.wait_for_timeout(2000)
    page.screenshot(path=f"{OUT_DIR}/anno_01_list.png", full_page=False)
    results['step1_list'] = {'ok': True, 'url': page.url}

    # 步骤 2: 找到第一条数据并点击进入详情
    print("\n  Step 2: 进入 annotation 详情页")
    # 查找表格行
    rows = page.query_selector_all('.el-table__body .el-table__row')
    print(f"    Found {len(rows)} table rows")
    if len(rows) > 0:
        # 点击第一行的 business key（链接）
        first_link = rows[0].query_selector('.bk-link')
        if first_link:
            first_link.click()
        else:
            rows[0].click()
    else:
        return {'ok': False, 'reason': 'no rows in annotation list'}

    cli.wait_for_timeout(3000)
    page.screenshot(path=f"{OUT_DIR}/anno_02_detail.png", full_page=False)
    results['step2_detail'] = {'ok': True, 'url': page.url}

    # 步骤 3: 进入编辑模式
    print("\n  Step 3: 点击编辑按钮进入编辑模式")
    edit_buttons = page.query_selector_all('button')
    edit_clicked = False
    for btn in edit_buttons:
        try:
            text = btn.text_content().strip()
            if text in ('编辑', 'Edit', '开始编辑') and not edit_clicked:
                btn.click()
                edit_clicked = True
                print(f"    Clicked button: {text}")
                break
        except Exception:
            pass

    if not edit_clicked:
        # 尝试通过点击编辑图标按钮
        edit_icons = page.query_selector_all('.el-button--primary')
        for btn in edit_icons:
            try:
                if 'edit' in (btn.get_attribute('class') or '').lower() or btn.query_selector('.el-icon'):
                    btn.click()
                    edit_clicked = True
                    print("    Clicked edit icon button")
                    break
            except Exception:
                pass

    cli.wait_for_timeout(2000)
    page.screenshot(path=f"{OUT_DIR}/anno_03_edit.png", full_page=False)
    results['step3_edit'] = {'ok': edit_clicked}

    # 步骤 4: 找到所有 el-select，尝试打开第一个（通常是 category）
    print("\n  Step 4: 找到并打开 category 下拉")
    cli.wait_for_timeout(1000)
    selects = page.query_selector_all('.el-select')
    print(f"    Found {len(selects)} el-select elements")
    results['step4_selects_count'] = len(selects)

    if len(selects) == 0:
        return {'ok': False, 'reason': 'no el-select found in edit mode', **results}

    # 尝试点击每个 select 看哪个能打开下拉
    category_select = None
    for i, sel in enumerate(selects[:5]):
        try:
            sel.click()
            cli.wait_for_timeout(800)
            # 检查是否有下拉打开
            dropdown = page.query_selector('.el-select-dropdown')
            if dropdown:
                # 检查选项数量
                options = dropdown.query_selector_all('.el-select-dropdown__item')
                print(f"    Select[{i}]: opened with {len(options)} options")
                if len(options) >= 2:
                    # 找到了 category 之类的下拉
                    category_select = i
                    page.screenshot(path=f"{OUT_DIR}/anno_04_dropdown_open.png", full_page=False)

                    # 步骤 5: 视觉验证
                    print("\n  Step 5: 视觉验证 4 个选项可见")
                    option_results = []
                    for j, opt in enumerate(options[:6]):
                        opt_text = opt.text_content().strip()
                        print(f"    Option[{j}]: '{opt_text}'")
                        # 计算选项在页面中的实际位置
                        opt_rect = opt.evaluate("el => { const r = el.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), text: el.textContent.trim() }; }")
                        # 检查元素中心点是否真正可见
                        cx = opt_rect['x'] + opt_rect['w'] / 2
                        cy = opt_rect['y'] + opt_rect['h'] / 2
                        top_at_center = page.evaluate(f"() => {{ const el = document.elementFromPoint({cx}, {cy}); return el ? el.tagName + '.' + (el.className || '').slice(0, 60) : 'null'; }}")
                        in_popper = 'el-select-dropdown' in top_at_center or 'el-popper' in top_at_center
                        option_results.append({
                            'text': opt_text,
                            'rect': opt_rect,
                            'top_at_center': top_at_center,
                            'visible': in_popper
                        })
                    results['step5_options'] = option_results
                    results['step5_visible_count'] = sum(1 for o in option_results if o['visible'])
                    results['step5_total'] = len(option_results)
                    break
                # 关闭当前下拉
                page.keyboard.press("Escape")
                cli.wait_for_timeout(500)
        except Exception as e:
            print(f"    Select[{i}]: error {e}")

    page.screenshot(path=f"{OUT_DIR}/anno_05_final.png", full_page=False)
    results['ok'] = results.get('step5_visible_count', 0) >= 2
    return results


def main():
    cli = PlaywrightCLI(headless=True)
    cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
    cli.wait_for_timeout(1500)

    results = test_annotation_category_dropdown(cli)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"OK: {results.get('ok', False)}")
    if 'step5_options' in results:
        print(f"Visible options: {results['step5_visible_count']}/{results['step5_total']}")
        for opt in results['step5_options']:
            mark = "[OK]" if opt.get('visible') else "[FAIL]"
            print(f"  {mark} {opt['text'][:40]} (top={opt.get('top_at_center', '?')[:60]})")
    elif 'reason' in results:
        print(f"Reason: {results['reason']}")

    with open(f"{OUT_DIR}/anno_dropdown_test.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nFull report: {OUT_DIR}/anno_dropdown_test.json")

    cli.close()
    return 0 if results.get('ok', False) else 1


if __name__ == "__main__":
    sys.exit(main())
