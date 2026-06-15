#!/usr/bin/env python3
"""
精确诊断 BO_SUPPLIER_BO_REQ_01 是否真的居中。
关键：用 path.getPointAtLength(pathLen/2) 拿真实中点 (不是 bbox 中心)
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

        # 启用 console 日志
        page.on('console', lambda msg: print(f'[browser {msg.type}] {msg.text}'))

        await page.wait_for_timeout(500)

        # 精确诊断: 找到 BO_SUPPLIER_BO_REQ_01
        diag = await page.evaluate(r'''() => {
            const svg = document.querySelector('svg');
            if (!svg) return {error: 'no svg'};
            const vb = svg.viewBox?.baseVal;
            if (!vb) return {error: 'no viewBox'};
            const svgRect = svg.getBoundingClientRect();
            const scale = svgRect.width / vb.width;

            // 找 BO_SUPPLIER_BO_REQ_01 label
            const labels = Array.from(document.querySelectorAll('g.edgeLabel'));
            const target = labels.find(l => (l.textContent||'').includes('BO_SUPPLIER_BO_REQ_01'));
            if (!target) return {error: 'label not found', labelTexts: labels.map(l => l.textContent.trim())};

            // 找到对应的 path - 用 g.edgeLabel 的 transform 推算它在哪个 path 中点
            const transform = target.getAttribute('transform') || '';
            const tMatch = transform.match(/translate\(([-\d.]+)[,\s]+([-\d.]+)\)/);
            const labelX = tMatch ? parseFloat(tMatch[1]) : 0;
            const labelY = tMatch ? parseFloat(tMatch[2]) : 0;

            // 收集所有 path 候选
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
            if (!bestPath) {
                return {
                    error: 'no matching path',
                    labelX, labelY,
                    labelText: target.textContent.trim(),
                    edgePathCount: edgePaths.length,
                    flowLinkCount: flowLinks.length,
                    totalPathCount: allPaths.length,
                    firstFewPathMid: allPaths.slice(0, 5).map(({path, src}) => {
                        try {
                            const pl = path.getTotalLength();
                            const m = path.getPointAtLength(pl / 2);
                            return {src, midX: m.x.toFixed(1), midY: m.y.toFixed(1)};
                        } catch (e) { return {src, err: e.message}; }
                    })
                };
            }
            const pathEl = bestPath;

            // [v40.6 关键] 输出从 g.edgeLabel 一路到 svg 根的所有祖先 transform,
            // 排查 "label viewport ≠ 算出来的 midPt" 的根因
            let ancestry = [];
            let cur = target;
            while (cur && cur !== svg) {
                const tr = cur.getAttribute && cur.getAttribute('transform');
                const tag = cur.tagName;
                const cls = cur.getAttribute && cur.getAttribute('class');
                const ctm = cur.getCTM ? (() => { try { const m = cur.getCTM(); return m ? `CTM=(${m.a.toFixed(2)},${m.b.toFixed(2)},${m.c.toFixed(2)},${m.d.toFixed(2)},${m.e.toFixed(1)},${m.f.toFixed(1)})` : 'no CTM'; } catch(e) { return 'CTM err: '+e.message; } })() : '';
                ancestry.push({tag, cls, transform: tr, ctm});
                cur = cur.parentNode;
            }
            // 当前元素的 CTM
            let labelCtm = null;
            try {
                const m = target.getCTM();
                if (m) labelCtm = {a:m.a, b:m.b, c:m.c, d:m.d, e:m.e, f:m.f};
            } catch (e) {}
            // path 的 CTM
            let pathCtm = null;
            try {
                const m = pathEl.getCTM();
                if (m) pathCtm = {a:m.a, b:m.b, c:m.c, d:m.d, e:m.e, f:m.f};
            } catch (e) {}

            // 真实几何中点 (SVG user 坐标)
            const pathLen = pathEl.getTotalLength();
            const mid = pathEl.getPointAtLength(pathLen / 2);

            // 同时输出 svg viewBox / svgRect / 计算缩放
            const svgInfo = {
                vbX: vb.x, vbY: vb.y, vbW: vb.width, vbH: vb.height,
                svgRectLeft: svgRect.left.toFixed(1), svgRectTop: svgRect.top.toFixed(1),
                svgRectW: svgRect.width.toFixed(1), svgRectH: svgRect.height.toFixed(1),
                scale: scale.toFixed(4),
                svgViewCtm: (() => { try { const m = svg.getCTM(); return m ? `(${m.a.toFixed(3)},${m.b.toFixed(3)},${m.c.toFixed(3)},${m.d.toFixed(3)},${m.e.toFixed(1)},${m.f.toFixed(1)})` : 'null'; } catch(e) { return 'err'; } })()
            };

            // 用 svg CTM 验证 mid viewport 位置
            let midViaCTMX = 0, midViaCTMY = 0;
            try {
                const sp = pathEl.getPointAtLength(pathLen / 2);
                const svgP = pathEl.ownerSVGElement.createSVGPoint();
                svgP.x = sp.x; svgP.y = sp.y;
                const m = pathEl.getCTM();
                if (m) {
                    const ctmdPt = svgP.matrixTransform(m);
                    midViaCTMX = ctmdPt.x; midViaCTMY = ctmdPt.y;
                }
            } catch (e) {}
            // 用 getBoundingClientRect 验证 path 真实位置
            const pRect = pathEl.getBoundingClientRect();

            // 把 SVG 坐标 → viewport 坐标
            const midVpX = svgRect.left + mid.x * scale;
            const midVpY = svgRect.top + mid.y * scale;

            // label 的 viewport 中心
            const lRect = target.getBoundingClientRect();
            const labelCenterVpX = lRect.left + lRect.width / 2;
            const labelCenterVpY = lRect.top + lRect.height / 2;

            // path 起点/终点 (SVG user 坐标)
            const start = pathEl.getPointAtLength(0);
            const end = pathEl.getPointAtLength(pathLen);
            const startVpX = svgRect.left + start.x * scale;
            const startVpY = svgRect.top + start.y * scale;
            const endVpX = svgRect.left + end.x * scale;
            const endVpY = svgRect.top + end.y * scale;

            // g.edgeLabel transform
            const edgeLabelTransform = target.getAttribute('transform');
            // g.label transform
            const innerLabelG = target.querySelector('g.label');
            const gLabelTransform = innerLabelG ? innerLabelG.getAttribute('transform') : null;
            // foreignObject
            const fo = target.querySelector('foreignObject');
            const foX = fo?.getAttribute('x');
            const foY = fo?.getAttribute('y');
            const foW = fo?.getAttribute('width');
            const foH = fo?.getAttribute('height');
            // labelBkg
            const labelBkg = fo?.querySelector(':scope > div');
            const lbRect = labelBkg?.getBoundingClientRect();
            // path 的 d (前 80 字符)
            const dAttr = pathEl.getAttribute('d')?.substring(0, 200);

            return {
                labelText: target.textContent.trim(),
                pathLen: pathLen.toFixed(2),
                bestSrc,
                midSVG: {x: mid.x.toFixed(1), y: mid.y.toFixed(1)},
                midVp: {x: midVpX.toFixed(1), y: midVpY.toFixed(1)},
                midViaCTM: {x: midViaCTMX.toFixed(1), y: midViaCTMY.toFixed(1)},
                pathRect: {x: pRect.x.toFixed(1), y: pRect.y.toFixed(1), w: pRect.width.toFixed(1), h: pRect.height.toFixed(1)},
                startVp: {x: startVpX.toFixed(1), y: startVpY.toFixed(1)},
                endVp: {x: endVpX.toFixed(1), y: endVpY.toFixed(1)},
                labelCenterVp: {x: labelCenterVpX.toFixed(1), y: labelCenterVpY.toFixed(1)},
                labelRect: {x: lRect.x.toFixed(1), y: lRect.y.toFixed(1), w: lRect.width.toFixed(1), h: lRect.height.toFixed(1)},
                labelBkgRect: lbRect ? {x: lbRect.x.toFixed(1), y: lbRect.y.toFixed(1), w: lbRect.width.toFixed(1), h: lbRect.height.toFixed(1)} : null,
                edgeLabelTransform,
                gLabelTransform,
                foX, foY, foW, foH,
                labelCtm,
                pathCtm,
                svgInfo,
                d: dAttr,
                ancestry,
                diffXpx: (labelCenterVpX - midVpX).toFixed(2),
                diffYpx: (labelCenterVpY - midVpY).toFixed(2),
            };
        }''')

        print('=== BO_SUPPLIER_BO_REQ_01 精确诊断 ===')
        for k, v in diag.items():
            print(f'  {k}: {v}')

        # 同时截一张包含 BO_SUPPLIER_BO_REQ_01 的局部图
        if 'labelRect' in diag:
            lr = diag['labelRect']
            # 用 page.screenshot clip 区域
            x = max(0, float(lr['x']) - 80)
            y = max(0, float(lr['y']) - 80)
            w = float(lr['w']) + 160
            h = float(lr['h']) + 160
            await page.screenshot(
                path=r'd:\filework\zoom_bo_supplier_bo_req_01.png',
                clip={'x': x, 'y': y, 'width': w, 'height': h}
            )
            print(f'\nSaved zoom: d:/filework/zoom_bo_supplier_bo_req_01.png (clip {x},{y} {w}x{h})')

        await browser.close()

asyncio.run(main())
