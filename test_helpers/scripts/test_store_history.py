"""
完整跟踪 store checked count 变化
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import time
import json


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

        # 1. 勾选 domain
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

        # 2. 展开关系面板
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

        # 3. 持续监视 store 状态 5 秒
        cli.evaluate("""
            () => {
                window.__storeHistory = [];
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;

                const recordState = (event) => {
                    const checked = Object.values(store.nodesMap).filter(n => n.checked).length;
                    const indet = Object.values(store.nodesMap).filter(n => n.indeterminate).length;
                    const allIds = elTreeRef.getCheckedKeys();
                    window.__storeHistory.push({
                        time: Date.now(),
                        event,
                        checked,
                        indet,
                        total: store.nodesMap ? Object.keys(store.nodesMap).length : 0,
                        checkedKeysCount: allIds.length
                    });
                };

                recordState('init');

                // 监视 store.setData
                const origSetData = store.setData.bind(store);
                store.setData = function(data) {
                    recordState('before_setData');
                    const r = origSetData(data);
                    recordState('after_setData');
                    return r;
                };

                // 每 100ms 记录一次
                window.__recorder = setInterval(() => recordState('periodic'), 100);
            }
        """)

        # 4. 点击"范围外"
        print("[Step] 点击 范围外")
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
        time.sleep(4)

        # 5. 收集历史
        cli.evaluate("() => clearInterval(window.__recorder)")
        history = cli.evaluate("() => window.__storeHistory || []")
        print(f"\n[store history] ({len(history)} 条):")
        for h in history:
            print(f"  t={h['time']}, event={h['event']}, checked={h['checked']}, indet={h['indet']}, total={h['total']}, keys={h['checkedKeysCount']}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
