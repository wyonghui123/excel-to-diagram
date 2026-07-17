"""
[V007.60d] 完整走通: 选产品 → 选版本 → 选财务云 scope → 选关系范围 → 图表视图
"""
import sys
import os
import time
import json

sys.path.insert(0, r"D:\filework\worktrees/release-prep\test_helpers")
sys.path.insert(0, r"D:\filework\excel-to-diagram\test_helpers")

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3006"


def dump_step(page, name):
    page.wait_for_timeout(500)
    page.screenshot(path=f"test_output/v760d_{name}.png", full_page=True)
    print(f"    截图: test_output/v760d_{name}.png")


def main():
    print("=" * 70)
    print("[V007.60d] 端到端走通: 选产品/版本/财务云/范围内与外部")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()

        console_msgs = []
        def on_console(msg):
            console_msgs.append((msg.type, msg.text))
            t = msg.text
            if msg.type in ("error",) or "V007" in t or "mermaid" in t.lower() or "Syntax" in t or "chart" in t.lower() or "elk" in t.lower():
                print(f"  [console.{msg.type}] {t[:300]}")
        page.on("console", on_console)
        page.on("pageerror", lambda err: print(f"  [pageerror] {err}"))

        # 1. dev-login + 主页 + archdata
        print("\n[1] dev-login + 主页 + archdata ...")
        page.goto("http://localhost:3018/api/v1/auth/dev-login?username=admin",
                  wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(500)
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)
        page.evaluate("() => document.querySelector('#app').__vue_app__.config.globalProperties.$router.push('/system/archdata')")
        page.wait_for_url("**/system/archdata**", timeout=15000)
        page.wait_for_timeout(3000)
        dump_step(page, "01_archdata")

        # 2. 选产品 (选第一个有效产品 — 用 DEMOPROD)
        print("\n[2] 选产品 (DEMOPROD)...")
        page.locator(".el-select").first.click()
        page.wait_for_timeout(1500)
        # 找 DEMOPROD 或第一个非 TTTTTT 的
        options = page.evaluate("""
            () => Array.from(document.querySelectorAll('.el-select-dropdown__item')).map(i => i.textContent.trim())
        """)
        print(f"    产品列表: {options[:10]}")
        # 选 DEMOPROD
        target = None
        for opt in options:
            if "DEMO" in opt.upper() and "PROD" in opt.upper():
                target = opt
                break
        if not target:
            target = options[1] if len(options) > 1 else options[0]  # 跳过第一个占位
        print(f"    选: {target!r}")
        page.locator(".el-select-dropdown__item").filter(has_text=target).first.click()
        page.wait_for_timeout(2000)
        dump_step(page, "02_product_selected")

        # 3. 选版本 (等版本下拉框出现)
        print("\n[3] 选版本...")
        page.wait_for_timeout(2000)
        # 第二个 .el-select 应该是版本
        selects = page.locator(".el-select")
        n_selects = selects.count()
        print(f"    selects 数: {n_selects}")
        if n_selects >= 2:
            selects.nth(1).click()
            page.wait_for_timeout(1500)
            dump_step(page, "03_version_dropdown")
            version_options = page.evaluate("""
                () => Array.from(document.querySelectorAll('.el-select-dropdown__item')).map(i => i.textContent.trim())
            """)
            print(f"    版本列表: {version_options[:10]}")
            # 选第一个版本
            if version_options:
                page.locator(".el-select-dropdown__item").first.click()
                page.wait_for_timeout(2000)
        dump_step(page, "04_version_selected")

        # 4. 等 UI 出现范围选择
        print("\n[4] 等范围 UI 出现...")
        page.wait_for_timeout(3000)
        ui = page.evaluate("""
            () => {
                // 找所有树
                const trees = document.querySelectorAll('.el-tree, [class*="tree"]')
                // 找所有 .el-tree-node (有内容)
                const treeNodes = document.querySelectorAll('.el-tree-node__content')
                // 找范围相关的 label
                const labels = Array.from(document.querySelectorAll('label, .el-form-item__label, .el-checkbox__label, [class*="scope"]')).map(l => l.textContent.trim().slice(0, 60)).filter(t => t).slice(0, 30)
                // 找所有可点击的 checkbox
                const cbs = Array.from(document.querySelectorAll('.el-checkbox, .el-radio')).map(c => ({
                    tag: c.tagName,
                    label: c.textContent.trim().slice(0, 60),
                    checked: c.querySelector('input')?.checked,
                })).slice(0, 30)
                return {
                    treeCount: trees.length,
                    treeNodeCount: treeNodes.length,
                    treeNodeSample: Array.from(treeNodes).slice(0, 20).map(n => n.textContent.trim().slice(0, 60)),
                    labels,
                    cbs,
                }
            }
        """)
        print(f"    tree count: {ui.get('treeCount')}")
        print(f"    treeNode count: {ui.get('treeNodeCount')}")
        if ui.get("treeNodeSample"):
            for n in ui["treeNodeSample"][:15]:
                print(f"      - {n!r}")
        print(f"    labels: {ui.get('labels', [])[:15]}")
        print(f"    cbs:")
        for cb in ui.get("cbs", [])[:15]:
            print(f"      - {cb}")

        browser.close()


if __name__ == "__main__":
    main()
