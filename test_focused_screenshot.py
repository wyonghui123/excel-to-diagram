#!/usr/bin/env python3
"""Take focused screenshot of BO_SUPPLIER_BO_REQ_01 line"""
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

        # Find the BO_SUPPLIER_BO_REQ_01 label
        info = await page.evaluate(r'''() => {
            const labels = document.querySelectorAll('g.edgeLabel');
            for (const l of labels) {
                if ((l.textContent || '').trim() === 'BO_SUPPLIER_BO_REQ_01') {
                    const rect = l.getBoundingClientRect();
                    return {found: true, rect: {x: rect.x, y: rect.y, w: rect.width, h: rect.height}, transform: l.getAttribute('transform')};
                }
            }
            return {found: false};
        }''')
        print(f'BO_SUPPLIER_BO_REQ_01 label: {info}')

        if info.get('found'):
            rect = info['rect']
            # Screenshot the area around the label
            await page.screenshot(path=r'd:\filework\diagram_supplier_req.png', clip={
                'x': max(0, rect['x'] - 300),
                'y': max(0, rect['y'] - 150),
                'width': min(800, rect['w'] + 600),
                'height': min(400, rect['h'] + 300)
            })
            print('Saved: d:/filework/diagram_supplier_req.png')

            # Hover to show tooltip
            await page.evaluate(f'''() => {{
                const labels = document.querySelectorAll('g.edgeLabel');
                for (const l of labels) {{
                    if ((l.textContent || '').trim() === 'BO_SUPPLIER_BO_REQ_01') {{
                        const r = l.getBoundingClientRect();
                        const e1 = new MouseEvent('mouseenter', {{bubbles: true, clientX: r.left+r.width/2, clientY: r.top+r.height/2, view: window}});
                        l.dispatchEvent(e1);
                        const e2 = new MouseEvent('mousemove', {{bubbles: true, clientX: r.left+r.width/2, clientY: r.top+r.height/2, view: window}});
                        l.dispatchEvent(e2);
                        return;
                    }}
                }}
            }}''')
            await page.wait_for_timeout(1000)
            await page.screenshot(path=r'd:\filework\diagram_supplier_req_tooltip.png', clip={
                'x': max(0, rect['x'] - 300),
                'y': max(0, rect['y'] - 150),
                'width': min(900, rect['w'] + 700),
                'height': min(500, rect['h'] + 400)
            })
            print('Saved tooltip: d:/filework/diagram_supplier_req_tooltip.png')

        await browser.close()

asyncio.run(main())
