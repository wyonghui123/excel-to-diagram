"""
_diag_manual_bo5.py - BO 图手动入口切色变灰 (v5: 小范围 + SVG class 对比)

展开树 -> 勾选第一个 BO 叶子 (小图) -> 图表展示 -> dump(INIT + mermaid code)
-> 切 colorScheme/colorGroupBy/centerScopeHighlight -> 逐步 dump。
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3005'
OUT = Path('test_helpers/scripts/_diag_manual_bo5_out')
OUT.mkdir(parents=True, exist_ok=True)

DUMP_JS = """() => {
    const out = {}
    const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
    const ns = svgs.find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
    if (!ns) { out.err = 'no node svg'; out.nSvg = svgs.length; return out }
    out.nSvg = svgs.length
    out.svgClass = (ns.getAttribute('class') || '').slice(0, 150)
    const rects = ns.querySelectorAll('g.node rect, g.nodes rect')
    const fills = {}
    rects.forEach(r => { const f = r.getAttribute('fill'); if (f) fills[f] = (fills[f] || 0) + 1 })
    let gray = 0
    for (const k in fills) {
        if (['#808080','rgb(128, 128, 128)','#fafafa','rgb(250, 250, 250)','#EDEDED','rgb(237, 237, 237)'].includes(k)) gray += fills[k]
    }
    out.rects = rects.length
    out.distinct = Object.keys(fills).length
    out.fills = fills
    out.gray = gray
    const code = window.__lastMermaidCode
    if (code) {
        const c = typeof code === 'string' ? code : JSON.stringify(code)
        out.mermaidHead = c.slice(0, 300)
        out.styleCmds = (c.match(/^style |style /gm) || []).length
        out.classDefs = (c.match(/classDef /g) || []).length
        out.hasFlowchart = c.indexOf('flowchart') !== -1
    }
    return out
}"""


def dump(cli, tag):
    try:
        s = cli.evaluate(DUMP_JS, retries=1)
        print(f'[v] {tag}: ' + json.dumps({k: v for k, v in s.items() if k not in ('mermaidHead', 'fills')}, ensure_ascii=False)[:900], flush=True)
        if s.get('fills'):
            print(f'[v]   fills={json.dumps(s["fills"], ensure_ascii=False)[:400]}', flush=True)
        if s.get('mermaidHead'):
            print(f'[v]   code: {s["mermaidHead"]}', flush=True)
        return s
    except Exception as e:
        print(f'[v] {tag}: FAIL {type(e).__name__}: {str(e)[:150]}', flush=True)
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

        print('[v] 3 展开树全部层级', flush=True)
        try:
            r = cli.evaluate_async("""{
                const sleep = ms => new Promise(r => setTimeout(r, ms));
                for (let i = 0; i < 30; i++) {
                    const icons = document.querySelectorAll('.el-tree-node__expand-icon.is-expandable');
                    const un = Array.from(icons).find(ic => !ic.classList.contains('expanded'));
                    if (!un) break;
                    un.click();
                    await sleep(350);
                }
                return 'expanded';
            }""", timeout=15000)
            print(f'[v]   {r}', flush=True)
        except Exception as e:
            print(f'[v]   expand fail: {e}', flush=True)
        cli.wait_for_timeout(3000)

        print('[v] 4 勾选第一个 BO 叶子', flush=True)
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
                        const label = n.querySelector('.oss-node-label, .el-tree-node__label')?.textContent?.trim() || '?'
                        cb.click()
                        return 'checked: ' + label
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
            (OUT / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')
            return
        cli.wait_for_timeout(5000)

        s0 = dump(cli, '0 INIT')

        def set_store(key, val):
            try:
                r = cli.evaluate(f"() => {{ const s = window.__configStore; if (!s) return 'no store'; s.{key} = {json.dumps(val)}; return 'ok ' + {json.dumps(key)} + '=' + JSON.stringify(s.{key}) }}", retries=1)
                print(f'[v]   set -> {r}', flush=True)
            except Exception as e:
                print(f'[v]   set fail: {e}', flush=True)
            cli.wait_for_timeout(7000)

        print('[v] 6 切 colorScheme -> vibrant', flush=True)
        set_store('colorScheme', 'vibrant')
        s1 = dump(cli, '1 scheme-vibrant')

        print('[v] 7 切 colorGroupBy -> serviceModule', flush=True)
        set_store('colorGroupBy', 'serviceModule')
        s2 = dump(cli, '2 group-serviceModule')

        print('[v] 8 切 centerScopeHighlight -> false', flush=True)
        set_store('centerScopeHighlight', False)
        s3 = dump(cli, '3 centerOff')

        print()
        print('========== 结论 ==========', flush=True)
        for tag, s in [('INIT', s0), ('scheme', s1), ('group', s2), ('centerOff', s3)]:
            if s:
                print(f'{tag}: rects={s.get("rects")} distinct={s.get("distinct")} gray={s.get("gray")} '
                      f'class="{s.get("svgClass")}" styleCmds={s.get("styleCmds")} classDefs={s.get("classDefs")}', flush=True)

        keys = ['updateColorsOnly', 'renderMermaid', 'updateNodeColors', 'warn', 'error']
        filt = [l for l in console_msgs if any(k in l for k in keys)]
        print(f'\n[v] console 关键 {len(filt)} 条 (末 25):', flush=True)
        for log in filt[-25:]:
            print(f'  {log[:250]}', flush=True)
        (OUT / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')
        print(f'\n[v] 输出: {OUT}', flush=True)


if __name__ == '__main__':
    main()
