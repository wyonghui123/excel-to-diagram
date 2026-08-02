"""
_verify_color_switch.py - 验证图表 toolbar 切换"颜色分组/配色/中心范围"是否生效

[FIX 2026-08-02] 点击选项必须限定在目标 select 邻近的 popper 内:
   el-select 的所有下拉在页面加载时都挂载在 body (display:block),
   用全局 querySelectorAll('.el-select-dropdown__item') 点击会把其他隐藏
   下拉的同名选项也点掉 (例如"服务模块图"把 chartType 改掉) → 验证污染。

步骤:
1. dev-login
2. shortcut 进入图表视图 (productCode + versionId)
3. 读取切换前 SVG 节点颜色分布 (统计 distinct fill)
4. 通过 toolbar 切换颜色分组 domain -> subDomain -> serviceModule
5. 读取切换后颜色分布
6. 对比: 若无变化 -> 复现 bug; 有变化 -> 正常
7. 输出 console 错误
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
    // 找距 anchor 最近且有尺寸的 popper
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
            return 'clicked: ' + it.textContent.trim() + ' (popper items: ' + Array.from(items).map(i => i.textContent.trim()).join('/') + ')'
        }
    }
    return 'not found in popper: ' + __TEXT__
}
""".replace('__SEL__', sel_json).replace('__TEXT__', text_json)
    clicked = cli.evaluate(js)
    cli.wait_for_timeout(6000)
    return clicked


def get_color_stats(cli):
    """统计 SVG 中节点 rect 的 fill 颜色分布 (选择真正的 flowchart svg)"""
    return cli.evaluate("""() => {
        const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
        const svg = svgs.find(s => s.classList.contains('flowchart')) || null
        if (!svg) return { error: 'no flowchart svg', svgCount: svgs.length }
        const rects = svg.querySelectorAll('g.node rect, g.nodes rect')
        const colors = {}
        let total = 0
        rects.forEach(r => {
            const fill = r.getAttribute('fill') || r.style.fill || 'none'
            colors[fill] = (colors[fill] || 0) + 1
            total++
        })
        return { total, distinctColors: Object.keys(colors).length, colors }
    }""")


def get_store(cli):
    return cli.evaluate("""() => {
        const cs = window.__configStore
        if (!cs) return { error: 'no __configStore' }
        return {
            chartType: cs.chartType?.value ?? cs.chartType,
            colorGroupBy: cs.colorGroupBy?.value ?? cs.colorGroupBy,
            colorScheme: cs.colorScheme?.value ?? cs.colorScheme,
            centerScopeHighlight: cs.centerScopeHighlight?.value ?? cs.centerScopeHighlight
        }
    }""")


