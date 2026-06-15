#!/usr/bin/env python3
"""v40.8 批量验证 - 所有 edge label 是否居中"""
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

        # 批量验证: 计算每个 edge label 跟其最近 path 中点的偏差
        result = await pg.evaluate("""() => {
            const allSvgs = Array.from(document.querySelectorAll('svg'));
            const ds = allSvgs.find(s => s.getAttribute('class')?.includes('flowchart') && s.getAttribute('class')?.includes('hide-tails'));
            if (!ds) return {err: 'no svg'};

            const labels = Array.from(ds.querySelectorAll('g.edgeLabel'));
            const paths = Array.from(ds.querySelectorAll('path.flowchart-link'));

            const results = labels.map((t, idx) => {
                const tTransform = t.getAttribute('transform') || '';
                const tMatch = tTransform.match(/translate\\(([-\\d.]+)[,\\s]+([-\\d.]+)\\)/);
                if (!tMatch) return {idx, text: t.textContent.trim().substring(0, 40), err: 'no transform'};
                const lx = parseFloat(tMatch[1]); const ly = parseFloat(tMatch[2]);

                // 找最近 path
                let bp = null, bd = Infinity;
                paths.forEach(p => {
                    try {
                        const m = p.getPointAtLength(p.getTotalLength()/2);
                        const d = Math.hypot(m.x-lx, m.y-ly);
                        if (d < bd) { bd = d; bp = p; }
                    } catch (e) {}
                });
                if (!bp) return {idx, text: t.textContent.trim().substring(0, 40), err: 'no path'};

                const pm = bp.getPointAtLength(bp.getTotalLength()/2);
                const pr = bp.getBoundingClientRect();
                const lbr = t.querySelector('foreignObject div.labelBkg')?.getBoundingClientRect();

                // path 中点 viewport: 用 getPointAtLength 拿 SVG 几何中点, 再用 CTM 换算到 viewport
                // 关键: 路径几何中点 (getPointAtLength) ≠ 路径包围盒中心 (pr.x + pr.width/2)
                //       对角线 path 的几何中点跟包围盒中心差很多
                let pathMidVpX, pathMidVpY;
                const ctm = bp.getScreenCTM();
                if (ctm) {
                    // pm 是 SVG 用户空间坐标, 用 CTM 换算到屏幕空间
                    pathMidVpX = ctm.a * pm.x + ctm.c * pm.y + ctm.e;
                    pathMidVpY = ctm.b * pm.x + ctm.d * pm.y + ctm.f;
                } else {
                    // fallback: 用包围盒中心
                    pathMidVpX = pr.x + pr.width/2;
                    pathMidVpY = pr.y + pr.height/2;
                }

                // labelBkg 中心 viewport
                const lbCenterVpX = lbr ? lbr.x + lbr.width/2 : null;
                const lbCenterVpY = lbr ? lbr.y + lbr.height/2 : null;

                return {
                    idx,
                    text: t.textContent.trim().substring(0, 40),
                    labelBkgW: lbr ? lbr.width.toFixed(1) : null,
                    pathMidVpX: pathMidVpX.toFixed(1),
                    lbCenterVpX: lbCenterVpX ? lbCenterVpX.toFixed(1) : null,
                    dx: lbr ? (lbCenterVpX - pathMidVpX).toFixed(1) : null,
                    dy: lbr ? (lbCenterVpY - pathMidVpY).toFixed(1) : null,
                };
            });

            return results;
        }""")

        # 写入文件
        with open('d:/filework/excel-to-diagram/v408_batch_verify.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # 统计
        if isinstance(result, list):
            centered = sum(1 for r in result if r.get('dx') and abs(float(r['dx'])) < 3)
            total = len(result)
            print(f'\n=== 居中验证结果 ===')
            print(f'总标签: {total}, 居中(±3px): {centered}, 失败: {total - centered}')
            print(f'\n详情:')
            for r in result:
                flag = 'OK' if r.get('dx') and abs(float(r['dx'])) < 3 else 'X'
                print(f"  [{flag}] {r.get('text', 'N/A')[:35]:<35} dx={r.get('dx', 'N/A'):>6} dy={r.get('dy', 'N/A'):>6} lbW={r.get('labelBkgW', 'N/A')}")
        await b.close()

asyncio.run(main())
