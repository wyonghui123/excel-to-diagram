"""检查 PLAM 分组结构 + 如何正确展开到对象."""
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
        # 检查 PLAM 分组结构
        r = cli.evaluate("""() => {
            const d = window.__archPage && window.__archPage.debug;
            const g = d.findGroup('PLAM');
            if(!g) return {error:'not found', groups: d.inspectGroups()};
            return { id:g.id, title:g.title, groupType:g.groupType, collapsed:g.collapsed,
                     directNodesCount: (g.directNodes||[]).length,
                     children: (g.children||[]).map(c=>({code:c.elementCode||c.id,type:c.groupType,collapsed:c.collapsed})),
                     containers: (g.containers||[]).map(c=>({code:c.elementCode||c.id,type:c.groupType,collapsed:c.collapsed})) };
        }""")
        print('[PLAM STRUCT]', json.dumps(r, ensure_ascii=False))

        # diagramData 中 PLAM 的 BO / 计划单
        r2 = cli.evaluate("""() => {
            const d = window.__archPage && window.__archPage.debug;
            const data = d.getDiagramData();
            const nodes = (data.nodes||[]).filter(n => n.code==='PLAM' || (n.serviceModule&&n.serviceModule==='PLAM') || /计划/.test(n.name||''));
            return nodes.map(n=>({code:n.code,name:n.name,serviceModule:n.serviceModule,id:n.id}));
        }""")
        print('[PLAM NODES]', json.dumps(r2, ensure_ascii=False))

if __name__ == '__main__':
    main()
