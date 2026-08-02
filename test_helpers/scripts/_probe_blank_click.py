"""
_probe_blank_click.py - 复现"点击画布空白区域不清除高亮"问题 (2026-08-02)

链路: MermaidComponent -> useSvgProcessor.renderAnnotationOverlay -> annotationOverlay.bindAnnotationInteraction
  - 点节点/容器/连线 -> highlightTargetElement (加 .annotation-highlighted + 红色 drop-shadow)
  - 点空白 -> clearAllHighlights (应清掉 .annotation-highlighted)

步骤:
  A. INIT: .annotation-highlighted 计数 (期望 0)
  B. 真鼠标点一个节点中心 -> 计数 (期望 > 0)
  C. 真鼠标点 svg 左上角空白 -> 计数 (期望 0, 复现则 > 0)
  D. 用 evaluate 在 svg 本身上 dispatch click (e.target===svg 的纯空白路径) -> 计数
  E. 用 elementFromPoint 在空白采样点看 e.target 是什么元素 (诊断根因)
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3005'
OUT = Path('test_helpers/scripts/_probe_blank_click_out')
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
    out.highlightedCls = Array.from(hl).slice(0, 3).map(el => {
        const rect = el.querySelector('rect, polygon')
        return { tag: el.tagName, id: el.id, cls: el.getAttribute('class'), filter: rect ? (rect.style.filter || '') : '' }
    })
    // svg bbox
    const b = ns.getBoundingClientRect()
    out.bbox = { x: b.x, y: b.y, w: b.width, h: b.height }
    // 采样点 (相对 svg 左上)
    const pts = [[5, 5], [10, b.height / 2], [b.width / 2, 5], [b.width - 5, b.height - 5], [b.width / 2, b.height / 2]]
    out.samples = pts.map(([dx, dy]) => {
        const x = b.x + dx, y = b.y + dy
        const el = document.elementFromPoint(x, y)
        let chain = []
        let cur = el
        while (cur && cur !== ns && chain.length < 8) {
            chain.push({ tag: cur.tagName, id: (cur.id || '').slice(0, 40), cls: (cur.getAttribute && cur.getAttribute('class')) || '' })
            cur = cur.parentElement
        }
        return { at: [dx, dy], targetTag: el ? el.tagName : null, targetCls: el && el.getAttribute ? (el.getAttribute('class') || '') : '', chain }
    })
    // 节点 bbox 列表 (前 3 个)
    out.nodes = Array.from(ns.querySelectorAll('g.node, g.nodes')).slice(0, 3).map(n => {
        const r = n.getBoundingClientRect()
        return { id: n.id, x: r.x, y: r.y, w: r.width, h: r.height }
    })
    // [诊断] 复制 findTargetFromEvent 的匹配逻辑: 对采样点分类
    //   node 需要 class 含 node 且带 data-code; container 仅 cluster (非 subgraphs/subgraph)
    const classifyTarget = (el) => {
        if (!el) return 'none'
        let cur = el
        while (cur && cur !== ns) {
            if (cur.classList) {
                if (cur.classList.contains('node') && cur.hasAttribute('data-code')) return 'node'
                if (cur.classList.contains('cluster')) return 'container'
                if (cur.classList.contains('edgeLabel')) return 'relation-label'
                if (cur.tagName && cur.tagName.toLowerCase() === 'path' && cur.parentElement && !cur.parentElement.classList.contains('edgeLabel')) return 'relation-path'
            }
            cur = cur.parentElement
        }
        return 'none'
    }
    out.sampleTypes = out.samples.map(s => {
        const el = document.elementFromPoint(s.targetTag ? (out.bbox.x + s.at[0]) : 0, 0)
        return { at: s.at, type: classifyTarget(document.elementFromPoint(out.bbox.x + s.at[0], out.bbox.y + s.at[1])) }
    })
    // 节点 rect 中心点分类 (验证点 node 是否真的命中 node)
    out.nodeTypes = Array.from(ns.querySelectorAll('g.node, g.nodes')).slice(0, 5).map(n => {
        const r = n.getBoundingClientRect()
        const el = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
        return { id: n.id, dataCode: n.getAttribute('data-code'), type: classifyTarget(el), hasDataCodeAttr: n.hasAttribute('data-code') }
    })
    // panel 选中态
    out.panelSelected = Array.from(document.querySelectorAll('.annotation-item-selected')).length
    return out
})""".replace('(WRAP)', WRAP)


def safe_eval(cli, js):
    try:
        return cli.evaluate(js)
    except Exception as e:
        return f'eval err: {e}'


