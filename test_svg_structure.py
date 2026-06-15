"""看 mermaid 11 实际 SVG 结构"""
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
            const out = {}

            // 1. SVG 顶层结构
            out.svgChildren = Array.from(svg.children).map(c => ({
                tag: c.tagName,
                class: c.getAttribute('class'),
                childCount: c.children.length
            }))

            // 2. 找 g.root
            const gRoot = svg.querySelector('g.root')
            out.hasGRoot = !!gRoot
            if (gRoot) {
                out.gRootChildren = Array.from(gRoot.children).map(c => ({
                    tag: c.tagName,
                    class: c.getAttribute('class'),
                    childCount: c.children.length
                }))
            } else {
                // 看 svg 下第一层 g
                out.firstLevelG = Array.from(svg.querySelectorAll(':scope > g')).map(c => ({
                    class: c.getAttribute('class'),
                    childCount: c.children.length
                }))
                // 看其他可能的 root class
                out.svgChildrenTags = Array.from(svg.children).map(c => c.tagName + '.' + (c.getAttribute('class') || ''))
            }

            // 3. 找包含 CREATES 的 edgeLabel
            const edgeLabels = Array.from(svg.querySelectorAll('g.edgeLabel'))
            const createsEdgeLabels = edgeLabels.filter(el => (el.textContent || '').trim() === 'CREATES')

            out.edgeLabelCount = edgeLabels.length
            out.createsEdgeLabelCount = createsEdgeLabels.length
            if (createsEdgeLabels.length > 0) {
                out.createsEdgeLabels = createsEdgeLabels.map(el => ({
                    outerHTML: el.outerHTML.substring(0, 400),
                    parentClass: el.parentElement ? el.parentElement.getAttribute('class') : null,
                    closestG: el.closest('g') ? el.closest('g').getAttribute('class') : null
                }))
            }

            // 4. 找 bidi link
            const app = window.__diagramApp
            const links = app.diagramData?.value?.links || app.diagramData?.links || []
            const bidiIdx = links.findIndex(l => l.relationDirection === '双向')
            const bidi = bidiIdx >= 0 ? links[bidiIdx] : null
            out.bidiIdx = bidiIdx
            out.bidiCode = bidi?.relationCode

            return out
        }""")

        print("=" * 60)
        print(f"svgChildren: {result.get('svgChildren', [])}")
        print(f"hasGRoot: {result.get('hasGRoot')}")
        print(f"gRootChildren:")
        for c in result.get('gRootChildren', []):
            print(f"  {c}")
        if result.get('firstLevelG'):
            print(f"firstLevelG: {result.get('firstLevelG')}")
        if result.get('svgChildrenTags'):
            print(f"svgChildrenTags: {result.get('svgChildrenTags')}")
        print(f"\nedgeLabel 数量: {result.get('edgeLabelCount', 0)}")
        print(f"'CREATES' edgeLabel 数量: {result.get('createsEdgeLabelCount', 0)}")
        if result.get('createsEdgeLabels'):
            for cl in result['createsEdgeLabels'][:3]:
                print(f"  parentClass={cl['parentClass']}, closestG={cl['closestG']}")
                print(f"  outerHTML: {cl['outerHTML']}")
        print(f"\n双向 link index: {result.get('bidiIdx')}, relationCode: {result.get('bidiCode')}")

        await browser.close()


asyncio.run(main())
