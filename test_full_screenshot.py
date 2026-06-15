#!/usr/bin/env python3
"""Take full page screenshot of the diagram"""
import asyncio
from playwright.async_api import async_playwright
import json

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = await context.new_page()

        await page.goto('http://localhost:3004/', timeout=20000)
        await page.wait_for_load_state('networkidle', timeout=15000)
        await page.evaluate("""async () => {
            await fetch('/api/v1/auth/dev-login?username=admin', {credentials: 'include'});
        }""")

        pv = await page.evaluate("""async () => {
            const r = await fetch('/api/v2/bo/product/list', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({page:1,page_size:200,search:'SUPPLY_CHAIN'})});
            const b = await r.json();
            const p = b.data.find(x => x.code==='SUPPLY_CHAIN') || b.data[0];
            const r2 = await fetch('/api/v2/bo/version/list', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({page:1,page_size:50,product_id:p.id,search:'v1'})});
            const b2 = await r2.json();
            return {pid: p.id, vid: b2.data[0].id};
        }""")
        arch_data = {'versionId': pv['vid'], 'productId': pv['pid'], 'hierarchyFilter': {}}
        await page.evaluate(f"""() => {{
            sessionStorage.setItem('archDataForDiagram', JSON.stringify({json.dumps(arch_data)}));
            sessionStorage.setItem('lastArchDataForDiagram', JSON.stringify({json.dumps(arch_data)}));
            sessionStorage.setItem('archDataCurrentStep', '3');
            sessionStorage.setItem('archDataChartType', 'businessObject');
        }}""")
        await page.goto('http://localhost:3004/archdata-chart', timeout=20000)
        await page.wait_for_load_state('networkidle', timeout=15000)
        await page.wait_for_timeout(2000)

        await page.evaluate('''() => {
            const els = document.querySelectorAll('.el-radio, .chart-type-card, [class*="chart-type"]');
            for (const el of els) { if ((el.innerText||'').includes('业务对象图')) { el.click(); return; } }
        }''')
        await page.wait_for_timeout(800)
        for _ in range(2):
            await page.evaluate('''() => {
                for (const b of document.querySelectorAll('button')) { if (b.innerText.trim() === '下一步') { b.click(); return; } }
            }''')
            await page.wait_for_timeout(2000)
        await page.evaluate('''() => {
            for (const b of document.querySelectorAll('button')) { if (b.innerText.trim().includes('生成')) { b.click(); return; } }
        }''')
        await page.wait_for_timeout(15000)

        # Take full page screenshot
        await page.screenshot(path=r'd:\filework\diagram_full_v40_5.png', full_page=True)
        print('Saved full page screenshot: d:/filework/diagram_full_v40_5.png')

        # Check centering for all edge labels
        check = await page.evaluate(r'''() => {
            const labels = document.querySelectorAll('g.edgeLabel');
            const results = [];
            for (const l of labels) {
                const text = (l.textContent || '').trim();
                const lRect = l.getBoundingClientRect();
                // Find corresponding path
                const allLabels = Array.from(document.querySelectorAll('g.edgeLabel'));
                const idx = allLabels.indexOf(l);
                let pathEl = null;
                const edgePaths = document.querySelectorAll('g.edges.edgePaths > g.edgePath');
                if (edgePaths[idx]) pathEl = edgePaths[idx].querySelector('path');
                if (!pathEl) {
                    const fl = document.querySelectorAll('path.flowchart-link');
                    if (fl[idx]) pathEl = fl[idx];
                }
                if (!pathEl) continue;
                const pRect = pathEl.getBoundingClientRect();
                const labelCenterY = lRect.y + lRect.height / 2;
                const pathCenterY = pRect.y + pRect.height / 2;
                const diff = Math.abs(labelCenterY - pathCenterY);
                results.push({text: text.substring(0, 30), diffPx: diff.toFixed(2), labelCenterY: labelCenterY.toFixed(1), pathCenterY: pathCenterY.toFixed(1)});
            }
            return results;
        }''')
        print('\n=== Edge label centering (diff < 1px = centered) ===')
        for r in check:
            status = 'OK' if float(r['diffPx']) < 1 else 'OFF'
            print(f'  [{status}] {r["text"]:30s} diff={r["diffPx"]}px (label y={r["labelCenterY"]}, line y={r["pathCenterY"]})')

        await browser.close()

asyncio.run(main())
