# -*- coding: utf-8 -*-
# 用 setter 陷阱捕获 MM.collapsed 被改成 true 的调用栈
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
try:
    page = cli.authenticated_navigate("/system/archdata?preset=scp&mode=debug",
        wait_for_selector=".embedded-chart-view", timeout=30000)
    page.wait_for_function("() => !!window.__archPage && !!window.__archPage.verify", timeout=30000)
    page.wait_for_timeout(2500)

    # 双击展开 MM
    page.evaluate("""() => {
        const svg = document.querySelector('svg.flowchart');
        const nodes = svg.querySelectorAll('g.node[id*="COLLAPSE_SD_MM"]');
        if (nodes.length === 0) return 'no-node';
        nodes[0].dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
        return 'dblclicked';
    }""")
    page.wait_for_timeout(2000)

    # 安装 setter 陷阱: 找到 chartConfig.layoutControl.groups 中的 MM 分组, 重定义 collapsed
    trap = page.evaluate("""() => {
        const chart = window.__archPage.chartConfig;
        const _f=(list)=>{for(const g of list||[]){if((g.elementCode||g.id)==='MM')return g;const r=_f(g.children);if(r)return r;const r2=_f(g.containers);if(r2)return r2;}return null;};
        const mm = _f(chart?.layoutControl?.groups);
        if (!mm) return { ok:false, reason:'MM not found' };
        const before = mm.collapsed;
        window.__mmSetLog = [];
        const desc = Object.getOwnPropertyDescriptor(mm, 'collapsed');
        // 保存原始值, 用 defineProperty 装 setter
        let val = mm.collapsed;
        try {
            Object.defineProperty(mm, 'collapsed', {
                configurable: true,
                enumerable: true,
                get() { return val; },
                set(v) {
                    if (v === true && val !== true) {
                        window.__mmSetLog.push({ from: val, to: v, stack: (new Error().stack||'').split('\\n').slice(1,12).join(' | ') });
                    }
                    val = v;
                }
            });
            return { ok:true, before, desc: desc ? 'had-desc' : 'no-desc' };
        } catch(e) {
            return { ok:false, reason: String(e && e.message||e) };
        }
    }""")
    print("[trap]", json.dumps(trap))

    # 切换 centerScopeHighlight
    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(2000)

    n = page.evaluate("() => window.__mmSetLog.length")
    print(f"=== MM.collapsed 被置 true 的调用栈 ({n} 次) ===")
    logs = page.evaluate("() => window.__mmSetLog")
    for l in logs[:10]:
        print("  from", l['from'], "-> to", l['to'])
        print("  stack:", l['stack'][:600])
        print("  ---")
finally:
    cli.close()