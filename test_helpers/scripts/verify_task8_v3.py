"""
Task 8 Verification v3 - Use dev shortcut URL to bypass UI selection.
Flow: auth → probe API for version+domain → navigate with shortcut → verify panels.
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

        # Probe: find version with child_count > 0, then fetch first domain ID for that version
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
                // Fetch first domain ID for this version
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
            cli.screenshot('task8v3_nodata.png')
        else:
            pcode = best.get('productCode') or best.get('productName')
            vcode = best.get('versionCode') or best.get('versionName')
            domainId = probe.get('firstDomainId')
            print(f"[target] product={pcode} version={vcode} (domains={best['childCount']}, firstDomainId={domainId})")
            log('step0', True, f"found: {pcode}/{vcode} domain={domainId}")

            # Build shortcut URL with scope (domain ID). URL-encode the base64 scope.
            scope_json = json.dumps({"domain": [domainId]} if domainId else {})
            scope_b64 = base64.b64encode(scope_json.encode()).decode()
            scope_encoded = urllib.parse.quote(scope_b64, safe='')
            shortcut_path = f'/system/archdata?shortcut=1&productCode={urllib.parse.quote(str(pcode), safe="")}&versionCode={urllib.parse.quote(str(vcode), safe="")}&scope={scope_encoded}'
            print(f"\n[shortcut] authenticated_navigate to: {shortcut_path[:120]}...")

            # authenticated_navigate does: dev-login → goto home → router.push(shortcut_path)
            # Coming from home route, the archdata component mounts fresh → restoreContext + tryApplyShortcut run.
            cli.authenticated_navigate(shortcut_path, wait_for_selector='.gt-btn-chart-toggle', timeout=60000)
            # Wait for shortcut logic (restoreContext + tryApplyShortcut: up to 6s for versionContext + scope + toggle)
            print("[shortcut] waiting for shortcut logic...")
            time.sleep(15)

            # Debug: check current state
            state = cli.evaluate('''() => {
                const btn = document.querySelector('.gt-btn-chart-toggle');
                const layout = document.querySelector('.rst-panel-layout');
                const selProd = document.querySelectorAll('.gt-select')[0];
                const selVer = document.querySelectorAll('.gt-select')[1];
                const app = document.querySelector('#app');
                return {
                    btnText: btn ? btn.textContent.trim() : null,
                    btnDisabled: btn ? btn.disabled : null,
                    layoutExists: !!layout,
                    selProdText: selProd ? selProd.textContent.trim().substring(0, 50) : null,
                    selVerText: selVer ? selVer.textContent.trim().substring(0, 50) : null,
                    appExists: !!app,
                    bodyText: document.body ? document.body.textContent.trim().substring(0, 200) : null,
                    url: window.location.href.substring(0, 120),
                };
            }''')
            print(f"[debug] state: {json.dumps(state, ensure_ascii=False)}")
            # Check console messages
            msgs = cli.evaluate('''() => (window.__lastError || "no error captured")''')
            print(f"[debug] console: checking messages...")

            # Step 4: chart view shows layout panel
            print("\n=== Step 4: chart view shows layout panel ===")
            panel = cli.evaluate('''() => {
                const p = document.querySelector('.rst-panel-layout');
                const t = p && p.querySelector('.collapsible-panel__title');
                const vm = document.querySelector('.momp-chart-view, .embedded-chart-view, [class*="chart-view"]');
                return {
                    layoutExists: !!p,
                    title: t ? t.textContent.trim() : null,
                    collapsed: p ? p.classList.contains('is-collapsed') : null,
                    chartViewVisible: !!vm,
                    viewMode: window.__app__?.config?.globalProperties?.$pinia?._s?.get('momp')?.viewMode || 'unknown'
                };
            }''')
            log('step4', panel.get('layoutExists') and panel.get('title') == '布局设置',
                f"layout panel: {json.dumps(panel, ensure_ascii=False)}")
            cli.screenshot('task8v3_step4_chart.png')

            # Step 5: 4-panel mutex
            print("\n=== Step 5: 4-panel mutex ===")
            if results.get('step4', {}).get('ok'):
                # Expand layout panel (click its header)
                cli.click('.rst-panel-layout .collapsible-panel__header')
                time.sleep(1)
                s1 = cli.evaluate('''() => {
                    const g = (s) => {const e=document.querySelector(s); return e?{found:true,collapsed:e.classList.contains('is-collapsed')}:{found:false}};
                    return {layout:g('.rst-panel-layout'),object:g('.rst-panel-object'),relation:g('.rst-panel-relation'),filter:g('.rst-panel-filter')};
                }''')
                layout_ok = s1['layout']['found'] and not s1['layout']['collapsed']
                others_collapsed = all(s1[k]['collapsed'] for k in ['object','relation','filter'] if s1[k]['found'])
                log('step5a', layout_ok and others_collapsed, f"layout expanded, others collapsed: {json.dumps(s1, ensure_ascii=False)}")

                # Expand object panel (should collapse layout)
                cli.click('.rst-panel-object .collapsible-panel__header')
                time.sleep(1)
                s2 = cli.evaluate('''() => {
                    const g = (s) => {const e=document.querySelector(s); return e?{found:true,collapsed:e.classList.contains('is-collapsed')}:{found:false}};
                    return {layout:g('.rst-panel-layout'),object:g('.rst-panel-object'),relation:g('.rst-panel-relation'),filter:g('.rst-panel-filter')};
                }''')
                obj_ok = s2['object']['found'] and not s2['object']['collapsed']
                layout_collapse = s2['layout']['collapsed']
                log('step5b', obj_ok and layout_collapse, f"object expanded, layout collapsed: {json.dumps(s2, ensure_ascii=False)}")
            else:
                log('step5', False, 'skipped - step4 failed')

            # Step 6: list view hides panel
            print("\n=== Step 6: list view hides panel ===")
            list_btn = cli.evaluate('''() => {const b=document.querySelector('.gt-btn-chart-toggle'); return b?{text:b.textContent.trim()}:null}''')
            if list_btn and '列表' in list_btn.get('text', ''):
                cli.click('.gt-btn-chart-toggle')
                time.sleep(2)
                hidden = cli.evaluate('''() => !document.querySelector('.rst-panel-layout')''')
                log('step6', hidden, f"layout panel hidden in list view: {hidden}")
                cli.screenshot('task8v3_step6_list.png')
            else:
                log('step6', False, f"could not switch to list: {list_btn}")

            # Step 8: drawer removed
            print("\n=== Step 8: drawer removed ===")
            drawer = cli.evaluate('''() => {
                const d = document.querySelectorAll('.el-drawer');
                const vis = Array.from(d).filter(x => {const r=x.getBoundingClientRect(); return r.width>0 && r.height>0});
                return {count: d.length, visible: vis.length};
            }''')
            log('step8', drawer['visible'] == 0, f"drawers: total={drawer['count']}, visible={drawer['visible']}")

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
