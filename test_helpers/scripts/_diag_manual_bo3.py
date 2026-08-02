"""
_diag_manual_bo3.py - BO 图手动入口变灰复现 (精简健壮版, 2026-08-02)

目标: 完整模拟用户手动操作 (勾选 scope -> 图表展示 -> 切换颜色),
逐步 dump SVG 节点 fill, 对比初始 vs 切换后, 定位"切换后节点变灰"根因。

用 `python -u` 运行以获得实时输出。
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3005'
OUT = Path('test_helpers/scripts/_diag_manual_bo3_out')
OUT.mkdir(parents=True, exist_ok=True)

DUMP_JS = """() => {
    const result = { err: null }
    const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
    const nodeSvg = svgs.find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
    if (!nodeSvg) {
        result.err = 'no node svg'
        result.svgCount = svgs.length
        result.svgClasses = svgs.slice(0, 5).map(s => s.getAttribute('class') || '')
        return result
    }
    result.svgCount = svgs.length
    result.svgClass = (nodeSvg.getAttribute('class') || '').slice(0, 200)
    const rects = nodeSvg.querySelectorAll('g.node rect, g.nodes rect')
    const fills = {}
    let centerBorder = 0, gray = 0, noFill = 0
    rects.forEach(r => {
        const fill = r.getAttribute('fill') || ''
        if (!fill) { noFill++; return }
        fills[fill] = (fills[fill] || 0) + 1
        if (['#808080', 'rgb(128, 128, 128)', '#fafafa', 'rgb(250, 250, 250)', '#EDEDED', 'rgb(237, 237, 237)'].includes(fill)) gray++
        const dash = (r.style.strokeDasharray || r.getAttribute('stroke-dasharray') || '').toString()
        const sw = (r.style.strokeWidth || r.getAttribute('stroke-width') || '').toString().replace('px', '')
        if (dash.indexOf('6') !== -1 && sw === '3') centerBorder++
    })
    const links = nodeSvg.querySelectorAll('.flowchart-link path, .edgePaths > path, .edgePath path')
    const linkColors = {}
    links.forEach(p => {
        const c = p.getAttribute('stroke') || p.style.stroke || ''
        if (c) linkColors[c] = (linkColors[c] || 0) + 1
    })
    // 第一个带 fill 的节点 rect 详情 (attribute vs style)
    let firstRect = null
    for (const r of rects) {
        if (r.getAttribute('fill')) { firstRect = r; break }
    }
    result.rectTotal = rects.length
    result.fills = fills
    result.distinct = Object.keys(fills).length
    result.gray = gray
    result.noFill = noFill
    result.centerBorder = centerBorder
    result.linkColors = linkColors
    result.firstRectAttr = firstRect ? (firstRect.getAttribute('fill') + ' | stroke=' + firstRect.getAttribute('stroke')) : null
    result.firstRectStyle = firstRect ? (firstRect.getAttribute('style') || '').slice(0, 300) : null
    const code = window.__lastMermaidCode
    if (code) {
        const c = typeof code === 'string' ? code : JSON.stringify(code)
        result.mermaidHead = c.slice(0, 400)
        result.mermaidStyleCount = (c.match(/style |classDef /g) || []).length
    }
    return result
}"""


def dump(cli, tag):
    try:
        s = cli.evaluate(DUMP_JS)
        print(f'[v] {tag}: ' + json.dumps({k: v for k, v in s.items() if k not in ('mermaidHead',)}, ensure_ascii=False)[:1500], flush=True)
        if s.get('mermaidHead'):
            print(f'[v]   mermaidHead: {s["mermaidHead"][:300]}', flush=True)
        return s
    except Exception as e:
        print(f'[v] {tag}: dump fail: {e}', flush=True)
        return {}


def snap(cli, name):
    try:
        cli.screenshot(str(OUT / name))
        print(f'[v]   screenshot {name} ok', flush=True)
    except Exception as e:
        print(f'[v]   screenshot {name} fail: {e}', flush=True)


def main():
    console_msgs = []
    with PlaywrightCLI(headless=True) as cli:
        def on_console(msg):
            if msg.type in ('error', 'warning'):
                console_msgs.append(f'[{msg.type}] {msg.text[:300]}')
        def on_pageerror(err):
            console_msgs.append(f'[PAGEERROR] {str(err)[:300]}')

        print('[v] Step 1: dev-login', flush=True)
        cli.goto(f"{BASE}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
        cli.wait_for_timeout(1500)
        cli._page.on('console', on_console)
        cli._page.on('pageerror', on_pageerror)

        print('[v] Step 2: 列表页 (手动入口, 无 shortcut)', flush=True)
        cli.goto(f"{BASE}/system/archdata?productCode=TTTTT000&versionId=863", wait_until="domcontentloaded")
        cli.wait_for_timeout(15000)
        try:
            info = cli.evaluate("""() => ({
                treeCbs: document.querySelectorAll('.el-tree .el-checkbox').length,
                toggle: document.querySelectorAll('.gt-btn-chart-toggle').length,
                cmt: document.querySelectorAll('.cmt-select').length,
                svg: document.querySelectorAll('.mermaid-container svg').length,
                toggleDisabled: !!document.querySelector('.gt-btn-chart-toggle')?.disabled
            })""")
            print(f'[v]   list: {json.dumps(info, ensure_ascii=False)}', flush=True)
        except Exception as e:
            print(f'[v]   list state fail: {e}', flush=True)

        print('[v] Step 3: 勾选 scope 树', flush=True)
        try:
            checked = cli.evaluate("""() => {
                const cbs = Array.from(document.querySelectorAll('.el-tree .el-checkbox'))
                if (!cbs.length) return 'no tree checkbox'
                // 优先找叶子节点 (无下级展开箭头的), 避免勾选父节点级联几百个
                const target = cbs.find(cb => !cb.closest('.el-tree-node')?.querySelector('.el-tree-node__expand-icon.is-expandable')) || cbs[0]
                const label = target.closest('.el-tree-node__content')?.querySelector('.oss-node-label, .el-tree-node__label')?.textContent?.trim() || '?'
                if (!target.querySelector('input[type=checkbox]')?.checked) {
                    target.click()
                }
                return 'clicked: ' + label
            }""")
            print(f'[v]   {checked}', flush=True)
        except Exception as e:
            print(f'[v]   check fail: {e}', flush=True)
        cli.wait_for_timeout(10000)

        print('[v] Step 4: 点击 图表展示', flush=True)
        try:
            r = cli.evaluate("""() => {
                const btn = Array.from(document.querySelectorAll('.gt-btn-chart-toggle'))
                    .find(b => b.textContent.includes('图表展示'))
                if (!btn) return 'no toggle btn'
                if (btn.disabled) return 'toggle disabled'
                btn.click()
                return 'clicked'
            }""")
            print(f'[v]   {r}', flush=True)
        except Exception as e:
            print(f'[v]   toggle fail: {e}', flush=True)

        svg_found = False
        for i in range(12):
            cli.wait_for_timeout(5000)
            try:
                n = cli.evaluate("""() => Array.from(document.querySelectorAll('.mermaid-container svg'))
                    .filter(s => s.querySelectorAll('g.node, g.nodes').length > 0).length""")
            except Exception as e:
                n = f'err {e}'
            print(f'[v]   poll[{i}] nodeSvg={n}', flush=True)
            if n == 1:
                svg_found = True
                break
        if not svg_found:
            print('[v] !!! 图表未渲染', flush=True)
            (OUT / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')
            return
        cli.wait_for_timeout(4000)

        s0 = dump(cli, '0 INIT')
        snap(cli, '0_init.png')

        def set_store(cli, key, val):
            js = f"() => {{ const s = window.__configStore; if (!s) return 'no store'; const before = JSON.stringify({{cs: s.colorScheme, gb: s.colorGroupBy, csh: s.centerScopeHighlight}}); s.{key} = {json.dumps(val)}; return 'before=' + before }}"
            try:
                print(f'[v]   set {key}={val} -> ' + str(cli.evaluate(js)), flush=True)
            except Exception as e:
                print(f'[v]   set {key} fail: {e}', flush=True)
            cli.wait_for_timeout(6000)

        print('[v] Step 5: 切配色 default -> vibrant', flush=True)
        set_store(cli, 'colorScheme', 'vibrant')
        s1 = dump(cli, '1 scheme-vibrant')
        snap(cli, '1_scheme_vibrant.png')

        print('[v] Step 6: 切颜色分组 domain -> serviceModule', flush=True)
        set_store(cli, 'colorGroupBy', 'serviceModule')
        s2 = dump(cli, '2 group-serviceModule')
        snap(cli, '2_group_serviceModule.png')

        print('[v] Step 7: 切中心范围 on -> off', flush=True)
        set_store(cli, 'centerScopeHighlight', False)
        s3 = dump(cli, '3 centerOff')
        snap(cli, '3_centerOff.png')

        print()
        print('========== 结论 ==========', flush=True)
        for tag, s in [('INIT', s0), ('scheme-vibrant', s1), ('group-serviceModule', s2), ('centerOff', s3)]:
            if s:
                print(f'{tag}: total={s.get("rectTotal")} distinct={s.get("distinct")} gray={s.get("gray")} '
                      f'noFill={s.get("noFill")} centerBorder={s.get("centerBorder")} '
                      f'links={s.get("linkColors")}', flush=True)

        keys = ['updateColorsOnly', 'updateNodeColors', 'renderMermaid', 'buildColorMap', 'warn', 'error']
        filt = [l for l in console_msgs if any(k in l for k in keys)]
        print(f'\n[v] 关键 console ({len(filt)} 条, 最后 30 条):', flush=True)
        for log in filt[-30:]:
            print(f'  {log[:300]}', flush=True)

        (OUT / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')
        print(f'\n[v] 输出: {OUT}', flush=True)


if __name__ == '__main__':
    main()
