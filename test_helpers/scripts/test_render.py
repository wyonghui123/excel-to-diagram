"""检查 el-tree 是否被重新渲染"""
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

        # 标记 el-tree
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                window.__markedTree = trees[1];
                window.__markedStore = trees[1].__vueParentComponent.proxy.store;
                window.__renderCount = 0;
                
                // 监视 store 变化
                const store = window.__markedStore;
                const origSetData = store.setData.bind(store);
                store.setData = function(data) {
                    window.__renderCount++;
                    console.log('[MONITOR] setData called, count:', window.__renderCount, 'dataLen:', data?.length);
                    return origSetData(data);
                };
            }
        """)

        # 点击 input
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.rss-node-label');
                    if (labelEl?.textContent?.trim() === '范围外') {
                        const input = node.querySelector('.el-checkbox__original');
                        if (input) {
                            input.click();
                            return;
                        }
                    }
                }
            }
        """)
        time.sleep(2)

        # 检查
        result = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const sameTree = trees[1] === window.__markedTree;
                const sameStore = trees[1].__vueParentComponent.proxy.store === window.__markedStore;
                const store = trees[1].__vueParentComponent.proxy.store;
                return {
                    sameTree,
                    sameStore,
                    renderCount: window.__renderCount,
                    storeChecked: Object.values(store.nodesMap).filter(n => n.checked).length
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
