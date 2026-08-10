"""展开到业务对象后, 检查 DP↔计划单(PLD003) 边标签 + highlight DP 结果."""
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
        r = cli.evaluate("() => { const d = window.__archPage && window.__archPage.debug; return d.setExpandLevel('businessObject'); }")
        print('[SET BO LEVEL]', json.dumps(r, ensure_ascii=False))
        time.sleep(4)

        r2 = cli.evaluate("""() => {
            const svg = document.querySelector('.mermaid-content svg');
            const labels = Array.from(svg.querySelectorAll('g.edgeLabel')).map((e,i)=>({i, text:(e.textContent||'').trim()}));
            const nodes = Array.from(svg.querySelectorAll('g.node')).map(e => e.getAttribute('data-container-code')||e.getAttribute('data-code')||null).filter(Boolean);
            // 计划单相关边
            const pld = labels.filter(l => /PLD003/.test(l.text) || (l.text.includes('DP') && /PLD/.test(l.text)));
            return { labelCount: labels.length, nodeCount: nodes.length, nodes, pld, labels };
        }""")
        print('[BO LEVEL EDGES]', json.dumps(r2, ensure_ascii=False))

        # 高亮 DP
        r3 = cli.evaluate("""() => {
            const d = window.__archPage && window.__archPage.debug;
            d.highlightRelations('DP');
            const svg = document.querySelector('.mermaid-content svg');
            const hlNodes = Array.from(svg.querySelectorAll('g.node[data-rel-hl], g.cluster[data-rel-hl]')).map(e => e.getAttribute('data-container-code')||e.getAttribute('data-code'));
            return { hlNodes, hlEdgeCount: svg.querySelectorAll('path[data-rel-hl]').length };
        }""")
        print('[HIGHLIGHT DP BO LEVEL]', json.dumps(r3, ensure_ascii=False))

        cli.screenshot('diag_rel_hl_bo.png')

if __name__ == '__main__':
    main()
