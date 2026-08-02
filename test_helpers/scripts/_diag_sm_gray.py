"""
_diag_sm_gray.py - dump 服务模块图灰色节点信息 (2026-08-02)

背景: SM 图 6/12 节点 fill=#808080 且切换配色/分组不联动。
     需确认: 灰色节点的 id/code/rect 属性, 以及 __configStore 状态。
"""
import sys
import json
import base64
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI


def select_option(cli, selector, text):
    cli.click(selector, timeout=5000)
    cli.wait_for_timeout(800)
    sel_json = json.dumps(selector)
    text_json = json.dumps(text)
    js = r"""
() => {
    const anchor = document.querySelector(__SEL__)
    if (!anchor) return 'no anchor'
    const wrapper = anchor.querySelector('.el-select__wrapper') || anchor
    const aRect = wrapper.getBoundingClientRect()
    const ax = aRect.x + aRect.width / 2
    const ay = aRect.y + aRect.height / 2
    const poppers = document.querySelectorAll('body .el-select-dropdown')
    let best = null, bestDist = Infinity
    for (const p of poppers) {
        const rect = p.getBoundingClientRect()
        if (rect.width === 0 || rect.height === 0) continue
        const cx = rect.x + rect.width / 2
        const cy = rect.y + rect.height / 2
        const d = Math.hypot(cx - ax, cy - ay)
        if (d < bestDist) { bestDist = d; best = p }
    }
    if (!best) return 'no popper'
    const items = best.querySelectorAll('.el-select-dropdown__item')
    for (const it of items) {
        if (it.textContent.includes(__TEXT__)) {
            it.click()
            return 'clicked: ' + it.textContent.trim()
        }
    }
    return 'not found: ' + __TEXT__
}
""".replace('__SEL__', sel_json).replace('__TEXT__', text_json)
    clicked = cli.evaluate(js)
    cli.wait_for_timeout(6000)
    return clicked


def main():
    base_url = 'http://localhost:3005'
    output_dir = Path('test_helpers/scripts/_diag_sm_gray_out')
    output_dir.mkdir(parents=True, exist_ok=True)

    scope = {
        'sub_domain': [299],
        'business_object': [3220, 3218, 3221, 2797, 2788, 2793, 1839, 2896, 3219, 2784,
                            2792, 2781, 2779, 1838, 2780, 2795, 2794, 1637, 2789, 2777,
                            2778, 2782, 2785, 1636, 2796, 2783, 2790, 2791, 2786, 2787]
    }
    scope_b64 = base64.b64encode(json.dumps(scope).encode('utf-8')).decode('ascii')

    with PlaywrightCLI(headless=True) as cli:
        print('[v] dev-login')
        cli.goto(f"{base_url}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
        cli.wait_for_timeout(1500)

        print('[v] shortcut 进入图表视图')
        url = f"{base_url}/system/archdata?shortcut=1&productCode=TTTTT000&versionId=863&scope={scope_b64}&scopeType=all&viewMode=chart"
        cli.goto(url, wait_until="domcontentloaded")
        cli.wait_for_timeout(20000)

        print('[v] 切到服务模块图')
        print(select_option(cli, '.cmt-select:nth-of-type(1)', '服务模块图'))

        # dump 每个节点的属性
        info = cli.evaluate("""() => {
            const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
            const svg = svgs.find(s => s.classList.contains('flowchart')) || null
            if (!svg) return { error: 'no svg' }
            const nodes = svg.querySelectorAll('g.node')
            const out = []
            nodes.forEach((g, i) => {
                const rect = g.querySelector('rect')
                const labelText = g.querySelector('text, span')
                out.push({
                    i,
                    gid: g.id || g.getAttribute('id'),
                    code: g.getAttribute('data-code') || '',
                    name: g.getAttribute('data-name') || (labelText ? labelText.textContent.trim().slice(0, 30) : ''),
                    fill: rect ? (rect.getAttribute('fill') || rect.style.fill) : null,
                    stroke: rect ? rect.getAttribute('stroke') : null,
                    dash: rect ? rect.getAttribute('stroke-dasharray') : null
                })
            })
            return out
        }""")
        print('[v] SM 图节点 dump:')
        for row in info:
            marker = ' <<<< GRAY' if row.get('fill') in ('rgb(128, 128, 128)', '#808080') else ''
            print(f'  [{row["i"]}] id={row["gid"]} code={row["code"]} name={row["name"]} fill={row["fill"]} stroke={row["stroke"]} dash={row["dash"]}{marker}')

        # store 状态
        store = cli.evaluate("""() => {
            const cs = window.__configStore
            if (!cs) return { error: 'no __configStore' }
            const g = (k) => { try { const v = cs[k]; return v && v.value !== undefined ? v.value : v } catch(e) { return 'ERR' } }
            return {
                chartType: g('chartType'),
                colorGroupBy: g('colorGroupBy'),
                colorScheme: g('colorScheme'),
                centerScopeHighlight: g('centerScopeHighlight'),
                centerScopeColor: g('centerScopeColor'),
                centerScopeLen: (g('centerScope') || []).length,
                centerScope: g('centerScope')
            }
        }""")
        print(f'[v] store: {json.dumps(store, ensure_ascii=False)}')

        cli.screenshot(str(output_dir / 'sm_gray.png'))
        print(f'[v] 截图保存到 {output_dir}')


if __name__ == '__main__':
    main()
