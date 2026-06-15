"""Debug: 直接读 mermaid 渲染前的 <pre> 元素，看实际语法"""
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

        # 1. dev-login
        await page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        print("✓ dev-login")

        # 2. 找一个有数据的版本
        products_resp = await page.request.get("http://localhost:3010/api/v2/bo/product")
        products = await products_resp.json()
        product_list = products.get("data", {}).get("items", []) or products.get("data", [])
        if not product_list:
            print("❌ 无产品")
            return

        # 找有数据的版本
        for prod in product_list[:5]:
            print(f"  试产品: {prod.get('name', prod.get('id'))}")
            versions_resp = await page.request.get(
                f"http://localhost:3010/api/v2/bo/version?product_id={prod['id']}"
            )
            versions = await versions_resp.json()
            version_list = versions.get("data", {}).get("items", []) or versions.get("data", [])
            if not version_list:
                continue
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
                    bo_count = len(data.get("business_objects", []))
                    rel_count = len(data.get("relationships", []))
                    if bo_count > 0 and rel_count > 0:
                        product = prod
                        version = {"id": version_id, "name": version_id}
                        print(f"  ✓ 找到: {version_id} (BO={bo_count}, R={rel_count})")
                        break
            if 'version' in dir() and version:
                break

        # 3. 拉 preview
        arch_data_resp = await page.request.get(
            f"http://localhost:3010/api/v2/bo/architecture/preview?version_id={version['id']}"
        )
        arch_data = (await arch_data_resp.json()).get("data", {})

        # 注入 1 条双向
        bidi_count = sum(1 for r in arch_data.get("relationships", []) if r.get("relation_direction") == "双向")
        if bidi_count == 0 and len(arch_data.get("relationships", [])) > 0:
            arch_data["relationships"][0]["relation_direction"] = "双向"
            arch_data["relationships"][0]["relationType"] = "CALLS"
            print(f"  🆕 注入双向: rel[0]")

        # 4. 预填 sessionStorage
        await page.goto("http://localhost:3004/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        arch_data_str = json.dumps(arch_data, ensure_ascii=False)
        await page.evaluate(f"""(data) => {{
            sessionStorage.setItem('archDataForDiagram', data.arch);
            sessionStorage.setItem('lastArchDataForDiagram', data.arch);
            sessionStorage.setItem('archDataCurrentStep', '2');
            sessionStorage.setItem('archDataChartType', 'businessObject');
        }}""", {"arch": arch_data_str})

        # 5. 导航到 chart 页
        await page.evaluate("sessionStorage.setItem('archDataCurrentStep', '0')")
        await page.goto("http://localhost:3004/archdata-chart", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        print(f"  URL: {page.url}")

        # 6. 触发 generateDiagram
        triggered = await page.evaluate("""() => {
            const app = window.__diagramApp
            if (!app) return { ok: false, reason: '__diagramApp not exposed' }
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
            return { ok: true, hasDiagram: !!app.diagramData, currentStep: app.currentStep && app.currentStep.value }
        }""")
        print(f"  触发: {triggered}")

        # 7. 等渲染 + dump mermaid 语法
        await page.wait_for_timeout(8000)

        # 同时读 mermaid pre 元素 + window.__lastMermaidCode
        result = await page.evaluate("""() => {
            const out = {
                windowLastCode: (typeof window !== 'undefined' && window.__lastMermaidCode) || null,
                windowLastCodeLen: (window.__lastMermaidCode || '').length,
                preText: null,
                preTextLen: 0,
                preDataCode: null,
                preDataCodeLen: 0
            }
            const pres = document.querySelectorAll('pre.mermaid')
            if (pres.length > 0) {
                const pre = pres[0]
                out.preText = pre.textContent
                out.preTextLen = pre.textContent.length
                // 也读 data-code 属性 (有些实现会保存)
                out.preDataCode = pre.getAttribute('data-code') || null
                out.preDataCodeLen = (out.preDataCode || '').length
            }
            // 看 mermaidContent 内是否有 <pre> 嵌套
            const content = document.querySelector('.mermaid-content')
            if (content) {
                out.contentInnerHTML = content.innerHTML.substring(0, 2000)
            }
            // 找所有 script 里有没有 mermaid
            const scripts = document.querySelectorAll('script')
            out.scriptCount = scripts.length
            return out
        }""")

        print(f"\n  window.__lastMermaidCode: len={result['windowLastCodeLen']}")
        print(f"  pre.textContent: len={result['preTextLen']}")
        if result['preText']:
            print(f"\n  ===== pre.textContent =====")
            print(result['preText'][:3000])
            print(f"  ===== END =====\n")
        print(f"  pre.data-code: len={result['preDataCodeLen']}")
        if result.get('contentInnerHTML'):
            print(f"\n  ===== contentInnerHTML (前 2000 字符) =====")
            print(result['contentInnerHTML'][:2000])
            print(f"  ===== END =====\n")

        # 保存到文件
        with open("e2e_debug_dump.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n  saved to e2e_debug_dump.json")

        await browser.close()


asyncio.run(main())
