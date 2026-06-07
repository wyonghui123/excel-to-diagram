"""追踪点击后数据清空的原因"""
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

        # 装 setData 监控
        cli.evaluate("""
            () => {
                window.__events = [];
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vc = relTree.__vueParentComponent;
                const proxy = vc.proxy;
                const store = proxy.store;
                
                // 监控 setData
                const origSetData = store.setData.bind(store);
                store.setData = function(data) {
                    window.__events.push({
                        type: 'setData',
                        time: Date.now(),
                        dataLen: data?.length || 0,
                        stack: new Error().stack.split('\\n').slice(1, 4).join(' | ')
                    });
                    return origSetData(data);
                };
                
                // 监控 props.data 变化
                const origData = proxy.data;
                
                // 监控 @check 事件
                relTree.addEventListener('check', (e) => {
                    window.__events.push({
                        type: 'check_event',
                        time: Date.now()
                    });
                }, true);
            }
        """)

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
                        if (checkbox) checkbox.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(3)

        # 收集事件
        events = cli.evaluate("() => window.__events || []")
        print(f"\n[Events] {len(events)} 条:")
        for e in events:
            print(f"  {e}")

        # 最终状态
        final = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                if (trees.length < 2) return { error: 'no tree' };
                const vc = trees[1].__vueParentComponent;
                const store = vc?.proxy?.store;
                return {
                    storeNodes: store ? Object.keys(store.nodesMap).length : 0,
                    storeChecked: store ? Object.values(store.nodesMap).filter(n => n.checked).length : 0,
                    dataLen: vc?.proxy?.data?.length || 0
                };
            }
        """)
        print(f"\n[Final] {final}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
