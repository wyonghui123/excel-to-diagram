#!/usr/bin/env python3
"""截图验证 v40.8 居中修复"""
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

        # 全图截图
        await pg.screenshot(path='d:/filework/excel-to-diagram/v408_full.png', full_page=True)

        # 在 BO_SUPPLIER_BO_REQ_01 上画标记
        d = await pg.evaluate("""() => {
            const allSvgs = Array.from(document.querySelectorAll('svg'));
            const ds = allSvgs.find(s => s.getAttribute('class')?.includes('flowchart') && s.getAttribute('class')?.includes('hide-tails'));
            const ls = Array.from(ds.querySelectorAll('g.edgeLabel'));
            const t = ls.find(l => (l.textContent||'').includes('BO_SUPPLIER_BO_REQ_01'));
            const paths = Array.from(ds.querySelectorAll('path.flowchart-link'));
            const tMatch = t.getAttribute('transform').match(/translate\\(([-\\d.]+)[,\\s]+([-\\d.]+)\\)/);
            const lx = parseFloat(tMatch[1]); const ly = parseFloat(tMatch[2]);
            let bp = null, bd = Infinity;
            paths.forEach(p => { try { const m = p.getPointAtLength(p.getTotalLength()/2); const d = Math.hypot(m.x-lx, m.y-ly); if (d<bd) { bd=d; bp=p; } } catch(e){} });
            const pm = bp.getPointAtLength(bp.getTotalLength()/2);

            // 红色圆点: path 几何中点 (SVG 坐标)
            const c1 = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            c1.setAttribute('cx', pm.x); c1.setAttribute('cy', pm.y);
            c1.setAttribute('r', '5'); c1.setAttribute('fill', 'red');
            c1.setAttribute('stroke', 'yellow'); c1.setAttribute('stroke-width', '2');
            bp.parentNode.appendChild(c1);

            // 蓝色圆点: g.edgeLabel 中心
            const c2 = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            c2.setAttribute('cx', lx); c2.setAttribute('cy', ly);
            c2.setAttribute('r', '5'); c2.setAttribute('fill', 'blue');
            c2.setAttribute('stroke', 'cyan'); c2.setAttribute('stroke-width', '2');
            ds.appendChild(c2);
            return 'ok';
        }""")

        # 缩放到 BO_SUPPLIER_BO_REQ_01 周围
        d2 = await pg.evaluate("""() => {
            const allSvgs = Array.from(document.querySelectorAll('svg'));
            const ds = allSvgs.find(s => s.getAttribute('class')?.includes('flowchart') && s.getAttribute('class')?.includes('hide-tails'));
            const ls = Array.from(ds.querySelectorAll('g.edgeLabel'));
            const t = ls.find(l => (l.textContent||'').includes('BO_SUPPLIER_BO_REQ_01'));
            const lb = t.querySelector('foreignObject div.labelBkg');
            if (lb) {
                lb.scrollIntoView({block:'center', inline:'center', behavior:'instant'});
                const r = lb.getBoundingClientRect();
                return {x: r.x, y: r.y, w: r.width, h: r.height};
            }
            return null;
        }""")
        print('labelBkg rect:', d2)
        await pg.wait_for_timeout(500)

        # 再次截图 (缩放后)
        await pg.screenshot(path='d:/filework/excel-to-diagram/v408_zoom_bo_supplier_req_01.png')

        # 截一个围绕 label 的区域
        if d2:
            r = d2
            # 扩大一些范围
            pad_x = 200
            pad_y = 50
            clip = {
                'x': max(0, r['x'] - pad_x),
                'y': max(0, r['y'] - pad_y),
                'width': r['w'] + 2 * pad_x,
                'height': r['h'] + 2 * pad_y
            }
            await pg.screenshot(path='d:/filework/excel-to-diagram/v408_bo_supplier_req_01_zoom.png', clip=clip)

        await b.close()

asyncio.run(main())
