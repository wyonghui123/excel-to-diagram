"""
_diag_css_probe.py - 探针: 定位 UI 切色后覆盖 rect 内联 fill 的 CSS 规则

流程: 手动路径 (供应链云/供应链计划 子领域) → 图表展示 → UI 切 鲜艳 → 分析首个节点 rect:
  1. 外层容器 class (.mermaid-content.businessObject ? serviceModule ?)
  2. rect 的 attr fill / 内联 style fill (含 priority) / computedStyle fill
  3. 所有匹配 rect 且声明 fill 的 CSS 规则 (selector + important)
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3005'
OUT = Path('test_helpers/scripts/_diag_css_probe_out')
OUT.mkdir(parents=True, exist_ok=True)

WRAP = """(fn) => Promise.race([ fn(), new Promise((res) => setTimeout(() => res({ timeout: true }), 2500)) ])"""

PROBE_JS = """((WRAP))(() => {
    const out = {}
    // 1. 容器 class
    const content = document.querySelector('.mermaid-content')
    if (content) out.contentClass = content.className.slice(0, 160)
    const svg = Array.from(document.querySelectorAll('.mermaid-container svg')).find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
    if (!svg) { out.svg = 0; return out }
    out.svg = 1
    out.svgClass = (svg.getAttribute('class') || '').slice(0, 160)
    const rect = svg.querySelector('g.node rect, g.nodes rect')
    if (!rect) { out.rect = 0; return out }
    out.rect = 1
    out.rectHtml = rect.outerHTML.slice(0, 340)
    out.fillAttr = rect.getAttribute('fill')
    out.inlineFill = rect.style.fill
    out.inlinePriority = rect.style.getPropertyPriority('fill')
    out.computedFill = getComputedStyle(rect).fill
    // g.node 父级继承源
    const g = rect.closest('g.node') || rect.closest('g.nodes')
    if (g) {
        out.nodeClass = g.getAttribute('class')
        out.nodeFillAttr = g.getAttribute('fill')
        out.nodeInlineFill = g.style.fill
        out.nodeComputedFill = getComputedStyle(g).fill
    }
    // 2. 匹配 rect 且声明 fill 的 CSS 规则
    const matching = []
    const seen = new Set()
    for (const sheet of document.styleSheets) {
        let rules
        try { rules = sheet.cssRules } catch (e) { continue }
        const walk = (rs) => {
            for (const r of rs) {
                if (r.cssRules) { walk(r.cssRules); continue }
                if (r.selectorText && r.style) {
                    let prop = null, imp = ''
                    try { prop = r.style.getPropertyValue('fill') } catch (e) {}
                    if (prop) {
                        try { imp = r.style.getPropertyPriority('fill') } catch (e) {}
                        if (rect.matches(r.selectorText)) {
                            const key = r.selectorText + '|' + prop + '|' + imp
                            if (!seen.has(key)) {
                                seen.add(key)
                                matching.push({ sel: r.selectorText.slice(0, 130), fill: prop.slice(0, 40), imp })
                            }
                        }
                    }
                }
            }
        }
        try { walk(rules) } catch (e) {}
    }
    out.matchingRules = matching.slice(0, 20)
    return out
})""".replace('(WRAP)', WRAP)


def safe_eval(cli, js):
    try:
        return cli.evaluate_async(js, timeout=10000)
    except Exception as e:
        return {'pyErr': f'{type(e).__name__}: {str(e)[:150]}'}


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

        print('[v] 5 INIT 探针', flush=True)
        p0 = safe_eval(cli, PROBE_JS)
        print(json.dumps(p0, ensure_ascii=False, indent=2)[:2600], flush=True)

        print('[v] 6 UI 切 鲜艳', flush=True)
        ui_js = """((WRAP))(async () => {
            const sleep = ms => new Promise(r => setTimeout(r, ms));
            const selects = Array.from(document.querySelectorAll('.cmt-select'))
            const sel = selects[2]
            if (!sel) return 'no select'
            const wrap = sel.querySelector('.el-select__wrapper') || sel
            wrap.click()
            await sleep(500)
            const dds = Array.from(document.querySelectorAll('.el-select-dropdown')).filter(d => {
                const st = getComputedStyle(d)
                return st.display !== 'none' && st.visibility !== 'hidden' && d.offsetParent !== null
            })
            const dd = dds[dds.length - 1]
            const items = Array.from(dd.querySelectorAll('.el-select-dropdown__item'))
            const target = items.find(i => (i.textContent || '').trim().includes('鲜艳'))
            if (!target) return 'no item'
            target.click()
            await sleep(600)
            return 'selected 鲜艳'
        })""".replace('(WRAP)', WRAP)
        print(f'[v]   {safe_eval(cli, ui_js)}', flush=True)
        cli.wait_for_timeout(9000)

        print('[v] 7 切色后探针', flush=True)
        p1 = safe_eval(cli, PROBE_JS)
        print(json.dumps(p1, ensure_ascii=False, indent=2)[:3000], flush=True)

        (OUT / 'probe_init.json').write_text(json.dumps(p0, ensure_ascii=False, indent=2), encoding='utf-8')
        (OUT / 'probe_after_switch.json').write_text(json.dumps(p1, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\n[v] 输出: {OUT}', flush=True)


if __name__ == '__main__':
    main()
