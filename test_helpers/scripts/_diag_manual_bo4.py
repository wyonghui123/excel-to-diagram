"""
_diag_manual_bo4.py - 极简探针: BO 图手动入口切色变灰 (2026-08-02 v4)

只做: 进页面 -> 勾选叶子 BO -> 图表展示 -> 等 SVG ->
最小 fill 统计 -> 切 colorScheme -> 再统计。不截图, 极简 evaluate。
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3005'

MINI_JS = """() => {
    const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
    const ns = svgs.find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
    if (!ns) return { svg: 0, nSvg: svgs.length, cls: svgs.slice(0,3).map(s=>s.getAttribute('class')||'') }
    const rects = ns.querySelectorAll('g.node rect, g.nodes rect')
    const fills = {}
    rects.forEach(r => { const f = r.getAttribute('fill'); if (f) fills[f] = (fills[f]||0)+1 })
    let gray = 0
    for (const k in fills) {
        if (['#808080','rgb(128, 128, 128)','#fafafa','rgb(250, 250, 250)','#EDEDED','rgb(237, 237, 237)'].includes(k)) gray += fills[k]
    }
    const svgClass = ns.getAttribute('class') || ''
    return { svg: 1, nSvg: svgs.length, svgClass: svgClass.slice(0,120), rects: rects.length,
             distinct: Object.keys(fills).length, fills: fills, gray: gray,
             scheme: window.__configStore ? window.__configStore.colorScheme : '?',
             groupBy: window.__configStore ? window.__configStore.colorGroupBy : '?' }
}"""


def mini(cli, tag):
    try:
        s = cli.evaluate(MINI_JS, retries=1)
        print(f'[v] {tag}: ' + json.dumps(s, ensure_ascii=False)[:1200], flush=True)
        return s
    except Exception as e:
        print(f'[v] {tag}: FAIL {type(e).__name__}: {str(e)[:200]}', flush=True)
        return None


def main():
    console_msgs = []
    with PlaywrightCLI(headless=True) as cli:
        print('[v] 1 dev-login', flush=True)
        cli.goto(f"{BASE}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
        cli.wait_for_timeout(1200)
        cli._page.on('console', lambda m: console_msgs.append(f'[{m.type}] {m.text[:250]}') if m.type in ('error', 'warning') else None)
        cli._page.on('pageerror', lambda e: console_msgs.append(f'[PAGEERROR] {str(e)[:250]}'))

        print('[v] 2 列表页', flush=True)
        cli.goto(f"{BASE}/system/archdata?productCode=TTTTT000&versionId=863", wait_until="domcontentloaded")
        cli.wait_for_timeout(12000)

        print('[v] 3 展开树第一层', flush=True)
        try:
            r = cli.evaluate("""() => {
                const icons = document.querySelectorAll('.el-tree-node__expand-icon')
                if (icons.length) { icons[0].click(); return 'clicked expand ' + icons.length }
                return 'no expand icon'
            }""", retries=1)
            print(f'[v]   {r}', flush=True)
        except Exception as e:
            print(f'[v]   expand fail: {e}', flush=True)
        cli.wait_for_timeout(4000)

        print('[v] 4 勾选第一个叶子 BO', flush=True)
        try:
            r = cli.evaluate("""() => {
                const nodes = Array.from(document.querySelectorAll('.el-tree-node'))
                for (const n of nodes) {
                    const expand = n.querySelector('.el-tree-node__expand-icon')
                    if (expand && expand.classList.contains('is-expandable')) continue
                    const cb = n.querySelector('.el-checkbox')
                    if (!cb) continue
                    const input = cb.querySelector('input[type=checkbox]')
                    if (input && !input.checked) {
                        cb.click()
                        const label = n.querySelector('.oss-node-label, .el-tree-node__label')?.textContent?.trim() || '?'
                        return 'clicked leaf: ' + label
                    }
                }
                return 'no un-checked leaf'
            }""", retries=1)
            print(f'[v]   {r}', flush=True)
        except Exception as e:
            print(f'[v]   check fail: {e}', flush=True)
        cli.wait_for_timeout(6000)

        print('[v] 5 点击 图表展示', flush=True)
        try:
            r = cli.evaluate("""() => {
                const b = Array.from(document.querySelectorAll('.gt-btn-chart-toggle')).find(x => x.textContent.includes('图表展示'))
                if (!b) return 'no btn'
                b.click(); return 'clicked'
            }""", retries=1)
            print(f'[v]   {r}', flush=True)
        except Exception as e:
            print(f'[v]   toggle fail: {e}', flush=True)

        found = False
        for i in range(10):
            cli.wait_for_timeout(4000)
            try:
                n = cli.evaluate("""() => Array.from(document.querySelectorAll('.mermaid-container svg')).filter(s => s.querySelectorAll('g.node, g.nodes').length > 0).length""", retries=1)
            except Exception as e:
                n = f'ERR {type(e).__name__}'
            print(f'[v]   poll[{i}] svg={n}', flush=True)
            if n == 1:
                found = True
                break
        if not found:
            print('[v] !!! 未渲染', flush=True)
            (Path('test_helpers/scripts/_diag_manual_bo4_out') / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')
            return
        cli.wait_for_timeout(3000)

        s0 = mini(cli, 'INIT')
        print('[v] 6 切 colorScheme -> vibrant', flush=True)
        try:
            print('[v]   set -> ' + str(cli.evaluate("() => { if (window.__configStore) { window.__configStore.colorScheme = 'vibrant'; return 'ok' } return 'no store' }", retries=1)), flush=True)
        except Exception as e:
            print(f'[v]   set fail: {e}', flush=True)
        cli.wait_for_timeout(6000)
        s1 = mini(cli, 'AFTER-scheme')

        print('[v] 7 切 colorGroupBy -> serviceModule', flush=True)
        try:
            print('[v]   set -> ' + str(cli.evaluate("() => { if (window.__configStore) { window.__configStore.colorGroupBy = 'serviceModule'; return 'ok' } return 'no store' }", retries=1)), flush=True)
        except Exception as e:
            print(f'[v]   set fail: {e}', flush=True)
        cli.wait_for_timeout(6000)
        s2 = mini(cli, 'AFTER-group')

        print('[v] 8 切 centerScopeHighlight -> false', flush=True)
        try:
            print('[v]   set -> ' + str(cli.evaluate("() => { if (window.__configStore) { window.__configStore.centerScopeHighlight = false; return 'ok' } return 'no store' }", retries=1)), flush=True)
        except Exception as e:
            print(f'[v]   set fail: {e}', flush=True)
        cli.wait_for_timeout(6000)
        s3 = mini(cli, 'AFTER-centerOff')

        print()
        print('========== 结论 ==========', flush=True)
        for tag, s in [('INIT', s0), ('AFTER-scheme', s1), ('AFTER-group', s2), ('AFTER-centerOff', s3)]:
            if s:
                print(f'{tag}: rects={s.get("rects")} distinct={s.get("distinct")} gray={s.get("gray")} scheme={s.get("scheme")} groupBy={s.get("groupBy")}', flush=True)

        keys = ['updateColorsOnly', 'renderMermaid', 'warn', 'error']
        filt = [l for l in console_msgs if any(k in l for k in keys)]
        print(f'\n[v] console 关键 {len(filt)} 条 (末 25):', flush=True)
        for log in filt[-25:]:
            print(f'  {log[:250]}', flush=True)
        out = Path('test_helpers/scripts/_diag_manual_bo4_out')
        out.mkdir(parents=True, exist_ok=True)
        (out / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')


if __name__ == '__main__':
    main()
