"""
_probe_node_dom.py - 检查 ELK 节点 label 的 DOM 结构 (为 getNodeLabelText 兜底选择器取证)
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3005'
WRAP = """(fn) => Promise.race([ fn(), new Promise((res) => setTimeout(() => res({ timeout: true }), 2500)) ])"""


def safe_eval(cli, js):
    try:
        return cli.evaluate(js)
    except Exception as e:
        return f'eval err: {e}'


def main():
    with PlaywrightCLI(headless=True) as cli:
        print('[v] 1 dev-login', flush=True)
        cli.goto(f"{BASE}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
        cli.wait_for_timeout(1200)

        print('[v] 2 列表页', flush=True)
        cli.goto(f"{BASE}/system/archdata?productCode=TTTTT000&versionId=863", wait_until="domcontentloaded")
        cli.wait_for_timeout(12000)

        print('[v] 3 展开供应链云 → 勾选供应链计划', flush=True)
        r = safe_eval(cli, """((WRAP))(async () => {
            const sleep = ms => new Promise(r => setTimeout(r, ms));
            const findNode = (text) => Array.from(document.querySelectorAll('.el-tree-node')).find(n => {
                const t = n.querySelector('.oss-node-label, .el-tree-node__label')?.textContent?.trim() || ''
                return t.includes(text)
            })
            const dom = findNode('供应链云')
            if (!dom) return 'no 供应链云'
            const icon = dom.querySelector('.el-tree-node__expand-icon')
            if (icon && !icon.classList.contains('expanded')) { icon.click(); await sleep(1500) }
            const sd = findNode('供应链计划')
            if (!sd) return 'no 供应链计划'
            const cb = sd.querySelector('.el-checkbox input[type=checkbox]')
            if (cb && !cb.checked) cb.click()
            return 'checked'
        })""".replace('(WRAP)', WRAP))
        print(f'[v]   {r}', flush=True)
        cli.wait_for_timeout(8000)

        print('[v] 4 点击 图表展示', flush=True)
        try:
            r = cli.evaluate("""() => {
                const b = Array.from(document.querySelectorAll('.gt-btn-chart-toggle')).find(x => x.textContent.includes('图表展示'))
                if (!b) return 'no btn'
                b.click(); return 'clicked'
            }""", retries=1)
            print(f'[v]   {r}', flush=True)
        except Exception as e:
            print(f'[v]   toggle fail: {e}', flush=True)

        for i in range(30):
            cli.wait_for_timeout(4000)
            n = safe_eval(cli, """((WRAP))(() => Array.from(document.querySelectorAll('.mermaid-container svg')).filter(s => s.querySelectorAll('g.node, g.nodes').length > 0).length)""".replace('(WRAP)', WRAP))
            if n == 1:
                print(f'[v]   poll[{i}] svg=1', flush=True)
                break
        try:
            cli._page.wait_for_function("() => !!(window.__archPage?.mermaid?.lastRender?.endTime)", timeout=180000)
            print('[v]   render done', flush=True)
        except Exception as e:
            print(f'[v]   render wait fail: {e}', flush=True)
        cli.wait_for_timeout(3000)

        out = safe_eval(cli, """((WRAP))(() => {
            const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
            const ns = svgs.find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
            const nodes = Array.from(ns.querySelectorAll('g.node, g.nodes'))
            return nodes.slice(0, 3).map(n => ({
                id: n.id,
                cls: n.getAttribute('class'),
                dataCode: n.getAttribute('data-code'),
                dataId: n.getAttribute('data-id'),
                innerHTML: n.innerHTML.substring(0, 500)
            }))
        })""".replace('(WRAP)', WRAP))
        print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)

        # 找第 1 个节点内所有可能的文本容器
        out2 = safe_eval(cli, """((WRAP))(() => {
            const svgs = Array.from(document.querySelectorAll('.mermaid-container svg'))
            const ns = svgs.find(s => s.querySelectorAll('g.node, g.nodes').length > 0)
            const n0 = ns.querySelectorAll('g.node, g.nodes')[0]
            if (!n0) return 'no node'
            const cands = []
            n0.querySelectorAll('div, foreignObject, text, .label, .nodeLabel').forEach(el => {
                cands.push({ tag: el.tagName, cls: el.getAttribute && el.getAttribute('class'), text: (el.textContent || '').trim().substring(0, 60) })
            })
            return cands
        })""".replace('(WRAP)', WRAP))
        print(json.dumps(out2, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
