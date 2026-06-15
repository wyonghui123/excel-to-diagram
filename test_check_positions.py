#!/usr/bin/env python3
"""检查 g.edgeLabel 实际 viewport 位置 vs path 实际 viewport 位置"""
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
            const ds = allSvgs.find(s => s.getAttribute('class')?.includes('flowchart'));
            const ls = Array.from(ds.querySelectorAll('g.edgeLabel'));
            const t = ls.find(l => (l.textContent||'').includes('BO_SUPPLIER_BO_REQ_01'));
            const paths = Array.from(ds.querySelectorAll('path.flowchart-link'));
            const tMatch = t.getAttribute('transform').match(/translate\\(([-\\d.]+)[,\\s]+([-\\d.]+)\\)/);
            const lx = parseFloat(tMatch[1]); const ly = parseFloat(tMatch[2]);
            let bp = null, bd = Infinity;
            paths.forEach(p => { try { const m = p.getPointAtLength(p.getTotalLength()/2); const d = Math.hypot(m.x-lx, m.y-ly); if (d<bd) { bd=d; bp=p; } } catch(e){} });
            const pm = bp.getPointAtLength(bp.getTotalLength()/2);

            // 1. 在 ds (SVG) 直接 append 一个测试 circle, 验证 SVG viewBox transform
            const testC1 = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            testC1.setAttribute('cx', pm.x); testC1.setAttribute('cy', pm.y);
            testC1.setAttribute('r', '4'); testC1.setAttribute('fill', 'red');
            testC1.setAttribute('data-test', 'svg-direct');
            ds.appendChild(testC1);
            const t1Rect = testC1.getBoundingClientRect();

            // 2. 在 g.edgePath 内部 append 一个测试 circle
            const testC2 = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            testC2.setAttribute('cx', pm.x); testC2.setAttribute('cy', pm.y);
            testC2.setAttribute('r', '4'); testC2.setAttribute('fill', 'green');
            testC2.setAttribute('data-test', 'edge-path');
            bp.parentNode.appendChild(testC2);
            const t2Rect = testC2.getBoundingClientRect();

            // 3. path 自身的位置
            const pRect = bp.getBoundingClientRect();

            // 4. g.edgeLabel 自身的位置
            const elRect = t.getBoundingClientRect();

            // 5. labelBkg 位置
            const fo = t.querySelector('foreignObject');
            const lb = fo?.querySelector(':scope > div');
            const lbRect = lb?.getBoundingClientRect();

            return {
                pathD: bp.getAttribute('d'),
                pathSVG: `(${pm.x.toFixed(1)},${pm.y.toFixed(1)})`,
                pathRect: `(${pRect.x.toFixed(1)},${pRect.y.toFixed(1)},${pRect.width.toFixed(1)},${pRect.height.toFixed(1)})`,
                testC1_in_svg: `(${t1Rect.x.toFixed(1)},${t1Rect.y.toFixed(1)})`,
                testC2_in_edgePath: `(${t2Rect.x.toFixed(1)},${t2Rect.y.toFixed(1)})`,
                edgeLabelRect: `(${elRect.x.toFixed(1)},${elRect.y.toFixed(1)},${elRect.width.toFixed(1)},${elRect.height.toFixed(1)})`,
                labelBkgRect: lbRect ? `(${lbRect.x.toFixed(1)},${lbRect.y.toFixed(1)},${lbRect.width.toFixed(1)},${lbRect.height.toFixed(1)})` : null,
                svgRect: `(${ds.getBoundingClientRect().x.toFixed(1)},${ds.getBoundingClientRect().y.toFixed(1)},${ds.getBoundingClientRect().width.toFixed(1)},${ds.getBoundingClientRect().height.toFixed(1)})`,
            };
        }""")
        import pprint
        pprint.pprint(d, width=200)
        await b.close()

asyncio.run(main())
