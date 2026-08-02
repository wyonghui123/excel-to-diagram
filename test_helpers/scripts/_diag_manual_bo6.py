"""
_diag_manual_bo6.py - BO 图手动入口切色变灰 (v6: 全部 evaluate 带 JS 侧 Promise.race 超时保护)

关键改进 vs v5:
  - 每个 dump/set 都包 Promise.race(2500ms), 主线程繁忙也最多等 2.5s, 不会无限挂死
  - 优先读 window.__lastMermaidCode (判断 mermaid code 本身是否彩色)
  - 输出 fills 分布 (读 getAttribute fill)
  - 记录 lastRender 状态 (window.__archPage.mermaid.lastRender)
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3005'
OUT = Path('test_helpers/scripts/_diag_manual_bo6_out')
OUT.mkdir(parents=True, exist_ok=True)

# 每个 JS 调用包一层 Promise.race, 超时 2500ms 返回 {timeout:true}
# 注意: 模板里必须写 ((WRAP)) 双括号, 替换后得到 ((fn) => Promise.race(...))(() => ...) 才是"调用"
WRAP = """(fn) => Promise.race([ fn(), new Promise((res) => setTimeout(() => res({ timeout: true }), 2500)) ])"""

# 传给 evaluate_async: 它是表达式 (不含函数包裹), evaluate_async 内部包 async () => { return <expr> }
DUMP_JS = """((WRAP))(() => {
    const out = {}
    const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
    const ns = svgs.find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
    out.nSvg = svgs.length
    if (!ns) { out.svg = 0; return out }
    out.svg = 1
    out.svgClass = (ns.getAttribute('class') || '').slice(0, 150)
    out.hasFlowchart = (ns.getAttribute('class') || '').includes('flowchart')
    const rects = ns.querySelectorAll('g.node rect, g.nodes rect')
    const fills = {}
    let noFill = 0
    rects.forEach(r => {
        const f = r.getAttribute('fill')
        if (!f || f === 'none') { noFill++; return }
        fills[f] = (fills[f] || 0) + 1
    })
    out.rects = rects.length
    out.noFill = noFill
    out.distinct = Object.keys(fills).length
    out.fills = fills
    out.gray = 0
    for (const k in fills) {
        if (['#808080','rgb(128, 128, 128)','#fafafa','rgb(250, 250, 250)','#EDEDED','rgb(237, 237, 237)','#ECECFF','rgb(236, 236, 255)','#ffffff','rgb(255, 255, 255)','#fff'].includes(k)) out.gray += fills[k]
    }
    const code = window.__lastMermaidCode
    if (code) {
        const c = typeof code === 'string' ? code : JSON.stringify(code)
        out.codeHead = c.slice(0, 260)
        out.styleCmds = (c.match(/^style |\\nstyle /gm) || []).length
        out.classDefs = (c.match(/classDef /g) || []).length
        out.linkStyles = (c.match(/linkStyle /g) || []).length
    }
    const lr = window.__archPage?.mermaid?.lastRender
    out.lastRender = lr ? { node: lr.nodeCount, edge: lr.edgeCount, durMs: lr.durationMs, t: lr.endTime } : null
    const st = window.__configStore
    if (st) out.store = { colorScheme: st.colorScheme, colorGroupBy: st.colorGroupBy, centerScopeHighlight: st.centerScopeHighlight }
    return out
})""".replace('(WRAP)', WRAP)


def safe_eval(cli, js, tag):
    # 用 evaluate_async (本身 await Promise), 规避 sync evaluate 对 Promise 返回值的序列化问题
    try:
        return cli.evaluate_async(js, timeout=10000)
    except Exception as e:
        return {'pyErr': f'{type(e).__name__}: {str(e)[:150]}'}


def dump(cli, tag):
    s = safe_eval(cli, DUMP_JS, tag)
    if s.get('timeout'):
        print(f'[v] {tag}: ** JS 超时 (主线程繁忙) **', flush=True)
        return s
    print(f'[v] {tag}: svg={s.get("svg")} cls="{s.get("svgClass")}" flow={s.get("hasFlowchart")} '
          f'rects={s.get("rects")} distinct={s.get("distinct")} gray={s.get("gray")} '
          f'style={s.get("styleCmds")} classDef={s.get("classDefs")} link={s.get("linkStyles")} '
          f'lastRender={s.get("lastRender")} store={s.get("store")}', flush=True)
    if s.get('fills'):
        print(f'[v]   fills={json.dumps(s["fills"], ensure_ascii=False)[:360]}', flush=True)
    if s.get('codeHead'):
        print(f'[v]   code: {s["codeHead"]}', flush=True)
    return s


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

        print('[v] 3 多轮展开树 (懒加载, 每次点击等 600ms)', flush=True)
        try:
            r = safe_eval(cli, """((WRAP))(async () => {
                const sleep = ms => new Promise(r => setTimeout(r, ms));
                let rounds = 0, clicks = 0;
                for (let i = 0; i < 60; i++) {
                    const icons = Array.from(document.querySelectorAll('.el-tree-node__expand-icon.is-expandable'))
                    const un = icons.filter(ic => !ic.classList.contains('expanded'))
                    if (un.length === 0) break
                    rounds = i + 1
                    for (const ic of un.slice(0, 3)) {
                        ic.click(); clicks++
                    }
                    await sleep(600)
                }
                return `rounds=${rounds} clicks=${clicks}`;
            })""".replace('(WRAP)', WRAP), 'expand')
            print(f'[v]   {r}', flush=True)
        except Exception as e:
            print(f'[v]   expand fail: {e}', flush=True)
        cli.wait_for_timeout(4000)

        print('[v] 3b 输出树节点文本 (前 60 个)', flush=True)
        try:
            r = safe_eval(cli, """((WRAP))(() => {
                const labels = Array.from(document.querySelectorAll('.el-tree-node .oss-node-label, .el-tree-node .el-tree-node__label, .el-tree-node__content'))
                return labels.slice(0, 60).map((el, i) => {
                    const cb = el.closest('.el-tree-node__content')?.querySelector('input[type=checkbox]')
                    return (i) + ':' + (el.textContent || '').trim().slice(0, 40) + (cb ? ' [cb]' : '')
                })
            })""".replace('(WRAP)', WRAP), 'treenodes')
            print(f'[v]   {json.dumps(r, ensure_ascii=False)[:1500]}', flush=True)
        except Exception as e:
            print(f'[v]   treenodes fail: {e}', flush=True)

        print('[v] 4 勾选 供应链云 领域', flush=True)
        try:
            r = safe_eval(cli, """((WRAP))(() => {
                const nodes = Array.from(document.querySelectorAll('.el-tree-node'))
                const target = nodes.find(n => {
                    const t = n.querySelector('.oss-node-label, .el-tree-node__label')?.textContent?.trim() || ''
                    return t.includes('供应链云')
                })
                if (!target) return 'no 供应链云'
                const cb = target.querySelector('.el-checkbox input[type=checkbox]')
                if (!cb) return 'no checkbox'
                if (cb.checked) return 'already checked'
                cb.click()
                return 'checked 供应链云'
            })""".replace('(WRAP)', WRAP), 'checkdomain')
            print(f'[v]   {r}', flush=True)
        except Exception as e:
            print(f'[v]   check fail: {e}', flush=True)
        cli.wait_for_timeout(8000)

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
        for i in range(12):
            cli.wait_for_timeout(4000)
            n = safe_eval(cli, """((WRAP))(() => Array.from(document.querySelectorAll('.mermaid-container svg')).filter(s => s.querySelectorAll('g.node, g.nodes').length > 0).length)""".replace('(WRAP)', WRAP), 'poll')
            print(f'[v]   poll[{i}] svg={n}', flush=True)
            if n == 1:
                found = True
                break
        if not found:
            print('[v] !!! 未渲染', flush=True)
            (OUT / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')
            return

        # 等 mermaid.run 完全结束 (lastRender.endTime 出现), 避免在 ELK 布局进行中 dump 卡死
        print('[v] 等渲染完成信号...', flush=True)
        try:
            cli._page.wait_for_function(
                "() => !!(window.__archPage?.mermaid?.lastRender?.endTime)",
                timeout=150000
            )
            print('[v]   render done', flush=True)
        except Exception as e:
            print(f'[v]   render wait fail: {e} (继续尝试 dump)', flush=True)
        cli.wait_for_timeout(3000)

        s0 = dump(cli, '0 INIT')

        def set_store(key, val):
            r = safe_eval(cli, f"""((WRAP))(() => {{ const s = window.__configStore; if (!s) return 'no store'; s.{key} = {json.dumps(val)}; return 'ok ' + JSON.stringify(s.{key}) }})""".replace('(WRAP)', WRAP), 'set')
            print(f'[v]   set -> {r}', flush=True)
            cli.wait_for_timeout(9000)

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
            if s and not s.get('timeout'):
                print(f'{tag}: svg={s.get("svg")} rects={s.get("rects")} distinct={s.get("distinct")} gray={s.get("gray")} '
                      f'class="{s.get("svgClass")}" style={s.get("styleCmds")} classDef={s.get("classDefs")}', flush=True)

        keys = ['updateColorsOnly', 'renderMermaid', 'updateNodeColors', 'warn', 'error', '颜色']
        filt = [l for l in console_msgs if any(k in l for k in keys)]
        print(f'\n[v] console 关键 {len(filt)} 条 (末 30):', flush=True)
        for log in filt[-30:]:
            print(f'  {log[:260]}', flush=True)
        (OUT / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')
        print(f'\n[v] 输出: {OUT}', flush=True)


if __name__ == '__main__':
    main()
