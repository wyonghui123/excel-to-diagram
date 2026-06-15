#!/usr/bin/env python3
"""
详细查看 BO_SUPPLIER_BO_REQ_01 标签的实际渲染情况
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
        await page.wait_for_timeout(500)

        diag = await page.evaluate(r'''() => {
            // 找主 SVG
            const allSvgs = Array.from(document.querySelectorAll('svg'));
            const diagramSvg = allSvgs.find(s => s.getAttribute('class')?.includes('flowchart') && s.getAttribute('class')?.includes('hide-tails')) || allSvgs.find(s => s.querySelector('g.edgeLabel'));
            if (!diagramSvg) return {error: 'no diagram svg'};
            const vb = diagramSvg.viewBox?.baseVal;
            const svgRect = diagramSvg.getBoundingClientRect();

            // 找 label
            const labels = Array.from(diagramSvg.querySelectorAll('g.edgeLabel'));
            const target = labels.find(l => (l.textContent||'').includes('BO_SUPPLIER_BO_REQ_01'));
            if (!target) return {error: 'label not found'};

            // 找 path
            const paths = Array.from(diagramSvg.querySelectorAll('path.flowchart-link'));
            let bestPath = null, bestDist = Infinity;
            const transform = target.getAttribute('transform') || '';
            const tMatch = transform.match(/translate\(([-\d.]+)[,\s]+([-\d.]+)\)/);
            const labelX = tMatch ? parseFloat(tMatch[1]) : 0;
            const labelY = tMatch ? parseFloat(tMatch[2]) : 0;
            paths.forEach(p => {
                try {
                    const m = p.getPointAtLength(p.getTotalLength() / 2);
                    const d = Math.hypot(m.x - labelX, m.y - labelY);
                    if (d < bestDist) { bestDist = d; bestPath = p; }
                } catch (e) {}
            });
            if (!bestPath) return {error: 'no path'};

            const pathLen = bestPath.getTotalLength();
            const pathMid = bestPath.getPointAtLength(pathLen / 2);

            // 用主 SVG 的 viewBox 计算正确的 viewport 位置
            const scaleX = svgRect.width / vb.width;
            const scaleY = svgRect.height / vb.height;
            const pathMidVpX = svgRect.left + (pathMid.x - vb.x) * scaleX;
            const pathMidVpY = svgRect.top + (pathMid.y - vb.y) * scaleY;

            // label 实际位置
            const lRect = target.getBoundingClientRect();
            const fo = target.querySelector('foreignObject');
            const labelBkg = fo?.querySelector(':scope > div');
            const lbRect = labelBkg?.getBoundingClientRect();
            const pEl = labelBkg?.querySelector('p');
            const pRect = pEl?.getBoundingClientRect();
            const spanEl = pEl?.querySelector('span');
            const spanRect = spanEl?.getBoundingClientRect();

            // 字体 / line-height / padding
            const divStyle = labelBkg ? window.getComputedStyle(labelBkg) : null;
            const pStyle = pEl ? window.getComputedStyle(pEl) : null;
            const spanStyle = spanEl ? window.getComputedStyle(spanEl) : null;

            // 文字内容 (逐字符)
            const text = target.textContent || '';
            const charRects = [];
            if (spanEl) {
                const range = document.createRange();
                range.selectNodeContents(spanEl);
                const rects = range.getClientRects();
                for (let i = 0; i < Math.min(rects.length, 5); i++) {
                    charRects.push({x: rects[i].x.toFixed(1), y: rects[i].y.toFixed(1), w: rects[i].width.toFixed(1), h: rects[i].height.toFixed(1)});
                }
            }

            // path 端点 viewport
            const pStart = bestPath.getPointAtLength(0);
            const pEnd = bestPath.getPointAtLength(pathLen);
            const pStartVpX = svgRect.left + (pStart.x - vb.x) * scaleX;
            const pStartVpY = svgRect.top + (pStart.y - vb.y) * scaleY;
            const pEndVpX = svgRect.left + (pEnd.x - vb.x) * scaleX;
            const pEndVpY = svgRect.top + (pEnd.y - vb.y) * scaleY;

            // pathRect
            const pRect2 = bestPath.getBoundingClientRect();

            return {
                diagramSvgRect: {x: svgRect.x.toFixed(1), y: svgRect.y.toFixed(1), w: svgRect.width.toFixed(1), h: svgRect.height.toFixed(1)},
                diagramVb: {x: vb.x, y: vb.y, w: vb.width, h: vb.height},
                scaleX: scaleX.toFixed(4),
                scaleY: scaleY.toFixed(4),
                pathMidSVG: {x: pathMid.x.toFixed(1), y: pathMid.y.toFixed(1)},
                pathMidVp: {x: pathMidVpX.toFixed(1), y: pathMidVpY.toFixed(1)},
                pathRect: {x: pRect2.x.toFixed(1), y: pRect2.y.toFixed(1), w: pRect2.width.toFixed(1), h: pRect2.height.toFixed(1)},
                pathEndVp: {startX: pStartVpX.toFixed(1), startY: pStartVpY.toFixed(1), endX: pEndVpX.toFixed(1), endY: pEndVpY.toFixed(1)},
                pathD: bestPath.getAttribute('d'),
                labelRect: {x: lRect.x.toFixed(1), y: lRect.y.toFixed(1), w: lRect.width.toFixed(1), h: lRect.height.toFixed(1)},
                labelCenterVp: {x: (lRect.x + lRect.width/2).toFixed(1), y: (lRect.y + lRect.height/2).toFixed(1)},
                labelBkgRect: lbRect ? {x: lbRect.x.toFixed(1), y: lbRect.y.toFixed(1), w: lbRect.width.toFixed(1), h: lbRect.height.toFixed(1)} : null,
                labelBkgCenter: lbRect ? {x: (lbRect.x + lbRect.width/2).toFixed(1), y: (lbRect.y + lbRect.height/2).toFixed(1)} : null,
                pRect: pRect ? {x: pRect.x.toFixed(1), y: pRect.y.toFixed(1), w: pRect.width.toFixed(1), h: pRect.height.toFixed(1)} : null,
                pCenter: pRect ? {x: (pRect.x + pRect.width/2).toFixed(1), y: (pRect.y + pRect.height/2).toFixed(1)} : null,
                spanRect: spanRect ? {x: spanRect.x.toFixed(1), y: spanRect.y.toFixed(1), w: spanRect.width.toFixed(1), h: spanRect.height.toFixed(1)} : null,
                spanCenter: spanRect ? {x: (spanRect.x + spanRect.width/2).toFixed(1), y: (spanRect.y + spanRect.height/2).toFixed(1)} : null,
                divStyle: divStyle ? {fontSize: divStyle.fontSize, lineHeight: divStyle.lineHeight, padding: divStyle.padding, display: divStyle.display, whiteSpace: divStyle.whiteSpace, textAlign: divStyle.textAlign, height: divStyle.height} : null,
                pStyle: pStyle ? {fontSize: pStyle.fontSize, lineHeight: pStyle.lineHeight, margin: pStyle.margin, padding: pStyle.padding, height: pStyle.height} : null,
                spanStyle: spanStyle ? {fontSize: spanStyle.fontSize, lineHeight: spanStyle.lineHeight, height: spanStyle.height} : null,
                text: text.substring(0, 100),
                charRects: charRects.length > 0 ? charRects : null,
                diffLabelToPath: {x: (lRect.x + lRect.width/2 - pathMidVpX).toFixed(2), y: (lRect.y + lRect.height/2 - pathMidVpY).toFixed(2)},
                diffBkgToPath: lbRect ? {x: (lbRect.x + lbRect.width/2 - pathMidVpX).toFixed(2), y: (lbRect.y + lbRect.height/2 - pathMidVpY).toFixed(2)} : null,
                diffSpanToPath: spanRect ? {x: (spanRect.x + spanRect.width/2 - pathMidVpX).toFixed(2), y: (spanRect.y + spanRect.height/2 - pathMidVpY).toFixed(2)} : null,
            };
        }''')

        print('=== BO_SUPPLIER_BO_REQ_01 详细诊断 (用正确的 SVG) ===')
        import pprint
        pprint.pprint(diag, width=200)

        # 截一张包含 label + path 上下区域的图
        if 'labelRect' in diag and 'pathRect' in diag:
            lr = diag['labelRect']
            pr = diag['pathRect']
            # 找出 label 和 path 的合并区域
            min_x = min(float(lr['x']), float(pr['x'])) - 100
            min_y = min(float(lr['y']), float(pr['y'])) - 80
            max_x = max(float(lr['x']) + float(lr['w']), float(pr['x']) + float(pr['w'])) + 100
            max_y = max(float(lr['y']) + float(lr['h']), float(pr['y']) + float(pr['h'])) + 80
            x = max(0, min_x)
            y = max(0, min_y)
            w = max_x - x
            h = max_y - y
            await page.screenshot(
                path=r'd:\filework\zoom_v407_3.png',
                clip={'x': x, 'y': y, 'width': w, 'height': h}
            )
            print(f'\nSaved zoom: d:/filework/zoom_v407_3.png (clip {x},{y} {w}x{h})')
            print(f'  labelRect: {lr["x"]},{lr["y"]} {lr["w"]}x{lr["h"]}')
            print(f'  pathRect: {pr["x"]},{pr["y"]} {pr["w"]}x{pr["h"]}')

        await browser.close()

asyncio.run(main())
