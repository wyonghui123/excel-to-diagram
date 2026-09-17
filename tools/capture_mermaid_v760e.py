"""
[V007.60e] 直接调用 API + 灌 store 触发图表渲染
- 拿产品列表 → 选第一个
- 拿版本列表 → 选第一个
- 拿域/子域列表 → 找"财务云" (子域) → 拿到 sub_domain_id
- 拿关系列表 → 拿"范围内与外部"对应的关系 IDs
- 构造 chartData → 灌进 store → 跳到 /archdata-chart → 抓 mermaidCode
"""
import sys
import os
import time
import json
import urllib.request

sys.path.insert(0, r"D:\filework\worktrees/release-prep\test_helpers")
sys.path.insert(0, r"D:\filework\excel-to-diagram\test_helpers")

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3006"
API = "http://localhost:3018/api/v1"


def api(path):
    url = f"{API}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"_error": str(e), "_url": url}


def main():
    print("=" * 70)
    print("[V007.60e] Playwright 内 fetch + 灌 store")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()
        page.on("console", lambda m: print(f"  [console.{m.type}] {m.text[:300]}") if m.type in ("error", "warning") or "V007" in m.text or "mermaid" in m.text.lower() or "Syntax" in m.text or "chart" in m.text.lower() else None)
        page.on("pageerror", lambda e: print(f"  [pageerror] {e}"))

        # dev-login
        page.goto("http://localhost:3018/api/v1/auth/dev-login?username=admin",
                  wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(500)

        # 在浏览器内 fetch (带 cookie)
        print("\n[1] 浏览器内 fetch /bo/products ...")
        products = page.evaluate("""
            async () => {
                const r = await fetch('/api/v2/bo/products?limit=20', { credentials: 'include' })
                return { status: r.status, body: await r.text() }
            }
        """)
        print(f"  status: {products.get('status')}")
        try:
            pd = json.loads(products.get("body", "{}"))
            print(f"  keys: {list(pd.keys())[:5]}")
            items = pd.get("data", {}).get("items", []) if isinstance(pd.get("data"), dict) else (pd.get("data", []) if isinstance(pd.get("data"), list) else [])
            print(f"  products count: {len(items)}")
            if items:
                print(f"  sample: {items[0]}")
        except Exception as e:
            print(f"  parse err: {e}")
            print(f"  body: {products.get('body', '')[:500]}")
            return
        if not items:
            return
        product = items[0]
        pid = product.get("id") or product.get("product_id") or product.get("productId")
        print(f"  选: {product.get('name', product.get('code', pid))} (id={pid})")

        # 2. 拿版本
        print(f"\n[2] 浏览器内 fetch /bo/products/{pid}/versions ...")
        r = page.evaluate(f"""
            async () => {{
                const r = await fetch(`/api/v2/bo/products/{pid}/versions?limit=10`, {{ credentials: 'include' }})
                return {{ status: r.status, body: await r.text() }}
            }}
        """)
        try:
            vd = json.loads(r.get("body", "{}"))
            vitems = vd.get("data", {}).get("items", []) if isinstance(vd.get("data"), dict) else (vd.get("data", []) if isinstance(vd.get("data"), list) else [])
            print(f"  versions count: {len(vitems)}")
            if vitems:
                print(f"  sample: {vitems[0]}")
        except Exception as e:
            print(f"  parse err: {e}")
            print(f"  body: {r.get('body', '')[:500]}")
            return
        if not vitems:
            return
        version = vitems[0]
        vid = version.get("id") or version.get("version_id") or version.get("versionId")
        print(f"  选: {version.get('name', version.get('code', vid))} (id={vid})")

        # 3. 找"财务云"
        print(f"\n[3] 找 '财务云' sub_domain (version {vid}) ...")
        caiwu = page.evaluate(f"""
            async () => {{
                const paths = [
                    `/api/v2/bo/versions/{vid}/sub-domains`,
                    `/api/v2/bo/versions/{vid}/hierarchy`,
                    `/api/v2/bo/versions/{vid}/domains`,
                ]
                for (const p of paths) {{
                    const r = await fetch(p, {{ credentials: 'include' }})
                    if (!r.ok) continue
                    const j = await r.json()
                    function find(obj) {{
                        if (!obj) return null
                        if (Array.isArray(obj)) {{ for (const v of obj) {{ const r = find(v); if (r) return r }} return null }}
                        if (typeof obj === 'object') {{
                            const name = (obj.name || obj.code || '').toString()
                            if (name.includes('财务') || name.toLowerCase().includes('finance') || name.toLowerCase().includes('caiwu')) return obj
                            for (const v of Object.values(obj)) {{ const r = find(v); if (r) return r }}
                        }}
                        return null
                    }}
                    const hit = find(j)
                    if (hit) return {{ path: p, hit }}
                }}
                return null
            }}
        """)
        if not caiwu:
            print(f"  [WARN] 财务云未找到")
            # 列下层级
            for path in [f"/api/v2/bo/versions/{vid}/hierarchy", f"/api/v2/bo/versions/{vid}/sub-domains", f"/api/v2/bo/versions/{vid}/domains"]:
                r = page.evaluate(f"""
                    async () => {{
                        const r = await fetch('{path}', {{ credentials: 'include' }})
                        return {{ status: r.status, body: r.ok ? await r.text() : '' }}
                    }}
                """)
                if r.get("status") == 200:
                    print(f"\n  --- {path} ---")
                    print(r.get("body", "")[:2000])
            return
        print(f"  找到: {caiwu.get('hit')}")
        caiwu_id = caiwu["hit"].get("id") or caiwu["hit"].get("sub_domain_id") or caiwu["hit"].get("subDomainId")
        print(f"  caiwu_id = {caiwu_id}")

        # 4. 拿关系 (看样本即可, 不必精确选)
        print(f"\n[4] 关系样本 ...")
        r = page.evaluate(f"""
            async () => {{
                const r = await fetch(`/api/v2/bo/versions/{vid}/service-module-relationships?limit=5`, {{ credentials: 'include' }})
                return {{ status: r.status, body: r.ok ? await r.text() : '' }}
            }}
        """)
        print(f"  body: {r.get('body', '')[:500]}")

        # 5. 灌 store
        chartData = {
            "versionId": vid,
            "productId": pid,
            "hierarchyFilter": {"sub_domain_id": [caiwu_id]},
            "relationTypeFilter": [],
            "relationIds": []
        }
        print(f"\n[5] 灌 store + 切 chart tab ...")
        result = page.evaluate(f"""
            () => {{
                const app = document.querySelector('#app').__vue_app__
                const pinia = app.config.globalProperties.$pinia
                const chartStore = pinia._s.get('chartArchData')
                if (!chartStore) return {{ error: 'no chartArchData store' }}

                const data = {json.dumps(chartData)}
                chartStore.setArchData(data)

                try {{
                    sessionStorage.setItem('lastArchDataForDiagram', JSON.stringify(data))
                    sessionStorage.setItem('archDataForDiagram', JSON.stringify(data))
                    sessionStorage.setItem('archDataCurrentStep', '3')
                }} catch (e) {{}}

                const tabStore = pinia._s.get('tab')
                const chartTabId = '/archdata-chart'
                const existing = tabStore.tabs.find(t => t.id === chartTabId)
                if (existing) {{
                    existing.closable = true
                    existing.pinned = false
                    tabStore.switchTab(chartTabId)
                }} else {{
                    tabStore.openTab({{
                        id: chartTabId,
                        label: '架构数据图表',
                        path: chartTabId,
                        pinned: false,
                        closable: true,
                    }})
                }}

                const router = app.config.globalProperties.$router
                router.push('/archdata-chart')

                return {{ ok: true }}
            }}
        """)
        print(f"  store 设置: {result}")

        # 等图表渲染
        print("  等待图表渲染...")
        info = None
        for i in range(30):
            page.wait_for_timeout(2000)
            info = page.evaluate("""
                () => ({
                    lastCode: !!window.__lastMermaidCode,
                    codeLen: window.__lastMermaidCode?.length || 0,
                    hasError: !!window.__mermaidLastError,
                    errMsg: window.__mermaidLastError?.message,
                    errStr: window.__mermaidLastError?.str,
                    errHash: window.__mermaidLastError?.hash,
                    errName: window.__mermaidLastError?.name,
                })
            """)
            print(f"  [{i*2:3d}s] code={info.get('codeLen')} error={info.get('hasError')}")
            if info.get("hasError"):
                print(f"    ERR msg: {info.get('errMsg')}")
                print(f"    ERR str: {info.get('errStr')}")
                print(f"    ERR hash: {info.get('errHash')}")
                print(f"    ERR name: {info.get('errName')}")
            if info.get("codeLen", 0) > 1000:
                break

        page.screenshot(path="test_output/v760e_01_chart.png", full_page=True)

        # 6. 抓完整 mermaidCode
        if info.get("lastCode"):
            full_code = page.evaluate("() => window.__lastMermaidCode")
            with open("test_output/v760e_mermaid_code.txt", "w", encoding="utf-8") as f:
                f.write(full_code)
            print(f"\n  mermaidCode 已保存: test_output/v760e_mermaid_code.txt ({len(full_code)} chars)")
            print(f"  前 500 chars:\n{full_code[:500]}")
            print(f"  后 500 chars:\n{full_code[-500:]}")

        # 7. 独立 mermaid.render() 测试
        print(f"\n[7] 独立测试 mermaidCode (browser mermaid.render)...")
        test_result = page.evaluate("""
            async () => {
                const code = window.__lastMermaidCode
                if (!code) return { error: 'no code' }
                // vite dev 3007 的 mermaid 没加载, 先从 vite 拿
                try {
                    const mod = await import('/node_modules/.vite/deps/mermaid.js')
                    window.__mermaid_test_lib = mod.default || mod
                } catch (e) {
                    return { error: 'mermaid not available: ' + e.message }
                }
                const mm = window.__mermaid_test_lib
                try {
                    mm.initialize({
                        startOnLoad: false,
                        securityLevel: 'loose',
                        flowchart: { htmlLabels: true, maxEdges: 10000 },
                        maxTextSize: 9999999,
                        maxEdges: 10000,
                    })
                } catch (e) {}
                const id = 'svg_test_' + Date.now()
                try {
                    const { svg } = await mm.render(id, code)
                    return { ok: true, svgLen: svg.length }
                } catch (e) {
                    return {
                        ok: false,
                        message: e?.message || String(e),
                        name: e?.name,
                        hash: e?.hash,
                    }
                }
            }
        """)
        print(f"  独立测试: {test_result}")

        browser.close()


if __name__ == "__main__":
    main()
