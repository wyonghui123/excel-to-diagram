#!/usr/bin/env python3
"""
简化的截图: 找到 BO_SUPPLIER_BO_REQ_01 label 的位置,然后用红色框标出 path + label
"""
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
        await page.wait_for_timeout(2000)

        # 在页面上叠加标记
        await page.evaluate(r'''() => {
            const allSvgs = Array.from(document.querySelectorAll('svg'));
            const diagramSvg = allSvgs.find(s => s.getAttribute('class')?.includes('flowchart') && s.getAttribute('class')?.includes('hide-tails'));
            if (!diagramSvg) return;
            const labels = Array.from(diagramSvg.querySelectorAll('g.edgeLabel'));
            const target = labels.find(l => (l.textContent||'').includes('BO_SUPPLIER_BO_REQ_01'));
            if (!target) return;

            // 找 path
            const paths = Array.from(diagramSvg.querySelectorAll('path.flowchart-link'));
            const tMatch = target.getAttribute('transform').match(/translate\(([-\d.]+)[,\s]+([-\d.]+)\)/);
            const lx = tMatch ? parseFloat(tMatch[1]) : 0;
            const ly = tMatch ? parseFloat(tMatch[2]) : 0;
            let bestPath = null, bestDist = Infinity;
            paths.forEach(p => {
                try {
                    const m = p.getPointAtLength(p.getTotalLength() / 2);
                    const d = Math.hypot(m.x - lx, m.y - ly);
                    if (d < bestDist) { bestDist = d; bestPath = p; }
                } catch (e) {}
            });

            // 1. 在 path 中点画一个红圈
            if (bestPath) {
                const pl = bestPath.getTotalLength();
                const mid = bestPath.getPointAtLength(pl / 2);
                const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                circle.setAttribute('cx', mid.x);
                circle.setAttribute('cy', mid.y);
                circle.setAttribute('r', '5');
                circle.setAttribute('fill', 'red');
                circle.setAttribute('stroke', 'yellow');
                circle.setAttribute('stroke-width', '2');
                circle.setAttribute('data-debug-marker', 'path-mid');
                bestPath.parentNode.appendChild(circle);
            }

            // 2. 在 g.edgeLabel 位置画一个蓝圈
            const circle2 = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            const tr = target.getAttribute('transform');
            const m2 = tr.match(/translate\(([-\d.]+)[,\s]+([-\d.]+)\)/);
            circle2.setAttribute('cx', m2[1]);
            circle2.setAttribute('cy', m2[2]);
            circle2.setAttribute('r', '5');
            circle2.setAttribute('fill', 'blue');
            circle2.setAttribute('stroke', 'cyan');
            circle2.setAttribute('stroke-width', '2');
            circle2.setAttribute('data-debug-marker', 'edge-label');
            diagramSvg.appendChild(circle2);
        }''')

        await page.wait_for_timeout(500)

        # 截全图
        await page.screenshot(path=r'd:\filework\full_with_markers.png', full_page=True)
        print('Saved full with markers: d:/filework/full_with_markers.png')

        # 截 BO_SUPPLIER_BO_REQ_01 区域 (包含 line + label)
        clip_info = await page.evaluate(r'''() => {
            const allSvgs = Array.from(document.querySelectorAll('svg'));
            const diagramSvg = allSvgs.find(s => s.getAttribute('class')?.includes('flowchart') && s.getAttribute('class')?.includes('hide-tails'));
            const labels = Array.from(diagramSvg.querySelectorAll('g.edgeLabel'));
            const target = labels.find(l => (l.textContent||'').includes('BO_SUPPLIER_BO_REQ_01'));
            if (!target) return null;

            // 找 path
            const paths = Array.from(diagramSvg.querySelectorAll('path.flowchart-link'));
            const tMatch = target.getAttribute('transform').match(/translate\(([-\d.]+)[,\s]+([-\d.]+)\)/);
            const lx = parseFloat(tMatch[1]);
            const ly = parseFloat(tMatch[2]);
            let bestPath = null, bestDist = Infinity;
            paths.forEach(p => {
                try {
                    const m = p.getPointAtLength(p.getTotalLength() / 2);
                    const d = Math.hypot(m.x - lx, m.y - ly);
                    if (d < bestDist) { bestDist = d; bestPath = p; }
                } catch (e) {}
            });
            const lRect = target.getBoundingClientRect();
            const pRect = bestPath.getBoundingClientRect();
            return {
                label: {x: lRect.x, y: lRect.y, w: lRect.width, h: lRect.height},
                path: {x: pRect.x, y: pRect.y, w: pRect.width, h: pRect.height},
            };
        }''')

        if clip_info:
            min_x = min(clip_info['label']['x'], clip_info['path']['x']) - 100
            min_y = min(clip_info['label']['y'], clip_info['path']['y']) - 80
            max_x = max(clip_info['label']['x'] + clip_info['label']['w'], clip_info['path']['x'] + clip_info['path']['w']) + 200
            max_y = max(clip_info['label']['y'] + clip_info['label']['h'], clip_info['path']['y'] + clip_info['path']['h']) + 80
            await page.screenshot(
                path=r'd:\filework\zoom_with_markers.png',
                clip={'x': max(0, min_x), 'y': max(0, min_y), 'width': max_x - max(0, min_x), 'height': max_y - max(0, min_y)}
            )
            print(f'Saved zoom: d:/filework/zoom_with_markers.png  label={clip_info["label"]}, path={clip_info["path"]}')

        await browser.close()

asyncio.run(main())
