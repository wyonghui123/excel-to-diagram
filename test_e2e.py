#!/usr/bin/env python3
"""
E2E test: arch mgmt → SUPPLY_CHAIN/v1.0 → chart view → verify diagram
- bidirectional arrows on BO_SUPPLIER_BO_REQ_01
- edge labels centered on lines
- tooltip enum resolution
"""
import asyncio
import json
import os
import sys
from playwright.async_api import async_playwright

OUT_DIR = r'd:\filework'

async def safe_json(r):
    """Safely parse JSON response, return dict with status and parsed body"""
    text = await r.text()
    body = None
    parse_err = None
    try:
        body = json.loads(text) if text else None
    except Exception as e:
        parse_err = str(e)
    return {'ok': r.ok, 'status': r.status, 'body': body, 'text': text[:500] if text else '', 'parse_err': parse_err}

async def main():
    console_logs = []
    page_errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = await context.new_page()

        page.on('console', lambda msg: console_logs.append(f'[{msg.type}] {msg.text}'))
        page.on('pageerror', lambda err: page_errors.append(str(err)))

        # ============== 1. Login via dev-login ==============
        print('=' * 60)
        print('STEP 1: Login via dev-login')
        await page.goto('http://localhost:3004/', timeout=20000)
        await page.wait_for_load_state('networkidle', timeout=15000)

        login = await page.evaluate("""async () => {
            const r = await fetch('/api/v1/auth/dev-login?username=admin', {credentials: 'include'});
            const text = await r.text();
            let body = null;
            try { body = JSON.parse(text); } catch (e) {}
            return {ok: r.ok, status: r.status, body: body};
        }""")
        print(f'  Login: status={login["status"]} ok={login["ok"]}')
        if not login['ok']:
            print(f'  FAILED: {login.get("body")}')
            await browser.close()
            return
        print(f'  User: {login["body"]["data"]["user"]["display_name"]}')

        # ============== 2. Find SUPPLY_CHAIN and v1.0 directly via API ==============
        print()
        print('STEP 2: Find SUPPLY_CHAIN + v1.0 via API')
        products_data = await page.evaluate("""async () => {
            const r = await fetch('/api/v2/bo/product/list', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({page: 1, page_size: 200, search: 'SUPPLY_CHAIN'})
            });
            const text = await r.text();
            let body = null;
            try { body = JSON.parse(text); } catch (e) {return {parse_err: e, text: text};}
            return body;
        }""")
        # Response shape: {success, data: [...], page, page_size, total}
        if isinstance(products_data, dict):
            products = products_data.get('data') or []
        elif isinstance(products_data, list):
            products = products_data
        else:
            products = []
        if not products:
            print(f'  No products found. response keys: {list(products_data.keys()) if isinstance(products_data, dict) else "N/A"}')
            print(f'  Raw: {json.dumps(products_data, ensure_ascii=False)[:500]}')
            await browser.close()
            return
        product = next((p for p in products if p.get('code') == 'SUPPLY_CHAIN'), products[0])
        product_id = product['id']
        print(f'  Product: id={product_id} code={product["code"]} name={product["name"]}')

        versions_data = await page.evaluate(f"""async () => {{
            const r = await fetch('/api/v2/bo/version/list', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{page: 1, page_size: 50, product_id: {product_id}, search: 'v1'}})
            }});
            const text = await r.text();
            let body = null;
            try {{ body = JSON.parse(text); }} catch (e) {{return {{parse_err: e, text: text}};}}
            return body;
        }}""")
        if isinstance(versions_data, dict):
            versions = versions_data.get('data') or []
        elif isinstance(versions_data, list):
            versions = versions_data
        else:
            versions = []
        if not versions:
            print(f'  No versions found. Raw: {json.dumps(versions_data, ensure_ascii=False)[:500]}')
            await browser.close()
            return
        version = versions[0]
        version_id = version['id']
        print(f'  Version: id={version_id} code={version.get("code")} name={version["name"]}')

        # ============== 3. Navigate to archdata-chart with store data ==============
        # Use chartArchDataStore (set via Pinia) so the chart page reads from store directly
        # OR navigate to /system/archdata and click chart button
        print()
        print('STEP 3: Navigate to /system/archdata and select product/version')

        # Try direct API approach: pre-set archData in sessionStorage + go to chart page
        # This bypasses the dropdown UI issue
        print('  Approach: use sessionStorage to pre-set archData, then go to chart page')

        # archData shape: { versionId, productId, hierarchyFilter, relationTypeFilter? }
        arch_data = {
            'versionId': version_id,
            'productId': product_id,
            'hierarchyFilter': {},
        }

        # Set sessionStorage in browser context (mirror what MultiObjectManagementPage does)
        await page.evaluate(f"""() => {{
            sessionStorage.setItem('archDataForDiagram', JSON.stringify({json.dumps(arch_data)}));
            sessionStorage.setItem('lastArchDataForDiagram', JSON.stringify({json.dumps(arch_data)}));
            sessionStorage.setItem('archDataCurrentStep', '3');
            sessionStorage.setItem('archDataChartType', 'businessObject');
        }}""")
        print(f'  archData set in sessionStorage: {arch_data}')

        # Navigate to archdata-chart page
        print()
        print('STEP 4: Navigate to /archdata-chart')
        await page.goto('http://localhost:3004/archdata-chart', timeout=20000)
        await page.wait_for_load_state('networkidle', timeout=15000)
        await page.wait_for_timeout(15000)  # Wait for diagram to render

        url = page.url
        print(f'  Current URL: {url}')

        # Check page state - was there a redirect or error?
        page_state = await page.evaluate('''() => {
            const h = document.querySelector("h1, h2, .el-page-header__content");
            const rootContent = document.querySelector("#app")?.innerText?.slice(0, 500);
            return {
                url: window.location.href,
                title: document.title,
                h1: h ? h.innerText : null,
                contentSample: rootContent,
                hasMermaid: !!document.querySelector(".mermaid-container"),
                hasMermaidSvg: document.querySelectorAll("svg").length,
            };
        }''')
        print(f'  Page state: {json.dumps(page_state, ensure_ascii=False)[:500]}')

        # ============== 4.5. Click through 3-step wizard to display step ==============
        print()
        print('STEP 4.5: Click through wizard (Type → Config → Display)')

        async def click_by_text(selector, text, exact=False):
            """Click first element matching selector and containing text"""
            exact_js = 'true' if exact else 'false'
            ok = await page.evaluate(f'''() => {{
                const els = document.querySelectorAll({json.dumps(selector)});
                const target = {json.dumps(text)};
                for (const el of els) {{
                    const t = (el.innerText || el.textContent || '').trim();
                    if (({exact_js} && t === target) || (!{exact_js} && t.includes(target))) {{
                        el.click();
                        return {{text: t, tag: el.tagName}};
                    }}
                }}
                return null;
            }}''')
            return ok

        # Step 1: select "业务对象图" chart type
        chart_type_card = await click_by_text('.el-radio, .chart-type-card, [class*="chart-type"]', '业务对象图')
        print(f'  Click chart type card: {chart_type_card}')

        # Click "下一步" button (advance to step 2)
        await page.wait_for_timeout(800)
        next_btn = await click_by_text('button', '下一步')
        print(f'  Click 下一步: {next_btn}')
        await page.wait_for_timeout(2000)

        # Click "下一步" again (advance to step 3 - display)
        next_btn2 = await click_by_text('button', '下一步')
        print(f'  Click 下一步 (2nd): {next_btn2}')
        await page.wait_for_timeout(2000)

        # Click "生成" button if present
        gen_btn = await click_by_text('button', '生成')
        print(f'  Click 生成: {gen_btn}')
        await page.wait_for_timeout(10000)  # Wait for diagram render

        # Check current state
        step_state = await page.evaluate('''() => {
            const stepItems = document.querySelectorAll('.el-step, [class*="step-item"]');
            const currentStep = Array.from(stepItems).findIndex(s => s.className.includes('is-current') || s.className.includes('active'));
            const hasMermaid = !!document.querySelector('.mermaid-container svg');
            return {
                stepCount: stepItems.length,
                currentStep: currentStep,
                hasMermaid: hasMermaid,
                mermaidSvgs: document.querySelectorAll('.mermaid-container svg').length,
            };
        }''')
        print(f'  Step state: {step_state}')

        # ============== 5. Verify diagram state ==============
        print()
        print('STEP 5: Verify diagram state')

        await page.screenshot(path=os.path.join(OUT_DIR, 'diagram_e2e.png'), full_page=False)

        # Count basic elements
        basic = await page.evaluate('''() => {
            return {
                mermaidSvgs: document.querySelectorAll(".mermaid-container svg").length,
                edgeLabels: document.querySelectorAll("g.edgeLabel").length,
                edgePaths: document.querySelectorAll("g.edges.edgePaths > g.edgePath").length,
                nodes: document.querySelectorAll("g.node").length,
            };
        }''')
        print(f'  Mermaid SVGs: {basic["mermaidSvgs"]}')
        print(f'  edgeLabels: {basic["edgeLabels"]}')
        print(f'  edgePaths: {basic["edgePaths"]}')
        print(f'  nodes: {basic["nodes"]}')

        # Check bidirectional attributes (try both structures: g.edgePath AND path.flowchart-link)
        bidi = await page.evaluate('''() => {
            // Try g.edges.edgePaths > g.edgePath path (new Mermaid 11 structure)
            let paths = document.querySelectorAll("g.edges.edgePaths > g.edgePath path");
            let usedStructure = "g.edgePath";
            if (paths.length === 0) {
                // Fallback: path.flowchart-link directly (ELK layout or older Mermaid)
                paths = document.querySelectorAll("path.flowchart-link");
                usedStructure = "path.flowchart-link";
            }
            const bidiPaths = [];
            paths.forEach((p, idx) => {
                if (p.getAttribute("data-bidirectional") === "true") {
                    bidiPaths.push({
                        idx: idx,
                        markerStart: p.getAttribute("marker-start"),
                        markerEnd: p.getAttribute("marker-end"),
                        relationCode: p.closest('g.edgePath, g')?.getAttribute('data-relation-code')
                    });
                }
            });
            return {usedStructure: usedStructure, totalPaths: paths.length, bidiPaths: bidiPaths};
        }''')
        print(f'  Edge path structure: {bidi["usedStructure"]} (total: {bidi["totalPaths"]})')
        print(f'  Bidirectional paths: {len(bidi["bidiPaths"])}')
        for b in bidi['bidiPaths']:
            print(f'    {b}')

        # Check edge label transforms
        labels = await page.evaluate('''() => {
            const labels = document.querySelectorAll("g.edgeLabel");
            return Array.from(labels).slice(0, 5).map(l => ({
                transform: l.getAttribute("transform"),
                relationCode: l.getAttribute("data-relation-code"),
                text: (l.textContent || "").trim().slice(0, 50)
            }));
        }''')
        print(f'  Edge label samples (first 5):')
        for l in labels:
            print(f'    {l}')

        # Check label has midpoint transform
        label_midpoint_check = await page.evaluate('''() => {
            const labels = document.querySelectorAll("g.edgeLabel");
            const results = [];
            labels.forEach((l, idx) => {
                const t = l.getAttribute("transform") || "";
                const match = t.match(/translate\\(([\\d.\\-]+),\\s*([\\d.\\-]+)\\)/);
                if (match) {
                    results.push({idx: idx, x: parseFloat(match[1]), y: parseFloat(match[2])});
                }
            });
            return {count: labels.length, withTransform: results.length, samples: results.slice(0, 3)};
        }''')
        print(f'  Edge label midpoint transforms: withTransform={label_midpoint_check["withTransform"]}/{label_midpoint_check["count"]}')
        for s in label_midpoint_check['samples']:
            print(f'    {s}')

        # ============== 6. Tooltip test ==============
        print()
        print('STEP 6: Test tooltip on edge')
        tooltip_result = await page.evaluate(r'''async () => {
            const label = document.querySelector('g.edgeLabel');
            if (!label) return {error: 'No edgeLabel found'};

            // Try g.edgePath first, fallback to flowchart-link
            let paths = document.querySelectorAll('g.edges.edgePaths > g.edgePath path');
            if (paths.length === 0) {
                paths = document.querySelectorAll('path.flowchart-link');
            }
            if (paths.length === 0) return {error: 'No edge path found'};

            // Hover the label (where event listener is attached) with proper event sequence
            const rect = label.getBoundingClientRect();
            const cx = rect.left + rect.width / 2;
            const cy = rect.top + rect.height / 2;

            // Set up a real mouseover (mouseenter doesn't bubble, mousemove does)
            const fire = (el, type) => {
                const e = new MouseEvent(type, {bubbles: type === 'mousemove' || type === 'mouseenter', clientX: cx, clientY: cy, view: window});
                el.dispatchEvent(e);
            };
            fire(label, 'mouseenter');
            fire(label, 'mousemove');
            await new Promise(r => setTimeout(r, 800));

            // Find mermaid-tooltip (the edge tooltip, NOT user menu tooltip)
            const mtip = document.getElementById('mermaid-tooltip');
            return {
                pathCount: paths.length,
                labelText: (label.textContent || '').trim().slice(0, 80),
                edgeTooltipExists: !!mtip,
                edgeTooltipVisible: mtip ? (mtip.style.visibility !== 'hidden' && mtip.offsetWidth > 0) : false,
                edgeTooltipText: mtip ? (mtip.textContent || '').trim().slice(0, 300) : null,
            };
        }''')
        print(f'  Tooltip result: {json.dumps(tooltip_result, ensure_ascii=False, indent=2)}')

        # ============== 7. Page errors & diagnostic logs ==============
        print()
        print('STEP 7: Page errors and diagnostic logs')

        if page_errors:
            print('  PAGE ERRORS:')
            for err in page_errors[:5]:
                print(f'    {err[:300]}')
        else:
            print('  No page errors')

        # Filter diagnostic logs
        diag_logs = [log for log in console_logs if any(k in log for k in [
            'v40.2', 'v40.1', 'forceEdgeLabelToMidpoint', 'addBidirectionalAttributes',
            'addLinkCodeAttributes', 'fixArrowMarkers', 'isBidirectionalLink',
            '[useTooltip]', 'Bidirectional'
        ])]
        print(f'  Diagnostic log entries: {len(diag_logs)}')
        for log in diag_logs[:30]:
            print(f'    {log[:400]}')

        # Save logs
        with open(os.path.join(OUT_DIR, 'console_logs_e2e.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(console_logs))
        print(f'\n  Total console logs: {len(console_logs)}')
        print(f'  Saved to: {os.path.join(OUT_DIR, "console_logs_e2e.txt")}')

        await browser.close()

asyncio.run(main())
