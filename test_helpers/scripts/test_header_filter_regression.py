#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回归测试：列表表头过滤 popover 必须可见
使用 authenticated_navigate 设置 product context 后再访问 list 页面
"""
import sys
import os
import json

sys.path.insert(0, r'd:\filework\excel-to-diagram\test_helpers')
from browser_auth_cli import PlaywrightCLI

OUT_DIR = r"d:\filework\excel-to-diagram\test_results\popper_audit"
os.makedirs(OUT_DIR, exist_ok=True)


def main():
    cli = PlaywrightCLI(headless=True)
    page = cli._ensure_browser()

    # 1. 设置 product+version 上下文
    print("\n[1] Setting up product/version context via API")
    cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
    cli.wait_for_timeout(1500)

    # 通过 API 获取产品和版本
    products = page.evaluate("""
        async () => {
            // API 已经在 2026-05-14 迁移到 v2
            const res = await fetch('/api/v2/bo/products?limit=1', { credentials: 'include' });
            const data = await res.json();
            return data.data || data.items || data;
        }
    """)
    print(f"    Products type: {type(products).__name__}, value: {repr(products)[:300]}")

    if products and len(products) > 0:
        first_prod = products[0] if isinstance(products, list) else products
        pid = first_prod.get('id') if isinstance(first_prod, dict) else None
        if not pid:
            print(f"    [WARN] No product id found in: {first_prod}")
            cli.close()
            return 1
        # 获取版本
        versions = page.evaluate(f"""
            async () => {{
                const res = await fetch('http://localhost:3010/api/v1/products/{pid}/versions?pageSize=1', {{ credentials: 'include' }});
                const data = await res.json();
                const list = data.data?.list || data.data || data.items || data;
                return Array.isArray(list) ? list : [];
            }}
        """)
        print(f"    Versions count: {len(versions) if isinstance(versions, list) else 'N/A'}")

        if versions and len(versions) > 0:
            first_ver = versions[0] if isinstance(versions, list) else versions
            vid = first_ver.get('id') if isinstance(first_ver, dict) else None
            if not vid:
                print(f"    [WARN] No version id found in: {first_ver}")
                cli.close()
                return 1
            # 设置 session
            cli.goto(f"http://localhost:3010/api/v1/version-context/set?product_id={pid}&version_id={vid}")
            cli.wait_for_timeout(1500)
            print(f"    Set version context: product={pid}, version={vid}")
        else:
            print(f"    [WARN] No versions found")

    # 2. 重新进入页面，让 context 生效
    cli.goto("http://localhost:3004/")
    cli.wait_for_timeout(2500)
    page.screenshot(path=f"{OUT_DIR}/regression_01_home.png", full_page=False)

    # 3. 用 authenticated_navigate 跳到 list 页面
    print("\n[2] Navigate to business_object list")
    try:
        cli.authenticated_navigate('/object/business_object', wait_for_selector='.el-table, .filter-trigger', timeout=10000)
    except Exception as e:
        print(f"    [WARN] authenticated_navigate failed: {e}, trying direct")
        cli.goto("http://localhost:3004/#/object/business_object")
        cli.wait_for_timeout(3500)
    cli.wait_for_timeout(2000)

    page.screenshot(path=f"{OUT_DIR}/regression_02_list.png", full_page=True)
    print(f"    URL: {page.url}")

    # 检查页面内容
    body = page.evaluate("() => document.body.textContent.slice(0, 300)")
    print(f"    Body snippet: {body[:200]}")

    # 4. 找 filter triggers
    triggers = page.query_selector_all('.filter-trigger')
    print(f"\n[3] Found {len(triggers)} .filter-trigger elements")

    if len(triggers) == 0:
        # 可能是 GenericObjectList 页面而不是 MetaListPage
        # 或者 header filter 根本没渲染
        # 列出所有 th 单元格
        ths = page.query_selector_all('th')
        print(f"    [DEBUG] Found {len(ths)} th cells")
        for i, th in enumerate(ths[:5]):
            txt = th.text_content().strip()[:30]
            print(f"      th[{i}]: '{txt}'")
        cli.close()
        return 1

    # 5. 点击第一个 trigger，验证 popover 出现
    results = {
        'url': page.url,
        'triggers_found': len(triggers),
        'triggers_tested': 0,
        'triggers_passed': 0,
        'details': []
    }

    for i in range(min(3, len(triggers))):
        trigger = triggers[i]
        try:
            print(f"\n[4.{i+1}] Hover + Click trigger[{i}]")
            # 先 hover 让它可见
            trigger.hover()
            cli.wait_for_timeout(300)
            trigger.click()
            cli.wait_for_timeout(800)

            page.screenshot(path=f"{OUT_DIR}/regression_03_trigger_{i}.png", full_page=False)

            # 检查 popover
            popover_data = page.evaluate("""
                () => {
                    const candidates = document.querySelectorAll('.el-popover, .el-popper');
                    const results = [];
                    for (const p of candidates) {
                        const r = p.getBoundingClientRect();
                        const s = getComputedStyle(p);
                        const hasFilterPanel = p.querySelector('.filter-panel') !== null;
                        if (!hasFilterPanel) continue;
                        const isVisible = r.width > 0 && r.height > 0
                            && s.display !== 'none'
                            && s.visibility !== 'hidden'
                            && parseFloat(s.opacity) > 0.01;
                        const inViewport = r.x >= 0 && r.y >= 0
                            && r.x + r.width <= window.innerWidth
                            && r.y + r.height <= window.innerHeight;
                        // 检查 elementFromPoint 在 popover 中心
                        let topInPopper = null;
                        if (isVisible && inViewport) {
                            const topEl = document.elementFromPoint(r.x + r.width/2, r.y + r.height/2);
                            topInPopper = topEl ? (topEl.closest('.el-popover, .el-popper') !== null) : false;
                        }
                        results.push({
                            rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
                            display: s.display,
                            visibility: s.visibility,
                            opacity: s.opacity,
                            zIndex: s.zIndex,
                            isVisible,
                            inViewport,
                            topInPopper
                        });
                    }
                    return results;
                }
            """)
            print(f"    Found {len(popover_data)} filter popovers")
            visible = [p for p in popover_data if p.get('isVisible') and p.get('inViewport') and p.get('topInPopper')]
            print(f"    Visible & on top: {len(visible)}/{len(popover_data)}")

            results['triggers_tested'] += 1
            if len(visible) > 0:
                results['triggers_passed'] += 1

            for j, p in enumerate(popover_data):
                mark = "[OK]" if p.get('isVisible') and p.get('inViewport') and p.get('topInPopper') else "[FAIL]"
                print(f"      {mark} popover[{j}]: rect={p.get('rect')}, vis={p.get('isVisible')}, z={p.get('zIndex')}, topInPopper={p.get('topInPopper')}")

            results['details'].append({
                'trigger_index': i,
                'popovers': popover_data
            })

            page.keyboard.press("Escape")
            cli.wait_for_timeout(500)
        except Exception as e:
            print(f"    [ERROR] trigger[{i}]: {e}")
            results['details'].append({'trigger_index': i, 'error': str(e)})

    cli.close()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Triggers: {results['triggers_found']}, Tested: {results['triggers_tested']}, Passed: {results['triggers_passed']}")
    overall = results['triggers_passed'] >= 1 and results['triggers_tested'] >= 1
    print(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
