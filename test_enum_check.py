#!/usr/bin/env python3
"""Check enum cache state in browser via playwright"""
import asyncio
from playwright.async_api import async_playwright
import json

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = await context.new_page()

        # Capture all console logs
        console_logs = []
        page.on('console', lambda msg: console_logs.append(f'[{msg.type}] {msg.text}'))
        page.on('pageerror', lambda err: console_logs.append(f'[pageerror] {err}'))

        await page.goto('http://localhost:3004/', timeout=20000)
        await page.wait_for_load_state('networkidle', timeout=15000)

        # Login
        login = await page.evaluate("""async () => {
            const r = await fetch('/api/v1/auth/dev-login?username=admin', {credentials: 'include'});
            return {ok: r.ok, status: r.status};
        }""")
        print(f'Login: {login}')

        # Get products/versions
        pv = await page.evaluate("""async () => {
            const r = await fetch('/api/v2/bo/product/list', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({page: 1, page_size: 200, search: 'SUPPLY_CHAIN'})
            });
            const body = await r.json();
            const products = body.data || [];
            const product = products.find(p => p.code === 'SUPPLY_CHAIN') || products[0];
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

        # Click next button twice
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
        await page.wait_for_timeout(12000)

        # Now check enum cache state
        check = await page.evaluate('''() => {
            // Try to access module exports
            const result = {enumService: null, cache: null, windowMaps: {}};

            // Check window vars
            result.windowMaps.relationType = !!window.__relationTypeEnumMap;
            result.windowMaps.direction = !!window.__relationDirectionEnumMap;

            // Try to access the module via dynamic import
            return result;
        }''')
        print(f'Check: {json.dumps(check, ensure_ascii=False, indent=2)}')

        # Manually fetch enum APIs to see what data is available
        enum_data = await page.evaluate('''async () => {
            try {
                const r1 = await fetch('/api/v1/enums/direction/options');
                const d1 = await r1.json();
                const r2 = await fetch('/api/v1/enums/relation_type/options');
                const d2 = await r2.json();
                return {direction: d1, relation_type: d2};
            } catch(e) { return {error: e.message}; }
        }''')
        print(f'Enum API data: {json.dumps(enum_data, ensure_ascii=False, indent=2)}')

        # Now hover the first edge label and check tooltip
        hover = await page.evaluate('''async () => {
            const label = document.querySelector('g.edgeLabel');
            if (!label) return {error: 'no label'};
            const rect = label.getBoundingClientRect();
            const cx = rect.left + rect.width / 2;
            const cy = rect.top + rect.height / 2;
            const fire = (el, type) => {
                const e = new MouseEvent(type, {bubbles: true, clientX: cx, clientY: cy, view: window});
                el.dispatchEvent(e);
            };
            fire(label, 'mouseenter');
            fire(label, 'mousemove');
            await new Promise(r => setTimeout(r, 800));
            const mtip = document.getElementById('mermaid-tooltip');
            return {tipText: mtip ? mtip.textContent : null};
        }''')
        print(f'Hover result: {json.dumps(hover, ensure_ascii=False, indent=2)}')

        # Print all console logs that contain relevant keywords
        print()
        print('=== Relevant console logs ===')
        for log in console_logs:
            if any(k in log.lower() for k in ['enum', 'cache', 'preload', 'relation', 'direction', 'tooltip', 'warning']):
                print(f'  {log[:300]}')

        await browser.close()

asyncio.run(main())
