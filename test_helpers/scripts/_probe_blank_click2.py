"""
_probe_blank_click2.py - 定位"点空白不清高亮"的具体失败场景 (2026-08-02)

场景覆盖:
  A. INIT 高亮数 (期望 0)
  B. 点节点 → .annotation-highlighted > 0
  C. 点 svg 角落空白 → 清除 (已知 PASS)
  D. 点 cluster 内部空白 (cluster 背景 rect, 非节点) → 观察是否高亮 cluster (用户感知"点空白没清除")
  E. 点连线 label → tooltip 高亮 (path strokeWidth 4px + 源/目标节点红描边) → 点空白 → 观察是否清除
  F. 高亮后点空白 → panel .annotation-item-selected 是否清除
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3005'
OUT = Path('test_helpers/scripts/_probe_blank_click2_out')
OUT.mkdir(parents=True, exist_ok=True)

WRAP = """(fn) => Promise.race([ fn(), new Promise((res) => setTimeout(() => res({ timeout: true }), 2500)) ])"""

DUMP_JS = """((WRAP))(() => {
    const out = {}
    const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
    const ns = svgs.find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
    if (!ns) { out.svg = 0; return out }
    out.svg = 1
    const hl = ns.querySelectorAll('.annotation-highlighted')
    out.highlighted = hl.length
    out.highlightedIds = Array.from(hl).slice(0, 3).map(el => ({ id: el.id, cls: el.getAttribute('class') }))
    // tooltip 高亮: 粗描边 path (strokeWidth>2) + 红描边 node rect
    let thickPaths = 0
    ns.querySelectorAll('path').forEach(p => {
        const sw = (p.style.strokeWidth || p.getAttribute('stroke-width') || '').replace('px', '')
        if (parseFloat(sw) > 2) thickPaths++
    })
    out.thickPaths = thickPaths
    let redNodeStrokes = 0
    ns.querySelectorAll('g.node rect, g.node polygon').forEach(r => {
        const st = r.style.stroke || ''
        if (st === '#FF6B6B' || st === 'rgb(255, 107, 107)') redNodeStrokes++
    })
    out.redNodeStrokes = redNodeStrokes
    // panel 选中
    out.panelSelected = document.querySelectorAll('.annotation-item-selected').length
    // svg bbox + 采样点
    const b = ns.getBoundingClientRect()
    out.bbox = { x: b.x, y: b.y, w: b.width, h: b.height }
    return out
})""".replace('(WRAP)', WRAP)


def safe_eval(cli, js):
    try:
        return cli.evaluate(js)
    except Exception as e:
        return f'eval err: {e}'


def dump(cli, tag):
    d = safe_eval(cli, DUMP_JS)
    print(f'[v] {tag}: highlighted={d.get("highlighted")} thickPaths={d.get("thickPaths")} '
          f'redNodeStrokes={d.get("redNodeStrokes")} panelSelected={d.get("panelSelected")}', flush=True)
    if d.get('highlightedIds'):
        print(f'[v]   hl={json.dumps(d["highlightedIds"], ensure_ascii=False)}', flush=True)
    return d


def get_point(cli, js_selector_expr, label):
    """用 JS 表达式计算一个屏幕坐标点"""
    js = f"""((WRAP))(() => {{
        const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
        const ns = svgs.find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
        if (!ns) return {{ err: 'no svg' }}
        const el = {js_selector_expr}
        if (!el) return {{ err: 'no el' }}
        const r = el.getBoundingClientRect()
        return {{ x: r.x + r.width / 2, y: r.y + r.height / 2 }}
    }})""".replace('(WRAP)', WRAP)
    p = safe_eval(cli, js)
    print(f'[v]   {label}: {p}', flush=True)
    return p


def click_at(cli, p, label):
    if isinstance(p, dict) and 'x' in p:
        cli._page.mouse.click(p['x'], p['y'])
        cli.wait_for_timeout(700)
        print(f'[v]   clicked {label} at ({p["x"]:.0f},{p["y"]:.0f})', flush=True)
    else:
        print(f'[v]   skip {label}: {p}', flush=True)


def main():
    with PlaywrightCLI(headless=True) as cli:
        print('[v] 1 dev-login', flush=True)
        cli.goto(f"{BASE}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
        cli.wait_for_timeout(1200)

        print('[v] 2 列表页', flush=True)
        cli.goto(f"{BASE}/system/archdata?productCode=TTTTT000&versionId=863", wait_until="domcontentloaded")
        cli.wait_for_timeout(12000)

        print('[v] 3 展开供应链云 → 勾选供应链计划', flush=True)
        r = safe_eval(cli, """((WRAP))(async () => {
            const sleep = ms => new Promise(r => setTimeout(r, ms));
            const findNode = (text) => Array.from(document.querySelectorAll('.el-tree-node')).find(n => {
                const t = n.querySelector('.oss-node-label, .el-tree-node__label')?.textContent?.trim() || ''
                return t.includes(text)
            })
            const dom = findNode('供应链云')
            if (!dom) return 'no 供应链云'
            const icon = dom.querySelector('.el-tree-node__expand-icon')
            if (icon && !icon.classList.contains('expanded')) { icon.click(); await sleep(1500) }
            const sd = findNode('供应链计划')
            if (!sd) return 'no 供应链计划'
            const cb = sd.querySelector('.el-checkbox input[type=checkbox]')
            if (cb && !cb.checked) cb.click()
            return 'checked 供应链计划'
        })""".replace('(WRAP)', WRAP))
        print(f'[v]   {r}', flush=True)
        cli.wait_for_timeout(8000)

        print('[v] 4 点击 图表展示', flush=True)
        try:
            r = cli.evaluate("""() => {
                const b = Array.from(document.querySelectorAll('.gt-btn-chart-toggle')).find(x => x.textContent.includes('图表展示'))
                if (!b) return 'no btn'
                b.click(); return 'clicked'
            }""", retries=1)
            print(f'[v]   {r}', flush=True)
        except Exception as e:
            print(f'[v]   toggle fail: {e}', flush=True)

        for i in range(30):
            cli.wait_for_timeout(4000)
            n = safe_eval(cli, """((WRAP))(() => Array.from(document.querySelectorAll('.mermaid-container svg')).filter(s => s.querySelectorAll('g.node, g.nodes').length > 0).length)""".replace('(WRAP)', WRAP))
            if n == 1:
                print(f'[v]   poll[{i}] svg=1', flush=True)
                break
        try:
            cli._page.wait_for_function("() => !!(window.__archPage?.mermaid?.lastRender?.endTime)", timeout=180000)
            print('[v]   render done', flush=True)
        except Exception as e:
            print(f'[v]   render wait fail: {e}', flush=True)
        cli.wait_for_timeout(3000)

        results = {}

        print('[v] A INIT', flush=True)
        results['A'] = dump(cli, 'A')

        print('[v] B 点真实节点 g.node[data-code][0]', flush=True)
        p = get_point(cli, "ns.querySelector('g.node[data-code]')", 'real-node0')
        click_at(cli, p, 'real-node0')
        results['B'] = dump(cli, 'B after real node click')

        print('[v] C 点 svg 角落空白', flush=True)
        p = get_point(cli, "ns", 'svg-center')  # 先取 svg bbox
        if isinstance(p, dict) and 'x' in p:
            js = """((WRAP))(() => {
                const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
                const ns = svgs.find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
                const b = ns.getBoundingClientRect()
                return { x: b.x + 5, y: b.y + 5 }
            })""".replace('(WRAP)', WRAP)
            corner = safe_eval(cli, js)
            click_at(cli, corner, 'corner')
        results['C'] = dump(cli, 'C after corner blank')

        print('[v] D 点 cluster 内部空白 (背景 rect, 远离节点)', flush=True)
        # 重新选中一个真实节点做高亮
        p = get_point(cli, "ns.querySelector('g.node[data-code]')", 'real-node0-again')
        click_at(cli, p, 'real-node0-again')
        dump(cli, 'D0 re-highlight')
        # 在 svg 可视范围内找"落在 cluster 背景上的空白点": 遍历 svg 内网格,
        # 找 elementFromPoint 的元素链含 g.cluster 但不含 node/edge/label 的点 (即"点 cluster 背景空白")
        js_blank = """((WRAP))(() => {
            const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
            const ns = svgs.find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
            const b = ns.getBoundingClientRect()
            const clusters = Array.from(ns.querySelectorAll('g.cluster'))
            if (!clusters.length) return { err: 'no cluster' }
            for (let dy = 0.08; dy <= 0.92; dy += 0.04) {
                for (let dx = 0.08; dx <= 0.92; dx += 0.04) {
                    const x = b.x + b.width * dx, y = b.y + b.height * dy
                    const el = document.elementFromPoint(x, y)
                    if (!el) continue
                    let cur = el
                    let inCluster = false, isNode = false, isEdge = false, isLabel = false
                    while (cur && cur !== ns) {
                        if (cur.classList) {
                            if (cur.classList.contains('cluster')) inCluster = true
                            if (cur.classList.contains('node')) isNode = true
                            if (cur.classList.contains('edgeLabel') || cur.classList.contains('edgePath') || cur.classList.contains('flowchart-link')) isEdge = true
                            if (cur.classList.contains('cluster-label')) isLabel = true
                        }
                        cur = cur.parentElement
                    }
                    if (inCluster && !isNode && !isEdge && !isLabel) return { x, y, at: [dx, dy] }
                }
            }
            return { err: 'no blank-in-cluster point found' }
        })""".replace('(WRAP)', WRAP)
        blank = safe_eval(cli, js_blank)
        print(f'[v]   cluster blank point: {blank}', flush=True)
        click_at(cli, blank, 'cluster-blank')
        results['D'] = dump(cli, 'D after cluster blank')

        print('[v] G 点 cluster 标题 → 应选中容器 (正例)', flush=True)
        # 找一个 bbox 中心落在 svg 可视范围内的 cluster-label
        p = get_point(cli, """Array.from(ns.querySelectorAll('g.cluster .cluster-label, g.cluster text')).find(l => {
            const r = l.getBoundingClientRect()
            const b = ns.getBoundingClientRect()
            const cx = r.x + r.width / 2, cy = r.y + r.height / 2
            return cx >= b.x && cx <= b.x + b.width && cy >= b.y && cy <= b.y + b.height
        })""", 'cluster-title-visible')
        click_at(cli, p, 'cluster-title-visible')
        results['G'] = dump(cli, 'G after cluster title click')

        print('[v] E 点连线 label → tooltip 高亮', flush=True)
        p = get_point(cli, "ns.querySelector('.edgeLabel')", 'edgeLabel0')
        click_at(cli, p, 'edgeLabel0')
        results['E1'] = dump(cli, 'E1 after edge click')
        # 点空白
        js_corner = """((WRAP))(() => {
            const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
            const ns = svgs.find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
            const b = ns.getBoundingClientRect()
            return { x: b.x + 5, y: b.y + 5 }
        })""".replace('(WRAP)', WRAP)
        click_at(cli, safe_eval(cli, js_corner), 'corner2')
        results['E2'] = dump(cli, 'E2 after blank (edge highlight cleared?)')

        print()
        print('========== 结论 ==========', flush=True)
        print(f'A. INIT: {results["A"].get("highlighted")} (期望 0)', flush=True)
        print(f'B. 点节点: {results["B"].get("highlighted")} (期望 >0)', flush=True)
        print(f'C. 角落空白: {results["C"].get("highlighted")} (期望 0)', flush=True)
        print(f'D. cluster 内空白: {results["D"].get("highlighted")} (期望 0, 若 >0 = BUG 点空白反而高亮 cluster)', flush=True)
        print(f'G. cluster 标题: {results["G"].get("highlighted")} (期望 >0, 点标题应选中容器)', flush=True)
        print(f'E1. 点连线: thickPaths={results["E1"].get("thickPaths")} redNodeStrokes={results["E1"].get("redNodeStrokes")}', flush=True)
        print(f'E2. 连线后点空白: thickPaths={results["E2"].get("thickPaths")} redNodeStrokes={results["E2"].get("redNodeStrokes")} (期望 0)', flush=True)

        (OUT / 'dump.json').write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        print(f'\n[v] 输出: {OUT}', flush=True)


if __name__ == '__main__':
    main()
