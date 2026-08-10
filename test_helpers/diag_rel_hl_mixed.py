"""复现混合视图 (真实UI双击展开路径): 双击 PLAM 展开到对象, DP 保持折叠.
检查边标签 + highlightRelations('DP') 结果.
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

def snap(cli):
    return cli.evaluate("""() => {
        const svg = document.querySelector('.mermaid-content svg');
        const labels = Array.from(svg.querySelectorAll('g.edgeLabel')).map((e,i)=>({i, text:(e.textContent||'').trim()}));
        const nodes = Array.from(svg.querySelectorAll('g.node')).map(e => e.getAttribute('data-container-code')||e.getAttribute('data-code')||null).filter(Boolean);
        return { labels, nodes };
    }""")

def main():
    with PlaywrightCLI() as cli:
        cli.authenticated_navigate('/system/archdata?preset=scp&mode=debug',
                                   wait_for_selector=None, timeout=90000)
        wait_svg(cli)
        # 用真实双击路径展开 PLAM 到对象
        r = cli.evaluate("""() => {
            const d = window.__archPage && window.__archPage.debug;
            const el = document.querySelector('g.node[data-container-code="PLAM"]') || document.querySelector('g.node[data-code="PLAM"]');
            if (!el) return {error:'PLAM node not found'};
            return d.testDblClick('g.node[data-container-code="PLAM"], g.node[data-code="PLAM"]');
        }""")
        print('[DBLCLICK PLAM]', json.dumps(r, ensure_ascii=False)[:600])
        # 等待 PLD003 出现
        bo_seen = None
        for _ in range(60):
            s = snap(cli)
            bos = [n for n in s['nodes'] if n in ('PLD003','PLD006','PLB001')]
            if bos:
                bo_seen = bos
                break
            time.sleep(1)
        print('[BO SEEN]', json.dumps(bo_seen, ensure_ascii=False))
        s = snap(cli)
        print('[MIXED EDGES]', json.dumps(s, ensure_ascii=False))

        r3 = cli.evaluate("""() => {
            const d = window.__archPage && window.__archPage.debug;
            d.highlightRelations('DP');
            const svg = document.querySelector('.mermaid-content svg');
            const hlNodes = Array.from(svg.querySelectorAll('g.node[data-rel-hl], g.cluster[data-rel-hl]')).map(e => e.getAttribute('data-container-code')||e.getAttribute('data-code'));
            const hlEdges = Array.from(svg.querySelectorAll('path[data-rel-hl]')).length;
            return { hlNodes, hlEdgeCount: hlEdges };
        }""")
        print('[HIGHLIGHT DP MIXED]', json.dumps(r3, ensure_ascii=False))
        cli.screenshot('diag_rel_hl_mixed.png')

if __name__ == '__main__':
    main()