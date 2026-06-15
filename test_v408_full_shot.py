#!/usr/bin/env python3
"""简单截图 - 只截图不画标记"""
import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        c = await b.new_context(viewport={'width': 1600, 'height': 1000})
        pg = await c.new_page()
        await pg.goto('http://localhost:3004/', timeout=20000)
        await pg.wait_for_load_state('networkidle', timeout=15000)
        await pg.evaluate("async () => { await fetch('/api/v1/auth/dev-login?username=admin', {credentials:'include'}); }")
        pv = await pg.evaluate("""async () => {
            const r = await fetch('/api/v2/bo/product/list', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({page:1,page_size:200,search:'SUPPLY_CHAIN'})});
            const b = await r.json();
            const p = b.data.find(x => x.code==='SUPPLY_CHAIN') || b.data[0];
            const r2 = await fetch('/api/v2/bo/version/list', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({page:1,page_size:50,product_id:p.id,search:'v1'})});
            const b2 = await r2.json();
            return {pid: p.id, vid: b2.data[0].id};
        }""")
        ad = {'versionId': pv['vid'], 'productId': pv['pid'], 'hierarchyFilter': {}}
        await pg.evaluate(f"""() => {{
            sessionStorage.setItem('archDataForDiagram', JSON.stringify({json.dumps(ad)}));
            sessionStorage.setItem('lastArchDataForDiagram', JSON.stringify({json.dumps(ad)}));
            sessionStorage.setItem('archDataCurrentStep', '3');
            sessionStorage.setItem('archDataChartType', 'businessObject');
        }}""")
        await pg.goto('http://localhost:3004/archdata-chart', timeout=20000)
        await pg.wait_for_load_state('networkidle', timeout=15000)
        await pg.wait_for_timeout(2000)
        await pg.evaluate("""() => {
            const e = document.querySelectorAll('.el-radio, .chart-type-card, [class*="chart-type"]');
            for (const x of e) { if ((x.innerText||'').includes('业务对象图')) { x.click(); return; } }
        }""")
        await pg.wait_for_timeout(800)
        for _ in range(2):
            await pg.evaluate("""() => {
                for (const b of document.querySelectorAll('button')) { if (b.innerText.trim() === '下一步') { b.click(); return; } }
            }""")
            await pg.wait_for_timeout(2000)
        await pg.evaluate("""() => {
            for (const b of document.querySelectorAll('button')) { if (b.innerText.trim().includes('生成')) { b.click(); return; } }
        }""")
        await pg.wait_for_timeout(15000)
        await pg.wait_for_timeout(2000)
        await pg.screenshot(path='d:/filework/excel-to-diagram/v408_full.png', full_page=True)
        print('full screenshot saved')
        await b.close()

asyncio.run(main())