def main():
    base_url = 'http://localhost:3005'
    output_dir = Path('test_helpers/scripts/_verify_color_out')
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

        print('[verify] Step 1: dev-login')
        cli.goto(f"{base_url}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
        cli.wait_for_timeout(1500)
        cli._page.on('console', lambda msg: console_msgs.append(f'[{msg.type}] {msg.text}'))
        cli._page.on('pageerror', lambda err: console_msgs.append(f'[PAGEERROR] {err}'))

        print('[verify] Step 2: shortcut 进入图表视图')
        url = f"{base_url}/system/archdata?shortcut=1&productCode=TTTTT000&versionId=863&scope={scope_b64}&scopeType=all&viewMode=chart"
        cli.goto(url, wait_until="domcontentloaded")
        cli.wait_for_timeout(20000)

        state = cli.evaluate("""() => ({
            hasChart: !!document.querySelector('.embedded-chart-view'),
            svgCount: document.querySelectorAll('.mermaid-container svg').length,
            nodeCount: document.querySelectorAll('.mermaid-container svg g.node').length,
            toolbarVisible: !!document.querySelector('.chart-mini-toolbar'),
            cmtSelects: document.querySelectorAll('.cmt-select').length
        })""")
        print(f'[verify] chart state: {json.dumps(state, indent=2, ensure_ascii=False)}')
        if not state.get('svgCount'):
            print('[verify] !! 图表未渲染, 打印 console 最后 30 条:')
            for log in console_msgs[-30:]:
                print(f'  {log[:300]}')
            return

        # ===== 1. 颜色分组 domain -> subDomain -> serviceModule =====
        before = get_color_stats(cli)
        store0 = get_store(cli)
        print(f'[verify] store0: {json.dumps(store0, ensure_ascii=False)}')
        print(f'[verify] BEFORE colorGroupBy=domain: {json.dumps(before, ensure_ascii=False)}')
        cli.screenshot(str(output_dir / 'before_domain.png'))

        print('[verify] Step 3: 颜色分组 domain -> subDomain')
        r1 = select_option(cli, '.cmt-select:nth-of-type(2)', '按子领域')
        print(f'[verify] {r1}')
        after_sub = get_color_stats(cli)
        store1 = get_store(cli)
        print(f'[verify] store after subDomain: {json.dumps(store1, ensure_ascii=False)}')
        print(f'[verify] AFTER colorGroupBy=subDomain: {json.dumps(after_sub, ensure_ascii=False)}')

        print('[verify] Step 3b: 颜色分组 subDomain -> serviceModule')
        r2 = select_option(cli, '.cmt-select:nth-of-type(2)', '按服务模块')
        print(f'[verify] {r2}')
        after_sm = get_color_stats(cli)
        store2 = get_store(cli)
        print(f'[verify] store after serviceModule: {json.dumps(store2, ensure_ascii=False)}')
        print(f'[verify] AFTER colorGroupBy=serviceModule: {json.dumps(after_sm, ensure_ascii=False)}')
        cli.screenshot(str(output_dir / 'after_serviceModule.png'))

        # ===== 2. 配色 default -> vibrant =====
        print('[verify] Step 4: 配色 default -> vibrant')
        r3 = select_option(cli, '.cmt-select:nth-of-type(3)', '鲜艳')
        print(f'[verify] {r3}')
        after_vibrant = get_color_stats(cli)
        store3 = get_store(cli)
        print(f'[verify] store after vibrant: {json.dumps(store3, ensure_ascii=False)}')
        print(f'[verify] AFTER colorScheme=vibrant: {json.dumps(after_vibrant, ensure_ascii=False)}')
        cli.screenshot(str(output_dir / 'after_vibrant.png'))

        # ===== 3. 中心范围 区分 -> 不区分 =====
        print('[verify] Step 5: 中心范围 区分 -> 不区分')
        r4 = select_option(cli, '.cmt-select:nth-of-type(4)', '不区分')
        print(f'[verify] {r4}')
        after_center = get_color_stats(cli)
        store4 = get_store(cli)
        print(f'[verify] store after centerOff: {json.dumps(store4, ensure_ascii=False)}')
        print(f'[verify] AFTER centerScopeHighlight=false: {json.dumps(after_center, ensure_ascii=False)}')
        cli.screenshot(str(output_dir / 'after_centerOff.png'))

        # ===== 对比结论 =====
        print()
        print('========== 对比结论 ==========')
        print(f'domain        : distinct={before.get("distinctColors")} total={before.get("total")}')
        print(f'subDomain     : distinct={after_sub.get("distinctColors")} total={after_sub.get("total")}')
        print(f'serviceModule : distinct={after_sm.get("distinctColors")} total={after_sm.get("total")}')
        print(f'vibrant       : distinct={after_vibrant.get("distinctColors")} total={after_vibrant.get("total")}')
        print(f'centerOff     : distinct={after_center.get("distinctColors")} total={after_center.get("total")}')

        changed_group = before.get('colors') != after_sm.get('colors') or before.get('total') != after_sm.get('total')
        changed_scheme = after_sm.get('colors') != after_vibrant.get('colors')
        changed_center = after_vibrant.get('colors') != after_center.get('colors')
        print(f'颜色分组切换 {"生效 ✓" if changed_group else "无效 ✗"}')
        print(f'配色切换 {"生效 ✓" if changed_scheme else "无效 ✗"}')
        print(f'中心范围切换 {"生效 ✓" if changed_center else "无效 ✗"}')

        errors = [l for l in console_msgs if '[error]' in l.lower() or '[pageerror]' in l.lower()]
        print(f'\n[verify] console errors ({len(errors)} 条):')
        for log in errors[-15:]:
            print(f'  {log[:400]}')

        (output_dir / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')
        print(f'\n[verify] 输出保存到 {output_dir}')


if __name__ == '__main__':
    main()
