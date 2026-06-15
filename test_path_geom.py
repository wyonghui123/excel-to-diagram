#!/usr/bin/env python3
"""Investigate path geometry vs label position"""
import asyncio
from playwright.async_api import async_playwright
import json

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = await context.new_page()

        bg_logs = []
        page.on('console', lambda msg: bg_logs.append(f'[{msg.type}] {msg.text}') if 'bgRect' in msg.text or 'v40.4' in msg.text else None)

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

        # Get the BO_SUPPLIER_BO_REQ_01 path and label
        info = await page.evaluate(r'''() => {
            const labels = document.querySelectorAll('g.edgeLabel');
            const targetLabel = Array.from(labels).find(l => (l.textContent||'').trim() === 'BO_SUPPLIER_BO_REQ_01');
            if (!targetLabel) return {error: 'label not found'};

            const labelTransform = targetLabel.getAttribute('transform');

            // Find corresponding path
            const allLabels = Array.from(document.querySelectorAll('g.edgeLabel'));
            const idx = allLabels.indexOf(targetLabel);

            let pathEl = null;
            // Try g.edgePath structure
            const edgePaths = document.querySelectorAll('g.edges.edgePaths > g.edgePath');
            if (edgePaths[idx]) {
                pathEl = edgePaths[idx].querySelector('path');
            }
            if (!pathEl) {
                const flowLinks = document.querySelectorAll('path.flowchart-link');
                if (flowLinks[idx]) pathEl = flowLinks[idx];
            }

            if (!pathEl) return {error: 'path not found'};

            const pathLen = pathEl.getTotalLength();
            const midPt = pathEl.getPointAtLength(pathLen / 2);
            const startPt = pathEl.getPointAtLength(0);
            const endPt = pathEl.getPointAtLength(pathLen);

            // Get bounding boxes
            const pathRect = pathEl.getBoundingClientRect();
            const labelRect = targetLabel.getBoundingClientRect();

            // Get label's foreignObject
            const fo = targetLabel.querySelector('foreignObject');
            const foWidth = fo ? fo.getAttribute('width') : null;
            const foHeight = fo ? fo.getAttribute('height') : null;
            const foX = fo ? fo.getAttribute('x') : null;
            const foY = fo ? fo.getAttribute('y') : null;

            // Inner g.label
            const innerLabel = targetLabel.querySelector('g.label');
            const innerLabelTransform = innerLabel ? innerLabel.getAttribute('transform') : null;

            // background rect (if any)
            const bgRect = targetLabel.querySelector('rect[data-bg-rect]');
            const bgRectInfo = bgRect ? {
                x: bgRect.getAttribute('x'),
                y: bgRect.getAttribute('y'),
                w: bgRect.getAttribute('width'),
                h: bgRect.getAttribute('height')
            } : null;

            // labelBkg div
            const labelBkg = targetLabel.querySelector('.labelBkg');
            const labelBkgStyle = labelBkg ? {
                padding: getComputedStyle(labelBkg).padding,
                width: labelBkg.getBoundingClientRect().width,
                height: labelBkg.getBoundingClientRect().height
            } : null;

            return {
                labelTransform,
                innerLabelTransform,
                pathD: pathEl.getAttribute('d'),
                pathLen,
                midPt: {x: midPt.x, y: midPt.y},
                startPt: {x: startPt.x, y: startPt.y},
                endPt: {x: endPt.x, y: endPt.y},
                pathRect: {x: pathRect.x, y: pathRect.y, w: pathRect.width, h: pathRect.height},
                labelRect: {x: labelRect.x, y: labelRect.y, w: labelRect.width, h: labelRect.height},
                foInfo: {w: foWidth, h: foHeight, x: foX, y: foY},
                bgRectInfo,
                labelBkgStyle
            };
        }''')
        print(json.dumps(info, ensure_ascii=False, indent=2))

        # Print bgRect-related logs
        print('\n=== bgRect logs ===')
        for log in bg_logs:
            print(f'  {log}')

        await browser.close()

asyncio.run(main())
