"""
_diag_node_colors.py - 逐节点追踪切换颜色分组/配色/中心范围前后的 fill 变化

重现用户场景: shortcut 进入图表视图 (不带 scope), 读取每个 g.node 的
data-code + fill, 切换 toolbar 选择后再读取, 对比哪些节点变灰/变浅。
"""
import sys
import json
import base64
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

DIAG_LOG = Path('test_helpers/scripts/_diag_node_colors_out/full.log')


def log(*args):
    line = ' '.join(str(a) for a in args)
    print(line)
    with DIAG_LOG.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


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
    let best = null
    let bestDist = Infinity
    for (const p of poppers) {
        const rect = p.getBoundingClientRect()
        if (rect.width === 0 || rect.height === 0) continue
        const cx = rect.x + rect.width / 2
        const cy = rect.y + rect.height / 2
        const d = Math.hypot(cx - ax, cy - ay)
        if (d < bestDist) { bestDist = d; best = p }
    }
    if (!best) return 'no visible popper near ' + __SEL__
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


def get_node_colors(cli):
    """每个 g.node 的 data-code + fill"""
    return cli.evaluate("""() => {
        const svg = document.querySelector('.mermaid-container svg.flowchart')
        if (!svg) return { error: 'no flowchart svg' }
        const nodes = {}
        svg.querySelectorAll('g.node').forEach(n => {
            const code = n.getAttribute('data-code') || n.querySelector('[data-code]')?.getAttribute('data-code') || n.id
            const rect = n.querySelector('rect')
            const fill = rect ? (rect.getAttribute('fill') || rect.style.fill || 'none') : 'no-rect'
            nodes[code] = fill
        })
        return { count: Object.keys(nodes).length, nodes }
    }""")


def get_store(cli):
    return cli.evaluate("""() => {
        const cs = window.__configStore
        if (!cs) return { error: 'no __configStore' }
        return {
            chartType: cs.chartType?.value ?? cs.chartType,
            colorGroupBy: cs.colorGroupBy?.value ?? cs.colorGroupBy,
            colorScheme: cs.colorScheme?.value ?? cs.colorScheme,
            centerScopeHighlight: cs.centerScopeHighlight?.value ?? cs.centerScopeHighlight,
            centerScopeLen: (cs.centerScope?.value ?? cs.centerScope ?? []).length
        }
    }""")


def main():
    base_url = 'http://localhost:3005'
    out = Path('test_helpers/scripts/_diag_node_colors_out')
    out.mkdir(parents=True, exist_ok=True)

    # 带 scope (与 _verify_color_switch.py 相同), 模拟用户选择中心范围后进入
    scope = {
        'sub_domain': [299],
        'business_object': [3220, 3218, 3221, 2797, 2788, 2793, 1839, 2896, 3219, 2784,
                            2792, 2781, 2779, 1838, 2780, 2795, 2794, 1637, 2789, 2777,
                            2778, 2782, 2785, 1636, 2796, 2783, 2790, 2791, 2786, 2787]
    }
    scope_b64 = base64.b64encode(json.dumps(scope).encode('utf-8')).decode('ascii')
    url = f"{base_url}/system/archdata?shortcut=1&productCode=TTTTT000&versionId=863&scope={scope_b64}&scopeType=all&viewMode=chart"

    with PlaywrightCLI(headless=True) as cli:
        console_msgs = []
        cli.goto(f"{base_url}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
        cli.wait_for_timeout(1500)
        cli._page.on('console', lambda msg: console_msgs.append(f'[{msg.type}] {msg.text}'))
        cli._page.on('pageerror', lambda err: console_msgs.append(f'[PAGEERROR] {err}'))

        cli.goto(url, wait_until="domcontentloaded")
        cli.wait_for_timeout(20000)

        # ============ 1. 初始 (centerScopeHighlight 默认) ============
        st = get_store(cli)
        before = get_node_colors(cli)
        log(f'[diag] store: {json.dumps(st, ensure_ascii=False)}')
        log(f'[diag] BEFORE ({before.get("count")}): {json.dumps(before.get("nodes", {}), ensure_ascii=False)}')
        cli.screenshot(str(out / 'before.png'))

        # ============ 2. 中心范围 -> 不区分 (先确认全彩) ============
        log('\n[diag] === 中心范围 -> 不区分 ===')
        log(f'[diag] {select_option(cli, ".cmt-select:nth-of-type(4)", "不区分")}')
        st_off = get_store(cli)
        after_off = get_node_colors(cli)
        log(f'[diag] store: {json.dumps(st_off, ensure_ascii=False)}')
        log(f'[diag] AFTER centerOff ({after_off.get("count")}): {json.dumps(after_off.get("nodes", {}), ensure_ascii=False)}')
        cli.screenshot(str(out / 'center_off.png'))

        # ============ 3. 切 颜色分组 -> subDomain (全彩态下) ============
        log('\n[diag] === 全彩态下切 颜色分组 -> subDomain ===')
        log(f'[diag] {select_option(cli, ".cmt-select:nth-of-type(2)", "按子领域")}')
        st1 = get_store(cli)
        after_sub = get_node_colors(cli)
        log(f'[diag] store: {json.dumps(st1, ensure_ascii=False)}')
        log(f'[diag] AFTER subDomain ({after_sub.get("count")}): {json.dumps(after_sub.get("nodes", {}), ensure_ascii=False)}')
        cli.screenshot(str(out / 'center_off_sub.png'))

        # ============ 4. 切 配色 -> vibrant ============
        log('\n[diag] === 配色 -> vibrant ===')
        log(f'[diag] {select_option(cli, ".cmt-select:nth-of-type(3)", "鲜艳")}')
        st2 = get_store(cli)
        after_vib = get_node_colors(cli)
        log(f'[diag] store: {json.dumps(st2, ensure_ascii=False)}')
        log(f'[diag] AFTER vibrant ({after_vib.get("count")}): {json.dumps(after_vib.get("nodes", {}), ensure_ascii=False)}')
        cli.screenshot(str(out / 'center_off_vibrant.png'))

        # ============ 5. 中心范围 -> 区分 (恢复) ============
        log('\n[diag] === 中心范围 -> 区分 ===')
        log(f'[diag] {select_option(cli, ".cmt-select:nth-of-type(4)", "区分")}')
        st3 = get_store(cli)
        after_on = get_node_colors(cli)
        log(f'[diag] store: {json.dumps(st3, ensure_ascii=False)}')
        log(f'[diag] AFTER centerOn ({after_on.get("count")}): {json.dumps(after_on.get("nodes", {}), ensure_ascii=False)}')
        cli.screenshot(str(out / 'center_on.png'))

        errors = [l for l in console_msgs if '[error]' in l.lower() or '[pageerror]' in l.lower()]
        log(f'\n[diag] console errors ({len(errors)} 条):')
        for l in errors[-15:]:
            log(f'  {l[:400]}')
        (out / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')
        log(f'[diag] 输出保存到 {out}')


if __name__ == '__main__':
    main()
