"""
_diag_manual_bo7.py - BO 图 UI 下拉切色变灰复现 (v7.1 数据范围对齐)

关键改进 vs v6:
  - dump 读取 getComputedStyle(rect).fill (视觉真实颜色) vs getAttribute('fill') (属性) vs rect.style.fill (内联)
    -> 若属性彩色但 computed 灰 = 内联/CSS 覆盖 fill 属性, 就是用户看到的灰色
  - 切色走真实 UI el-select 下拉点击 (完全复刻用户操作), 而不是 __configStore 直改
  - [v7.1] 数据范围 = 供应链云领域下的 供应链计划 子领域 (sub_domain 299, 30 BOs):
      展开"供应链云" → 勾选"供应链计划"子领域节点 (不再勾整个领域 141 BOs)
      已通过 _verify_scope_data.py 核实: id=299 code=SCP name=供应链计划, domain_id=2200 (供应链云)
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3005'
OUT = Path('test_helpers/scripts/_diag_manual_bo7_out')
OUT.mkdir(parents=True, exist_ok=True)

WRAP = """(fn) => Promise.race([ fn(), new Promise((res) => setTimeout(() => res({ timeout: true }), 2500)) ])"""

DUMP_JS = """((WRAP))(() => {
    const out = {}
    const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
    const ns = svgs.find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
    out.nSvg = svgs.length
    if (!ns) { out.svg = 0; return out }
    out.svg = 1
    out.svgClass = (ns.getAttribute('class') || '').slice(0, 150)
    const rects = ns.querySelectorAll('g.node rect, g.nodes rect')
    const attrs = {}, comps = {}, inlines = {}
    rects.forEach(r => {
        const a = r.getAttribute('fill')
        if (a && a !== 'none') attrs[a] = (attrs[a] || 0) + 1
        const c = getComputedStyle(r).fill
        if (c && c !== 'none') comps[c] = (comps[c] || 0) + 1
        const s = r.style && r.style.fill
        if (s && s !== 'none') inlines[s] = (inlines[s] || 0) + 1
    })
    out.rects = rects.length
    out.attrsDistinct = Object.keys(attrs).length
    out.compsDistinct = Object.keys(comps).length
    out.inlineDistinct = Object.keys(inlines).length
    out.attrs = attrs
    out.comps = comps
    out.inlines = inlines
    const GRAY = ['#808080','rgb(128, 128, 128)','#fafafa','rgb(250, 250, 250)','#EDEDED','rgb(237, 237, 237)','#ECECFF','rgb(236, 236, 255)','#ffffff','rgb(255, 255, 255)','#fff','#e0e0e0','rgb(224, 224, 224)','#f0f0f0','rgb(240, 240, 240)','#ececff']
    out.compsGray = 0
    for (const k in comps) { if (GRAY.includes(k)) out.compsGray += comps[k] }
    const code = window.__lastMermaidCode
    if (code) {
        const c = typeof code === 'string' ? code : JSON.stringify(code)
        out.codeHead = c.slice(0, 200)
        out.styleCmds = (c.match(/^style |\\nstyle /gm) || []).length
        out.classDefs = (c.match(/classDef /g) || []).length
    }
    const lr = window.__archPage?.mermaid?.lastRender
    out.lastRender = lr ? { node: lr.nodeCount, edge: lr.edgeCount, durMs: lr.durationMs, t: lr.endTime } : null
    const st = window.__configStore
    if (st) out.store = { colorScheme: st.colorScheme, colorGroupBy: st.colorGroupBy, centerScopeHighlight: st.centerScopeHighlight }
    return out
})""".replace('(WRAP)', WRAP)


def safe_eval(cli, js, tag):
    try:
        return cli.evaluate_async(js, timeout=10000)
    except Exception as e:
        return {'pyErr': f'{type(e).__name__}: {str(e)[:150]}'}


def dump(cli, tag):
    s = safe_eval(cli, DUMP_JS, tag)
    if s.get('timeout'):
        print(f'[v] {tag}: ** JS 超时 (主线程繁忙) **', flush=True)
        return s
    print(f'[v] {tag}: svg={s.get("svg")} rects={s.get("rects")} '
          f'attr={s.get("attrsDistinct")} comp={s.get("compsDistinct")} inline={s.get("inlineDistinct")} '
          f'compsGray={s.get("compsGray")} store={s.get("store")} lastRender={s.get("lastRender")}', flush=True)
    if s.get('attrs') and not s.get('timeout'):
        print(f'[v]   attrs={json.dumps(s["attrs"], ensure_ascii=False)[:280]}', flush=True)
    if s.get('comps') and not s.get('timeout'):
        print(f'[v]   comps={json.dumps(s["comps"], ensure_ascii=False)[:280]}', flush=True)
    if s.get('inlines') and not s.get('timeout'):
        print(f'[v]   inlines={json.dumps(s["inlines"], ensure_ascii=False)[:280]}', flush=True)
    return s


# 用 UI 点击第 idx 个 .cmt-select 并选文本含 opt 的选项
def ui_select(cli, idx, opt):
    js = """((WRAP))(async () => {
        const sleep = ms => new Promise(r => setTimeout(r, ms));
        const selects = Array.from(document.querySelectorAll('.cmt-select'))
        const sel = selects[IDX]
        if (!sel) return 'no select ' + IDX
        const wrap = sel.querySelector('.el-select__wrapper') || sel.querySelector('.el-select') || sel
        wrap.click()
        await sleep(500)
        const dds = Array.from(document.querySelectorAll('.el-select-dropdown')).filter(d => {
            const st = getComputedStyle(d)
            return st.display !== 'none' && st.visibility !== 'hidden' && d.offsetParent !== null
        })
        if (dds.length === 0) return 'no dropdown'
        const dd = dds[dds.length - 1]
        const items = Array.from(dd.querySelectorAll('.el-select-dropdown__item'))
        const target = items.find(i => (i.textContent || '').trim().includes('OPT'))
        if (!target) return 'no item ' + 'OPT' + ' (items: ' + items.map(i => i.textContent.trim()).join(',') + ')'
        target.click()
        await sleep(600)
        return 'selected ' + 'OPT'
    })""".replace('(WRAP)', WRAP).replace('IDX', str(idx)).replace("'OPT'", f"'{opt}'")
    r = safe_eval(cli, js, f'ui-select[{idx}]={opt}')
    print(f'[v]   ui: {r}', flush=True)
    cli.wait_for_timeout(9000)


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

        print('[v] 3 展开 供应链云 领域, 勾选其下 供应链计划 子领域', flush=True)
        try:
            r = safe_eval(cli, """((WRAP))(async () => {
                const sleep = ms => new Promise(r => setTimeout(r, ms));
                const findNode = (text) => Array.from(document.querySelectorAll('.el-tree-node')).find(n => {
                    const t = n.querySelector('.oss-node-label, .el-tree-node__label')?.textContent?.trim() || ''
                    return t.includes(text)
                })
                // 3a. 展开 供应链云 (懒渲染: 子领域节点在父节点展开后才进 DOM)
                const dom = findNode('供应链云')
                if (!dom) return 'no 供应链云'
                const icon = dom.querySelector('.el-tree-node__expand-icon')
                if (icon && !icon.classList.contains('expanded')) {
                    icon.click()
                    await sleep(1500)
                }
                // 3b. 勾选 供应链计划 子领域
                const sd = findNode('供应链计划')
                if (!sd) return 'no 供应链计划 (子领域节点未渲染?)'
                const cb = sd.querySelector('.el-checkbox input[type=checkbox]')
                if (!cb) return 'no checkbox'
                if (cb.checked) return 'already checked'
                cb.click()
                return 'checked 供应链计划'
            })""".replace('(WRAP)', WRAP), 'checksubdomain')
            print(f'[v]   {r}', flush=True)
        except Exception as e:
            print(f'[v]   check fail: {e}', flush=True)
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

        found = False
        for i in range(30):
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

        print('[v] 等渲染完成信号...', flush=True)
        try:
            cli._page.wait_for_function(
                "() => !!(window.__archPage?.mermaid?.lastRender?.endTime)",
                timeout=180000
            )
            print('[v]   render done', flush=True)
        except Exception as e:
            print(f'[v]   render wait fail: {e} (继续)', flush=True)
        cli.wait_for_timeout(3000)

        s0 = dump(cli, '0 INIT')

        print('[v] 5 UI 切 配色 -> 鲜艳 (select idx 2)', flush=True)
        ui_select(cli, 2, '鲜艳')
        s1 = dump(cli, '1 UI-scheme-vibrant')

        print('[v] 6 UI 切 颜色分组 -> 按服务模块 (select idx 1)', flush=True)
        ui_select(cli, 1, '按服务模块')
        s2 = dump(cli, '2 UI-group-serviceModule')

        print('[v] 7 UI 切 中心范围 -> 不区分 (select idx 3)', flush=True)
        ui_select(cli, 3, '不区分')
        s3 = dump(cli, '3 UI-centerOff')

        print()
        print('========== 结论 ==========', flush=True)
        for tag, s in [('INIT', s0), ('scheme', s1), ('group', s2), ('centerOff', s3)]:
            if s and not s.get('timeout'):
                print(f'{tag}: rects={s.get("rects")} attr={s.get("attrsDistinct")} comp={s.get("compsDistinct")} compsGray={s.get("compsGray")}', flush=True)

        filt = [l for l in console_msgs if any(k in l for k in ['color', 'updateNode', 'updateColor', 'renderMermaid', 'PAGEERROR', 'TypeError', 'Uncaught'])]
        print(f'\n[v] console 颜色/错误相关 {len(filt)} 条 (末 40):', flush=True)
        for log in filt[-40:]:
            print(f'  {log[:260]}', flush=True)
        (OUT / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')
        print(f'\n[v] 输出: {OUT}', flush=True)


if __name__ == '__main__':
    main()
