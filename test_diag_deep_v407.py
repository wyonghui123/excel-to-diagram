#!/usr/bin/env python3
"""
深度诊断: 为什么 BO_SUPPLIER_BO_REQ_01 label 看着不在连线中间
关键排查: SVG 实际尺寸 / path 真实位置 / label 真实位置
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

        # 全屏截图,看实际位置
        await page.screenshot(path=r'd:\filework\full_screenshot_deep.png', full_page=True)
        print('Saved full screenshot: d:/filework/full_screenshot_deep.png')

        # 详细诊断
        diag = await page.evaluate(r'''() => {
            const svg = document.querySelector('svg');
            if (!svg) return {error: 'no svg'};
            const vb = svg.viewBox?.baseVal;
            const svgRect = svg.getBoundingClientRect();

            // 1. 检查所有 SVG 元素
            const allSvgs = Array.from(document.querySelectorAll('svg'));
            const svgInfo = allSvgs.map(s => {
                const r = s.getBoundingClientRect();
                const v = s.viewBox?.baseVal;
                return {
                    cls: s.getAttribute('class'),
                    rect: {x: r.x.toFixed(1), y: r.y.toFixed(1), w: r.width.toFixed(1), h: r.height.toFixed(1)},
                    vb: v ? `${v.x},${v.y},${v.width},${v.height}` : null,
                    children: s.children.length
                };
            });

            // 2. 找 label
            const labels = Array.from(document.querySelectorAll('g.edgeLabel'));
            const target = labels.find(l => (l.textContent||'').includes('BO_SUPPLIER_BO_REQ_01'));
            if (!target) return {error: 'label not found', svgInfo};

            // 3. label 的 transform
            const transform = target.getAttribute('transform') || '';
            const tMatch = transform.match(/translate\(([-\d.]+)[,\s]+([-\d.]+)\)/);
            const labelX = tMatch ? parseFloat(tMatch[1]) : 0;
            const labelY = tMatch ? parseFloat(tMatch[2]) : 0;

            // 4. 收集所有 path 候选 - 这次记录 SVG user 坐标 + viewport 坐标
            const edgePaths = document.querySelectorAll('g.edges.edgePaths > g.edgePath');
            const flowLinks = document.querySelectorAll('path.flowchart-link');
            const allPaths = [];
            edgePaths.forEach((ep, i) => {
                const p = ep.querySelector('path');
                if (p && p.getAttribute('d')) allPaths.push({path: p, src: 'edgePath[' + i + ']'});
            });
            flowLinks.forEach((p, i) => {
                if (p.getAttribute('d')) allPaths.push({path: p, src: 'flowchart-link[' + i + ']'});
            });

            let bestPath = null, bestDist = Infinity, bestSrc = '';
            allPaths.forEach(({path, src}) => {
                try {
                    const pl = path.getTotalLength();
                    const m = path.getPointAtLength(pl / 2);
                    const d = Math.hypot(m.x - labelX, m.y - labelY);
                    if (d < bestDist) { bestDist = d; bestPath = path; bestSrc = src; }
                } catch (e) {}
            });
            if (!bestPath) return {error: 'no path'};

            // 5. path 的真实 viewport 位置 (用 getBoundingClientRect)
            const pRect = bestPath.getBoundingClientRect();
            const pathLen = bestPath.getTotalLength();
            const mid = bestPath.getPointAtLength(pathLen / 2);

            // 6. 用 SVGPoint + CTM 算 path mid 的 viewport 位置
            const svgP = bestPath.ownerSVGElement.createSVGPoint();
            svgP.x = mid.x; svgP.y = mid.y;
            const ctm = bestPath.getCTM();
            const midViaCTM = ctm ? svgP.matrixTransform(ctm) : null;

            // 7. label 的真实 viewport 位置
            const lRect = target.getBoundingClientRect();
            const fo = target.querySelector('foreignObject');
            const labelBkg = fo?.querySelector(':scope > div');
            const lbRect = labelBkg?.getBoundingClientRect();

            // 8. path 端点
            const startPt = bestPath.getPointAtLength(0);
            const endPt = bestPath.getPointAtLength(pathLen);

            // 9. 用 CTM 算端点
            const startSVG = bestPath.ownerSVGElement.createSVGPoint();
            startSVG.x = startPt.x; startSVG.y = startPt.y;
            const startViaCTM = ctm ? startSVG.matrixTransform(ctm) : null;
            const endSVG = bestPath.ownerSVGElement.createSVGPoint();
            endSVG.x = endPt.x; endSVG.y = endPt.y;
            const endViaCTM = ctm ? endSVG.matrixTransform(ctm) : null;

            // 10. label ancestry
            const ancestry = [];
            let cur = target;
            while (cur && cur.tagName !== 'HTML') {
                const tag = cur.tagName;
                const cls = cur.getAttribute ? cur.getAttribute('class') : null;
                const tr = cur.getAttribute && cur.getAttribute('transform');
                const ctmStr = cur.getCTM ? (() => { try { const m = cur.getCTM(); return m ? `(${m.a.toFixed(2)},${m.b.toFixed(2)},${m.c.toFixed(2)},${m.d.toFixed(2)},${m.e.toFixed(1)},${m.f.toFixed(1)})` : 'no CTM'; } catch(e) { return 'err'; } })() : '';
                const styleTransform = cur.style?.transform || null;
                ancestry.push({tag, cls, transform: tr, ctm: ctmStr, styleTransform});
                cur = cur.parentNode;
            }

            // 11. path ancestry
            const pathAncestry = [];
            cur = bestPath;
            while (cur && cur.tagName !== 'HTML') {
                const tag = cur.tagName;
                const cls = cur.getAttribute ? cur.getAttribute('class') : null;
                const tr = cur.getAttribute && cur.getAttribute('transform');
                const ctmStr = cur.getCTM ? (() => { try { const m = cur.getCTM(); return m ? `(${m.a.toFixed(2)},${m.b.toFixed(2)},${m.c.toFixed(2)},${m.d.toFixed(2)},${m.e.toFixed(1)},${m.f.toFixed(1)})` : 'no CTM'; } catch(e) { return 'err'; } })() : '';
                const styleTransform = cur.style?.transform || null;
                pathAncestry.push({tag, cls, transform: tr, ctm: ctmStr, styleTransform});
                cur = cur.parentNode;
            }

            return {
                svgInfo,
                bestSrc,
                pathD: bestPath.getAttribute('d').substring(0, 200),
                pathSVG: {start: `(${startPt.x.toFixed(1)},${startPt.y.toFixed(1)})`, end: `(${endPt.x.toFixed(1)},${endPt.y.toFixed(1)})`, mid: `(${mid.x.toFixed(1)},${mid.y.toFixed(1)})`},
                pathViaCTM: {
                    start: startViaCTM ? `(${startViaCTM.x.toFixed(1)},${startViaCTM.y.toFixed(1)})` : null,
                    end: endViaCTM ? `(${endViaCTM.x.toFixed(1)},${endViaCTM.y.toFixed(1)})` : null,
                    mid: midViaCTM ? `(${midViaCTM.x.toFixed(1)},${midViaCTM.y.toFixed(1)})` : null,
                },
                pathRect: {x: pRect.x.toFixed(1), y: pRect.y.toFixed(1), w: pRect.width.toFixed(1), h: pRect.height.toFixed(1)},
                pathCtm: ctm ? {a:ctm.a, b:ctm.b, c:ctm.c, d:ctm.d, e:ctm.e, f:ctm.f} : null,
                labelTransform: transform,
                labelX, labelY,
                labelRect: {x: lRect.x.toFixed(1), y: lRect.y.toFixed(1), w: lRect.width.toFixed(1), h: lRect.height.toFixed(1)},
                labelBkgRect: lbRect ? {x: lbRect.x.toFixed(1), y: lbRect.y.toFixed(1), w: lbRect.width.toFixed(1), h: lbRect.height.toFixed(1)} : null,
                foX: fo?.getAttribute('x'),
                foY: fo?.getAttribute('y'),
                foW: fo?.getAttribute('width'),
                foH: fo?.getAttribute('height'),
                ancestry,
                pathAncestry,
            };
        }''')

        print('\n=== 深度诊断: BO_SUPPLIER_BO_REQ_01 ===')
        import pprint
        pprint.pprint(diag, width=160)

        # 截一张更大的图
        if 'labelRect' in diag:
            lr = diag['labelRect']
            x = max(0, float(lr['x']) - 150)
            y = max(0, float(lr['y']) - 150)
            w = float(lr['w']) + 300
            h = float(lr['h']) + 300
            await page.screenshot(
                path=r'd:\filework\zoom_bo_supplier_bo_req_01_v2.png',
                clip={'x': x, 'y': y, 'width': w, 'height': h}
            )
            print(f'\nSaved zoom: d:/filework/zoom_bo_supplier_bo_req_01_v2.png (clip {x},{y} {w}x{h})')

        await browser.close()

asyncio.run(main())
