"""检查 get_stats 获取的是哪个 el-tree"""
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
        time.sleep(3)

        # 检查所有 el-tree
        trees_info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                return Array.from(trees).map((t, i) => {
                    const vc = t.__vueParentComponent;
                    const proxy = vc?.proxy;
                    const store = proxy?.store;
                    return {
                        index: i,
                        domNodes: t.querySelectorAll('.el-tree-node').length,
                        storeNodes: store ? Object.keys(store.nodesMap).length : 0,
                        storeChecked: store ? Object.values(store.nodesMap).filter(n => n.checked).length : 0,
                        display: window.getComputedStyle(t).display,
                        dataLength: proxy?.data?.length || 0,
                        sampleLabels: Array.from(t.querySelectorAll('.el-tree-node')).slice(0, 3).map(n => 
                            n.querySelector('.rss-node-label, .oss-node-label')?.textContent?.trim()
                        )
                    };
                });
            }
        """)
        print(f"All trees: {trees_info}")

        # 找到关系范围树 (trees[1])
        if len(trees_info) >= 2:
            rel_tree = trees_info[1]
            print(f"\n关系范围树 (trees[1]): {rel_tree}")

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
                        if (checkbox) {
                            console.log('clicking 范围外');
                            checkbox.click();
                            return;
                        }
                    }
                }
                console.log('范围外 not found');
            }
        """)
        time.sleep(2)

        # 再次检查
        trees_after = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                return Array.from(trees).map((t, i) => {
                    const vc = t.__vueParentComponent;
                    const proxy = vc?.proxy;
                    const store = proxy?.store;
                    return {
                        index: i,
                        domNodes: t.querySelectorAll('.el-tree-node').length,
                        storeNodes: store ? Object.keys(store.nodesMap).length : 0,
                        storeChecked: store ? Object.values(store.nodesMap).filter(n => n.checked).length : 0
                    };
                });
            }
        """)
        print(f"\nAfter click: {trees_after}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
