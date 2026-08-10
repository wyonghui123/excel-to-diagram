# -*- coding: utf-8 -*-
"""通过真实注入源 __archPage.chartConfig 切换 centerScopeHighlight (走真实 UI 链路).
验证是否触发全量重渲染 (SVG 替换 + viewBox 变化) 导致图表缩小.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

def main():
    cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
    try:
        page = cli.authenticated_navigate("/system/archdata?preset=scp&mode=debug", timeout=20000)
        for _ in range(60):
            if page.evaluate("() => !!(window.__archPage && window.__archPage.debug && window.__archPage.debug.store)"):
                break
            page.wait_for_timeout(1000)
        page.wait_for_timeout(1500)

        # 查看 chartConfig 结构里 centerScopeHighlight 在哪
        info = page.evaluate("""() => {
            const cc = window.__archPage.chartConfig;
            if (!cc) return 'NO_CHARTCONFIG';
            return {
                hasCenterScopeHighlight: 'centerScopeHighlight' in cc,
                centerScopeHighlight: cc.centerScopeHighlight,
                keys: Object.keys(cc),
                hasAnnotationConfig: !!cc.annotationConfig,
                annKeys: cc.annotationConfig ? Object.keys(cc.annotationConfig) : null
            };
        }""")
        print("chartConfig:", info)

        # 展开到领域级
        page.evaluate("() => window.__archPage.debug.setExpandLevel('domain')")
        page.wait_for_timeout(2500)

        for toggle_idx, val in enumerate([False, True, False, True, False, True]):
            page.evaluate("""() => {
                window.__svgBefore = document.querySelector('.mermaid-content svg, pre.mermaid svg');
                window.__vbBefore = window.__svgBefore ? window.__svgBefore.getAttribute('viewBox') : null;
            }""")
            # 真实 UI 链路: 改 chartConfig.centerScopeHighlight
            page.evaluate(f"() => {{ window.__archPage.chartConfig.centerScopeHighlight = {str(val).lower()}; }}")
            samples = page.evaluate("""async () => {
                const out = [];
                for (let i = 0; i < 20; i++) {
                    const svg = document.querySelector('.mermaid-content svg, pre.mermaid svg');
                    const r = svg ? svg.getBoundingClientRect() : null;
                    out.push({
                        ms: i*50,
                        sameEl: svg === window.__svgBefore,
                        vb: svg ? svg.getAttribute('viewBox') : null,
                        svgW: r ? Math.round(r.width) : null,
                        svgH: r ? Math.round(r.height) : null,
                        opacity: svg ? svg.style.opacity : null,
                        tf: (document.querySelector('.mermaid-content')||{style:{}}).style.transform || null
                    });
                    await new Promise(q => setTimeout(q, 50));
                }
                return out;
            }""")
            print(f"=== 切换#{toggle_idx} csh={val} 前 vb={page.evaluate('() => window.__vbBefore')} ===")
            for s in samples:
                print(f"  {s['ms']}ms sameEl={s['sameEl']} svg={s['svgW']}x{s['svgH']} vb={s['vb'][:40] if s['vb'] else None} op={s['opacity']} tf={s['tf']}")
    finally:
        cli.close()

if __name__ == "__main__":
    main()