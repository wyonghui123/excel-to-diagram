"""
[V007.59] 验证假设: 3299 关系 + <br/> 节点 label 是否触发 mermaid 11.13.0 "Syntax error in text"

策略: 用 vite dev server (3007) 走, 这样 mermaid 模块可被 dynamic import.
  - vite preview 不会暴露 node_modules, 必须用 vite dev
"""
import sys
import os
import time

sys.path.insert(0, r"D:\filework\worktrees/release-prep\test_helpers")
sys.path.insert(0, r"D:\filework\excel-to-diagram\test_helpers")

from playwright.sync_api import sync_playwright

# vite dev server, dev-login 直接走 backend 3018
BASE_URL = "http://localhost:3007"


def build_mermaid_code(n_nodes: int, n_rels: int, label_style: str) -> str:
    parts = ["flowchart LR"]
    for i in range(n_nodes):
        if label_style == "br":
            parts.append(f'  n{i}["node{i}<br/>name"]')
        elif label_style == "space":
            parts.append(f'  n{i}["node{i} name"]')
        elif label_style == "hash10":
            parts.append(f'  n{i}["node{i}#10;name"]')
    for i in range(n_rels):
        src = i % n_nodes
        dst = (i + 1) % n_nodes
        parts.append(f"  n{src} --> n{dst}")
    return "\n".join(parts)


def main():
    print("=" * 70)
    print("[V007.59] 验证: 3299 关系 + <br/> 节点 label 是否触发 Syntax error")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.on("pageerror", lambda err: print(f"[pageerror] {err}"))

        # 1. dev-login (走 3018 = integration backend)
        print("\n[1] dev-login (port 3018)...")
        page.goto("http://localhost:3018/api/v1/auth/dev-login?username=admin",
                  wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(500)

        # 2. 加载 vite dev server 触发 mermaid 模块加载
        print("[2] 加载 vite dev 3007 (触发 mermaid chunk 加载)...")
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)

        # 3. 把 mermaid 暴露到 window
        print("[3] 尝试暴露 mermaid 到 window...")
        ok = page.evaluate("""
            async () => {
                // vite dev 会把 mermaid 优化到 /node_modules/.vite/deps/mermaid.js
                try {
                    const mod = await import('/node_modules/.vite/deps/mermaid.js')
                    if (mod && (mod.default || mod.render)) {
                        window.__mermaid_test_lib = mod.default || mod
                        return 'ok: vite-deps'
                    }
                } catch (e) {
                    return 'fail: ' + e.message
                }
            }
        """)
        print(f"   {ok}")

        if ok.startswith("fail"):
            print("[FAIL] 无法加载 mermaid, 退出")
            browser.close()
            return

        # 4. 初始化 mermaid (使用和项目一致的配置, maxEdges=10000 关键)
        page.evaluate("""
            () => {
                const m = window.__mermaid_test_lib
                m.initialize({
                    startOnLoad: false,
                    securityLevel: 'loose',
                    flowchart: {
                        htmlLabels: true,
                        useMaxWidth: true,
                        maxEdges: 10000,
                    },
                    theme: 'default',
                    maxTextSize: 9999999,
                    maxEdges: 10000,
                })
            }
        """)
        print("[4] mermaid initialized (maxEdges=10000)")

        # 同时初始化 elk layout 配置
        page.evaluate("""
            () => {
                const m = window.__mermaid_test_lib
                // elk 也需要在 flowchart 里指定
            }
        """)

        # 5. 测试不同规模 × 不同 label 风格 × 不同 layout engine
        cases = []
        # dagre (默认)
        for n_nodes, n_rels in [(20, 20), (100, 100), (500, 500), (1000, 1000), (2000, 2000), (3299, 3299)]:
            for style in ["space", "br"]:
                code = build_mermaid_code(n_nodes, n_rels, style)
                cases.append(("dagre", n_nodes, n_rels, style, code, len(code)))

        print(f"\n[5] 运行 {len(cases)} 个 dagre case (确认 stack overflow 阈值)...")
        results = []
        for engine, n_nodes, n_rels, style, code, code_len in cases:
            t0 = time.time()
            r = page.evaluate("""
                async (code) => {
                    const m = window.__mermaid_test_lib
                    const id = 'svg' + Date.now() + Math.floor(Math.random() * 99999)
                    try {
                        const { svg } = await m.render(id, code)
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
            """, code)
            r["engine"] = engine
            r["n_nodes"] = n_nodes
            r["n_rels"] = n_rels
            r["style"] = style
            r["code_len"] = code_len
            r["elapsed"] = round((time.time() - t0) * 1000)
            results.append(r)
            status = "OK" if r.get("ok") else f"FAIL: {r.get('message', '')[:80]}"
            print(f"   [{status}] engine={engine:6s} nodes={n_nodes:5d} rels={n_rels:5d} "
                  f"style={style:8s} code_len={code_len:8d} elapsed={r['elapsed']:6d}ms")

        # 6. 输出汇总
        print("\n" + "=" * 70)
        print("[汇总]")
        print("=" * 70)
        all_ok = all(r.get("ok") for r in results)
        print(f"全部 PASS: {all_ok}")
        if not all_ok:
            print("\n失败的 case:")
            for r in results:
                if not r.get("ok"):
                    print(f"  - n={r['n_nodes']} r={r['n_rels']} style={r['style']}: {r.get('message')}")

        # 7. 关键对比: 同样 n=3299, 哪种 style 通过
        print("\n3299 节点/关系 三种 style 对比:")
        for r in results:
            if r["n_nodes"] == 3299:
                status = "PASS" if r.get("ok") else "FAIL"
                print(f"  [{status}] style={r['style']:8s} code_len={r['code_len']}")

        browser.close()


if __name__ == "__main__":
    main()