def dump(cli, tag):
    d = safe_eval(cli, DUMP_JS)
    print(f'[v] {tag}: highlighted={d.get("highlighted")}', flush=True)
    if d.get('highlighted'):
        print(f'[v]   hl={json.dumps(d["highlightedCls"], ensure_ascii=False)[:400]}', flush=True)
    if d.get('samples'):
        for s in d['samples']:
            print(f'[v]   sample at {s["at"]}: {s["targetTag"]}.{s["targetCls"][:40]}', flush=True)
    return d


def click_node(cli, idx=0):
    """真鼠标点第 idx 个节点的中心"""
    js = """((WRAP))(() => {
        const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
        const ns = svgs.find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
        const nodes = Array.from(ns.querySelectorAll('g.node, g.nodes'))
        if (!nodes[IDX]) return { err: 'no node' }
        const r = nodes[IDX].getBoundingClientRect()
        return { x: r.x + r.width / 2, y: r.y + r.height / 2, id: nodes[IDX].id }
    })""".replace('(WRAP)', WRAP).replace('IDX', str(idx))
    p = safe_eval(cli, js)
    print(f'[v]   node[{idx}] {p}', flush=True)
    if isinstance(p, dict) and 'x' in p:
        cli._page.mouse.click(p['x'], p['y'])
        cli.wait_for_timeout(600)
    return p


def click_blank_svg_self(cli):
    """直接在 svg 元素上 dispatch click (e.target===svg)"""
    js = """((WRAP))(() => {
        const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
        const ns = svgs.find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
        if (!ns) return 'no svg'
        ns.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }))
        return 'dispatched on svg'
    })""".replace('(WRAP)', WRAP)
    return safe_eval(cli, js)


def click_blank_mouse(cli, dx, dy):
    """真鼠标点 svg 相对左上 (dx, dy) 的位置"""
    js = """((WRAP))(() => {
        const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
        const ns = svgs.find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
        const b = ns.getBoundingClientRect()
        return { x: b.x + DX, y: b.y + DY }
    })""".replace('(WRAP)', WRAP).replace('DX', str(dx)).replace('DY', str(dy))
    p = safe_eval(cli, js)
    print(f'[v]   blank click at svg+({dx},{dy}): {p}', flush=True)
    if isinstance(p, dict) and 'x' in p:
        cli._page.mouse.click(p['x'], p['y'])
        cli.wait_for_timeout(600)
    return p


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
            print(f'[v]   poll[{i}] svg={n}', flush=True)
            if n == 1:
                break
        try:
            cli._page.wait_for_function("() => !!(window.__archPage?.mermaid?.lastRender?.endTime)", timeout=180000)
            print('[v]   render done', flush=True)
        except Exception as e:
            print(f'[v]   render wait fail: {e}', flush=True)
        cli.wait_for_timeout(3000)

        print('[v] A INIT', flush=True)
        s_a = dump(cli, 'A INIT')

        print('[v] B 点节点 → 高亮', flush=True)
        click_node(cli, 0)
        s_b = dump(cli, 'B after node click')

        print('[v] C 真鼠标点 svg 左上 (5,5) 空白', flush=True)
        click_blank_mouse(cli, 5, 5)
        s_c = dump(cli, 'C after blank(5,5)')

        print('[v] D 真鼠标点 svg 右上空白 (w-5,5)', flush=True)
        if isinstance(s_c, dict) and s_c.get('bbox'):
            click_blank_mouse(cli, s_c['bbox']['w'] - 5, 5)
        s_d = dump(cli, 'D after blank(right)')

        print('[v] E svg 自身 dispatch click (纯空白路径)', flush=True)
        click_blank_svg_self(cli)
        s_e = dump(cli, 'E after svg self click')

        print()
        print('========== 结论 ==========', flush=True)
        print(f'A. INIT 高亮数={s_a.get("highlighted")} (期望 0)          : {"PASS" if s_a.get("highlighted") == 0 else "FAIL"}', flush=True)
        print(f'B. 点节点后 高亮数={s_b.get("highlighted")} (期望 >0)     : {"PASS" if (s_b.get("highlighted") or 0) > 0 else "FAIL"}', flush=True)
        print(f'C. 点空白(5,5)后 高亮数={s_c.get("highlighted")} (期望 0) : {"PASS" if s_c.get("highlighted") == 0 else "FAIL"}', flush=True)
        print(f'D. 点空白(右)后 高亮数={s_d.get("highlighted")} (期望 0)  : {"PASS" if s_d.get("highlighted") == 0 else "FAIL"}', flush=True)
        print(f'E. svg 自身 click 后 高亮数={s_e.get("highlighted")} (期望 0): {"PASS" if s_e.get("highlighted") == 0 else "FAIL"}', flush=True)

        (OUT / 'dump.json').write_text(json.dumps({'A': s_a, 'B': s_b, 'C': s_c, 'D': s_d, 'E': s_e}, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        print(f'\n[v] 输出: {OUT}', flush=True)


if __name__ == '__main__':
    main()
