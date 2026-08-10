"""诊断: 仅服务模块 渲染. 先看页面实际加载了什么视图. TTTTT000/V11/vid=863."""
import sys, time, json, base64, urllib.parse
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

FRONTEND = 'http://localhost:3005'
VID, PID, DOMAIN_ID, SUB_DOMAIN_ID = 863, 507, 2200, 299

def main():
    cli = PlaywrightCLI(headless=True)
    try:
        page = cli._ensure_browser()
        page.set_default_timeout(30000)
        page.goto(f'{FRONTEND}/api/v1/auth/dev-login?username=admin', wait_until='domcontentloaded', timeout=15000)
        time.sleep(1)
        # 先加载首页, 让 auth store 从 cookie 初始化并持久化到 localStorage
        page.goto(f'{FRONTEND}/', wait_until='domcontentloaded', timeout=15000)
        try:
            page.wait_for_function("""() => {
                const app = document.querySelector('#app')?.__vue_app__;
                let store = app?.config?.globalProperties?.$pinia?._s?.get('auth');
                if (!store) { for (const [,s] of (app?.config?.globalProperties?.$pinia?._s||[])) if(s.$id==='auth'){store=s;break;} }
                return !!(store && store.user);
            }""", timeout=20000)
        except Exception as e:
            print('[WARN] auth store not ready:', e)
        time.sleep(1)
        scope_json = json.dumps({'business_object': [], 'service_module': [], 'sub_domain': [SUB_DOMAIN_ID], 'domain': [DOMAIN_ID], 'relation_codes': []})
        scope_b64 = base64.b64encode(scope_json.encode('utf-8')).decode('ascii')
        scope_enc = urllib.parse.quote(scope_b64, safe='')
        page.goto(f'{FRONTEND}/system/archdata?shortcut=1&productId={PID}&versionId={VID}&scope={scope_enc}',
                  wait_until='domcontentloaded', timeout=15000)
        time.sleep(5)
        print('URL:', page.url)

        # 采集页面结构: 有哪些含 svg 的容器 / 主要文本
        info = page.evaluate('''() => {
            const out = { svgCount: document.querySelectorAll('svg').length,
                          embedExists: !!document.querySelector('.embedded-chart-view'),
                          embedCanvas: !!document.querySelector('.embedded-chart-view__canvas'),
                          bodyText: (document.body.innerText||'').slice(0, 800) };
            const svgs = document.querySelectorAll('.embedded-chart-view__canvas svg');
            let lens=[]; for (const s of svgs) lens.push((s.textContent||'').length);
            out.embedSvgLens = lens;
            return out;
        }''')
        print('PAGE INFO:', json.dumps(info, ensure_ascii=False, indent=1)[:2500])
        cli.screenshot('test_helpers/diag_initial.png')

        # 应用模板
        tpl = page.evaluate('''() => {
            const app = document.querySelector('#app').__vue_app__;
            const pinia = app.config.globalProperties.$pinia;
            const store = pinia._s.get('diagramConfig');
            if (!store || typeof store.applyViewTemplate !== 'function') return { error: 'no store' };
            store.applyViewTemplate('onlyServiceModules');
            return { viewTemplate: store.viewTemplate };
        }''')
        print('apply:', tpl)
        time.sleep(8)

        info2 = page.evaluate('''() => {
            const svgs = document.querySelectorAll('.embedded-chart-view__canvas svg');
            let lens=[]; for (const s of svgs) lens.push((s.textContent||'').length);
            const code = window.__lastMermaidCode||'';
            // 分析: 是否含 BO 节点定义 (N##["...(...)"]), 容器 subgraph 数量, 上提聚合节点
            const boDefs = (code.match(/N\\d+\\["[^"]*\\n\\([A-Z0-9]+\\)\\"]/g) || []);
            const subgraphs = (code.match(/subgraph /g) || []).length;
            const collapseNodes = (code.match(/COLLAPSE_[\\w\\u4e00-\\u9fff]+/g) || []);
            return { embedSvgLens: lens, codeLen: code.length,
                     boNodeCount: boDefs.length, boSample: boDefs.slice(0,5),
                     subgraphCount: subgraphs, collapseNodes: collapseNodes.slice(0,10),
                     discDisabledBo: window.__archPage?.debugLayout?.disabledBoCodes || [],
                     code1000: code.slice(0, 1000) };
        }''')
        print('AFTER APPLE:', json.dumps(info2, ensure_ascii=False)[:3000])
        cli.screenshot('test_helpers/diag_after.png')
    finally:
        cli.close()

if __name__ == '__main__':
    main()