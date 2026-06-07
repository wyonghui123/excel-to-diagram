"""
装 store.setData 监控，看状态丢失的精确时机
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

        # 装详细监控
        cli.evaluate("""
            () => {
                window.__setDataHistory = [];
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;
                const origSetData = store.setData.bind(store);
                store.setData = function(data) {
                    const before = Object.values(store.nodesMap).filter(n => n.checked).length;
                    const total = data?.length || 0;
                    window.__setDataHistory.push({
                        time: Date.now(),
                        event: 'setData_called',
                        before,
                        total,
                        stack: (new Error()).stack.split('\\n').slice(0, 6).join('\\n  ')
                    });
                    const r = origSetData(data);
                    const after = Object.values(store.nodesMap).filter(n => n.checked).length;
                    window.__setDataHistory.push({
                        time: Date.now(),
                        event: 'setData_returned',
                        before,
                        after,
                        total
                    });
                    return r;
                };
            }
        """)

        # 3. 点击 范围外
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
        time.sleep(2)

        # 4. 触发 silent refresh
        print("[Step] 触发 silent refresh (toggle 财务管理)")
        cli.evaluate("() => { window.__setDataHistory = [] }")
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

        # 5. 收集
        history = cli.evaluate("() => window.__setDataHistory || []")
        print(f"\n[setData history] ({len(history)} 条):")
        for h in history:
            t_str = h.get('time', 0)
            print(f"  event={h.get('event')}, before={h.get('before')}, after={h.get('after')}, total={h.get('total')}")
            if 'stack' in h:
                print(f"  stack:\n  {h['stack']}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
