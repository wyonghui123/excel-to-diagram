"""
[V007.60b] 深入探索: chartArchData store + 找到 500 错误源
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
    print("[V007.60b] 深入探索 chartArchData store")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()

        # 收集 network 错误
        net_errors = []
        page.on("response", lambda resp: (
            net_errors.append(f"[{resp.status}] {resp.url[:200]}")
            if resp.status >= 400 else None
        ))
        page.on("pageerror", lambda err: print(f"  [pageerror] {err}"))

        # 1. dev-login
        print("\n[1] dev-login (3018)...")
        page.goto("http://localhost:3018/api/v1/auth/dev-login?username=admin",
                  wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(500)

        # 2. 主页
        print("[2] 主页...")
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)

        # 3. 导航到 archdata
        print("[3] 跳转 /system/archdata ...")
        page.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__.config.globalProperties.$router
                router.push('/system/archdata')
            }
        """)
        page.wait_for_url("**/system/archdata**", timeout=15000)
        page.wait_for_timeout(3000)

        # 4. 探索 chartArchData
        print("\n[4] chartArchData store 内容...")
        info = page.evaluate("""
            () => {
                const app = document.querySelector('#app').__vue_app__
                const pinia = app.config.globalProperties.$pinia
                const chartStore = pinia._s.get('chartArchData')
                if (!chartStore) return { error: 'no chartArchData' }

                const arch = chartStore.archData
                return {
                    hasArchData: !!arch,
                    archKeys: arch ? Object.keys(arch).slice(0, 30) : [],
                    archSize: arch ? JSON.stringify(arch).length : 0,
                    // 详细看几个核心字段
                    hasProducts: arch?.products?.length || 0,
                    hasVersions: arch?.versions?.length || 0,
                    hasDomains: arch?.domains?.length || 0,
                    hasSubDomains: arch?.subDomains?.length || 0,
                    hasServiceModules: arch?.serviceModules?.length || 0,
                    hasBusinessObjects: arch?.businessObjects?.length || 0,
                    hasRelationships: arch?.serviceModuleRelationships?.length || 0,
                    productSample: arch?.products?.[0],
                    domainSample: arch?.domains?.[0],
                }
            }
        """)
        print(json.dumps(info, indent=2, ensure_ascii=False, default=str))

        # 5. 列出所有 network 4xx/5xx
        print("\n[5] 4xx/5xx 响应:")
        for e in net_errors[:20]:
            print(f"    {e}")

        browser.close()


if __name__ == "__main__":
    main()
