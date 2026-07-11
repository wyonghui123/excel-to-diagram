"""
[V007.61] 验证 elk 在 3299 边是否也会 syntax error / stack overflow
（这个测试用 Playwright 浏览器, 直接 import mermaid from vite dev 3007）
"""
import sys
import time
sys.path.insert(0, r"D:\filework\release-prep-worktree\test_helpers")
sys.path.insert(0, r"D:\filework\excel-to-diagram\test_helpers")

from playwright.sync_api import sync_playwright


def build_mermaid(n_nodes, n_rels, label_style):
    parts = ["flowchart LR"]
    for i in range(n_nodes):
        if label_style == "br":
            parts.append(f'  n{i}["node{i}<br/>name"]')
        else:
            parts.append(f'  n{i}["node{i} name"]')
    for i in range(n_rels):
        src = i % n_nodes
        dst = (i + 1) % n_nodes
        parts.append(f"  n{src} --> n{dst}")
    return "\n".join(parts)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.on("pageerror", lambda e: print(f"[pageerror] {e}"))

        # 用 vite dev 3007 (有 node_modules/.vite/deps)
        page.goto("http://localhost:3007/", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)

        # 加载 mermaid
        ok = page.evaluate("""
            async () => {
                try {
                    const mod = await import('/node_modules/.vite/deps/mermaid.js')
                    window.__m = mod.default || mod
                    return 'ok'
                } catch (e) {
                    return 'fail: ' + e.message
                }
            }
        """)
        print(f"mermaid load: {ok}")

        # 初始化, 指定 elk 布局 + maxEdges
        page.evaluate("""
            () => {
                window.__m.initialize({
                    startOnLoad: false,
                    securityLevel: 'loose',
                    flowchart: { htmlLabels: true, maxEdges: 10000, defaultRenderer: 'elk' },
                    maxTextSize: 9999999,
                    maxEdges: 10000,
                })
            }
        """)
        print("mermaid initialized with elk default")

        # 测试 dagre vs elk (通过两个 initialize 切换)
        for engine in ["dagre", "elk"]:
            page.evaluate(f"""
                () => {{
                    window.__m.initialize({{
                        startOnLoad: false,
                        securityLevel: 'loose',
                        flowchart: {{ htmlLabels: true, maxEdges: 10000, defaultRenderer: '{engine}' }},
                        maxTextSize: 9999999,
                        maxEdges: 10000,
                    }})
                }}
            """)
            print(f"\n--- engine = {engine} ---")
            for n in [500, 1000, 2000, 3299]:
                for style in ["br", "space"]:
                    code = build_mermaid(n, n, style)
                    t0 = time.time()
                    r = page.evaluate("""
                        async (code) => {
                            const m = window.__m
                            const id = 'svg' + Date.now() + Math.floor(Math.random() * 99999)
                            try {
                                const { svg } = await m.render(id, code)
                                return { ok: true, svgLen: svg.length }
                            } catch (e) {
                                return { ok: false, message: e?.message || String(e), name: e?.name }
                            }
                        }
                    """, code)
                    elapsed = round((time.time() - t0) * 1000)
                    status = "OK" if r.get("ok") else f"FAIL: {r.get('message', '')[:60]}"
                    print(f"  [{status}] n={n:5d} style={style:6s} elapsed={elapsed:6d}ms")

        browser.close()


if __name__ == "__main__":
    main()
