"""复现用户场景: expandGroup('PLAM', 99) 展开计划范围管理到对象后, 高亮需求计划(DP).
检查 DP 相关连线标签 + 高亮结果 + 边对应的 diagramData 信息.
"""
import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def wait_svg(cli, timeout=120):
    for _ in range(timeout):
        try:
            if cli.evaluate("() => !!document.querySelector('.mermaid-content svg') && !!(window.__archPage&&window.__archPage.debug)"):
                time.sleep(1.5)
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

def main():
    with PlaywrightCLI() as cli:
        cli.authenticated_navigate('/system/archdata?preset=scp&mode=debug',
                                   wait_for_selector=None, timeout=90000)
        wait_svg(cli)

        # 展开 PLAM 到业务对象
        r = cli.evaluate("() => { const d = window.__archPage && window.__archPage.debug; return d.expandGroup('PLAM', 99); }")
        print('[EXPAND PLAM]', json.dumps(r, ensure_ascii=False))
        time.sleep(3)

        r2 = cli.evaluate("""() => {
            const svg = document.querySelector('.mermaid-content svg');
            const labels = Array.from(svg.querySelectorAll('g.edgeLabel')).map((e,i)=>({i, text:(e.textContent||'').trim()}));
            const nodes = Array.from(svg.querySelectorAll('g.node')).map(e => e.getAttribute('data-container-code')||e.getAttribute('data-code')||null).filter(Boolean);
            // DP 相关边
            const dpLabels = labels.filter(l => l.text.split('-')[0]==='DP' || l.text.split('-').slice(-1)[0]==='DP');
            // 计划单相关: 含 PLAM 的边 (展开后应变为 BO 级)
            const plamLabels = labels.filter(l => /PLAM|计划/i.test(l.text));
            return { labels, nodes, dpLabels, plamLabels };
        }""")
        print('[EDGES AFTER EXPAND]', json.dumps(r2, ensure_ascii=False))

        # 高亮 DP
        r3 = cli.evaluate("""() => {
            const d = window.__archPage && window.__archPage.debug;
            d.highlightRelations('DP');
            const svg = document.querySelector('.mermaid-content svg');
            const hlNodes = Array.from(svg.querySelectorAll('g.node[data-rel-hl], g.cluster[data-rel-hl]')).map(e => e.getAttribute('data-container-code')||e.getAttribute('data-code'));
            return { hlNodes, hlEdgeCount: svg.querySelectorAll('path[data-rel-hl]').length };
        }""")
        print('[HIGHLIGHT DP AFTER EXPAND]', json.dumps(r3, ensure_ascii=False))

        # diagramData 中 PLAM / DP 相关 links 的 code/端点
        r4 = cli.evaluate("""() => {
            const d = window.__archPage && window.__archPage.debug;
            const data = d.getDiagramData();
            const links = (data.links||[]).filter(l => (l.code||'')==='PLAM-DP' || (l.code||'').startsWith('PLAM') || (l.code||'').startsWith('DP'));
            return { count: (data.links||[]).length, sample: links.slice(0,20).map(l=>({code:l.code,source:l.source,target:l.target,sourceName:l.sourceName,targetName:l.targetName,sourceCode:l.sourceCode,targetCode:l.targetCode})) };
        }""")
        print('[LINKS PLAM/DP]', json.dumps(r4, ensure_ascii=False))

        cli.screenshot('diag_rel_hl_plam2.png')

if __name__ == '__main__':
    main()
