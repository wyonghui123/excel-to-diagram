"""检查 el-tree check 事件是否触发"""
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

        for i in range(30):
            rel_count = cli.evaluate("""
                () => {
                    const trees = document.querySelectorAll('.el-tree');
                    if (trees.length < 2) return 0;
                    return trees[1].querySelectorAll('.el-tree-node').length;
                }
            """)
            if rel_count > 0:
                break
            time.sleep(1)

        # 装 check 事件监听
        cli.evaluate("""
            () => {
                window.__checkEvents = [];
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                
                // 监听原生 click
                relTree.addEventListener('click', (e) => {
                    window.__checkEvents.push({ type: 'click', target: e.target?.className });
                }, true);
                
                // 监听 el-tree 的 check 事件
                const vc = relTree.__vueParentComponent;
                const proxy = vc.proxy;
                const origEmit = proxy.$emit;
                proxy.$emit = function(event, ...args) {
                    if (event === 'check') {
                        window.__checkEvents.push({ 
                            type: 'check_emit', 
                            data: args[0]?.id,
                            checkedKeys: args[1]?.checkedKeys?.length
                        });
                    }
                    return origEmit.apply(this, [event, ...args]);
                };
                
                // 初始化 el-tree state
                proxy.getCheckedKeys();
            }
        """)
        time.sleep(0.5)

        # 点击 范围外
        print("[Step] 点击 范围外")
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.rss-node-label');
                    if (labelEl?.textContent?.trim() === '范围外') {
                        const checkbox = node.querySelector('.el-checkbox');
                        console.log('Found 范围外, checkbox:', checkbox?.className);
                        if (checkbox) {
                            checkbox.click();
                            return;
                        }
                    }
                }
                console.log('范围外 not found');
            }
        """)
        time.sleep(2)

        # 收集事件
        events = cli.evaluate("() => window.__checkEvents || []")
        print(f"\n[Events] {len(events)} 条:")
        for e in events:
            print(f"  {e}")

        # 检查 store 状态
        state = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vc = relTree.__vueParentComponent;
                const store = vc.proxy.store;
                return {
                    total: Object.keys(store.nodesMap).length,
                    checked: Object.values(store.nodesMap).filter(n => n.checked).length,
                    indet: Object.values(store.nodesMap).filter(n => n.indeterminate).length
                };
            }
        """)
        print(f"\n[State] {state}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
