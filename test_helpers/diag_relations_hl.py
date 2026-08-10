"""关系高亮验证 v2 (SVG 结构驱动 + 子树匹配) — 复用入口.

用法: 浏览器打开 /system/archdata?preset=scp&mode=debug 后执行
   window.__archPage.debug.highlightRelations('DP')   // 高亮"需求计划"相关连线与相连节点
   window.__archPage.debug.clearRelationsHighlight()  // 清除

v2 (2026-08-10) 新增/修复:
   - 子树匹配: 右键容器(如服务模块 DP)时, 若其相连边因另一端展开到业务对象而被重映射为
     更细颗粒度 (边标签为 BO 编码 "DP01-计划单" 而非 "DP-计划单"), 仍能被正确高亮.
   - 节点高亮采用"选择后同样的颜色" #409eff (蓝).
   - 连线高亮采用原色 (只加粗 + 轻微发光, 不改 stroke).
   - 点击图表空白区域批量解除高亮.
"""
import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def wait_svg(cli, timeout=120):
    for _ in range(timeout):
        if cli.evaluate("() => !!document.querySelector('.mermaid-content svg') && !!(window.__archPage&&window.__archPage.debug)"):
            time.sleep(1.5)
            return True
        time.sleep(1)
    return False

def main():
    with PlaywrightCLI() as cli:
        cli.authenticated_navigate('/system/archdata?preset=scp&mode=debug',
                                   wait_for_selector=None, timeout=60000)
        wait_svg(cli)

        for probe in ['DP', 'EXT', 'PLAM']:
            res = cli.evaluate(f"""() => {{
                const d = window.__archPage && window.__archPage.debug;
                if (!d || !d.highlightRelations) return {{ error: 'no highlightRelations' }};
                d.highlightRelations({json.dumps(probe)});
                const svg = document.querySelector('.mermaid-content svg');
                return {{
                    hlNodes: svg.querySelectorAll('g.node[data-rel-hl]').length,
                    hlNodeCodes: Array.from(svg.querySelectorAll('g.node[data-rel-hl]')).map(e => e.getAttribute('data-container-code')||e.getAttribute('data-code')),
                    hlEdges: svg.querySelectorAll('path[data-rel-hl]').length,
                    nodeStroke: (Array.from(svg.querySelectorAll('g.node[data-rel-hl] rect'))[0]||{{style:{{}}}}).style.stroke,
                    edgeStrokeInline: (Array.from(svg.querySelectorAll('path[data-rel-hl]'))[0]||{{style:{{stroke:''}}}}).style.stroke
                }};
            }}""")
            print(f'[HIGHLIGHT {probe} v2]', json.dumps(res, ensure_ascii=False))
            cli.evaluate("() => { const d = window.__archPage && window.__archPage.debug; if (d && d.clearRelationsHighlight) d.clearRelationsHighlight(); }")

        cli.screenshot('diag_relations_hl_v2.png')

if __name__ == '__main__':
    main()
