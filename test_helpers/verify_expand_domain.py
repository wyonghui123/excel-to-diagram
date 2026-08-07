"""
自测: "展开到领域" 渲染行为 (2026-08-06)
验证: 设 domain.collapsed=false, 子孙 (subDomain/serviceModule/BO) collapsed=true,
      读取真实 SVG 文本, 检查是否出现子领域 COLLAPSE 聚合节点 / 是否展开子领域容器.
前置: 前端 3005, 后端 3010.
"""
import sys, time, json, base64, urllib.parse
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

FRONTEND = 'http://localhost:3005'
PID, VID, DOMAIN_ID, SUB_DOMAIN_ID = 507, 863, 2200, 299


def svg_text(page):
    return page.evaluate('''() => {
        const svgs = document.querySelectorAll('.embedded-chart-view__canvas svg');
        let best = '', bestLen = 0;
        for (const s of svgs) { const l = (s.textContent || '').length; if (l > bestLen) { best = s.textContent || ''; bestLen = l; } }
        return best;
    }''')


def main():
    cli = PlaywrightCLI(headless=True)
    try:
        page = cli._ensure_browser()
        page.set_default_timeout(30000)
        page.goto(f'{FRONTEND}/api/v1/auth/dev-login?username=admin', wait_until='domcontentloaded', timeout=15000)
        time.sleep(1)
        scope_json = json.dumps({'business_object': [], 'service_module': [], 'sub_domain': [SUB_DOMAIN_ID], 'domain': [DOMAIN_ID], 'relation_codes': []})
        scope_enc = urllib.parse.quote(base64.b64encode(scope_json.encode()).decode('ascii'), safe='')
        page.goto(f'{FRONTEND}/system/archdata?shortcut=1&productId={PID}&versionId={VID}&scope={scope_enc}',
                  wait_until='domcontentloaded', timeout=15000)
        page.wait_for_function("""() => {
            const svgs = document.querySelectorAll('.embedded-chart-view__canvas svg');
            for (const s of svgs) if ((s.textContent||'').length > 100) return true;
            return false;
        }""", timeout=90000)
        time.sleep(3)
        page.wait_for_function("""
            () => !!(window.__archPage && window.__archPage.chartConfig && window.__archPage.chartConfig.layoutControl && window.__archPage.chartConfig.layoutControl.groups && window.__archPage.chartConfig.layoutControl.groups.length > 0)
        """, timeout=20000)

        # 读取顶级分组结构
        top = page.evaluate('''() => {
            const g = window.__archPage.chartConfig.layoutControl.groups;
            const sm = (x) => ({ id: x.id.slice(0,20), title: x.title, groupType: x.groupType, enabled: x.enabled, collapsed: x.collapsed, childCount: (x.children||[]).length, containerCount: (x.containers||[]).length });
            return (g||[]).map(sm);
        }''')
        print('TOP groups:', json.dumps(top, ensure_ascii=False))

        # 模拟"展开到领域": 仅 domain 展开, 子孙折叠
        print('apply 展开到领域 (domain expanded, descendants collapsed)')
        page.evaluate('''() => {
            const g = window.__archPage.chartConfig.layoutControl.groups;
            function lvl(gt){ if(gt==='domain')return 0; if(gt==='subDomain')return 1; if(gt==='serviceModule')return 2; return 3; }
            function walk(items){ for(const it of items||[]){ it.collapsed = lvl(it.groupType) > 0; walk(it.children); walk(it.containers); } }
            walk(g);
        }''')
        time.sleep(8)

        code = page.evaluate('() => window.__lastMermaidCode || ""')
        text = svg_text(page)
        # 诊断: 是否出现子领域 COLLAPSE 节点 / 子领域 subgraph
        diag = page.evaluate('''(code) => {
            const collapseSub = (code.match(/COLLAPSE_G?S?D?_[\\w\\u4e00-\\u9fff]+/g) || []).filter(s => /S?D|子|COLLAPSE/.test(s));
            const subgraphSub = (code.match(/subgraph G_SD_/g) || []).length;
            const subgraphDomain = (code.match(/subgraph G_D_/g) || []).length;
            const collapseAll = (code.match(/COLLAPSE_/g) || []).length;
            return { collapseCount: collapseAll, collapseNodes: (code.match(/COLLAPSE_[\\w\\u4e00-\\u9fff]+/g)||[]).slice(0,15),
                     subgraphSub, subgraphDomain, codeLen: code.length, codeHead: code.slice(0,800) };
        }''', code)
        print('DIAG:', json.dumps(diag, ensure_ascii=False))
        print('SVG len:', len(text))
        print('SVG head:', text[:300])
    finally:
        cli.close()


if __name__ == '__main__':
    main()