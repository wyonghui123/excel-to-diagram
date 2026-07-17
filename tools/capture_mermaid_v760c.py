"""
[V007.60c] 端到端复现 + 抓真实 mermaidCode
- 选择产品 (第一个)
- 选择版本 (第一个)
- 选择关系范围 (财务云 + 范围内与外部)
- 点击"图表视图"
- 等待图表 tab 打开 + 抓 mermaidCode + 抓错误
"""
import sys
import os
import time
import json

sys.path.insert(0, r"D:\filework\worktrees/release-prep\test_helpers")
sys.path.insert(0, r"D:\filework\excel-to-diagram\test_helpers")

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3006"


def main():
    print("=" * 70)
    print("[V007.60c] 端到端 + 抓真实 mermaidCode")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=200)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()

        console_msgs = []
        page.on("console", lambda msg: (
            console_msgs.append((msg.type, msg.text)),
            print(f"  [console.{msg.type}] {msg.text[:300]}")
            if msg.type in ("error", "warning") or "V007" in msg.text or "mermaid" in msg.text.lower() or "Syntax" in msg.text
            else None
        ))
        page.on("pageerror", lambda err: print(f"  [pageerror] {err}"))
        page.on("response", lambda resp: print(f"  [net {resp.status}] {resp.url[:200]}") if resp.status >= 400 else None)

        # 1. dev-login
        print("\n[1] dev-login (3018)...")
        page.goto("http://localhost:3018/api/v1/auth/dev-login?username=admin",
                  wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(500)

        # 2. 主页
        print("[2] 主页...")
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)

        # 3. archdata
        print("[3] /system/archdata ...")
        page.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__.config.globalProperties.$router
                router.push('/system/archdata')
            }
        """)
        page.wait_for_url("**/system/archdata**", timeout=15000)
        page.wait_for_timeout(3000)
        page.screenshot(path="test_output/v760c_01_archdata.png", full_page=True)

        # 4. 探索页面的关键元素 (产品/版本/范围/图表按钮)
        print("\n[4] 探索页面 UI 结构...")
        ui = page.evaluate("""
            () => {
                const out = {}
                // 找所有 .el-select
                out.selects = Array.from(document.querySelectorAll('.el-select')).map((s, i) => ({
                    idx: i,
                    placeholder: s.querySelector('.el-select__placeholder')?.textContent || '',
                    label: s.previousElementSibling?.textContent?.trim()?.slice(0, 30) || '',
                    text: s.textContent.trim().slice(0, 50),
                }))
                // 找树
                out.trees = Array.from(document.querySelectorAll('.el-tree, .el-tree-node')).length
                // 找按钮
                out.chartBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('图表视图'))
                if (out.chartBtn) {
                    out.chartBtnDisabled = out.chartBtn.disabled
                }
                // 找所有 input
                out.inputs = Array.from(document.querySelectorAll('input')).map((i, idx) => ({
                    idx,
                    type: i.type,
                    placeholder: i.placeholder,
                    value: i.value,
                })).slice(0, 20)
                return out
            }
        """)
        print(f"    selects: {json.dumps(ui.get('selects', []), ensure_ascii=False, indent=2)[:1000]}")
        print(f"    trees count: {ui.get('trees')}")
        print(f"    chart btn disabled: {ui.get('chartBtnDisabled')}")
        print(f"    inputs: {json.dumps(ui.get('inputs', []), ensure_ascii=False)[:500]}")

        # 5. 先打开第一个 .el-select 看下拉选项
        print("\n[5] 打开第一个下拉框 (产品选择)...")
        if ui.get("selects"):
            page.locator(".el-select").first.click()
            page.wait_for_timeout(1500)
            page.screenshot(path="test_output/v760c_02_first_select.png", full_page=True)
            # 看下拉项
            options = page.evaluate("""
                () => {
                    const items = document.querySelectorAll('.el-select-dropdown__item, .el-select-dropdown__list li')
                    return Array.from(items).map(i => i.textContent.trim().slice(0, 50))
                }
            """)
            print(f"    下拉项: {options[:20]}")

            # 找 "财务云" 相关
            caiwu = None
            for i, opt in enumerate(options):
                if "财务" in opt or "Finance" in opt.lower():
                    caiwu = i
                    break
            if caiwu is not None:
                print(f"    找到 '财务云' 在 index {caiwu}: {options[caiwu]!r}")
                page.locator(".el-select-dropdown__item").nth(caiwu).click()
                page.wait_for_timeout(2000)
            else:
                print(f"    未找到 '财务云', 选第一项: {options[0]!r}")
                page.locator(".el-select-dropdown__item").first.click()
                page.wait_for_timeout(2000)
            page.screenshot(path="test_output/v760c_03_after_product.png", full_page=True)

        # 6. 看是否出现版本选择
        print("\n[6] 探索版本选择...")
        ui2 = page.evaluate("""
            () => {
                const selects = Array.from(document.querySelectorAll('.el-select')).map((s, i) => ({
                    idx: i,
                    placeholder: s.querySelector('.el-select__placeholder')?.textContent || '',
                    text: s.textContent.trim().slice(0, 80),
                }))
                return { selects }
            }
        """)
        print(f"    selects now: {json.dumps(ui2.get('selects', []), ensure_ascii=False, indent=2)[:1000]}")

        # 关闭浏览器前保存
        page.wait_for_timeout(2000)
        page.screenshot(path="test_output/v760c_04_end.png", full_page=True)
        browser.close()


if __name__ == "__main__":
    main()
