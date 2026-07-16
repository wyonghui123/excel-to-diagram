"""
[V007.60] 端到端捕获: 完整走 "财务云" + "范围内与外部" 流程, 抓真实 mermaidCode + 错误
"""
import sys
import os
import time
import json

sys.path.insert(0, r"D:\filework\release-prep-worktree\test_helpers")
sys.path.insert(0, r"D:\filework\excel-to-diagram\test_helpers")

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3006"


def main():
    print("=" * 70)
    print("[V007.60] 端到端捕获: 财务云 + 范围内与外部 → 真实 mermaidCode")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()

        # 收集 console
        console_msgs = []
        page.on("console", lambda msg: (
            console_msgs.append(f"[{msg.type}] {msg.text[:300]}"),
            print(f"  [console.{msg.type}] {msg.text[:200]}")
        ))
        page.on("pageerror", lambda err: (
            console_msgs.append(f"[pageerror] {err}"),
            print(f"  [pageerror] {err}")
        ))

        # 1. dev-login
        print("\n[1] dev-login (3018)...")
        page.goto("http://localhost:3018/api/v1/auth/dev-login?username=admin",
                  wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(500)

        # 2. 主页
        print("[2] 主页...")
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)
        page.wait_for_function("() => window.__pinia || document.querySelector('#app')?.__vue_app__", timeout=10000)

        # 3. 导航到 archdata 页
        print("[3] 跳转到 /system/archdata ...")
        page.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__.config.globalProperties.$router
                router.push('/system/archdata')
            }
        """)
        page.wait_for_url("**/system/archdata**", timeout=15000)
        page.wait_for_timeout(3000)
        page.screenshot(path="test_output/v760_01_archdata.png", full_page=True)
        print("    已加载 archdata 页面")

        # 4. 详细看一下页面结构 (列出关键元素)
        print("\n[4] 探索页面元素...")
        info = page.evaluate("""
            () => {
                const out = {}
                // 找到所有可点击的视图按钮
                out.buttons = Array.from(document.querySelectorAll('button')).slice(0, 30).map(b => ({
                    text: b.textContent.trim().slice(0, 50),
                    cls: b.className.slice(0, 100),
                    disabled: b.disabled,
                }))
                // 树节点
                out.treeNodes = Array.from(document.querySelectorAll('.el-tree-node')).slice(0, 20).map(n => ({
                    text: n.textContent.trim().slice(0, 80),
                }))
                // 找到产品选择器
                out.selects = Array.from(document.querySelectorAll('select, .el-select, .el-cascader, [class*="select"]')).slice(0, 10).map(s => ({
                    tag: s.tagName,
                    cls: s.className.slice(0, 100),
                }))
                return out
            }
        """)
        print("    按钮列表:")
        for b in info.get("buttons", []):
            marker = " [DISABLED]" if b["disabled"] else ""
            print(f"      - {b['text']!r}{marker}")
        print(f"    树节点数: {len(info.get('treeNodes', []))}")
        if info.get("treeNodes"):
            for t in info["treeNodes"][:10]:
                print(f"      - {t['text']!r}")
        print(f"    选择器数: {len(info.get('selects', []))}")

        # 5. 直接操作 Pinia store - 这是最快的方式
        # 先看 store 结构
        print("\n[5] 探索 Pinia store...")
        store_info = page.evaluate("""
            () => {
                const app = document.querySelector('#app').__vue_app__
                const pinia = app.config.globalProperties.$pinia
                if (!pinia) return { error: 'no pinia' }
                const out = {}
                for (const [key, store] of pinia._s) {
                    out[key] = {
                        id: store.$id,
                        keys: Object.keys(store).filter(k => !k.startsWith('_') && !k.startsWith('$')).slice(0, 30),
                    }
                }
                return out
            }
        """)
        print("    Pinia stores:")
        for sid, info_s in store_info.items() if isinstance(store_info, dict) else []:
            print(f"      - {sid}: {info_s.get('keys', [])}")

        # 6. 等 5 秒让用户/AI 看一下截图
        print("\n[6] 等待 2 秒 (等待 UI 完全渲染)...")
        page.wait_for_timeout(2000)
        page.screenshot(path="test_output/v760_02_explored.png", full_page=True)

        # 7. 尝试通过 store 强制走通流程
        # 先看 archDataStore 的 products 列表
        print("\n[7] 探索 archData store 内容...")
        arch = page.evaluate("""
            () => {
                const app = document.querySelector('#app').__vue_app__
                const pinia = app.config.globalProperties.$pinia
                const archStore = pinia._s.get('archData') || pinia._s.get('archDataStore')
                if (!archStore) return { error: 'no archData store', stores: Array.from(pinia._s.keys()) }
                return {
                    products: archStore.products?.length || 0,
                    versions: archStore.versions?.length || 0,
                    productSample: archStore.products?.[0],
                    versionSample: archStore.versions?.[0],
                }
            }
        """)
        print(f"    archData: {arch}")

        browser.close()
        print("\n[done]")


if __name__ == "__main__":
    main()
