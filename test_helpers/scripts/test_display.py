"""检查 el-tree 的 display 状态"""
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

        # 等 store
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
        print(f"[Setup] store count: {store_count}")

        # 装 monitor
        cli.evaluate("""
            () => {
                window.__monitor = [];
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vc = relTree.__vueParentComponent;
                vc.proxy.getCheckedKeys();
                const store = vc.proxy.store;
                setInterval(() => {
                    const total = Object.keys(store.nodesMap).length;
                    const checked = Object.values(store.nodesMap).filter(n => n.checked).length;
                    const display = window.getComputedStyle(relTree).display;
                    window.__monitor.push({ time: Date.now(), total, checked, display });
                }, 100);
            }
        """)
        time.sleep(1)

        # 装 stack tracker on setData
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vc = relTree.__vueParentComponent;
                const store = vc.proxy.store;
                const origSetData = store.setData.bind(store);
                window.__setDataLog = [];
                store.setData = function(data) {
                    window.__setDataLog.push({
                        time: Date.now(),
                        count: data?.length || 0,
                        stack: new Error().stack.split('\\n').slice(0, 8).join(' | ')
                    });
                    return origSetData(data);
                };
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

        # 收集
        monitor = cli.evaluate("() => window.__monitor || []")
        setdata_log = cli.evaluate("() => window.__setDataLog || []")

        print(f"\n[Monitor] {len(monitor)} 条:")
        for i, m in enumerate(monitor[:30]):
            print(f"  +{(m['time'] - monitor[0]['time'])}ms, total={m['total']}, checked={m['checked']}, display={m['display']}")

        print(f"\n[setData] {len(setdata_log)} 次:")
        for s in setdata_log:
            print(f"  +{(s['time'] - setdata_log[0]['time'])}ms, count={s['count']}")
            print(f"    stack: {s['stack']}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
