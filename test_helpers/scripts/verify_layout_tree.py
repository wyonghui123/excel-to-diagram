"""
Verify LayoutControlPanel tree rendering after refactoring (browser).
Uses dev shortcut URL to load chart data, then verifies the layout panel tree.
Flow: auth → probe API for version+domain → navigate with shortcut → chart view → expand layout panel → verify tree.
"""
import sys, json, time, base64, urllib.parse
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

results = {}

def log(step, ok, detail):
    results[step] = {'ok': ok, 'detail': detail}
    print(f"[{step}] {'PASS' if ok else 'FAIL'}: {detail}")

try:
    with PlaywrightCLI(headless=True) as cli:
        print("=== Step 0: Auth + probe API for version with domain data ===")
        cli.authenticated_navigate('/system/archdata', wait_for_selector='.gt-select', timeout=45000)
        time.sleep(2)

        probe = cli.evaluate('''() => (async () => {
            const out = {};
            const pr = await fetch('/api/v2/bo/product?page=1&page_size=100', {credentials: 'include'});
            const pd = await pr.json();
            const prods = pd.data?.items || pd.items || pd.data || [];
            let best = null;
            for (const p of (Array.isArray(prods) ? prods : [])) {
                try {
                    const vr = await fetch(`/api/v2/bo/version?product_id=${p.id}&page=1&page_size=50`, {credentials: 'include'});
                    const vd = await vr.json();
                    const vers = vd.data?.items || vd.items || vd.data || [];
                    for (const v of (Array.isArray(vers) ? vers : [])) {
                        if ((v.child_count || 0) > 0) {
                            if (!best || (v.child_count || 0) > (best.childCount || 0)) {
                                best = {productId: p.id, productCode: p.code, productName: p.name,
                                        versionId: v.id, versionCode: v.code, versionName: v.name,
                                        childCount: v.child_count};
                            }
                        }
                    }
                } catch (e) {}
            }
            out.best = best;
            if (best) {
                const dr = await fetch(`/api/v2/bo/domain?version_id=${best.versionId}&page=1&page_size=5`, {credentials: 'include'});
                const dd = await dr.json();
                const doms = dd.data?.items || dd.items || dd.data || [];
                out.firstDomainId = (Array.isArray(doms) && doms.length > 0) ? doms[0].id : null;
                out.firstDomainName = (Array.isArray(doms) && doms.length > 0) ? doms[0].name : null;
            }
            return out;
        })()''')

        best = probe.get('best')
        if not best:
            log('step0', False, f"no version with domain data found")
            cli.screenshot('verify_layout_tree_nodata.png')
            raise SystemExit(1)

        pcode = best.get('productCode') or best.get('productName')
        vcode = best.get('versionCode') or best.get('versionName')
        domainId = probe.get('firstDomainId')
        print(f"[target] product={pcode} version={vcode} (domains={best['childCount']}, firstDomainId={domainId})")
        log('step0', True, f"found: {pcode}/{vcode} domain={domainId}")

        scope_json = json.dumps({"domain": [domainId]} if domainId else {})
        scope_b64 = base64.b64encode(scope_json.encode()).decode()
        scope_encoded = urllib.parse.quote(scope_b64, safe='')
        shortcut_path = f'/system/archdata?shortcut=1&productCode={urllib.parse.quote(str(pcode), safe="")}&versionCode={urllib.parse.quote(str(vcode), safe="")}&scope={scope_encoded}'
        print(f"\n[shortcut] navigate to: {shortcut_path[:120]}...")

        cli.authenticated_navigate(shortcut_path, wait_for_selector='.gt-btn-chart-toggle', timeout=60000)
        print("[shortcut] waiting for shortcut logic...")
        time.sleep(15)

        # Step 1: switch to chart view (layout panel only shows in chart mode)
        print("\n=== Step 1: switch to chart view ===")
        chart_btn = cli.evaluate('''() => {const b=document.querySelector('.gt-btn-chart-toggle'); return b?{text:b.textContent.trim(),disabled:b.disabled}:null}''')
        print(f"[debug] chart toggle: {chart_btn}")
        if chart_btn and '图表' in chart_btn.get('text', ''):
            cli.click('.gt-btn-chart-toggle')
            time.sleep(4)
        lay = cli.evaluate('''() => !!document.querySelector('.rst-panel-layout')''')
        log('step1', lay, f"layout panel exists in chart view: {lay}")
        cli.screenshot('verify_layout_tree_chart.png')

        # Step 2: expand layout panel
        print("\n=== Step 2: expand layout panel ===")
        if lay:
            header = cli.evaluate('''() => {const h=document.querySelector('.rst-panel-layout .collapsible-panel__header'); return !!h}''')
            if header:
                cli.click('.rst-panel-layout .collapsible-panel__header')
                time.sleep(2)
        expanded = cli.evaluate('''() => {
            const p = document.querySelector('.rst-panel-layout');
            return p ? !p.classList.contains('is-collapsed') : false;
        }''')
        log('step2', expanded, f"layout panel expanded: {expanded}")

        # Step 3: verify tree nodes, search box, add button, toolbar
        print("\n=== Step 3: verify tree structure ===")
        state = cli.evaluate('''() => {
            const nodes = document.querySelectorAll('.lgn-node');
            return {
                nodeCount: nodes.length,
                searchBox: !!document.querySelector('.lcp-search-input'),
                addBtn: !!document.querySelector('.lcp-add-group-btn'),
                firstTitle: nodes.length ? (nodes[0].querySelector('.lgn-title-text')?.textContent || '') : null,
                toolbarCount: document.querySelectorAll('.lcp-toolbar').length,
                hasCaret: document.querySelectorAll('.lgn-caret').length,
                hasTypeIcon: document.querySelectorAll('.lgn-type-icon').length,
            };
        }''')
        print(f"[debug] tree state: {json.dumps(state, ensure_ascii=False)}")
        log('step3a', state['nodeCount'] > 0, f"tree nodes rendered: {state['nodeCount']}")
        log('step3b', state['searchBox'] and state['addBtn'], f"toolbar: search={state['searchBox']}, add={state['addBtn']}")
        log('step3c', state['hasCaret'] > 0 and state['hasTypeIcon'] > 0, f"caret={state['hasCaret']}, typeIcon={state['hasTypeIcon']}")
        cli.screenshot('verify_layout_tree_panel.png')

        # Step 4: toggle a node's enabled via eye button (hover action)
        print("\n=== Step 4: tree node inline actions ===")
        eye = cli.evaluate('''() => {
            const e = document.querySelector('.lgn-eye');
            return e ? {exists: true, visible: e.offsetParent !== null} : {exists: false};
        }''')
        log('step4', eye.get('exists'), f"eye button present: {eye}")

        # Step 5: search filter
        print("\n=== Step 5: search filter ===")
        if state['searchBox']:
            cli.fill('.lcp-search-input input', '不存在的分组xyz')
            time.sleep(1)
            filtered = cli.evaluate('''() => document.querySelectorAll('.lgn-node').length''')
            print(f"[debug] after search '不存在的分组xyz': nodeCount={filtered}")
            cli.fill('.lcp-search-input input', '')
            time.sleep(1)
            restored = cli.evaluate('''() => document.querySelectorAll('.lgn-node').length''')
            log('step5', filtered == 0 and restored > 0, f"search: filtered={filtered}, restored={restored}")

        # Step 6: no JS errors
        print("\n=== Step 6: no JS errors ===")
        errors = cli.assert_no_errors()
        log('step6', errors['ok'], f"no JS errors: {errors['ok']}")

except SystemExit:
    pass
except Exception as e:
    import traceback
    traceback.print_exc()
    results['error'] = str(e)

print("\n" + "=" * 50)
print("SUMMARY")
for k, v in results.items():
    if isinstance(v, dict):
        print(f"  {k}: {'PASS' if v.get('ok') else 'FAIL'} - {v.get('detail','')[:120]}")
    else:
        print(f"  {k}: {v}")