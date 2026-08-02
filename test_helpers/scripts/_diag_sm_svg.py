"""
_diag_sm_svg.py - dump SM 图灰色节点 rect 完整 HTML + SVG style 标签 (2026-08-02)
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
    output_dir = Path('test_helpers/scripts/_diag_sm_svg_out')
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

        # dump 灰色节点 rect HTML + svg style 标签
        info = cli.evaluate("""() => {
            const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
            const svg = svgs.find(s => s.classList.contains('flowchart')) || null
            if (!svg) return { error: 'no svg' }
            const styles = Array.from(svg.querySelectorAll('style')).map(s => s.textContent.slice(0, 3000))
            const nodes = svg.querySelectorAll('g.node')
            const gray = []
            nodes.forEach(g => {
                const rect = g.querySelector('rect')
                const fill = rect ? (rect.getAttribute('fill') || rect.style.fill) : null
                if (fill === 'rgb(128, 128, 128)' || fill === '#808080') {
                    gray.push({
                        gid: g.id || '',
                        code: g.getAttribute('data-code') || '',
                        rectHTML: rect ? rect.outerHTML.slice(0, 600) : null
                    })
                }
            })
            return { styleTags: styles, grayCount: gray.length, gray }
        }""")
        print(f'[v] grayCount={info.get("grayCount")}')
        print('[v] style 标签:')
        for s in info.get('styleTags') or []:
            print(s)
        print('[v] 灰色节点 rect HTML:')
        for g in info.get('gray') or []:
            print(f'  --- {g["gid"]} code={g["code"]}')
            print(f'  {g["rectHTML"]}')

        (output_dir / 'dump.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'[v] dump 保存到 {output_dir}/dump.json')


if __name__ == '__main__':
    main()
