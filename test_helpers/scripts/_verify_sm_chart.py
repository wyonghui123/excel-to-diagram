"""
_verify_sm_chart.py - 验证服务模块图 (SM) 节点颜色链路 (2026-08-02)

背景: BO 图已验证"分组色+特殊边框"。但 SM 图初始节点颜色可能 fallback 到
      useBlockDiagramStyle 默认 #fafafa (浅灰) — 若 node.color 未赋值。
      MermaidComponent 切换时 updateNodeColors 会对所有图生效, 但初始渲染
      依赖语法层输出的 style。

验证:
A. BO 图初始节点颜色 (对照组, 期望分组色)
B. 切到 SM 图: 初始节点颜色分布 (若大面积 #fafafa/浅灰 -> 复现用户"节点还是灰色")
C. SM 图下切换配色: 节点是否联动变色
D. SM 图下切换颜色分组: 节点是否联动变色
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


def get_node_stats(cli):
    return cli.evaluate("""() => {
        const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
        const svg = svgs.find(s => s.classList.contains('flowchart')) || null
        if (!svg) return { error: 'no flowchart svg', svgCount: svgs.length }
        const rects = svg.querySelectorAll('g.node rect, g.nodes rect')
        const fills = {}
        let total = 0, centerBorder = 0
        rects.forEach(r => {
            const fill = r.getAttribute('fill') || r.style.fill || 'none'
            if (fill === 'none' || fill === 'transparent') return
            fills[fill] = (fills[fill] || 0) + 1
            total++
            // [FIX 2026-08-02] 中心模块边框: mermaid 把 style 指令的 stroke-dasharray:6,4 渲染为
            //   style="stroke-dasharray:6 !important;4: !important" → style.strokeDasharray='6'
            const dash = r.style.strokeDasharray || r.getAttribute('stroke-dasharray') || ''
            const sw = (r.style.strokeWidth || r.getAttribute('stroke-width') || '').replace('px', '')
            if (dash.indexOf('6') !== -1 && sw === '3') centerBorder++
        })
        let lightGray = 0
        for (const [c, n] of Object.entries(fills)) {
            // [FIX 2026-08-02 v5] #808080/rgb(128,128,128) 是中心范围的指定颜色 (原方案),
            //   不再视为"异常浅灰", 只统计 #fafafa 类 classDef 默认灰
            if (c === '#fafafa' || c === 'rgb(250, 250, 250)' || c === '#f0f0f0' || c === 'rgb(240, 240, 240)' || c === '#e0e0e0') lightGray += n
        }
        return { total, distinct: Object.keys(fills).length, fills, lightGray, centerBorder }
    }""")


def main():
    base_url = 'http://localhost:3005'
    output_dir = Path('test_helpers/scripts/_verify_sm_out')
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

        print('[v] Step 2: shortcut 进入图表视图')
        url = f"{base_url}/system/archdata?shortcut=1&productCode=TTTTT000&versionId=863&scope={scope_b64}&scopeType=all&viewMode=chart"
        cli.goto(url, wait_until="domcontentloaded")
        cli.wait_for_timeout(20000)

        state = cli.evaluate("""() => ({
            svgCount: document.querySelectorAll('.mermaid-container svg').length,
            nodeCount: document.querySelectorAll('.mermaid-container svg g.node').length,
            cmtSelects: document.querySelectorAll('.cmt-select').length
        })""")
        print(f'[v] chart state: {json.dumps(state, ensure_ascii=False)}')
        if not state.get('svgCount'):
            print('[v] !! 图表未渲染')
            for log in console_msgs[-30:]:
                print(f'  {log[:300]}')
            return

        # A. BO 图初始 (对照组)
        s_bo = get_node_stats(cli)
        print(f'[v] A. BO INIT: {json.dumps(s_bo, ensure_ascii=False)}')
        cli.screenshot(str(output_dir / 'A_bo_init.png'))

        # B. 切到服务模块图
        print('[v] Step 3: 图表类型 业务对象图 -> 服务模块图')
        r1 = select_option(cli, '.cmt-select:nth-of-type(1)', '服务模块图')
        print(f'[v] {r1}')
        s_sm = get_node_stats(cli)
        print(f'[v] B. SM INIT: {json.dumps(s_sm, ensure_ascii=False)}')
        cli.screenshot(str(output_dir / 'B_sm_init.png'))

        # C. SM 图切换配色
        print('[v] Step 4: SM 图配色 默认 -> 鲜艳')
        r2 = select_option(cli, '.cmt-select:nth-of-type(3)', '鲜艳')
        print(f'[v] {r2}')
        s_sm_v = get_node_stats(cli)
        print(f'[v] C. SM vibrant: {json.dumps(s_sm_v, ensure_ascii=False)}')
        cli.screenshot(str(output_dir / 'C_sm_vibrant.png'))

        # D. SM 图切换颜色分组
        print('[v] Step 5: SM 图颜色分组 按领域 -> 按服务模块')
        r3 = select_option(cli, '.cmt-select:nth-of-type(2)', '按服务模块')
        print(f'[v] {r3}')
        s_sm_g = get_node_stats(cli)
        print(f'[v] D. SM serviceModule: {json.dumps(s_sm_g, ensure_ascii=False)}')
        cli.screenshot(str(output_dir / 'D_sm_group.png'))

        print()
        print('========== 结论 ==========')
        bo_ok = (s_bo.get('distinct') or 0) > 1
        print(f'A. BO 图初始分组色 (对照)            : {"PASS" if bo_ok else "FAIL"}')
        sm_gray = (s_sm.get('lightGray') or 0) > (s_sm.get('total') or 1) * 0.5
        print(f'B. SM 图初始 浅灰节点占比 {s_sm.get("lightGray")}/{s_sm.get("total")}   : {"REPRODUCED (浅灰)" if sm_gray else "彩色"}')
        sm_v_ok = s_sm.get('fills') != s_sm_v.get('fills')
        print(f'C. SM 图切换配色联动变色             : {"PASS" if sm_v_ok else "FAIL"}')
        sm_g_ok = s_sm_v.get('fills') != s_sm_g.get('fills')
        print(f'D. SM 图切换颜色分组联动变色         : {"PASS" if sm_g_ok else "FAIL"}')

        errors = [l for l in console_msgs if '[error]' in l.lower() or '[pageerror]' in l.lower()]
        print(f'\n[v] console errors ({len(errors)} 条):')
        for log in errors[-15:]:
            print(f'  {log[:400]}')
        (output_dir / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')
        print(f'\n[v] 输出保存到 {output_dir}')


if __name__ == '__main__':
    main()
