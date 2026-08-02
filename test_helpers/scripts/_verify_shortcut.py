"""
verify_shortcut_code_support.py - 验证 useVersionContext productCode/versionCode 支持

验证步骤:
1. 启动 dev server (already done)
2. 用 shortcut_chart_view 直接跳转 (productCode + versionId)
3. 检查 versionContext 是否被正确设置
4. 检查 EmbeddedChartView 是否渲染
5. 截图保存
"""

import sys
import os
import json
import base64
import time
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI


def main():
    base_url = 'http://localhost:3005'
    output_dir = Path('test_helpers/scripts/_verify_out')
    output_dir.mkdir(parents=True, exist_ok=True)

    # 准备 scope (DEFAULT_SCOPE = 30 个 BO 触发复杂图)
    scope = {
        'sub_domain': [299],
        'business_object': [3220, 3218, 3221, 2797, 2788, 2793, 1839, 2896, 3219, 2784,
                          2792, 2781, 2779, 1838, 2780, 2795, 2794, 1637, 2789, 2777,
                          2778, 2782, 2785, 1636, 2796, 2783, 2790, 2791, 2786, 2787]
    }
    scope_b64 = base64.b64encode(json.dumps(scope).encode('utf-8')).decode('ascii')

    # 准备 scope 2 (短)
    scope2 = {'sub_domain': [299], 'business_object': [3220]}
    scope_b64_2 = base64.b64encode(json.dumps(scope2).encode('utf-8')).decode('ascii')

    with PlaywrightCLI(headless=True) as cli:
        # 收集 console 消息 (lazy init - _page 是 None 直到首次 _ensure_browser)
        console_msgs = []

        # Step 1: dev-login
        print('[verify] Step 1: dev-login')
        cli.goto(f"{base_url}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
        cli.wait_for_timeout(1500)

        # 现在 _page 已初始化, 装 listener
        cli._page.on('console', lambda msg: console_msgs.append(f'[{msg.type}] {msg.text}'))
        cli._page.on('pageerror', lambda err: console_msgs.append(f'[ERROR] {err}'))

        # Step 2: 找 productCode + versionId (int) 测试
        print('[verify] Step 2: 用 productCode=TTTTT000&versionId=863 shortcut')
        # 注: 我用一个可能不存在的 versionId 来触发查找路径
        # 这里用 863 + 'TTTTT000' 是 chart_diag.py 默认值
        url = f"{base_url}/system/archdata?shortcut=1&productCode=TTTTT000&versionId=863&scope={scope_b64}"
        cli.goto(url, wait_until="domcontentloaded")
        cli.wait_for_timeout(15000)  # 等 versionContext 初始化 + shortcut apply + mermaid 渲染

        # 检查 console logs
        print(f'[verify] recent console logs ({len(console_msgs)} 条):')
        for log in console_msgs[-25:]:
            print(f'  {log[:300]}')

        # Step 3: 检查 versionContext
        print('[verify] Step 3: 检查 versionContext')
        version_state = cli.evaluate("""() => {
            if (!window.__archPage || !window.__archPage.versionContext) return { error: 'no __archPage.versionContext' }
            const v = window.__archPage.versionContext
            return {
                selectedProductId: v.selectedProductId?.value ?? v.selectedProductId,
                selectedVersionId: v.selectedVersionId?.value ?? v.selectedVersionId,
                selectedProduct: v.selectedProduct?.value ?? v.selectedProduct,
                selectedVersion: v.selectedVersion?.value ?? v.selectedVersion,
                productsLoaded: (v.products?.value || v.products || []).length,
                versionsLoaded: (v.versions?.value || v.versions || []).length,
            }
        }""")
        print(f'[verify] versionContext state: {json.dumps(version_state, indent=2, ensure_ascii=False)}')

        # Step 4: 检查是否已切到 chart 视图
        print('[verify] Step 4: 检查 viewMode')
        view_mode = cli.evaluate("""() => {
            // 检查是否有 embedded-chart-view
            const embeddedChart = document.querySelector('.embedded-chart-view')
            const archSwitcher = document.querySelector('.arch-data-chart-switcher')
            const mermaidContainer = document.querySelector('.mermaid-container')
            const svgNode = document.querySelectorAll('svg g.node').length
            return {
                hasEmbeddedChart: !!embeddedChart,
                hasArchSwitcher: !!archSwitcher,
                hasMermaidContainer: !!mermaidContainer,
                svgNodeCount: svgNode,
                url: location.href,
            }
        }""")
        print(f'[verify] view state: {json.dumps(view_mode, indent=2, ensure_ascii=False)}')

        # Step 5: 截图
        screenshot_path = output_dir / 'shortcut_code_verify.png'
        cli.screenshot(str(screenshot_path))
        print(f'[verify] 截图: {screenshot_path}')

        # Step 6: 检查 page.canShowChart + shortcut 链路
        print('[verify] Step 6: 检查 chart button + shortcut 应用情况')
        chart_btn = cli.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('.global-toolbar .el-button'))
            for (const b of btns) {
                const t = (b.textContent || '').trim()
                if (t.includes('图表') || t.includes('列表') || t.includes('Chart')) {
                    return {
                        text: t,
                        disabled: b.disabled,
                        active: b.classList.contains('is-active'),
                    }
                }
            }
            return null
        }""")

        # 详细看 __archPage 的 canShowChart + scopeIds 状态
        page_state = cli.evaluate("""() => {
            if (!window.__archPage) return { error: 'no __archPage' }
            return {
                canShowChart: window.__archPage.canShowChart?.value ?? window.__archPage.canShowChart,
                hasScopeSelection: window.__archPage.hasScopeSelection?.value ?? window.__archPage.hasScopeSelection,
                scopeIds: window.__archPage.scopeIds?.value ?? window.__archPage.scopeIds,
                selectedVersionId: window.__archPage.versionContext?.selectedVersionId?.value ?? window.__archPage.versionContext?.selectedVersionId,
                selectedProductId: window.__archPage.versionContext?.selectedProductId?.value ?? window.__archPage.versionContext?.selectedProductId,
            }
        }""")
        print(f'[verify] page state: {json.dumps(page_state, indent=2, ensure_ascii=False)}')
        print(f'[verify] chart button: {chart_btn}')

        # 总结
        print('\n[verify] === 验证总结 (scenario 1: productCode + versionId) ===')
        if version_state.get('selectedVersionId'):
            print('[verify] ✓ versionContext.selectedVersionId 已设置')
        else:
            print('[verify] ✗ versionContext.selectedVersionId 未设置 (FAIL)')

        if view_mode.get('hasEmbeddedChart'):
            print('[verify] ✓ EmbeddedChartView 已渲染')
        else:
            print('[verify] ✗ EmbeddedChartView 未渲染 (FAIL)')

        if view_mode.get('svgNodeCount', 0) > 0:
            print(f'[verify] ✓ svg g.node 渲染 ({view_mode["svgNodeCount"]} 个)')
        else:
            print('[verify] ✗ svg g.node 未渲染')

        # ===== scenario 2: productCode + versionCode (新功能) =====
        print('\n[verify] === scenario 2: productCode=TTTTT000&versionCode=V11 ===')
        console_msgs.clear()
        url2 = f"{base_url}/system/archdata?shortcut=1&productCode=TTTTT000&versionCode=V11&scope={scope_b64_2}"
        cli.goto(url2, wait_until="domcontentloaded")
        cli.wait_for_timeout(15000)  # 等 mermaid 渲染完成

        version_state2 = None
        for retry in range(3):
            try:
                version_state2 = cli.evaluate("""() => {
                    if (!window.__archPage || !window.__archPage.versionContext) return { error: 'no versionContext' }
                    const v = window.__archPage.versionContext
                    return {
                        selectedProductId: v.selectedProductId?.value ?? v.selectedProductId,
                        selectedVersionId: v.selectedVersionId?.value ?? v.selectedVersionId,
                        selectedVersion: v.selectedVersion?.value ?? v.selectedVersion,
                    }
                }""")
                break
            except Exception as e:
                print(f'[verify] scenario 2 evaluate retry {retry}: {e}')
                cli.wait_for_timeout(3000)
        if version_state2 is None:
            version_state2 = {'error': 'evaluation failed'}
        print(f'[verify] scenario 2 versionContext: {json.dumps(version_state2, ensure_ascii=False)}')

        view_mode2 = None
        for retry in range(3):
            try:
                view_mode2 = cli.evaluate("""() => ({
                    hasEmbeddedChart: !!document.querySelector('.embedded-chart-view'),
                    svgNodeCount: document.querySelectorAll('svg g.node').length,
                })""")
                break
            except Exception as e:
                print(f'[verify] scenario 2 view evaluate retry {retry}: {e}')
                cli.wait_for_timeout(3000)
        if view_mode2 is None:
            view_mode2 = {'svgNodeCount': 0, 'hasEmbeddedChart': False}
        print(f'[verify] scenario 2 view: {view_mode2}')

        if view_mode2.get('svgNodeCount', 0) > 0:
            print(f'[verify] ✓ scenario 2: svg g.node 渲染 ({view_mode2["svgNodeCount"]} 个)')
            screenshot_path2 = output_dir / 'shortcut_vc_verify.png'
            cli.screenshot(str(screenshot_path2))
            print(f'[verify] scenario 2 截图: {screenshot_path2}')
        else:
            print('[verify] ✗ scenario 2: 未渲染')

        # 截 scenario 1 截图
        screenshot_path1 = output_dir / 'shortcut_code_verify.png'
        cli.screenshot(str(screenshot_path1))


if __name__ == '__main__':
    main()