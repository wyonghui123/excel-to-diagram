"""
详细诊断 el-tree 状态
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import time


def main():
    cli = PlaywrightCLI()
    try:
        cli.authenticated_navigate(
            '/system/archdata?productId=1&versionId=1',
            wait_for_selector='.multi-object-management',
            timeout=20000
        )
        cli.wait_for_timeout(3000)

        for i in range(15):
            tree_count = cli.evaluate("() => document.querySelectorAll('.el-tree').length")
            if tree_count > 0:
                break
            time.sleep(1)

        # 1. 勾选 财务管理
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const objectTree = trees[0];
                const nodes = objectTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.oss-node-label');
                    if (labelEl?.textContent?.trim() === '财务管理') {
                        const checkbox = node.querySelector('.el-checkbox');
                        if (checkbox) checkbox.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(2)

        # 2. 展开关系范围
        cli.evaluate("""
            () => {
                const panels = document.querySelectorAll('.collapsible-panel, .rst-panel-relation');
                for (const panel of panels) {
                    const titleEl = panel.querySelector('.panel-title, [class*="title"]');
                    if (titleEl?.textContent?.includes('关系范围')) {
                        const header = panel.querySelector('.panel-header, [class*="header"]');
                        if (header) header.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(2)

        for i in range(15):
            rel_count = cli.evaluate("""
                () => {
                    const trees = document.querySelectorAll('.el-tree');
                    if (trees.length < 2) return 0;
                    return trees[1].querySelectorAll('.el-tree-node').length;
                }
            """)
            if rel_count > 1:
                break
            time.sleep(1)

        # 装 monitor + 标记 oldStore
        cli.evaluate("""
            () => {
                window.__logs = [];
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                window.__oldElTree = vueComp.proxy;
                window.__oldStore = vueComp.proxy.store;
                const recordState = (label) => {
                    const total = Object.keys(window.__oldStore.nodesMap).length;
                    const checked = Object.values(window.__oldStore.nodesMap).filter(n => n.checked).length;
                    const tree = document.querySelectorAll('.el-tree')[1];
                    const newComp = tree?.__vueParentComponent;
                    const newStore = newComp?.proxy?.store;
                    const sameStore = newStore === window.__oldStore;
                    const sameElTree = newComp?.proxy === window.__oldElTree;
                    return { label, oldChecked: checked, oldTotal: total, sameStore, sameElTree, newChecked: newStore ? Object.values(newStore.nodesMap).filter(n => n.checked).length : 'N/A' };
                };
                window.__recordState = recordState;
                window.__recorder = setInterval(() => {
                    const r = recordState('periodic');
                    window.__logs.push(r);
                }, 200);
            }
        """)

        # 3. 点击 范围外
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                for (let i = 0; i < nodes.length; i++) {
                    const node = nodes[i];
                    const labelEl = node.querySelector('.rss-node-label');
                    if (labelEl?.textContent?.trim() === '范围外') {
                        const checkbox = node.querySelector('.el-checkbox');
                        if (checkbox) checkbox.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(2)

        s_after_click = cli.evaluate("() => window.__recordState('after_click')")
        print(f"[After Click] {s_after_click}")

        # 4. 触发 silent refresh
        cli.evaluate("() => { window.__logs = [] }")
        for i in range(2):
            cli.evaluate("""
                () => {
                    const trees = document.querySelectorAll('.el-tree');
                    const objectTree = trees[0];
                    const nodes = objectTree.querySelectorAll('.el-tree-node');
                    for (const node of nodes) {
                        const labelEl = node.querySelector('.oss-node-label');
                        if (labelEl?.textContent?.trim() === '财务管理') {
                            const checkbox = node.querySelector('.el-checkbox');
                            if (checkbox) checkbox.click();
                            return;
                        }
                    }
                }
            """)
            time.sleep(1)
        time.sleep(4)

        s_after_refresh = cli.evaluate("() => window.__recordState('after_refresh')")
        print(f"[After Refresh] {s_after_refresh}")

        logs = cli.evaluate("() => window.__logs || []")
        print(f"\n[Periodics] ({len(logs)} 条):")
        for l in logs:
            print(f"  {l}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
