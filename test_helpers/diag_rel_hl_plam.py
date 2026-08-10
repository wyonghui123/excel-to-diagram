"""复现用户场景: 展开计划范围管理(PLAM)到业务对象后, 高亮 需求计划(DP).
检查 DP 相关连线标签与高亮结果.
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

        # 展开 PLAM(计划范围管理) 到业务对象
        r = cli.evaluate("""() => {
            const d = window.__archPage && window.__archPage.debug;
            const store = d.store;
            const cfg = store.layoutControlConfig;
            const flatten = (list, depth=0) => Array.isArray(list)? list.flatMap(g=>g&&typeof g==='object'?[{g,depth},...flatten(g.children,depth+1),...flatten(g.containers,depth+1)]:[]) : [];
            const flat = flatten(cfg.groups);
            const plam = flat.find(x => (x.g.elementCode||x.g.id)==='PLAM');
            if(!plam) return {error:'PLAM not found', flat: flat.map(x=>({code:x.g.elementCode||x.g.id, t:x.g.groupType}))};
            const recurse = (list) => { if(!Array.isArray(list))return; list.forEach(g=>{ if(g&&typeof g==='object'){ g.collapsed = false; recurse(g.children); recurse(g.containers);} }); };
            plam.g.collapsed = false;
            recurse(plam.g.children);
            recurse(plam.g.containers);
            store.updateLayoutControlConfig(JSON.parse(JSON.stringify(cfg)));
            store.markGroupManualSet();
            return {expanded: plam.g.elementCode||plam.g.id};
        }""")
        print('[EXPAND PLAM]', json.dumps(r, ensure_ascii=False))
        time.sleep(3)

        # 重新检查边标签 + DP 高亮
        r2 = cli.evaluate("""() => {
            const svg = document.querySelector('.mermaid-content svg');
            const labels = Array.from(svg.querySelectorAll('g.edgeLabel')).map((e,i)=>({i, text:(e.textContent||'').trim()}));
            const nodes = Array.from(svg.querySelectorAll('g.node')).map(e => e.getAttribute('data-container-code')||e.getAttribute('data-code')||null).filter(Boolean);
            const dpLabels = labels.filter(l => /^DP-|DP$/i.test(l.text));
            const d = window.__archPage && window.__archPage.debug;
            d.highlightRelations('DP');
            const svg2 = document.querySelector('.mermaid-content svg');
            const hlNodes = Array.from(svg2.querySelectorAll('g.node[data-rel-hl], g.cluster[data-rel-hl]')).map(e => e.getAttribute('data-container-code')||e.getAttribute('data-code'));
            return { labels, nodes, dpLabels, hlNodes, hlEdgeCount: svg2.querySelectorAll('path[data-rel-hl]').length };
        }""")
        print('[AFTER EXPAND + HL DP]', json.dumps(r2, ensure_ascii=False))

        cli.screenshot('diag_rel_hl_plam.png')

if __name__ == '__main__':
    main()
