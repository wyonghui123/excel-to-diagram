"""
_diag_bo_switchback.py - 复现 BO 图在 SM 切换回来后切换颜色变灰 (2026-08-02)

假设: 用户可能先切到服务模块图 (SM), 再切回业务对象图 (BO), 之后切换颜色变灰。
shortcut 进入 BO 图直接切颜色已验证全彩。
本脚本: shortcut 进入 BO -> 切 SM -> 切回 BO -> 切换 配色/颜色分组/中心范围, 每步统计。
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
    if (!anchor) return 'no anchor: ' + __SEL__
    const wrapper = anchor.querySelector('.el-select__wrapper') || anchor
    const aRect = wrapper.getBoundingClientRect()
    const ax = aRect.x + aRect.width / 2
    const ay = aRect.y + aRect.height / 2
    const poppers = document.querySelectorAll('body .el-select-dropdown')
    let best = null, bestDist = Infinity
    for (const p of poppers) {
        const rect = p.getBoundingClientRect()
        if (rect.width === 0 || rect.height === 0) continue
        const d = Math.hypot(rect.x + rect.width / 2 - ax, rect.y + rect.height / 2 - ay)
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
    cli.wait_for_timeout(7000)
    return clicked


def get_node_stats(cli):
    return cli.evaluate("""() => {
        const svg = Array.from(document.querySelectorAll('.mermaid-container svg')).find(s => s.classList.contains('flowchart'))
        if (!svg) return { error: 'no flowchart svg' }
        const rects = svg.querySelectorAll('g.node rect, g.nodes rect')
        const fills = {}
        let total = 0, centerBorder = 0, gray = 0
        const samples = []
        rects.forEach((r, i) => {
            const fill = r.getAttribute('fill') || r.style.fill || 'none'
            if (fill === 'none' || fill === 'transparent') return
            fills[fill] = (fills[fill] || 0) + 1
            total++
            const dash = r.style.strokeDasharray || r.getAttribute('stroke-dasharray') || ''
            const sw = (r.style.strokeWidth || r.getAttribute('stroke-width') || '').replace('px', '')
            if (dash.indexOf('6') !== -1 && sw === '3') centerBorder++
            if (fill === '#808080' || fill === 'rgb(128, 128, 128)' || fill === '#fafafa' || fill === 'rgb(250, 250, 250)' || fill === '#EDEDED' || fill === 'rgb(237, 237, 237)' || fill === 'undefined') gray++
            if (i < 2) samples.push(r.outerHTML.slice(0, 280))
        })
        return { total, distinct: Object.keys(fills).length, fills, centerBorder, gray, samples }
    }""")


def main():
    base_url = 'http://localhost:3005'
    output_dir = Path('test_helpers/scripts/_diag_bo_switchback_out')
    output_dir.mkdir(parents=True, exist_ok=True)

    scope = {
        'sub_domain': [299],
        'business_object': [3220, 3218, 3221, 2797, 2788, 2793, 1839, 2896, 3219, 2784,
                            2792, 2781, 2779, 1838, 2780, 2795, 2794, 1637, 2789, 2777,
                            2778, 2782, 2785, 1636, 2796, 2783, 2790, 2791, 2786, 2787]
    }
    scope_b64 = base64.b64encode(json.dumps(scope).encode('utf-8')).decode('ascii')

    with PlaywrightCLI(headless=True) as cli:
        console_msgs = []
        print('[v] Step 1: dev-login')
        cli.goto(f"{base_url}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
        cli.wait_for_timeout(1500)
        cli._page.on('console', lambda msg: console_msgs.append(f'[{msg.type}] {msg.text}'))
        cli._page.on('pageerror', lambda err: console_msgs.append(f'[PAGEERROR] {err}'))

        print('[v] Step 2: shortcut 进入 BO 图')
        url = f"{base_url}/system/archdata?shortcut=1&productCode=TTTTT000&versionId=863&scope={scope_b64}&scopeType=all&viewMode=chart"
        cli.goto(url, wait_until="domcontentloaded")
        cli.wait_for_timeout(20000)

        def dump(tag):
            s = get_node_stats(cli)
            print(f'[v] {tag}: {json.dumps({k: v for k, v in s.items() if k != "samples"}, ensure_ascii=False)}')
            for h in s.get('samples') or []:
                print(f'      {h}')
            return s

        s0 = dump('0 BO INIT')
        cli.screenshot(str(output_dir / '0_bo_init.png'))

        print('[v] Step 3: 图表类型 BO -> SM')
        print(f'[v] {select_option(cli, ".cmt-select:nth-of-type(1)", "服务模块图")}')
        s1 = dump('1 SM')
        cli.screenshot(str(output_dir / '1_sm.png'))

        print('[v] Step 4: 图表类型 SM -> BO')
        print(f'[v] {select_option(cli, ".cmt-select:nth-of-type(1)", "业务对象图")}')
        s2 = dump('2 BO AFTER SWITCH BACK')
        cli.screenshot(str(output_dir / '2_bo_back.png'))

        print('[v] Step 5: 切换配色 默认 -> 鲜艳')
        print(f'[v] {select_option(cli, ".cmt-select:nth-of-type(3)", "鲜艳")}')
        s3 = dump('3 BO vibrant')
        cli.screenshot(str(output_dir / '3_vibrant.png'))

        print('[v] Step 6: 切换颜色分组 按领域 -> 按服务模块')
        print(f'[v] {select_option(cli, ".cmt-select:nth-of-type(2)", "按服务模块")}')
        s4 = dump('4 BO serviceModule')
        cli.screenshot(str(output_dir / '4_group.png'))

        print('[v] Step 7: 切换中心范围 区分 -> 不区分')
        print(f'[v] {select_option(cli, ".cmt-select:nth-of-type(4)", "不区分")}')
        s5 = dump('5 BO centerOff')
        cli.screenshot(str(output_dir / '5_centerOff.png'))

        print()
        print('========== 结论 ==========')
        for tag, s in [('0 INIT', s0), ('1 SM', s1), ('2 BO back', s2), ('3 vibrant', s3), ('4 group', s4), ('5 centerOff', s5)]:
            print(f'{tag}: total={s.get("total")}, distinct={s.get("distinct")}, centerBorder={s.get("centerBorder")}, gray={s.get("gray")}')

        colors = [l for l in console_msgs if 'updateColorsOnly' in l or 'updateNodeColors' in l or '[warn]' in l or '[error]' in l.lower()]
        print(f'\n[v] 颜色/警告 console ({len(colors)} 条):')
        for log in colors[-30:]:
            print(f'  {log[:300]}')

        (output_dir / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')
        print(f'\n[v] 输出保存到 {output_dir}')


if __name__ == '__main__':
    main()
