#!/usr/bin/env python3
"""
全面验证: 用 path.getPointAtLength + label.getCTM 算出真实居中差异
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

        await page.screenshot(path=r'd:\filework\diagram_full_v40_6.png', full_page=True)

        # 精确测所有 label 用 path.getPointAtLength 真实中点 (统一用 getBoundingClientRect 坐标系)
        check = await page.evaluate(r'''() => {
            const labels = Array.from(document.querySelectorAll('g.edgeLabel'));
            const results = [];
            for (const label of labels) {
                const text = (label.textContent || '').trim();
                // 找最近的 path 用 label 当前位置
                const lRect = label.getBoundingClientRect();
                const labelCenterX = lRect.x + lRect.width / 2;
                const labelCenterY = lRect.y + lRect.height / 2;

                const paths = Array.from(document.querySelectorAll('path.flowchart-link'))
                    .concat(Array.from(document.querySelectorAll('g.edges.edgePaths > g.edgePath > path')));
                let bestPath = null, bestD = Infinity;
                paths.forEach(p => {
                    if (!p.getAttribute('d')) return;
                    try {
                        const pl = p.getTotalLength();
                        const pt = p.getPointAtLength(pl / 2);
                        // path mid → browser viewport 用 getBoundingClientRect
                        const temp = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                        temp.setAttribute('cx', pt.x);
                        temp.setAttribute('cy', pt.y);
                        temp.setAttribute('r', '0.01');
                        p.parentNode.appendChild(temp);
                        const tempRect = temp.getBoundingClientRect();
                        temp.remove();
                        const tempCenterX = tempRect.x + tempRect.width / 2;
                        const tempCenterY = tempRect.y + tempRect.height / 2;
                        const d = Math.hypot(tempCenterX - labelCenterX, tempCenterY - labelCenterY);
                        if (d < bestD) { bestD = d; bestPath = p; }
                    } catch(e) {}
                });
                if (!bestPath) continue;
                const pl = bestPath.getTotalLength();
                const mid = bestPath.getPointAtLength(pl / 2);
                // 临时元素取 viewport 位置
                const temp = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                temp.setAttribute('cx', mid.x);
                temp.setAttribute('cy', mid.y);
                temp.setAttribute('r', '0.01');
                bestPath.parentNode.appendChild(temp);
                const tRect = temp.getBoundingClientRect();
                temp.remove();
                const midVpX = tRect.x + tRect.width / 2;
                const midVpY = tRect.y + tRect.height / 2;

                // labelBkg
                const fo = label.querySelector('foreignObject');
                const div = fo?.querySelector(':scope > div');
                const dRect = div?.getBoundingClientRect();

                // path 的真实 viewport rect
                const pRect = bestPath.getBoundingClientRect();

                results.push({
                    text: text.substring(0, 35),
                    midVpX: midVpX.toFixed(1),
                    midVpY: midVpY.toFixed(1),
                    pathRect: {x: pRect.x.toFixed(1), y: pRect.y.toFixed(1), w: pRect.width.toFixed(1), h: pRect.height.toFixed(1)},
                    labelCenterX: labelCenterX.toFixed(1),
                    labelCenterY: labelCenterY.toFixed(1),
                    divCenterX: dRect ? (dRect.x + dRect.width/2).toFixed(1) : '?',
                    divCenterY: dRect ? (dRect.y + dRect.height/2).toFixed(1) : '?',
                    diffX: (labelCenterX - midVpX).toFixed(2),
                    diffY: (labelCenterY - midVpY).toFixed(2),
                    diffDivY: dRect ? (dRect.y + dRect.height/2 - midVpY).toFixed(2) : '?',
                });
            }
            return results;
        }''')

        print('=== 全图 label 居中 (用 path.getPointAtLength 真实中点 vs label/div 几何中心) ===')
        print(f'{"label":36s} {"pathVpx":>9s} {"pathVpy":>9s} {"lblCx":>7s} {"lblCy":>7s} {"divCx":>7s} {"divCy":>7s} {"dX":>7s} {"dY":>7s} {"dDivY":>7s}')
        for r in check:
            status = 'OK' if abs(float(r['diffY'])) < 2.5 else 'OFF'
            print(f'[{status}] {r["text"]:35s} '
                  f'{r["midVpX"]:>9s} {r["midVpY"]:>9s} '
                  f'{r["labelCenterX"]:>7s} {r["labelCenterY"]:>7s} '
                  f'{r["divCenterX"]:>7s} {r["divCenterY"]:>7s} '
                  f'{r["diffX"]:>7s} {r["diffY"]:>7s} {r["diffDivY"]:>7s}')

        await browser.close()

asyncio.run(main())
