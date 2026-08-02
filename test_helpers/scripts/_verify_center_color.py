"""
_verify_center_color.py - 验证"回到原方案"后的中心范围颜色链路 (2026-08-02 v5)

方案: 区分中心范围时, 中心节点 fill = centerScopeColor (指定颜色, 默认 #808080 灰),
      非中心节点 = 分组色; 不再用粗虚线边框区分。

范围: 供应链云领域 / 供应链计划 子领域 (sub_domain 299, 30 BOs, 手动 UI 路径)

断言:
  A. INIT: 存在中心灰色节点 (#808080), 无虚线边框 (dashCount=0), 非中心节点彩色
  B. UI 切 鲜艳: 中心节点仍为灰色, 非中心节点联动变色, 仍无虚线边框
  C. UI 切 不区分 (centerScopeHighlight=false): 全图无灰色, 全部彩色, 无虚线边框
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3005'
OUT = Path('test_helpers/scripts/_verify_center_color_out')
OUT.mkdir(parents=True, exist_ok=True)

WRAP = """(fn) => Promise.race([ fn(), new Promise((res) => setTimeout(() => res({ timeout: true }), 2500)) ])"""

DUMP_JS = """((WRAP))(() => {
    const out = {}
    const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
    const ns = svgs.find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
    if (!ns) { out.svg = 0; return out }
    out.svg = 1
    const rects = ns.querySelectorAll('g.node rect, g.nodes rect')
    const comps = {}, attrs = {}
    let grayComp = 0, dashBorder = 0, total = 0
    rects.forEach(r => {
        total++
        const c = getComputedStyle(r).fill
        if (c && c !== 'none') comps[c] = (comps[c] || 0) + 1
        const a = r.getAttribute('fill')
        if (a && a !== 'none') attrs[a] = (attrs[a] || 0) + 1
        if (c === 'rgb(128, 128, 128)') grayComp++
        const dash = r.style.strokeDasharray || r.getAttribute('stroke-dasharray') || ''
        const sw = (r.style.strokeWidth || r.getAttribute('stroke-width') || '').replace('px', '')
        if (dash && sw === '3') dashBorder++
    })
    out.total = total
    out.grayComp = grayComp
    out.dashBorder = dashBorder
    out.compsDistinct = Object.keys(comps).length
    out.comps = comps
    out.attrs = attrs
    // [v6] 连线颜色统计
    const paths = ns.querySelectorAll('.edgePaths > path, .flowchart-link path, .edgePath path')
    const linkStrokes = {}
    let blackLinks = 0, grayLinks = 0
    paths.forEach(p => {
        const st = p.getAttribute('stroke') || p.style.stroke || getComputedStyle(p).stroke || ''
        if (!st) return
        linkStrokes[st] = (linkStrokes[st] || 0) + 1
        if (st === '#000000' || st === 'rgb(0, 0, 0)') blackLinks++
        if (st === '#808080' || st === 'rgb(128, 128, 128)') grayLinks++
    })
    out.linkTotal = paths.length
    out.linkStrokes = linkStrokes
    out.blackLinks = blackLinks
    out.grayLinks = grayLinks
    // [v6] 图例: 中心范围项必须是实心色块 (无 stroke-dasharray)
    const panel = document.querySelector('.color-legend-panel')
    if (panel) {
        const items = Array.from(panel.querySelectorAll('div')).filter(d => (d.textContent || '').trim() === '中心范围')
        if (items.length) {
            const rect = items[0].querySelector('svg rect')
            out.legendCenter = rect ? { fill: rect.getAttribute('fill'), dash: rect.getAttribute('stroke-dasharray') } : 'no rect'
        } else out.legendCenter = 'not found'
    } else out.legendCenter = 'no panel'
    const st = window.__configStore
    if (st) out.store = { colorScheme: st.colorScheme, colorGroupBy: st.colorGroupBy, centerScopeHighlight: st.centerScopeHighlight }
    return out
})""".replace('(WRAP)', WRAP)


def safe_eval(cli, js):
    try:
        return cli.evaluate_async(js, timeout=10000)
    except Exception as e:
        return {'pyErr': f'{type(e).__name__}: {str(e)[:150]}'}


def dump(cli, tag):
    s = safe_eval(cli, DUMP_JS)
    if s.get('timeout'):
        print(f'[v] {tag}: ** JS 超时 **', flush=True)
        return s
    print(f'[v] {tag}: svg={s.get("svg")} total={s.get("total")} grayComp={s.get("grayComp")} '
          f'dashBorder={s.get("dashBorder")} compsDistinct={s.get("compsDistinct")} store={s.get("store")}', flush=True)
    if s.get('comps'):
        print(f'[v]   comps={json.dumps(s["comps"], ensure_ascii=False)[:300]}', flush=True)
    if s.get('attrs'):
        print(f'[v]   attrs={json.dumps(s["attrs"], ensure_ascii=False)[:300]}', flush=True)
    return s


def ui_select(cli, idx, opt):
    js = """((WRAP))(async () => {
        const sleep = ms => new Promise(r => setTimeout(r, ms));
        const selects = Array.from(document.querySelectorAll('.cmt-select'))
        const sel = selects[IDX]
        if (!sel) return 'no select ' + IDX
        const wrap = sel.querySelector('.el-select__wrapper') || sel
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
        if (!target) return 'no item ' + 'OPT'
        target.click()
        await sleep(600)
        return 'selected ' + 'OPT'
    })""".replace('(WRAP)', WRAP).replace('IDX', str(idx)).replace("'OPT'", f"'{opt}'")
    r = safe_eval(cli, js)
    print(f'[v]   ui: {r}', flush=True)
    cli.wait_for_timeout(9000)


def main():
    with PlaywrightCLI(headless=True) as cli:
        print('[v] 1 dev-login', flush=True)
        cli.goto(f"{BASE}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
        cli.wait_for_timeout(1200)

        print('[v] 2 列表页', flush=True)
        cli.goto(f"{BASE}/system/archdata?productCode=TTTTT000&versionId=863", wait_until="domcontentloaded")
        cli.wait_for_timeout(12000)

        print('[v] 3 展开供应链云 → 勾选供应链计划', flush=True)
        r = safe_eval(cli, """((WRAP))(async () => {
            const sleep = ms => new Promise(r => setTimeout(r, ms));
            const findNode = (text) => Array.from(document.querySelectorAll('.el-tree-node')).find(n => {
                const t = n.querySelector('.oss-node-label, .el-tree-node__label')?.textContent?.trim() || ''
                return t.includes(text)
            })
            const dom = findNode('供应链云')
            if (!dom) return 'no 供应链云'
            const icon = dom.querySelector('.el-tree-node__expand-icon')
            if (icon && !icon.classList.contains('expanded')) { icon.click(); await sleep(1500) }
            const sd = findNode('供应链计划')
            if (!sd) return 'no 供应链计划'
            const cb = sd.querySelector('.el-checkbox input[type=checkbox]')
            if (cb && !cb.checked) cb.click()
            return 'checked 供应链计划'
        })""".replace('(WRAP)', WRAP))
        print(f'[v]   {r}', flush=True)
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

        for i in range(30):
            cli.wait_for_timeout(4000)
            n = safe_eval(cli, """((WRAP))(() => Array.from(document.querySelectorAll('.mermaid-container svg')).filter(s => s.querySelectorAll('g.node, g.nodes').length > 0).length)""".replace('(WRAP)', WRAP))
            print(f'[v]   poll[{i}] svg={n}', flush=True)
            if n == 1:
                break
        try:
            cli._page.wait_for_function("() => !!(window.__archPage?.mermaid?.lastRender?.endTime)", timeout=180000)
            print('[v]   render done', flush=True)
        except Exception as e:
            print(f'[v]   render wait fail: {e}', flush=True)
        cli.wait_for_timeout(3000)

        print('[v] 5 INIT', flush=True)
        s0 = dump(cli, 'A INIT')

        print('[v] 6 UI 切 鲜艳 (select idx 2)', flush=True)
        ui_select(cli, 2, '鲜艳')
        s1 = dump(cli, 'B vibrant')

        print('[v] 7 UI 切 不区分 (select idx 3)', flush=True)
        ui_select(cli, 3, '不区分')
        s2 = dump(cli, 'C centerOff')

        print()
        print('========== 结论 ==========', flush=True)
        ok_a = s0.get('grayComp') > 0 and s0.get('dashBorder') == 0 and (s0.get('compsDistinct') or 0) >= 3
        ok_b = s1.get('grayComp') == s0.get('grayComp') and s1.get('dashBorder') == 0 and (s1.get('compsDistinct') or 0) >= 3
        ok_c = s2.get('grayComp') == 0 and s2.get('dashBorder') == 0 and (s2.get('compsDistinct') or 0) >= 2
        print(f'A. INIT 中心灰={s0.get("grayComp")} 虚线={s0.get("dashBorder")} : {"PASS" if ok_a else "FAIL"}', flush=True)
        print(f'B. 鲜艳 中心灰={s1.get("grayComp")} 虚线={s1.get("dashBorder")} : {"PASS" if ok_b else "FAIL"}', flush=True)
        print(f'C. 不区分 中心灰={s2.get("grayComp")} 虚线={s2.get("dashBorder")} : {"PASS" if ok_c else "FAIL"}', flush=True)
        # [v6] 连线颜色: 区分模式双中心连线应为灰 #808080 (本数据集无双非中心连线);
        #   不区分模式 (centerScopeHighlight=false) 所有连线必须为黑色
        a_link = s0.get('grayLinks', 0) > 0 and (s0.get('linkTotal') or 0) > 0
        b_link = s1.get('grayLinks', 0) > 0 and (s1.get('linkTotal') or 0) > 0
        c_link = s2.get('blackLinks', 0) == (s2.get('linkTotal') or 0) and (s2.get('linkTotal') or 0) > 0
        print(f'A-link. 区分 INIT 灰连线={s0.get("grayLinks")}/{s0.get("linkTotal")} 黑连线={s0.get("blackLinks")} : {"PASS" if a_link else "FAIL"}', flush=True)
        print(f'B-link. 区分 鲜艳 灰连线={s1.get("grayLinks")}/{s1.get("linkTotal")} 黑连线={s1.get("blackLinks")} : {"PASS" if b_link else "FAIL"}', flush=True)
        print(f'C-link. 不区分 黑连线={s2.get("blackLinks")}/{s2.get("linkTotal")} : {"PASS" if c_link else "FAIL"}', flush=True)
        # [v6] 图例: 中心范围项实心色块 (无虚线)
        legend_ok = s0.get('legendCenter') and s0['legendCenter'] != 'no panel' and s0['legendCenter'] != 'not found' \
            and not s0['legendCenter'].get('dash') and s0['legendCenter'].get('fill')
        print(f'D-legend. 中心范围图例项 fill={s0.get("legendCenter")} : {"PASS" if legend_ok else "FAIL"}', flush=True)
        (OUT / 'dump.json').write_text(json.dumps({'INIT': s0, 'vibrant': s1, 'centerOff': s2}, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\n[v] 输出: {OUT}', flush=True)


if __name__ == '__main__':
    main()
