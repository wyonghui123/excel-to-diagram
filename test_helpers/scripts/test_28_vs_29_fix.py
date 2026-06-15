# -*- coding: utf-8 -*-
"""
Test for archdata-chart 28 vs 29 relation bug fix.
"""

import sys as _sys
import os as _os

_script_dir = _os.path.dirname(_os.path.abspath(__file__))
_test_helpers_dir = _os.path.dirname(_script_dir)
if _test_helpers_dir not in _sys.path:
    _sys.path.insert(0, _test_helpers_dir)

from browser_auth_cli import PlaywrightCLI


def main():
    cli = PlaywrightCLI()
    try:
        print("[1] Auth + navigate to archdata management...")
        page = cli.authenticated_navigate(
            target_path='/system/archdata',
            wait_for_selector='body',
            timeout=20000
        )
        print("  URL: " + str(page.url))
        page.wait_for_load_state('domcontentloaded')
        page.wait_for_timeout(5000)
        cli.screenshot('step1_archdata.png')

        # Inject archData via Pinia to bypass Excel upload (simulates loading arch data)
        print("[2] Navigate to chart page...")
        # First inject archData from sessionStorage into the chart store
        archdata_inject = page.evaluate("""
            (() => {
                // Find the sessionStorage key for arch data
                const keys = Object.keys(sessionStorage);
                const dataKey = keys.find(k => k.includes('chartArchData') || k.includes('archData'));
                let archData = null;
                if (dataKey) {
                    try { archData = JSON.parse(sessionStorage.getItem(dataKey)); } catch(e) {}
                }
                // Also try localStorage
                const localKeys = Object.keys(localStorage);
                const localDataKey = localKeys.find(k => k.includes('chartArchData') || k.includes('archData'));
                if (!archData && localDataKey) {
                    try { archData = JSON.parse(localStorage.getItem(localDataKey)); } catch(e) {}
                }
                return {
                    sessionKeys: keys,
                    dataKey: dataKey || 'none',
                    hasArchData: !!archData,
                    archDataKeys: archData ? Object.keys(archData).slice(0, 10) : []
                };
            })()
        """)
        print("  sessionKeys: " + str(archdata_inject.get('sessionKeys', [])))
        print("  dataKey: " + str(archdata_inject.get('dataKey', 'none')))
        print("  hasArchData: " + str(archdata_inject.get('hasArchData', False)))

        # Navigate to chart page
        page = cli.authenticated_navigate(
            target_path='/archdata-chart',
            wait_for_selector='body',
            timeout=20000
        )
        print("  URL: " + str(page.url))
        page.wait_for_load_state('domcontentloaded')
        page.wait_for_timeout(8000)
        cli.screenshot('step2_chart.png')

        print("[3] Inject mock archData to simulate loaded Excel...")
        # Inject mock archData with the same structure as loaded Excel
        mock_inject = page.evaluate("""
            (() => {
                try {
                    const app = document.querySelector('#app').__vue_app__;
                    const pinia = app.config.globalProperties.$pinia;
                    const chartStore = pinia._s.get('chartArchData');
                    if (!chartStore) return {success: false, error: 'no chartStore'};

                    // Build mock archData with TEST600 relation
                    const mockArchData = {
                        businessObjects: [
                            {id: 1, code: 'BO_REQ', name: '采购申请', domain: '采购管理', subDomain: '采购申请', serviceModule: '采购'},
                            {id: 2, code: 'BO_SUPPLIER', name: '供应商', domain: '采购管理', subDomain: '供应商管理', serviceModule: '采购'},
                            {id: 3, code: 'BO_PO', name: '采购订单', domain: '采购管理', subDomain: '采购订单', serviceModule: '采购'},
                            {id: 4, code: 'BO_WAREHOUSE', name: '仓库', domain: '库存管理', subDomain: '仓储管理', serviceModule: '库存'},
                            {id: 5, code: 'BO_INVENTORY', name: '库存', domain: '库存管理', subDomain: '库存业务', serviceModule: '库存'},
                            {id: 6, code: 'BO_INV_LOG', name: '库存台账', domain: '库存管理', subDomain: '库存业务', serviceModule: '库存'},
                            {id: 29, code: 'TEST600', name: '测试业务对象', domain: '外部', subDomain: '外部', serviceModule: '外部'},
                        ],
                        relationships: [
                            {id: 1, sourceCode: 'BO_SUPPLIER', targetCode: 'BO_REQ', relationCode: 'PROVIDES', relationName: '提供'},
                            {id: 5, sourceCode: 'BO_INVENTORY', targetCode: 'BO_INV_LOG', relationCode: 'GENERATES', relationName: '生成'},
                            {id: 12, sourceCode: 'BO_PO', targetCode: 'BO_REQ', relationCode: 'CONTAINS', relationName: '包含'},
                            {id: 29, sourceCode: 'TEST600', targetCode: 'BO_WAREHOUSE', relationCode: '', relationName: '外部关系'},
                            {id: 99, sourceCode: 'BO_REQ', targetCode: 'BO_REQ', relationCode: 'SELF_LOOP', relationName: '自环'},
                        ],
                        domainTree: [
                            {id: '采购管理', name: '采购管理', children: []},
                            {id: '库存管理', name: '库存管理', children: []},
                            {id: '外部', name: '外部', children: []},
                        ],
                        selectedNodeIds: [1, 2, 3, 4, 5, 6, 29],  // 选所有BO
                        relationTypeFilter: [],  // 空 = 全选关系
                    };

                    chartStore.setArchData(mockArchData);
                    return {success: true, archDataKeys: Object.keys(mockArchData), seq: chartStore.sequence};
                } catch(e) {
                    return {success: false, error: e.message};
                }
            })()
        """)
        print("  inject result: " + str(mock_inject.get('success', False)) + " error: " + str(mock_inject.get('error', 'none')))

        # Wait for the chart to re-render with the new data (watch on sequence should trigger)
        page.wait_for_timeout(8000)
        cli.screenshot('step3_after_inject.png')

        print("[4] Check chart data state...")
        state = page.evaluate("""
            (() => {
                try {
                    const app = document.querySelector('#app').__vue_app__;
                    if (!app) return {hasApp: false, error: 'no app'};
                    const pinia = app.config.globalProperties.$pinia;
                    const chartStore = pinia._s.get('chartArchData');
                    const body = document.body.innerText;
                    const statsM = body.match(/\d+\u9886\u57DF.*?\d+\u5173\u7CFB/g);
                    const relM = statsM && statsM[0] ? statsM[0].match(/(\d+)\u5173\u7CFB/) : null;
                    const objM = statsM && statsM[0] ? statsM[0].match(/(\d+)\u5BF9\u8C61/) : null;
                    return {
                        hasApp: true,
                        error: null,
                        stats: statsM ? statsM[0] : 'no-match',
                        relCount: relM ? parseInt(relM[1]) : -1,
                        objCount: objM ? parseInt(objM[1]) : -1,
                        hasTEST600: body.indexOf('TEST600') !== -1,
                        hasSDFASDF: body.indexOf('SDFASDF') !== -1,
                        hasSvg: !!document.querySelector('svg'),
                        bodySnippet: body.substring(0, 500),
                        archDataLen: chartStore && chartStore.archData ? Object.keys(chartStore.archData).length : -1
                    };
                } catch(e) {
                    return {hasApp: false, error: e.message, body: document.body.innerText.substring(0, 200)};
                }
            })()
        """)
        if state is None:
            print("  evaluate returned None")
            simple = page.evaluate('document.body.innerText.substring(0, 200)')
            print("  body: " + str(simple))
        print("  Stats: " + str(state.get('stats', 'N/A')))
        print("  relCount: " + str(state.get('relCount', -1)) + " (expect >= 5)")
        print("  objCount: " + str(state.get('objCount', -1)))
        print("  hasTEST600: " + str(state.get('hasTEST600', False)))
        print("  hasSvg: " + str(state.get('hasSvg', False)))
        print("  error: " + str(state.get('error', 'none')))
        print("  archDataLen: " + str(state.get('archDataLen', -1)))
        if state.get('bodySnippet'):
            print("  bodySnippet: " + str(state.get('bodySnippet', '')))
        cli.screenshot('step4_state.png')

        # Step 4: Select "业务对象图" chart type via Pinia store manipulation
        print("[5] Set chart type: 业务对象图 via Pinia...")
        chart_type_result = page.evaluate("""
            (() => {
                try {
                    const app = document.querySelector('#app').__vue_app__;
                    const pinia = app.config.globalProperties.$pinia;

                    // Try different store names
                    let chartStore = pinia._s.get('chartArchData');
                    if (!chartStore) {
                        // Try finding the store via Vue instance
                        const instances = document.querySelectorAll('[data-v-xxx]');
                        return {success: false, error: 'no chartStore', keys: Array.from(pinia._s._keyToRef.keys())};
                    }

                    // Set chart type - find the configStore
                    const configStore = pinia._s.get('diagramConfig');
                    if (!configStore) return {success: false, error: 'no configStore', chartKeys: chartStore ? Object.keys(chartStore).slice(0, 10) : []};

                    // Check what properties exist
                    const storeKeys = Object.keys(configStore);
                    const chartTypeKey = storeKeys.find(k => k.toLowerCase().includes('chart') || k.toLowerCase().includes('type') || k.toLowerCase().includes('display'));
                    return {
                        success: true,
                        storeKeys: storeKeys,
                        chartTypeKey: chartTypeKey || 'none',
                        chartStoreKeys: chartStore ? Object.keys(chartStore).slice(0, 10) : []
                    };
                } catch(e) {
                    return {success: false, error: e.message};
                }
            })()
        """)
        print("  store result: " + str(chart_type_result.get('success', False)))
        print("  store keys: " + str(chart_type_result.get('storeKeys', [])))
        print("  chart type key: " + str(chart_type_result.get('chartTypeKey', 'none')))
        print("  error: " + str(chart_type_result.get('error', 'none')))

        # Directly navigate to the chart display by setting currentStep to 3 and triggering generate
        print("[6] Directly set chart state to display step...")
        page.evaluate("""
            (() => {
                const app = document.querySelector('#app').__vue_app__;
                const pinia = app.config.globalProperties.$pinia;
                const chartStore = pinia._s.get('chartArchData');
                // Trigger a re-initialization
                if (chartStore) {
                    chartStore.setArchData(chartStore.archData);
                }
            })()
        """)
        page.wait_for_timeout(3000)
        cli.screenshot('step6_direct.png')

        print("[7] Check chart data state after type selection...")
        state = page.evaluate("""
            (() => {
                try {
                    const app = document.querySelector('#app').__vue_app__;
                    if (!app) return {hasApp: false, error: 'no app'};
                    const pinia = app.config.globalProperties.$pinia;
                    const chartStore = pinia._s.get('chartArchData');
                    const body = document.body.innerText;
                    const statsM = body.match(/\d+\u9886\u57DF.*?\d+\u5173\u7CFB/g);
                    const relM = statsM && statsM[0] ? statsM[0].match(/(\d+)\u5173\u7CFB/) : null;
                    const objM = statsM && statsM[0] ? statsM[0].match(/(\d+)\u5BF9\u8C61/) : null;
                    return {
                        hasApp: true,
                        error: null,
                        stats: statsM ? statsM[0] : 'no-match',
                        relCount: relM ? parseInt(relM[1]) : -1,
                        objCount: objM ? parseInt(objM[1]) : -1,
                        hasTEST600: body.indexOf('TEST600') !== -1,
                        hasSDFASDF: body.indexOf('SDFASDF') !== -1,
                        hasSvg: !!document.querySelector('svg'),
                        bodySnippet: body.substring(0, 500)
                    };
                } catch(e) {
                    return {hasApp: false, error: e.message, body: document.body.innerText.substring(0, 200)};
                }
            })()
        """)
        print("  Stats: " + str(state.get('stats', 'N/A')))
        print("  relCount: " + str(state.get('relCount', -1)) + " (expect >= 5)")
        print("  objCount: " + str(state.get('objCount', -1)))
        print("  hasTEST600: " + str(state.get('hasTEST600', False)))
        print("  hasSvg: " + str(state.get('hasSvg', False)))
        print("  error: " + str(state.get('error', 'none')))
        if state.get('bodySnippet'):
            print("  bodySnippet: " + str(state.get('bodySnippet', '')))
        cli.screenshot('step7_final_state.png')

        print("[8] Check Mermaid rendering...")
        svg_state = page.evaluate("""
            (() => {
                const svg = document.querySelector('svg');
                const hasTEST600 = svg ? svg.textContent.indexOf('TEST600') !== -1 : false;
                const nodeCount = svg ? svg.querySelectorAll('[class*="node"]').length : 0;
                const edgeCount = svg ? svg.querySelectorAll('[class*="edge"], [class*="link"]').length : 0;
                const mermaidErr = document.body.innerText.match(/Parse error|MermaidError/i);
                const syntaxErr = document.body.innerText.match(/Syntax error/i);
                return {
                    hasSvg: !!svg,
                    hasTEST600: hasTEST600,
                    nodeCount: nodeCount,
                    edgeCount: edgeCount,
                    mermaidErr: mermaidErr ? mermaidErr[0] : 'none',
                    syntaxErr: syntaxErr ? syntaxErr[0] : 'none'
                };
            })()
        """)
        print("  SVG nodes: " + str(svg_state.get('nodeCount', 0)))
        print("  SVG edges: " + str(svg_state.get('edgeCount', 0)))
        print("  SVG hasTEST600: " + str(svg_state.get('hasTEST600', False)))
        print("  MermaidErr: " + str(svg_state.get('mermaidErr', 'none')))
        print("  SyntaxErr: " + str(svg_state.get('syntaxErr', 'none')))
        cli.screenshot('step3_mermaid.png')

        print("")
        print("======== FINAL RESULT ========")
        rel_count = state.get('relCount', -1)
        has_test600 = state.get('hasTEST600', False) or svg_state.get('hasTEST600', False)
        print("  Stats: " + str(state.get('stats', 'N/A')))
        print("  relCount: " + str(rel_count) + " (expect >= 5)")
        print("  hasTEST600: " + str(has_test600))
        print("  hasSvg: " + str(svg_state.get('hasSvg', False)))
        print("============================")
        print("")

        cli.screenshot('step8_final.png')

        all_pass = True
        if rel_count >= 5:
            print("PASS relCount >= 5: " + str(rel_count))
        else:
            print("FAIL relCount < 5: " + str(rel_count))
            all_pass = False

        if has_test600:
            print("PASS TEST600 found")
        else:
            print("WARN TEST600 not found")

        if svg_state.get('hasSvg'):
            print("PASS SVG rendered")
        else:
            print("WARN No SVG detected")

        return all_pass

    except Exception as e:
        print("FAIL Exception: " + str(e))
        import traceback
        traceback.print_exc()
        try:
            cli.screenshot('test_error.png')
        except:
            pass
        return False
    finally:
        try:
            cli.close()
        except:
            pass


if __name__ == '__main__':
    ok = main()
    _sys.exit(0 if ok else 1)
