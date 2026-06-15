#!/usr/bin/env python3
"""验证 textHSvg 实际值 - 跟代码用相同的方式测"""
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

        # 用 processPairs 相同方式测
        result = await page.evaluate(r'''() => {
            const labels = Array.from(document.querySelectorAll('g.edgeLabel'));
            const target = labels.find(l => (l.textContent||'').includes('BO_SUPPLIER_BO_REQ_01'));
            if (!target) return {error: 'no label'};

            const fo = target.querySelector('foreignObject');
            const foWidth = parseFloat(fo.getAttribute('width'));
            const foHeight = parseFloat(fo.getAttribute('height'));
            const labelBkgDiv = fo.querySelector(':scope > div');
            const divRect = labelBkgDiv.getBoundingClientRect();
            const svgEl2 = fo.closest('svg');
            const svgRect2 = svgEl2.getBoundingClientRect();
            const vb2 = svgEl2.viewBox?.baseVal;

            let sc2 = 1;
            if (vb2 && vb2.width > 0) {
                sc2 = svgRect2.width / vb2.width;
            }
            const textHVp = divRect.height;
            const textHSvg = textHVp / (sc2 || 1);
            const textBaselineOffsetSvg = textHSvg * 0.35;

            // 父 g.edgeLabel transform & ctm
            const edgeLabelCTM = (() => { try { const m = target.getCTM(); return m ? `(${m.a.toFixed(3)},${m.b.toFixed(3)},${m.c.toFixed(3)},${m.d.toFixed(3)},${m.e.toFixed(1)},${m.f.toFixed(1)})` : null; } catch(e) { return 'err'; } })();
            const innerLabelG = target.querySelector('g.label');
            const gLabelTransform = innerLabelG ? innerLabelG.getAttribute('transform') : null;
            const edgeLabelTransform = target.getAttribute('transform');

            // 用 innerG 局部 (0, 0) 算出 viewport y
            let gLabelOriginVpY = null;
            try {
                const svgP = svgEl2.createSVGPoint();
                svgP.x = 0; svgP.y = 0;
                const m = innerLabelG.getCTM();
                const pt = svgP.matrixTransform(m);
                gLabelOriginVpY = pt.y;
            } catch (e) {}

            // 测 div 实际 font-size / line-height / p 元素的 rect
            const computedStyle = window.getComputedStyle(labelBkgDiv);
            const pEl = labelBkgDiv.querySelector('p');
            let pRect = null;
            if (pEl) pRect = pEl.getBoundingClientRect();
            const pStyle = pEl ? window.getComputedStyle(pEl) : null;
            const spanEl = pEl ? pEl.querySelector('span') : null;
            let spanRect = null;
            if (spanEl) spanRect = spanEl.getBoundingClientRect();

            return {
                foWidth, foHeight,
                divRect: {x: divRect.x.toFixed(1), y: divRect.y.toFixed(1), w: divRect.width.toFixed(1), h: divRect.height.toFixed(1)},
                divStyle: {fontSize: computedStyle.fontSize, lineHeight: computedStyle.lineHeight, padding: computedStyle.padding, display: computedStyle.display, verticalAlign: computedStyle.verticalAlign},
                pRect: pRect ? {x: pRect.x.toFixed(1), y: pRect.y.toFixed(1), w: pRect.width.toFixed(1), h: pRect.height.toFixed(1)} : null,
                pStyle: pStyle ? {fontSize: pStyle.fontSize, lineHeight: pStyle.lineHeight, margin: pStyle.margin, padding: pStyle.padding} : null,
                spanRect: spanRect ? {x: spanRect.x.toFixed(1), y: spanRect.y.toFixed(1), w: spanRect.width.toFixed(1), h: spanRect.height.toFixed(1)} : null,
                svgRect2: {x: svgRect2.x.toFixed(1), y: svgRect2.y.toFixed(1), w: svgRect2.width.toFixed(1), h: svgRect2.height.toFixed(1)},
                vb2: vb2 ? {x: vb2.x, y: vb2.y, w: vb2.width, h: vb2.height} : null,
                sc2,
                textHVp, textHSvg, textBaselineOffsetSvg,
                edgeLabelCTM, edgeLabelTransform, gLabelTransform, gLabelOriginVpY,
            };
        }''')

        print('=== 复现 processPairs 的 textH 计算 ===')
        for k, v in result.items():
            print(f'  {k}: {v}')

        await browser.close()

asyncio.run(main())
