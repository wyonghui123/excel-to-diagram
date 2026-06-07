"""检查 store 是否被重新创建"""
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

        # 标记 store + 立即 click
        print("[Step] 标记 store + click + 检查")
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                window.__oldStore = vueComp.proxy.store;
                window.__oldElTree = vueComp.proxy;

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

        time.sleep(0.5)

        # 检查新旧 store
        result = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const newStore = vueComp.proxy.store;
                const sameStore = newStore === window.__oldStore;
                const sameElTree = vueComp.proxy === window.__oldElTree;
                return {
                    sameStore,
                    sameElTree,
                    oldChecked: Object.values(window.__oldStore.nodesMap).filter(n => n.checked).length,
                    newChecked: Object.values(newStore.nodesMap).filter(n => n.checked).length,
                    oldTotal: Object.keys(window.__oldStore.nodesMap).length,
                    newTotal: window.__oldStore.nodesMap ? Object.keys(newStore.nodesMap).length : 'N/A',
                    newKeys: Object.keys(newStore.nodesMap).slice(0, 5)
                };
            }
        """)
        print(f"  result: {result}")

        # 看看是否在 silent refresh 过程中 (classifierLoading)
        load_state = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                if (trees.length < 2) return { error: 'no tree[1]', treeCount: trees.length };
                const loading = document.querySelector('.rss-loading');
                const empty = document.querySelector('.rss-empty');
                return {
                    treeCount: trees.length,
                    loadingVisible: loading?.offsetParent !== null,
                    emptyVisible: empty?.offsetParent !== null,
                    allTreeNodes: Array.from(trees[1].querySelectorAll('.el-tree-node')).map(n => n.querySelector('.rss-node-label')?.textContent?.trim()).slice(0, 10)
                };
            }
        """)
        print(f"  load state: {load_state}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
