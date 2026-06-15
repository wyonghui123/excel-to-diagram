#!/usr/bin/env python3
"""验证 v40.7 fix"""
import asyncio
from playwright.async_api import async_playwright
import json

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        c = await b.new_context(viewport={'width':1600,'height':1000})
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

        d = await pg.evaluate("""() => {
            const allSvgs = Array.from(document.querySelectorAll('svg'));
            const ds = allSvgs.find(s => s.getAttribute('class')?.includes('flowchart') && s.getAttribute('class')?.includes('hide-tails'));
            const ls = Array.from(ds.querySelectorAll('g.edgeLabel'));
            const t = ls.find(l => (l.textContent||'').includes('BO_SUPPLIER_BO_REQ_01'));
            const gl = t.querySelector('g.label');
            const fo = t.querySelector('foreignObject');
            const lb = fo?.querySelector(':scope > div');
            const vb = ds.viewBox?.baseVal;
            const sr = ds.getBoundingClientRect();
            const scaleX = sr.width / vb.width;
            const scaleY = sr.height / vb.height;
            const lr = t.getBoundingClientRect();
            const lbr = lb?.getBoundingClientRect();

            // 找 path
            const paths = Array.from(ds.querySelectorAll('path.flowchart-link'));
            const tMatch = t.getAttribute('transform').match(/translate\\(([-\\d.]+)[,\\s]+([-\\d.]+)\\)/);
            const lx = parseFloat(tMatch[1]); const ly = parseFloat(tMatch[2]);
            let bp = null, bd = Infinity;
            paths.forEach(p => {
                try { const m = p.getPointAtLength(p.getTotalLength()/2); const d = Math.hypot(m.x-lx, m.y-ly); if (d < bd) { bd = d; bp = p; } } catch (e) {}
            });
            const pr = bp.getBoundingClientRect();
            const pm = bp.getPointAtLength(bp.getTotalLength()/2);
            return {
                gLabelTransform: gl?.getAttribute('transform'),
                labelBkg: lbr ? {x: lbr.x.toFixed(2), y: lbr.y.toFixed(2), w: lbr.width.toFixed(2), h: lbr.height.toFixed(2)} : null,
                labelBkgCenter: lbr ? {x: (lbr.x + lbr.width/2).toFixed(2), y: (lbr.y + lbr.height/2).toFixed(2)} : null,
                pathRect: {x: pr.x.toFixed(2), y: pr.y.toFixed(2), w: pr.width.toFixed(2)},
                pathMidVp: {x: (sr.left + (pm.x - vb.x) * scaleX).toFixed(2), y: (sr.top + (pm.y - vb.y) * scaleY).toFixed(2)},
                pathMidY: pm.y,
                scaleX, scaleY,
                diffX: lbr ? ((lbr.x + lbr.width/2) - (sr.left + (pm.x - vb.x) * scaleX)).toFixed(2) : null,
                diffY: lbr ? ((lbr.y + lbr.height/2) - (sr.top + (pm.y - vb.y) * scaleY)).toFixed(2) : null,
            };
        }""")
        import pprint
        pprint.pprint(d, width=200)
        await b.close()

asyncio.run(main())
