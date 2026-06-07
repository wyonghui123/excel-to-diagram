"""检查 el-tree 实例是否变化"""
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

        for i in range(30):
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

        for i in range(15):
            store_count = cli.evaluate("""
                () => {
                    const trees = document.querySelectorAll('.el-tree');
                    if (trees.length < 2) return 0;
                    const vc = trees[1].__vueParentComponent;
                    if (!vc?.proxy?.store) return 0;
                    return Object.keys(vc.proxy.store.nodesMap).length;
                }
            """)
            if store_count > 5:
                break
            time.sleep(1)

        # 标记初始 el-tree
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                window.__markedTree = relTree;
                window.__markedStore = relTree.__vueParentComponent.proxy.store;
                window.__markedProxy = relTree.__vueParentComponent.proxy;
            }
        """)

        # 点击 范围外
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.rss-node-label');
                    if (labelEl?.textContent?.trim() === '范围外') {
                        const checkbox = node.querySelector('.el-checkbox');
                        if (checkbox) checkbox.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(3)

        # 检查 el-tree 是否变化
        result = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                if (trees.length < 2) return { treeCount: trees.length };
                const relTree = trees[1];
                const sameTree = relTree === window.__markedTree;
                const newProxy = relTree.__vueParentComponent.proxy;
                const sameProxy = newProxy === window.__markedProxy;
                const newStore = newProxy.store;
                const sameStore = newStore === window.__markedStore;
                const newStoreTotal = Object.keys(newStore.nodesMap).length;
                const newStoreChecked = Object.values(newStore.nodesMap).filter(n => n.checked).length;
                const oldStoreTotal = Object.keys(window.__markedStore.nodesMap).length;
                const oldStoreChecked = Object.values(window.__markedStore.nodesMap).filter(n => n.checked).length;
                return {
                    treeCount: trees.length,
                    sameTree,
                    sameProxy,
                    sameStore,
                    oldStore: { total: oldStoreTotal, checked: oldStoreChecked },
                    newStore: { total: newStoreTotal, checked: newStoreChecked },
                    display: window.getComputedStyle(relTree).display,
                    parentDisplay: window.getComputedStyle(relTree.parentElement).display
                };
            }
        """)
        print(f"Result: {result}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
