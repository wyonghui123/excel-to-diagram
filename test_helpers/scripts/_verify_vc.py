"""Test scenario 2 only - productCode + versionCode."""
import sys
import os
import json
import base64
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI


def main():
    base_url = 'http://localhost:3005'
    output_dir = Path('test_helpers/scripts/_verify_out')
    output_dir.mkdir(parents=True, exist_ok=True)

    # 短 scope
    scope = {'sub_domain': [299], 'business_object': [3220]}
    scope_b64 = base64.b64encode(json.dumps(scope).encode('utf-8')).decode('ascii')

    with PlaywrightCLI(headless=True) as cli:
        console_msgs = []
        # Step 1: dev-login
        cli.goto(f"{base_url}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
        cli.wait_for_timeout(1500)
        cli._page.on('console', lambda msg: console_msgs.append(f'[{msg.type}] {msg.text}'))
        cli._page.on('pageerror', lambda err: console_msgs.append(f'[ERROR] {err}'))

        # Step 2: 用 productCode + versionCode (新功能)
        print('[verify_vc] 跳转 productCode=TTTTT000&versionCode=V11')
        url = f"{base_url}/system/archdata?shortcut=1&productCode=TTTTT000&versionCode=V11&scope={scope_b64}"
        cli.goto(url, wait_until="domcontentloaded")
        cli.wait_for_timeout(8000)  # 等 mermaid 渲染
        # 等页面稳定 (没有 navigation)
        cli.wait_for_timeout(5000)

        version_state = cli.evaluate("""() => {
            if (!window.__archPage || !window.__archPage.versionContext) return { error: 'no versionContext' }
            const v = window.__archPage.versionContext
            return {
                selectedProductId: v.selectedProductId?.value ?? v.selectedProductId,
                selectedVersionId: v.selectedVersionId?.value ?? v.selectedVersionId,
                selectedVersion: v.selectedVersion?.value ?? v.selectedVersion,
            }
        }""")
        print(f'[verify_vc] versionContext: {json.dumps(version_state, ensure_ascii=False)}')

        view = cli.evaluate("""() => ({
            hasEmbeddedChart: !!document.querySelector('.embedded-chart-view'),
            hasArchSwitcher: !!document.querySelector('.arch-data-chart-switcher'),
            svgNodeCount: document.querySelectorAll('svg g.node').length,
            url: location.href,
        })""")
        print(f'[verify_vc] view: {view}')

        if view.get('svgNodeCount', 0) > 0:
            print(f'[verify_vc] ✓ svg g.node 渲染 ({view["svgNodeCount"]} 个)')
            cli.screenshot(str(output_dir / 'shortcut_vc_verify.png'))
        else:
            print('[verify_vc] ✗ 未渲染')
            cli.screenshot(str(output_dir / 'shortcut_vc_FAIL.png'))

        # 关键 logs
        print('\n[verify_vc] shortcut 相关 logs:')
        for log in console_msgs[-30:]:
            if 'shortcut' in log.lower() or 'version' in log.lower():
                print(f'  {log[:300]}')


if __name__ == '__main__':
    main()