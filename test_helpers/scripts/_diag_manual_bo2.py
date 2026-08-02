"""
_diag_manual_bo2.py - 手动入口 BO 图变灰问题真实复现 (2026-08-02 v2)

用户反馈: 业务对象图除了初始有颜色, 切换任何颜色选项后节点变灰, 连线颜色正确。

完整模拟用户手动操作: 勾选 scope 树 -> 点"图表展示" -> 初始统计 ->
方式A(点击 ChartMiniToolbar 下拉) / 方式B(console 改 __configStore) 切换颜色, 逐步统计。
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI


def select_option(cli, index, text):
    # index: 0=图表类型 1=颜色分组 2=配色 3=中心范围 4=备注类型
    js_prep = f"""() => {{
        const els = document.querySelectorAll('.cmt-select')
        if (!els[{index}]) return 'no cmt-select #' + {index} + ' (total=' + els.length + ')'
        els[{index}].scrollIntoView({{ block: 'center' }})
        els[{index}].querySelector('.el-select__wrapper')?.click()
        return 'opened'
    }}"""
    try:
        opened = cli.evaluate(js_prep)
        cli.wait_for_timeout(800)
    except Exception as e:
        return f'open fail: {e}'
    text_json = json.dumps(text)
    js = r"""
() => {
    const els = document.querySelectorAll('.cmt-select')
    const anchor = els[__IDX__]
    if (!anchor) return 'no cmt-select #' + __IDX__
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
""".replace('__IDX__', str(index)).replace('__TEXT__', text_json)
    clicked = cli.evaluate(js)
    cli.wait_for_timeout(6000)
    return clicked


def get_node_stats(cli):
    return cli.evaluate("""() => {
        const svg = Array.from(document.querySelectorAll('.mermaid-container svg'))
            .find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
        if (!svg) {
            const all = Array.from(document.querySelectorAll('.mermaid-container svg')).map(s =>
                ({ cls: s.getAttribute('class') || '', type: s.getAttribute('data-type') || '', id: s.id || '' }))
            return { error: 'no node svg', allSvg: all.slice(0, 8) }
        }
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
            if (['#808080', 'rgb(128, 128, 128)', '#fafafa', 'rgb(250, 250, 250)', '#EDEDED', 'rgb(237, 237, 237)'].includes(fill)) gray++
            if (i < 2) samples.push(r.outerHTML.slice(0, 400))
        })
        const links = svg.querySelectorAll('.flowchart-link path, .edgePaths > path, .edgePath path')
        const linkColors = {}
        links.forEach(p => {
            const c = p.getAttribute('stroke') || p.style.stroke || ''
            if (c) linkColors[c] = (linkColors[c] || 0) + 1
        })
        return { total, distinct: Object.keys(fills).length, fills, centerBorder, gray, linkColors, samples }
    }""")


def safe_screenshot(cli, path):
    try:
        cli.screenshot(path)
        return True
    except Exception as e:
        print(f'      [screenshot fail] {e}')
        return False


def main():
    base_url = 'http://localhost:3005'
    output_dir = Path('test_helpers/scripts/_diag_manual_bo2_out')
    output_dir.mkdir(parents=True, exist_ok=True)

    with PlaywrightCLI(headless=True) as cli:
        console_msgs = []
        print('[v] Step 1: dev-login')
        cli.goto(f"{base_url}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
        cli.wait_for_timeout(1500)
        cli._page.on('console', lambda msg: console_msgs.append(f'[{msg.type}] {msg.text}'))
        cli._page.on('pageerror', lambda err: console_msgs.append(f'[PAGEERROR] {err}'))

        print('[v] Step 2: 进入列表页 (手动入口, 无 shortcut)')
        url = f"{base_url}/system/archdata?productCode=TTTTT000&versionId=863"
        cli.goto(url, wait_until="domcontentloaded")
        cli.wait_for_timeout(18000)

        info = cli.evaluate("""() => ({
            scopeTreeCheckboxes: document.querySelectorAll('.el-tree .el-checkbox').length,
            chartToggle: document.querySelectorAll('.gt-btn-chart-toggle').length,
            cmtSelects: document.querySelectorAll('.cmt-select').length,
            svgCount: document.querySelectorAll('.mermaid-container svg').length,
            toggleDisabled: (document.querySelector('.gt-btn-chart-toggle')?.disabled) || false,
            toggleClass: document.querySelector('.gt-btn-chart-toggle')?.className || ''
        })""")
        print(f'[v] list state: {json.dumps(info, ensure_ascii=False)}')

        print('[v] Step 3: 勾选对象范围 (点击树中 checkbox, 打印 label)')
        checked = cli.evaluate("""() => {
            const cbs = document.querySelectorAll('.el-tree .el-checkbox')
            if (cbs.length === 0) return 'no checkbox'
            const labels = Array.from(cbs).map((cb, i) => {
                const label = cb.closest('.el-tree-node__content')?.querySelector('.oss-node-label, .el-tree-node__label')
                return (label ? label.textContent.trim() : '?') + '(' + (cb.querySelector('input')?.checked ? 'chk' : 'un') + ')'
            })
            for (const cb of cbs) {
                const input = cb.querySelector('input[type=checkbox]')
                if (input && !input.checked) {
                    cb.click()
                    return 'clicked #' + Array.from(cbs).indexOf(cb) + ' labels=[' + labels.join(', ') + ']'
                }
            }
            return 'all checked: ' + labels.join(', ')
        }""")
        print(f'[v] {checked}')
        cli.wait_for_timeout(12000)

        state2 = cli.evaluate("""() => ({
            checkedCount: document.querySelectorAll('.el-tree .el-checkbox input:checked').length,
            toggleDisabled: (document.querySelector('.gt-btn-chart-toggle')?.disabled) || false,
            badge: document.querySelector('.rst-panel-object .collapse-badge, .rst-panel-object .el-badge__content')?.textContent || '',
            toast: document.querySelector('.el-message')?.textContent || ''
        })""")
        print(f'[v] after check: {json.dumps(state2, ensure_ascii=False)}')

        print('[v] Step 4: 点击 图表展示 按钮')
        clicked = cli.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('.gt-btn-chart-toggle'))
            const btn = btns.find(b => b.textContent.includes('图表展示'))
            if (!btn) return 'no chart toggle btn'
            if (btn.disabled) return 'toggle disabled (scope?)'
            btn.click()
            return 'clicked'
        }""")
        print(f'[v] {clicked}')

        # 轮询 svg 出现 (最多 90s)
        svg_found = False
        for i in range(18):
            cli.wait_for_timeout(5000)
            st = cli.evaluate("""() => ({
                svg: Array.from(document.querySelectorAll('.mermaid-container svg'))
                       .filter(s => s.querySelectorAll('g.node, g.nodes').length > 0).length,
                loading: !!document.querySelector('.embedded-chart-view__loading'),
                error: document.querySelector('.embedded-chart-view__error')?.textContent || '',
                empty: document.querySelector('.embedded-chart-view__empty')?.textContent || '',
                viewMode: document.querySelector('.momp-chart-mode') ? 'chart' : 'list',
                cmt: document.querySelectorAll('.cmt-select').length
            })""")
            print(f'[v]   poll[{i}] {json.dumps(st, ensure_ascii=False)}')
            if st.get('svg') and st['svg'] > 0:
                svg_found = True
                break
            if st.get('error'):
                print(f'[v]   ERROR: {st["error"]}')
                break
        if not svg_found:
            print('[v] !!! 图表未渲染, 停止')
            (output_dir / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')
            return
        cli.wait_for_timeout(6000)

        def dump(tag):
            s = get_node_stats(cli)
            print(f'[v] {tag}: {json.dumps({k: v for k, v in s.items() if k != "samples"}, ensure_ascii=False)}')
            for h in s.get('samples') or []:
                print(f'      {h}')
            return s

        s0 = dump('0 BO INIT (manual)')
        safe_screenshot(cli, str(output_dir / '0_init.png'))

        print('[v] Step 5 (方式A): ChartMiniToolbar 切配色 默认 -> 鲜艳')
        print(f'[v] {select_option(cli, 2, "鲜艳")}')
        s1 = dump('1 A-vibrant')
        safe_screenshot(cli, str(output_dir / '1_A_vibrant.png'))

        print('[v] Step 6 (方式A): 切颜色分组 按领域 -> 按服务模块')
        print(f'[v] {select_option(cli, 1, "按服务模块")}')
        s2 = dump('2 A-serviceModule')
        safe_screenshot(cli, str(output_dir / '2_A_group.png'))

        print('[v] Step 7 (方式A): 切中心范围 区分 -> 不区分')
        print(f'[v] {select_option(cli, 3, "不区分")}')
        s3 = dump('3 A-centerOff')
        safe_screenshot(cli, str(output_dir / '3_A_centerOff.png'))

        print('[v] Step 8 (方式B): console 改 __configStore.colorScheme = vibrant')
        r = cli.evaluate("() => { window.__configStore.colorScheme = 'vibrant'; return 'now=' + window.__configStore.colorScheme }")
        print(f'[v] {r}')
        cli.wait_for_timeout(8000)
        s4 = dump('4 B-store-vibrant')
        safe_screenshot(cli, str(output_dir / '4_B_store_vibrant.png'))

        print('[v] Step 9 (方式B): console 改 __configStore.colorGroupBy = serviceModule')
        print(f'[v] {cli.evaluate("() => { window.__configStore.colorGroupBy = \'serviceModule\'; return \'set\' }")}')
        cli.wait_for_timeout(8000)
        s5 = dump('5 B-store-serviceModule')
        safe_screenshot(cli, str(output_dir / '5_B_store_group.png'))

        print('[v] Step 10 (方式B): console 改 __configStore.centerScopeHighlight = false')
        print(f'[v] {cli.evaluate("() => { window.__configStore.centerScopeHighlight = false; return \'set\' }")}')
        cli.wait_for_timeout(8000)
        s6 = dump('6 B-store-centerOff')
        safe_screenshot(cli, str(output_dir / '6_B_store_centerOff.png'))

        print()
        print('========== 结论 ==========')
        for tag, s in [('INIT', s0), ('A-vibrant', s1), ('A-serviceModule', s2), ('A-centerOff', s3),
                       ('B-store-vibrant', s4), ('B-store-serviceModule', s5), ('B-store-centerOff', s6)]:
            print(f'{tag}: total={s.get("total")}, distinct={s.get("distinct")}, '
                  f'centerBorder={s.get("centerBorder")}, gray={s.get("gray")}, '
                  f'linkColors={s.get("linkColors")}')

        keys = ['updateColorsOnly', 'updateNodeColors', 'renderMermaid', 'warn', 'error',
                'colorGroupBy', 'colorScheme', 'buildColorMap']
        colors = [l for l in console_msgs if any(k in l for k in keys)]
        print(f'\n[v] 关键 console ({len(colors)} 条, 显示最后 40 条):')
        for log in colors[-40:]:
            print(f'  {log[:400]}')

        (output_dir / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')
        print(f'\n[v] 输出保存到 {output_dir}')


if __name__ == '__main__':
    main()
