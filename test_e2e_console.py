"""Debug: 监听 console + pageerror, 找出 Syntax error 根因"""
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

        # 收集 console + error
        console_logs = []
        page_errors = []
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: page_errors.append(f"PageError: {err}"))

        # 1. dev-login
        await page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")

        # 2. 找有数据的版本
        products_resp = await page.request.get("http://localhost:3010/api/v2/bo/product")
        products = await products_resp.json()
        product_list = products.get("data", {}).get("items", []) or products.get("data", [])

        version = None
        for prod in product_list[:5]:
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

        # 3. 拉 preview
        arch_data_resp = await page.request.get(
            f"http://localhost:3010/api/v2/bo/architecture/preview?version_id={version['id']}"
        )
        arch_data = (await arch_data_resp.json()).get("data", {})

        # 4. sessionStorage
        await page.goto("http://localhost:3004/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        arch_data_str = json.dumps(arch_data, ensure_ascii=False)
        await page.evaluate(f"""(data) => {{
            sessionStorage.setItem('archDataForDiagram', data.arch);
            sessionStorage.setItem('lastArchDataForDiagram', data.arch);
            sessionStorage.setItem('archDataCurrentStep', '2');
            sessionStorage.setItem('archDataChartType', 'businessObject');
        }}""", {"arch": arch_data_str})

        # 5. 导航 + 触发
        await page.evaluate("sessionStorage.setItem('archDataCurrentStep', '0')")
        await page.goto("http://localhost:3004/archdata-chart", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        # 清空 console, 重新触发
        console_logs.clear()
        page_errors.clear()

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
        print(f"触发: {triggered}")

        # 6. 等
        await page.wait_for_timeout(10000)

        # 7. dump
        result = await page.evaluate("""() => {
            const pre = document.querySelector('pre.mermaid')
            return {
                lastMermaidCode: (window.__lastMermaidCode || ''),
                preText: pre ? pre.textContent : null,
                preHTML: pre ? pre.outerHTML.substring(0, 500) : null
            }
        }""")

        print(f"\n=== lastMermaidCode (len={len(result['lastMermaidCode'])}) ===")
        if result['lastMermaidCode']:
            print(result['lastMermaidCode'][:3000])
        else:
            print("(empty)")
        print(f"\n=== preText (前 500 字符) ===")
        print((result['preText'] or '')[:500])
        print(f"\n=== preHTML (前 500 字符) ===")
        print(result['preHTML'])

        # 8. 输出 console + error
        print(f"\n=== console.log (最近 20 条) ===")
        for log in console_logs[-20:]:
            print(log)
        print(f"\n=== page errors (全部) ===")
        for err in page_errors:
            print(err)

        # 保存完整 logs
        with open("e2e_console.log", "w", encoding="utf-8") as f:
            f.write(f"=== lastMermaidCode (len={len(result['lastMermaidCode'])}) ===\n")
            f.write(result['lastMermaidCode'])
            f.write(f"\n\n=== preText ===\n")
            f.write(result['preText'] or '')
            f.write(f"\n\n=== console ({len(console_logs)} 条) ===\n")
            for log in console_logs:
                f.write(log + "\n")
            f.write(f"\n=== pageErrors ({len(page_errors)} 条) ===\n")
            for err in page_errors:
                f.write(err + "\n")

        await browser.close()


asyncio.run(main())
