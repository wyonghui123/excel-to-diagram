"""检查 allIds 的变化"""
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

        # 记录每次 setData 的 allIds
        cli.evaluate("""
            () => {
                window.__allIdsHistory = [];
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vc = relTree.__vueParentComponent;
                const store = vc.proxy.store;
                const origSetData = store.setData.bind(store);
                store.setData = function(newData) {
                    const allIds = [];
                    const collectIds = (nodes) => {
                        for (const n of nodes) {
                            allIds.push(n.id);
                            if (n.children) collectIds(n.children);
                        }
                    };
                    collectIds(newData || []);
                    window.__allIdsHistory.push({
                        time: Date.now(),
                        count: allIds.length,
                        sample: allIds.slice(0, 5)
                    });
                    return origSetData(newData);
                };
            }
        """)

        # 等待操作
        time.sleep(5)

        # 收集历史
        history = cli.evaluate("() => window.__allIdsHistory || []")
        print(f"AllIds history ({len(history)} entries):")
        for i, h in enumerate(history):
            print(f"  [{i}] count={h['count']}, sample={h['sample']}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
