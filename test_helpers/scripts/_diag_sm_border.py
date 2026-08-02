"""_diag_sm_border.py - 检查 SM 图中心模块 rect 的实际边框样式 (2026-08-02)"""
import sys
import json
import base64
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI


def main():
    scope = {
        'sub_domain': [299],
        'business_object': [3220, 3218, 3221, 2797, 2788, 2793, 1839, 2896, 3219, 2784,
                            2792, 2781, 2779, 1838, 2780, 2795, 2794, 1637, 2789, 2777,
                            2778, 2782, 2785, 1636, 2796, 2783, 2790, 2791, 2786, 2787]
    }
    scope_b64 = base64.b64encode(json.dumps(scope).encode('utf-8')).decode('ascii')

    with PlaywrightCLI(headless=True) as cli:
        cli.goto('http://localhost:3005/api/v1/auth/dev-login?username=admin', wait_until='domcontentloaded')
        cli.wait_for_timeout(1500)
        url = f'http://localhost:3005/system/archdata?shortcut=1&productCode=TTTTT000&versionId=863&scope={scope_b64}&scopeType=all&viewMode=chart'
        cli.goto(url, wait_until='domcontentloaded')
        cli.wait_for_timeout(20000)

        cli.click('.cmt-select:nth-of-type(1)', timeout=5000)
        cli.wait_for_timeout(800)
        cli.evaluate("""() => {
            const p = Array.from(document.querySelectorAll('body .el-select-dropdown')).filter(x => x.getBoundingClientRect().height > 0).sort((a,b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)[0]
            const it = p ? Array.from(p.querySelectorAll('.el-select-dropdown__item')).find(i => i.textContent.includes('服务模块图')) : null
            if (it) it.click()
            return it ? 'ok' : 'miss'
        }""")
        cli.wait_for_timeout(6000)

        info = cli.evaluate("""() => {
            const svg = Array.from(document.querySelectorAll('.mermaid-container svg')).find(s => s.classList.contains('flowchart'))
            if (!svg) return { error: 'no svg' }
            const targets = ['SNPSP', 'PUM', 'SMKQM']
            const out = {}
            targets.forEach(code => {
                const g = svg.querySelector('g.node[id^="flowchart-' + code + '-"], g.node[data-code="' + code + '"]')
                if (!g) { out[code] = { error: 'node not found' }; return }
                const rect = g.querySelector('rect')
                out[code] = {
                    rectHTML: rect.outerHTML.slice(0, 350),
                    styleDash: rect.style.strokeDasharray || '',
                    attrDash: rect.getAttribute('stroke-dasharray') || '',
                    styleStroke: rect.style.stroke || rect.getAttribute('stroke'),
                    styleStrokeWidth: rect.style.strokeWidth || rect.getAttribute('stroke-width')
                }
            })
            return out
        }""")
        print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
