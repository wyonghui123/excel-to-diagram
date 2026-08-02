"""
_dump_svg.py - dump 图表 SVG 结构，确认 mermaid 11.13 节点 DOM 格式
用于定位 updateNodeColors 颜色选择器匹配失败问题
"""

import sys
import json
import base64
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI


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
        cli.goto(f"{base_url}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
        cli.wait_for_timeout(1500)

        url = f"{base_url}/system/archdata?shortcut=1&productCode=TTTTT000&versionId=863&scope={scope_b64}&scopeType=all&viewMode=chart"
        cli.goto(url, wait_until="domcontentloaded")
        cli.wait_for_timeout(20000)

        # 1. SVG 结构分析 (选择真正的 mermaid 图表 svg)
        svg_info = cli.evaluate("""() => {
            const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
            // 排除 icon svg (16x16), 选最大的 (图表 svg)
            const realSvg = svgs.filter(s => {
                const vb = (s.getAttribute('viewBox') || '').split(' ')
                return !(vb.length === 4 && vb[2] === '16' && vb[3] === '16')
            })[0] || svgs[svgs.length - 1] || null
            if (!realSvg) return { error: 'no svg' }
            const allG = Array.from(realSvg.querySelectorAll('g'))
            const nodeLike = allG.filter(g => g.id && g.id.includes('flowchart'))
            const rects = Array.from(realSvg.querySelectorAll('rect'))
            return {
                svgClass: realSvg.getAttribute('class'),
                svgViewBox: realSvg.getAttribute('viewBox'),
                totalG: allG.length,
                flowchartGCount: nodeLike.length,
                sampleNodeIds: nodeLike.slice(0, 3).map(g => g.id),
                sampleNodeClasses: nodeLike.slice(0, 3).map(g => g.getAttribute('class')),
                totalRects: rects.length,
                sampleRects: rects.slice(0, 8).map(r => ({
                    parent: r.parentElement?.tagName,
                    parentId: r.parentElement?.id,
                    parentClass: r.parentElement?.getAttribute('class'),
                    fill: r.getAttribute('fill'),
                    dataCode: r.getAttribute('data-code')
                })),
                hasDataCode: !!realSvg.querySelector('[data-code]'),
                dataCodeSamples: Array.from(realSvg.querySelectorAll('[data-code]')).slice(0, 3).map(el => ({
                    tag: el.tagName,
                    id: el.id,
                    dataCode: el.getAttribute('data-code')
                }))
            }
        }""")
        print('[verify] SVG structure:')
        print(json.dumps(svg_info, indent=2, ensure_ascii=False))

        # 2. 检查 window.__archPage 里有没有 nodeColorMappings
        mappings = cli.evaluate("""() => {
            const ap = window.__archPage
            if (!ap) return { error: 'no __archPage' }
            return {
                keys: Object.keys(ap),
                mermaidKeys: ap.mermaid ? Object.keys(ap.mermaid) : []
            }
        }""")
        print('\n[verify] __archPage keys:', json.dumps(mappings, ensure_ascii=False))

        # 3. 检查页面里是否有 store 暴露 colorGroupBy
        store_state = cli.evaluate("""() => {
            // 尝试通过 DOM 上的 Vue 组件实例拿 store
            const el = document.querySelector('.embedded-chart-view')
            if (!el || !el.__vueParentComponent) return { error: 'no vue instance' }
            // 向上找 RelationshipManagement
            let comp = el.__vueParentComponent
            let found = null
            while (comp) {
                if (comp.setupState && comp.setupState.chartConfig) {
                    found = {
                        name: comp.type?.name || comp.type?.__name,
                        chartConfig: JSON.parse(JSON.stringify(comp.setupState.chartConfig))
                    }
                    break
                }
                comp = comp.parent
            }
            return found || { error: 'no chartConfig found' }
        }""")
        print('\n[verify] chartConfig from vue instance:', json.dumps(store_state, indent=2, ensure_ascii=False))

        # 4. 保存一段 SVG 片段
        svg_html = cli.evaluate("""() => {
            const svg = document.querySelector('.mermaid-container svg')
            return svg ? svg.outerHTML.slice(0, 3000) : 'no svg'
        }""")
        (output_dir / 'svg_sample.txt').write_text(svg_html, encoding='utf-8')
        print(f'\n[verify] svg sample saved ({len(svg_html)} chars)')


if __name__ == '__main__':
    main()
