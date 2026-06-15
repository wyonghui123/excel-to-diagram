#!/usr/bin/env python3
"""截 BO_SUPPLIER_BO_REQ_01 的对比图 (v40.5 vs v40.6)"""
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

        # 全图
        await page.screenshot(path=r'd:\filework\diagram_full_v40_6.png', full_page=True)

        # 找 5 个典型 label 区域截图: BO_SUPPLIER_BO_REQ_01, BO_CUSTOMER_BO_SO_01, BO_AP_PAYMENT_BO_SUPPLIER_01 等
        for tgt in ['BO_SUPPLIER_BO_REQ_01', 'BO_CUSTOMER_BO_SO_01', 'BO_AP_PAYMENT_BO_SUPPLIER_01', 'BO_INVENTORY_BO_INV_LOG_01', 'BO_POL_BO_INVENTORY_01']:
            lr = await page.evaluate(f'''() => {{
                const labels = Array.from(document.querySelectorAll('g.edgeLabel'));
                const t = labels.find(l => (l.textContent||'').includes('{tgt}'));
                if (!t) return null;
                const r = t.getBoundingClientRect();
                return {{x: r.x, y: r.y, w: r.width, h: r.height}};
            }}''')
            if lr:
                x = max(0, lr['x'] - 100)
                y = max(0, lr['y'] - 30)
                w = lr['w'] + 200
                h = lr['h'] + 60
                fn = tgt
                await page.screenshot(path=rf'd:\filework\zoom_v40_6_{fn}.png', clip={'x': x, 'y': y, 'width': w, 'height': h})
                print(f'Saved: d:/filework/zoom_v40_6_{fn}.png  ({tgt} at {x:.0f},{y:.0f} {w:.0f}x{h:.0f})')

        await browser.close()

asyncio.run(main())
