"""关系高亮 probe — 复现用户场景: 需求计划(DP)服务模块 → 计划单 BO.
输出: 所有 edgeLabel 文本 + 端点解析 + highlightRelations('DP') 后高亮的边/节点.
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
                                   wait_for_selector=None, timeout=60000)
        wait_svg(cli)

        # 1) 输出所有边标签文本 + 节点 code (含 data-container-code / data-code)
        r = cli.evaluate("""() => {
            const svg = document.querySelector('.mermaid-content svg');
            const labels = Array.from(svg.querySelectorAll('g.edgeLabel')).map((e,i)=>({i, text: (e.textContent||'').trim()}));
            const nodes = Array.from(svg.querySelectorAll('g.node')).map(e => e.getAttribute('data-container-code')||e.getAttribute('data-code')||null).filter(Boolean);
            const clusters = Array.from(svg.querySelectorAll('g.cluster[data-container-code]')).map(e => e.getAttribute('data-container-code'));
            return { labels, nodes, clusters };
        }""")
        print('[EDGES+NODES]', json.dumps(r, ensure_ascii=False))

        # 2) 高亮 DP 服务模块
        r2 = cli.evaluate("""() => {
            const d = window.__archPage && window.__archPage.debug;
            d.highlightRelations('DP');
            const svg = document.querySelector('.mermaid-content svg');
            const hlNodes = Array.from(svg.querySelectorAll('g.node[data-rel-hl], g.cluster[data-rel-hl]')).map(e => e.getAttribute('data-container-code')||e.getAttribute('data-code'));
            const hlEdges = Array.from(svg.querySelectorAll('g.edgeLabel')).map((e,i)=>({i, text:(e.textContent||'').trim(), hl: !!e.nextElementSibling&&!!e.nextElementSibling.nextElementSibling}));
            return { hlNodes, hlEdgeCount: svg.querySelectorAll('path[data-rel-hl]').length };
        }""")
        print('[HIGHLIGHT DP]', json.dumps(r2, ensure_ascii=False))

        cli.screenshot('diag_rel_hl_probe.png')

if __name__ == '__main__':
    main()
