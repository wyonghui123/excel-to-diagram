#!/usr/bin/env python3
"""
极简诊断: 检查 BO_SUPPLIER_BO_REQ_01 labelBkg 的所有属性/样式/位置
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
        await page.wait_for_timeout(2000)  # 多等一下让样式注入

        diag = await page.evaluate(r'''() => {
            const allSvgs = Array.from(document.querySelectorAll('svg'));
            const diagramSvg = allSvgs.find(s => s.getAttribute('class')?.includes('flowchart') && s.getAttribute('class')?.includes('hide-tails'));
            if (!diagramSvg) return {error: 'no diagram svg'};
            const labels = Array.from(diagramSvg.querySelectorAll('g.edgeLabel'));
            const target = labels.find(l => (l.textContent||'').includes('BO_SUPPLIER_BO_REQ_01'));
            if (!target) return {error: 'label not found'};

            const fo = target.querySelector('foreignObject');
            const labelBkg = fo.querySelector(':scope > div');

            // 1. labelBkg 的 outerHTML
            const outerHTML = labelBkg.outerHTML.substring(0, 500);

            // 2. labelBkg 的 attribute / style
            const attrs = {};
            for (const a of labelBkg.attributes) attrs[a.name] = a.value;

            // 3. labelBkg 的 computed style
            const cs = window.getComputedStyle(labelBkg);
            const computed = {
                display: cs.display,
                position: cs.position,
                left: cs.left,
                top: cs.top,
                right: cs.right,
                bottom: cs.bottom,
                transform: cs.transform,
                transformOrigin: cs.transformOrigin,
                margin: cs.margin,
                marginLeft: cs.marginLeft,
                marginRight: cs.marginRight,
                marginTop: cs.marginTop,
                marginBottom: cs.marginBottom,
                padding: cs.padding,
                width: cs.width,
                height: cs.height,
                minWidth: cs.minWidth,
                maxWidth: cs.maxWidth,
                textAlign: cs.textAlign,
                whiteSpace: cs.whiteSpace,
                boxSizing: cs.boxSizing,
                fontSize: cs.fontSize,
                lineHeight: cs.lineHeight,
                overflow: cs.overflow,
                verticalAlign: cs.verticalAlign,
            };

            // 4. foreignObject 的 attribute / style
            const foAttrs = {};
            for (const a of fo.attributes) foAttrs[a.name] = a.value;
            const foCs = window.getComputedStyle(fo);
            const foComputed = {
                display: foCs.display,
                position: foCs.position,
                overflow: foCs.overflow,
                width: foCs.width,
                height: foCs.height,
                transform: foCs.transform,
            };

            // 5. g.label 的 transform
            const gLabel = target.querySelector('g.label');
            const gLabelTransform = gLabel ? gLabel.getAttribute('transform') : null;
            const gLabelCS = gLabel ? window.getComputedStyle(gLabel) : null;
            const gLabelComputed = gLabelCS ? {transform: gLabelCS.transform, transformOrigin: gLabelCS.transformOrigin} : null;

            // 6. g.edgeLabel 的 transform
            const elTransform = target.getAttribute('transform');

            // 7. labelBkg 实际位置
            const lbRect = labelBkg.getBoundingClientRect();
            const foRect = fo.getBoundingClientRect();

            return {
                outerHTML,
                attrs,
                computed,
                foAttrs,
                foComputed,
                gLabelTransform,
                gLabelComputed,
                elTransform,
                lbRect: {x: lbRect.x.toFixed(2), y: lbRect.y.toFixed(2), w: lbRect.width.toFixed(2), h: lbRect.height.toFixed(2)},
                foRect: {x: foRect.x.toFixed(2), y: foRect.y.toFixed(2), w: foRect.width.toFixed(2), h: foRect.height.toFixed(2)},
                lbVsFoOffsetX: (lbRect.x - foRect.x).toFixed(2),
                lbVsFoOffsetY: (lbRect.y - foRect.y).toFixed(2),
            };
        }''')

        print('=== labelBkg 详细诊断 ===')
        import pprint
        pprint.pprint(diag, width=200)

        await browser.close()

asyncio.run(main())
