#!/usr/bin/env python3
"""深入诊断 BO_SUPPLIER_BO_REQ_01 标签居中问题"""
import asyncio
import json
import sys
from playwright.async_api import async_playwright

OUT_FILE = r'd:/filework/excel-to-diagram/diag_v408_out.json'

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        c = await b.new_context(viewport={'width': 1600, 'height': 1000})
        pg = await c.new_page()

        # 收集所有 console 日志
        logs = []
        pg.on('console', lambda msg: logs.append(f'[{msg.type}] {msg.text}'))

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

        # 切到业务对象图
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

        # 详细诊断
        d = await pg.evaluate("""() => {
            const allSvgs = Array.from(document.querySelectorAll('svg'));
            const ds = allSvgs.find(s => s.getAttribute('class')?.includes('flowchart') && s.getAttribute('class')?.includes('hide-tails'));
            if (!ds) return {err: 'no flowchart svg'};
            const ls = Array.from(ds.querySelectorAll('g.edgeLabel'));
            const t = ls.find(l => (l.textContent||'').includes('BO_SUPPLIER_BO_REQ_01'));
            if (!t) return {err: 'no label', allLabels: ls.map(l => l.textContent.trim()).slice(0,10)};

            const fo = t.querySelector('foreignObject');
            const lb = fo?.querySelector(':scope > div');
            const gl = t.querySelector('g.label');

            const vb = ds.viewBox?.baseVal;
            const sr = ds.getBoundingClientRect();
            const scaleX = sr.width / vb.width;
            const scaleY = sr.height / vb.height;

            // 解析 g.edgeLabel 的 transform
            const tTransform = t.getAttribute('transform') || '';
            const tMatch = tTransform.match(/translate\\(([-\\d.]+)[,\\s]+([-\\d.]+)\\)/);
            const lx = tMatch ? parseFloat(tMatch[1]) : null;
            const ly = tMatch ? parseFloat(tMatch[2]) : null;

            // 找最近 path
            const paths = Array.from(ds.querySelectorAll('path.flowchart-link'));
            let bp = null, bd = Infinity;
            paths.forEach(p => {
                try {
                    const m = p.getPointAtLength(p.getTotalLength()/2);
                    const d = Math.hypot(m.x-lx, m.y-ly);
                    if (d < bd) { bd = d; bp = p; }
                } catch (e) {}
            });

            const pm = bp ? bp.getPointAtLength(bp.getTotalLength()/2) : null;
            const pr = bp ? bp.getBoundingClientRect() : null;
            const lr = t.getBoundingClientRect();
            const lbr = lb ? lb.getBoundingClientRect() : null;
            const fr = fo ? fo.getBoundingClientRect() : null;
            const gr = gl ? gl.getBoundingClientRect() : null;

            // 计算 path midpoint 在 viewport 坐标
            const pathMidVp = pm ? {
                x: sr.left + (pm.x - vb.x) * scaleX,
                y: sr.top + (pm.y - vb.y) * scaleY
            } : null;

            // 计算 labelBkg 中心在 viewport 坐标
            const lbCenterVp = lbr ? {
                x: lbr.x + lbr.width/2,
                y: lbr.y + lbr.height/2
            } : null;

            // g.edgeLabel 中心 (transform 中心) 在 viewport 坐标
            const elCenterVp = (lx !== null && ly !== null) ? {
                x: sr.left + (lx - vb.x) * scaleX,
                y: sr.top + (ly - vb.y) * scaleY
            } : null;

            return {
                svg: {
                    rect: {x: sr.left, y: sr.top, w: sr.width, h: sr.height},
                    viewBox: {x: vb.x, y: vb.y, w: vb.width, h: vb.height},
                    scaleX: scaleX,
                    scaleY: scaleY,
                },
                edgeLabel: {
                    transform: tTransform,
                    rect: {x: lr.x, y: lr.y, w: lr.width, h: lr.height},
                    centerSvg: {x: lx, y: ly},
                    centerVp: elCenterVp,
                },
                gLabel: gl ? {
                    transform: gl.getAttribute('transform'),
                    rect: {x: gr.x, y: gr.y, w: gr.width, h: gr.height},
                } : null,
                foreignObject: fo ? {
                    x: fo.getAttribute('x'),
                    y: fo.getAttribute('y'),
                    width: fo.getAttribute('width'),
                    height: fo.getAttribute('height'),
                    rect: {x: fr.x, y: fr.y, w: fr.width, h: fr.height},
                } : null,
                labelBkg: lbr ? {
                    rect: {x: lbr.x, y: lbr.y, w: lbr.width, h: lbr.height},
                    centerVp: lbCenterVp,
                    textContent: lb.textContent.trim().substring(0, 50),
                } : null,
                path: {
                    d: bp ? bp.getAttribute('d').substring(0, 200) : null,
                    midSvg: pm ? {x: pm.x, y: pm.y} : null,
                    midVp: pathMidVp,
                    rect: pr ? {x: pr.x, y: pr.y, w: pr.width, h: pr.height} : null,
                },
                // 关键 diff
                diffLabelBkg_to_pathMid: lbr && pm ? {
                    dx: (lbr.x + lbr.width/2) - (sr.left + (pm.x - vb.x) * scaleX),
                    dy: (lbr.y + lbr.height/2) - (sr.top + (pm.y - vb.y) * scaleY),
                } : null,
                diffELabel_to_pathMid: (lx !== null && pm) ? {
                    dx: (sr.left + (lx - vb.x) * scaleX) - (sr.left + (pm.x - vb.x) * scaleX),
                    dy: (sr.top + (ly - vb.y) * scaleY) - (sr.top + (pm.y - vb.y) * scaleY),
                } : null,
            };
        }""")

        # 写文件
        with open(OUT_FILE, 'w', encoding='utf-8') as f:
            json.dump({'diag': d, 'logs': logs[-30:]}, f, ensure_ascii=False, indent=2)
        print(f'Output: {OUT_FILE}')
        await b.close()

asyncio.run(main())
