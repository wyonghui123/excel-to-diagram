#!/usr/bin/env python3
"""Check enum cache state AFTER diagram renders"""
import asyncio
from playwright.async_api import async_playwright
import json

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = await context.new_page()

        console_logs = []
        page.on('console', lambda msg: console_logs.append(f'[{msg.type}] {msg.text}'))
        page.on('pageerror', lambda err: console_logs.append(f'[pageerror] {err}'))

        await page.goto('http://localhost:3004/', timeout=20000)
        await page.wait_for_load_state('networkidle', timeout=15000)

        # Login
        await page.evaluate("""async () => {
            await fetch('/api/v1/auth/dev-login?username=admin', {credentials: 'include'});
        }""")

        # Get products/versions
        pv = await page.evaluate("""async () => {
            const r = await fetch('/api/v2/bo/product/list', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({page: 1, page_size: 200, search: 'SUPPLY_CHAIN'})
            });
            const body = await r.json();
            const product = body.data.find(p => p.code === 'SUPPLY_CHAIN') || body.data[0];
            const r2 = await fetch('/api/v2/bo/version/list', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({page: 1, page_size: 50, product_id: product.id, search: 'v1'})
            });
            const body2 = await r2.json();
            return {productId: product.id, versionId: body2.data[0].id};
        }""")
        print(f'PV: {pv}')

        # Set sessionStorage and navigate
        arch_data = {
            'versionId': pv['versionId'],
            'productId': pv['productId'],
            'hierarchyFilter': {},
        }
        await page.evaluate(f"""() => {{
            sessionStorage.setItem('archDataForDiagram', JSON.stringify({json.dumps(arch_data)}));
            sessionStorage.setItem('lastArchDataForDiagram', JSON.stringify({json.dumps(arch_data)}));
            sessionStorage.setItem('archDataCurrentStep', '3');
            sessionStorage.setItem('archDataChartType', 'businessObject');
        }}""")

        await page.goto('http://localhost:3004/archdata-chart', timeout=20000)
        await page.wait_for_load_state('networkidle', timeout=15000)
        await page.wait_for_timeout(2000)

        # Click chart type
        await page.evaluate('''() => {
            const els = document.querySelectorAll('.el-radio, .chart-type-card, [class*="chart-type"]');
            for (const el of els) {
                const t = (el.innerText || '').trim();
                if (t.includes('业务对象图')) { el.click(); return; }
            }
        }''')
        await page.wait_for_timeout(800)

        for _ in range(2):
            await page.evaluate('''() => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    if (b.innerText.trim() === '下一步') { b.click(); return; }
                }
            }''')
            await page.wait_for_timeout(2000)

        # Click 生成图表
        await page.evaluate('''() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                if (b.innerText.trim().includes('生成')) { b.click(); return; }
            }
        }''')
        await page.wait_for_timeout(15000)  # Wait longer for render

        # NOW check the cache state of the ACTUAL module being used by MermaidComponent
        result = await page.evaluate("""async () => {
            try {
                // Check EnumService instance the page is using
                const mod = await import('/src/services/enumService.js');
                const svc = mod.default || mod.EnumService;

                // Check window state
                return {
                    cacheSize: svc._cache.size,
                    cacheKeys: [...svc._cache.keys()],
                    directionData: svc._cache.get('direction')?.data,
                    typeData: svc._cache.get('relation_type')?.data,
                };
            } catch (e) {
                return {error: e.message};
            }
        }""")
        print(f'Cache state AFTER render: {json.dumps(result, ensure_ascii=False, indent=2)}')

        # Print all console logs
        print()
        print('=== All console logs (enum-related) ===')
        for log in console_logs:
            if any(k in log.lower() for k in ['enum', 'cache', 'preload']):
                print(f'  {log[:300]}')

        await browser.close()

asyncio.run(main())
