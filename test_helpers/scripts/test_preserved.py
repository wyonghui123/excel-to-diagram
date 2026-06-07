"""检查 preservedCheckedKeys 的值"""
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

        # 检查 preservedCheckedKeys
        before = cli.evaluate("""
            () => {
                const panels = document.querySelectorAll('.collapsible-panel');
                for (const panel of panels) {
                    const titleEl = panel.querySelector('.panel-title, [class*="title"]');
                    if (titleEl?.textContent?.includes('关系范围')) {
                        const section = panel.querySelector('.rss-root');
                        if (!section) return { error: 'no rss-root' };
                        const vc = section.__vueParentComponent;
                        const setup = vc.setupState || {};
                        return {
                            preservedSize: setup.preservedCheckedKeys?.size || 0,
                            preservedKeys: setup.preservedCheckedKeys ? Array.from(setup.preservedCheckedKeys) : []
                        };
                    }
                }
                return { error: 'panel not found' };
            }
        """)
        print(f"Before click: {before}")

        # 直接修改 store 并触发 handleClassifierCheck
        result = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vc = relTree.__vueParentComponent;
                const proxy = vc.proxy;
                const store = proxy.store;
                
                // 找到 范围外 节点
                let targetNode = null;
                let targetKey = null;
                for (const [key, node] of Object.entries(store.nodesMap)) {
                    if (node.label === '范围外') {
                        targetNode = node;
                        targetKey = key;
                        break;
                    }
                }
                
                if (!targetNode) return { error: 'node not found' };
                
                // 手动设置 checked
                proxy.setChecked(targetKey, true);
                
                // 模拟 @check 事件
                const checkedKeys = proxy.getCheckedKeys();
                const halfCheckedKeys = proxy.getHalfCheckedKeys();
                
                // 找到 RelationScopeSection 组件并调用 handleClassifierCheck
                const panels = document.querySelectorAll('.collapsible-panel');
                for (const panel of panels) {
                    const titleEl = panel.querySelector('.panel-title, [class*="title"]');
                    if (titleEl?.textContent?.includes('关系范围')) {
                        const section = panel.querySelector('.rss-root');
                        const sectionVc = section.__vueParentComponent;
                        const setup = sectionVc.setupState || {};
                        if (setup.handleClassifierCheck) {
                            setup.handleClassifierCheck(targetNode.data, { 
                                checkedKeys, 
                                checkedNodes: [],
                                halfCheckedNodes: []
                            });
                            return { called: true, checkedKeys: checkedKeys.length };
                        }
                        return { error: 'no handleClassifierCheck' };
                    }
                }
                return { error: 'panel not found' };
            }
        """)
        print(f"Result: {result}")
        time.sleep(1)

        # 检查 preservedCheckedKeys
        after = cli.evaluate("""
            () => {
                const panels = document.querySelectorAll('.collapsible-panel');
                for (const panel of panels) {
                    const titleEl = panel.querySelector('.panel-title, [class*="title"]');
                    if (titleEl?.textContent?.includes('关系范围')) {
                        const section = panel.querySelector('.rss-root');
                        const vc = section.__vueParentComponent;
                        const setup = vc.setupState || {};
                        return {
                            preservedSize: setup.preservedCheckedKeys?.size || 0,
                            preservedKeys: setup.preservedCheckedKeys ? Array.from(setup.preservedCheckedKeys).slice(0, 5) : []
                        };
                    }
                }
                return { error: 'panel not found' };
            }
        """)
        print(f"After manual call: {after}")

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
        print(f"State: {state}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
