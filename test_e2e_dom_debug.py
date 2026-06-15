"""Debug: 详细检查 DOM 状态 - data-relation-code, data-bidirectional, path 结构"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        await page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")

        products_resp = await page.request.get("http://localhost:3010/api/v2/bo/product")
        products = await products_resp.json()
        product_list = products.get("data", {}).get("items", []) or products.get("data", [])

        version = None
        for prod in product_list[:10]:
            versions_resp = await page.request.get(
                f"http://localhost:3010/api/v2/bo/version?product_id={prod['id']}"
            )
            versions = await versions_resp.json()
            version_list = versions.get("data", {}).get("items", []) or versions.get("data", [])
            for v in version_list:
                version_id = v.get('id') if isinstance(v, dict) else v
                if not version_id:
                    continue
                preview_resp = await page.request.get(
                    f"http://localhost:3010/api/v2/bo/architecture/preview?version_id={version_id}"
                )
                preview = await preview_resp.json()
                if preview.get("success"):
                    data = preview.get("data", {})
                    if len(data.get("business_objects", [])) > 0 and len(data.get("relationships", [])) > 0:
                        version = {"id": version_id}
                        break
            if version:
                break

        if not version:
            print("❌ 没找到有数据的版本")
            await browser.close()
            return

        arch_data_resp = await page.request.get(
            f"http://localhost:3010/api/v2/bo/architecture/preview?version_id={version['id']}"
        )
        arch_data = (await arch_data_resp.json()).get("data", {})

        await page.goto("http://localhost:3004/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        arch_data_str = json.dumps(arch_data, ensure_ascii=False)
        await page.evaluate(f"""(data) => {{
            sessionStorage.setItem('archDataForDiagram', data.arch);
            sessionStorage.setItem('lastArchDataForDiagram', data.arch);
            sessionStorage.setItem('archDataCurrentStep', '2');
            sessionStorage.setItem('archDataChartType', 'businessObject');
        }}""", {"arch": arch_data_str})

        await page.evaluate("sessionStorage.setItem('archDataCurrentStep', '0')")
        await page.goto("http://localhost:3004/archdata-chart", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        await page.evaluate("""() => {
            const app = window.__diagramApp
            const rels = app.previewData?.value?.relationships || app.previewData?.relationships
            if (rels && rels.length > 0) {
                let r0 = rels[rels.length - 1]
                if (r0.relationDirection !== '双向') {
                    r0.relationDirection = '双向'
                    r0.relationType = 'CALLS'
                } else {
                    r0 = rels.find(r => r.relationDirection !== '双向')
                    if (r0) {
                        r0.relationDirection = '双向'
                        r0.relationType = 'CALLS'
                    }
                }
            }
            app.generateDiagram()
            if (app.currentStep && 'value' in app.currentStep) {
                app.currentStep.value = 2
            } else {
                app.currentStep = 2
            }
        }""")

        await page.wait_for_timeout(8000)

        result = await page.evaluate("""() => {
            const svg = document.querySelector('.mermaid-content svg')
            if (!svg) return { error: 'no svg' }

            // 1. 找所有 edgeLabel 的文本 + 父 g 的 data-relation-code
            const edgeLabels = Array.from(svg.querySelectorAll('.edgeLabel'))
            const labelInfo = edgeLabels.map((el, idx) => {
                const text = (el.textContent || '').trim()
                const g = el.closest('g')
                const dataRelCode = g ? g.getAttribute('data-relation-code') : null
                return { idx, text, dataRelCode }
            })

            // 2. 找双向 link (从 window.__diagramApp)
            const app = window.__diagramApp
            const links = app.diagramData?.value?.links || app.diagramData?.links || []
            const bidiLinks = links.filter(l => l.relationDirection === '双向')
            const bidiCodes = bidiLinks.map(l => l.relationCode)

            // 3. 找 data-bidirectional 属性
            const bidiPaths = Array.from(svg.querySelectorAll('path[data-bidirectional="true"]'))

            // 4. 找有 marker-start 的 path
            const markerStartPaths = Array.from(svg.querySelectorAll('path[marker-start]'))
            const bidiMarkerStart = markerStartPaths.filter(p => p.getAttribute('data-bidirectional') === 'true')

            // 5. 找所有 path (有 d 属性的)
            const allPaths = Array.from(svg.querySelectorAll('path[d]'))

            // 6. 列出所有唯一 text 内容
            const allTexts = [...new Set(labelInfo.map(l => l.text))]

            // 7. 找 CREATES text 是否在 label 中
            const createsMatch = labelInfo.filter(li => li.text.includes('CREATES') || li.text.includes('凭单'))
            const createsText = labelInfo.filter(li => li.text === 'CREATES')

            // 8. 找 bdi link 的 source/target 节点 path
            let bidiPathInfo = null
            if (bidiLinks.length > 0) {
                const bidi = bidiLinks[0]
                const sourceId = bidi.source
                const targetId = bidi.target
                // 找节点
                const sourceNodes = Array.from(svg.querySelectorAll('.node')).filter(n =>
                    (n.textContent || '').includes(bidi.sourceName || ''))
                const targetNodes = Array.from(svg.querySelectorAll('.node')).filter(n =>
                    (n.textContent || '').includes(bidi.targetName || ''))
                bidiPathInfo = {
                    source: bidi.source,
                    target: bidi.target,
                    sourceName: bidi.sourceName,
                    targetName: bidi.targetName,
                    relationCode: bidi.relationCode,
                    sourceNodeCount: sourceNodes.length,
                    targetNodeCount: targetNodes.length
                }
            }

            return {
                edgeLabelCount: edgeLabels.length,
                allTexts: allTexts.slice(0, 30),
                labelInfo: labelInfo.slice(0, 10),  // 前 10 个
                bidiCodes,
                bidiLinkCount: bidiLinks.length,
                bidiPathCount: bidiPaths.length,
                markerStartCount: markerStartPaths.length,
                bidiMarkerStartCount: bidiMarkerStart.length,
                allPathCount: allPaths.length,
                createsMatch,
                createsText,
                bidiPathInfo,
                linksTotal: links.length
            }
        }""")

        print("=" * 60)
        print(f"edgeLabel 总数: {result['edgeLabelCount']}")
        print(f"allPath 总数: {result['allPathCount']}")
        print(f"\n前 30 个唯一 edgeLabel text:")
        for t in result['allTexts'][:30]:
            print(f"  '{t}'")
        print(f"\n双向 link:")
        if result.get('bidiPathInfo'):
            for k, v in result['bidiPathInfo'].items():
                print(f"  {k}: {v}")
        print(f"\n'CREATES' 完整匹配的 edgeLabels: {len(result['createsText'])}")
        for ct in result['createsText'][:5]:
            print(f"  text='{ct['text']}', data-relation-code={ct['dataRelCode']}")
        print(f"\n包含 'CREATES' 或 '凭单' 的 edgeLabels: {len(result['createsMatch'])}")
        for ct in result['createsMatch'][:5]:
            print(f"  text='{ct['text']}', data-relation-code={ct['dataRelCode']}")
        print(f"\n前 10 个 edgeLabel 的 text + data-relation-code:")
        for li in result['labelInfo']:
            print(f"  [{li['idx']}] text='{li['text']}', data-relation-code={li['dataRelCode']}")
        print(f"\n双向 links 数量: {result['bidiLinkCount']}, codes={result['bidiCodes']}")
        print(f"data-bidirectional='true' path 数: {result['bidiPathCount']}")
        print(f"marker-start path 数: {result['markerStartCount']}")
        print(f"双向 + marker-start: {result['bidiMarkerStartCount']}")
        print(f"\n总 links: {result['linksTotal']}")

        # 寻找 bidi link 的 text 出现在 edgeLabels 中吗
        bidi_codes = result['bidiCodes']
        if bidi_codes:
            for code in bidi_codes:
                matches = [li for li in result['labelInfo'] if li['text'] == code]
                print(f"\n双向 code='{code}' 匹配到的 edgeLabel:")
                for m in matches:
                    print(f"  text='{m['text']}', data-relation-code={m['dataRelCode']}")

        await browser.close()


asyncio.run(main())
