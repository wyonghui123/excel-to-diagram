#!/usr/bin/env python3
"""截 v40.7 fix 后的图"""
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

        # 画标记
        await pg.evaluate("""() => {
            const allSvgs = Array.from(document.querySelectorAll('svg'));
            const ds = allSvgs.find(s => s.getAttribute('class')?.includes('flowchart') && s.getAttribute('hide-tails')) || allSvgs.find(s => s.getAttribute('class')?.includes('flowchart'));
            const ls = Array.from(ds.querySelectorAll('g.edgeLabel'));
            const t = ls.find(l => (l.textContent||'').includes('BO_SUPPLIER_BO_REQ_01'));
            const paths = Array.from(ds.querySelectorAll('path.flowchart-link'));
            const tMatch = t.getAttribute('transform').match(/translate\\(([-\\d.]+)[,\\s]+([-\\d.]+)\\)/);
            const lx = parseFloat(tMatch[1]); const ly = parseFloat(tMatch[2]);
            let bp = null, bd = Infinity;
            paths.forEach(p => { try { const m = p.getPointAtLength(p.getTotalLength()/2); const d = Math.hypot(m.x-lx, m.y-ly); if (d<bd) { bd=d; bp=p; } } catch(e){} });
            const pm = bp.getPointAtLength(bp.getTotalLength()/2);
            // 红色 - path 中点
            const c1 = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            c1.setAttribute('cx', pm.x); c1.setAttribute('cy', pm.y); c1.setAttribute('r', '6');
            c1.setAttribute('fill', 'red'); c1.setAttribute('stroke', 'yellow'); c1.setAttribute('stroke-width', '2');
            bp.parentNode.appendChild(c1);
            // 蓝色 - g.edgeLabel 位置
            const c2 = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            c2.setAttribute('cx', lx); c2.setAttribute('cy', ly); c2.setAttribute('r', '6');
            c2.setAttribute('fill', 'blue'); c2.setAttribute('stroke', 'cyan'); c2.setAttribute('stroke-width', '2');
            ds.appendChild(c2);
        }""")

        await pg.wait_for_timeout(500)

        # 全图
        await pg.screenshot(path=r'd:\filework\full_v407.png', full_page=True)
        print('Saved full: d:/filework/full_v407.png')

        # 缩放图
        info = await pg.evaluate("""() => {
            const allSvgs = Array.from(document.querySelectorAll('svg'));
            const ds = allSvgs.find(s => s.getAttribute('class')?.includes('flowchart'));
            const ls = Array.from(ds.querySelectorAll('g.edgeLabel'));
            const t = ls.find(l => (l.textContent||'').includes('BO_SUPPLIER_BO_REQ_01'));
            const paths = Array.from(ds.querySelectorAll('path.flowchart-link'));
            const tMatch = t.getAttribute('transform').match(/translate\\(([-\\d.]+)[,\\s]+([-\\d.]+)\\)/);
            const lx = parseFloat(tMatch[1]); const ly = parseFloat(tMatch[2]);
            let bp = null, bd = Infinity;
            paths.forEach(p => { try { const m = p.getPointAtLength(p.getTotalLength()/2); const d = Math.hypot(m.x-lx, m.y-ly); if (d<bd) { bd=d; bp=p; } } catch(e){} });
            const lbr = t.getBoundingClientRect();
            const pr = bp.getBoundingClientRect();
            return {label: {x: lbr.x, y: lbr.y, w: lbr.width, h: lbr.height}, path: {x: pr.x, y: pr.y, w: pr.width, h: pr.height}};
        }""")
        if info:
            min_x = min(info['label']['x'], info['path']['x']) - 100
            min_y = min(info['label']['y'], info['path']['y']) - 80
            max_x = max(info['label']['x'] + info['label']['w'], info['path']['x'] + info['path']['w']) + 200
            max_y = max(info['label']['y'] + info['label']['h'], info['path']['y'] + info['path']['h']) + 80
            await pg.screenshot(path=r'd:\filework\zoom_v407.png', clip={'x': max(0, min_x), 'y': max(0, min_y), 'width': max_x - max(0, min_x), 'height': max_y - max(0, min_y)})
            print(f'Saved zoom: d:/filework/zoom_v407.png')
            print(f'  label: {info["label"]}, path: {info["path"]}')

        await b.close()

asyncio.run(main())
