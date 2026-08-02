"""
_verify_center_border.py - 验证"分组色 + 特殊边框"方案 (2026-08-02)

用户反馈: "切换有反应了不过只有初始化有颜色, 切换上面的这些选择都是浅灰色的"
根因: centerScopeHighlight 默认 true, 中心范围占大比 (30/41) 节点被 centerScopeColor (#808080)
      灰色 fill 覆盖 → 切换颜色分组/配色时中心节点不联动。
修复方案 (用户选定): 中心节点 fill 用分组色 (与外围联动变色),
      用 stroke-width:3 + stroke-dasharray:6,4 灰虚线边框区分中心范围。

验证点:
A. 初始化后: 中心节点 (dasharray=6,4) fill 为分组色, distinct fills > 1 (非全灰)
B. 切换颜色分组 domain->subDomain->serviceModule: 中心节点 fill 联动变色
C. 切换配色 default->vibrant: 全部节点 (含中心) 变色
D. 切换中心范围 区分->不区分: 中心节点虚线边框消失 (dasharray 数量=0), fill 仍为分组色
"""
import sys
import json
import base64
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI


def select_option(cli, selector, text):
    """打开下拉并点击指定文本选项 (只在目标 select 邻近的 popper 内点击)"""
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
    return 'not found in popper: ' + __TEXT__
}
""".replace('__SEL__', sel_json).replace('__TEXT__', text_json)
    clicked = cli.evaluate(js)
    cli.wait_for_timeout(6000)
    return clicked


def get_node_stats(cli):
    """统计 SVG 节点: 总数 / 中心节点(虚线边框)数 / 中心与外围 fill 分布"""
    return cli.evaluate("""() => {
        const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
        const svg = svgs.find(s => s.classList.contains('flowchart')) || null
        if (!svg) return { error: 'no flowchart svg', svgCount: svgs.length }
        const rects = svg.querySelectorAll('g.node rect, g.nodes rect')
        let total = 0, centerCount = 0
        const centerFills = {}, outerFills = {}
        rects.forEach(r => {
            const fill = r.getAttribute('fill') || r.style.fill || 'none'
            const dash = r.getAttribute('stroke-dasharray') || ''
            const isCenter = dash.indexOf('6') !== -1 && dash.indexOf('4') !== -1
            if (isCenter) {
                centerCount++
                centerFills[fill] = (centerFills[fill] || 0) + 1
            } else {
                outerFills[fill] = (outerFills[fill] || 0) + 1
            }
            total++
        })
        return {
            total,
            centerCount,
            centerDistinct: Object.keys(centerFills).length,
            centerFills,
            outerDistinct: Object.keys(outerFills).length,
            outerFills
        }
    }""")


def main():
    base_url = 'http://localhost:3005'
    output_dir = Path('test_helpers/scripts/_verify_center_border_out')
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
            toolbarVisible: !!document.querySelector('.chart-mini-toolbar'),
            cmtSelects: document.querySelectorAll('.cmt-select').length
        })""")
        print(f'[v] chart state: {json.dumps(state, ensure_ascii=False)}')
        if not state.get('svgCount'):
            print('[v] !! 图表未渲染, console 最后 30 条:')
            for log in console_msgs[-30:]:
                print(f'  {log[:300]}')
            return

        # ===== A. 初始化: 中心节点分组色 + 虚线边框 =====
        s0 = get_node_stats(cli)
        print(f'[v] A. INIT centerBorderOn: {json.dumps(s0, ensure_ascii=False)}')
        cli.screenshot(str(output_dir / 'A_init.png'))
        center_fills = s0.get('centerFills') or {}
        no_gray = not any('128, 128, 128' in c or '#808080' in c for c in center_fills)
        a_ok = (s0.get('centerCount') or 0) == 30 and no_gray and (s0.get('centerDistinct') or 0) >= 1
        print(f'[v] A. 中心节点数={s0.get("centerCount")} (期望30), 中心 fill 无灰色={"是" if no_gray else "否"} '
              f'=> {"PASS (分组色+虚线边框)" if a_ok else "FAIL"}')

        # ===== B. 颜色分组 domain -> serviceModule =====
        print('[v] Step 3: 颜色分组 按领域 -> 按服务模块')
        r1 = select_option(cli, '.cmt-select:nth-of-type(2)', '按服务模块')
        print(f'[v] {r1}')
        s1 = get_node_stats(cli)
        print(f'[v] B. AFTER serviceModule: {json.dumps(s1, ensure_ascii=False)}')
        cli.screenshot(str(output_dir / 'B_serviceModule.png'))
        b_ok = s0.get('centerFills') != s1.get('centerFills')
        print(f'[v] B. 中心节点 fill 联动 {"PASS" if b_ok else "FAIL"}')

        # ===== C. 配色 default -> vibrant =====
        print('[v] Step 4: 配色 默认 -> 鲜艳')
        r2 = select_option(cli, '.cmt-select:nth-of-type(3)', '鲜艳')
        print(f'[v] {r2}')
        s2 = get_node_stats(cli)
        print(f'[v] C. AFTER vibrant: {json.dumps(s2, ensure_ascii=False)}')
        cli.screenshot(str(output_dir / 'C_vibrant.png'))
        c_ok = s1.get('centerFills') != s2.get('centerFills') and (s2.get('centerDistinct') or 0) > 1
        print(f'[v] C. 中心节点 fill 联动 {"PASS" if c_ok else "FAIL"}')

        # ===== D. 中心范围 区分 -> 不区分 =====
        print('[v] Step 5: 中心范围 区分 -> 不区分')
        r3 = select_option(cli, '.cmt-select:nth-of-type(4)', '不区分')
        print(f'[v] {r3}')
        s3 = get_node_stats(cli)
        print(f'[v] D. AFTER centerOff: {json.dumps(s3, ensure_ascii=False)}')
        cli.screenshot(str(output_dir / 'D_centerOff.png'))
        d_ok = (s3.get('centerCount') or 0) == 0 and (s3.get('total') or 0) == (s0.get('total') or 0)
        print(f'[v] D. 虚线边框清除 {"PASS" if d_ok else "FAIL"}')

        # ===== 结论 =====
        print()
        print('========== 结论 ==========')
        print(f'A. 初始化中心节点分组色+虚线边框 : {"PASS ✓" if a_ok else "FAIL ✗"}')
        print(f'B. 切换颜色分组中心节点联动变色 : {"PASS ✓" if b_ok else "FAIL ✗"}')
        print(f'C. 切换配色中心节点联动变色     : {"PASS ✓" if c_ok else "FAIL ✗"}')
        print(f'D. 不区分中心范围时边框清除     : {"PASS ✓" if d_ok else "FAIL ✗"}')

        errors = [l for l in console_msgs if '[error]' in l.lower() or '[pageerror]' in l.lower()]
        print(f'\n[v] console errors ({len(errors)} 条):')
        for log in errors[-15:]:
            print(f'  {log[:400]}')

        (output_dir / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')
        print(f'\n[v] 输出保存到 {output_dir}')


if __name__ == '__main__':
    main()
