"""直接测试 el-tree 内部状态"""
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

        # 2. 展开关系面板
        cli.evaluate("""
            () => {
                const panels = document.querySelectorAll('.collapsible-panel');
                for (const panel of panels) {
                    const titleEl = panel.querySelector('.panel-title, [class*="title"]');
                    if (titleEl?.textContent?.includes('关系范围')) {
                        if (panel.classList.contains('is-collapsed')) {
                            const header = panel.querySelector('.panel-header, [class*="header"]');
                            if (header) header.click();
                        }
                        return;
                    }
                }
            }
        """)
        time.sleep(3)

        # 3. 装一个 listener
        print("[Step 3] 装 click 监听")
        cli.evaluate("""
            () => {
                window.__events = [];
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                relTree.addEventListener('check', (e) => {
                    window.__events.push({
                        type: 'check_event',
                        target: e.target?.__vueParentComponent?.proxy?.data?.name,
                        detail: {
                            checkedKeys: relTree.getCheckedKeys ? relTree.getCheckedKeys() : 'N/A'
                        }
                    });
                }, true);
            }
        """)

        # 4. 直接点击 范围外 checkbox
        print("\n[Step 4] 点击 范围外")
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.rss-node-label');
                    if (labelEl?.textContent?.trim() === '范围外') {
                        // 详细查看 checkbox 状态
                        const checkbox = node.querySelector('.el-checkbox');
                        const input = checkbox?.querySelector('input[type="checkbox"]');
                        const isInput = input?.type;
                        const isChecked = input?.checked;
                        const isIndeterminate = input?.indeterminate;
                        const elTreeInput = node.querySelector('.el-checkbox__original');
                        console.log('checkbox:', { isInput, isChecked, isIndeterminate, hasInput: !!input });
                        if (checkbox) {
                            checkbox.click();
                        }
                        return;
                    }
                }
            }
        """)
        time.sleep(2)

        events = cli.evaluate("() => window.__events || []")
        print(f"  events: {events}")

        info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const store = vueComp.proxy.store;
                const total = Object.keys(store.nodesMap).length;
                const checked = Object.values(store.nodesMap).filter(n => n.checked).length;
                const indet = Object.values(store.nodesMap).filter(n => n.indeterminate).length;
                // 拿到所有 checked 节点的名字
                const checkedNames = Object.values(store.nodesMap).filter(n => n.checked).map(n => n.label);
                return { total, checked, indet, checkedNames };
            }
        """)
        print(f"  store: {info}")

        # 5. 看看 范围外 节点的 DOM 状态
        print("\n[Step 5] 范围外 DOM 状态")
        dom_state = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.rss-node-label');
                    if (labelEl?.textContent?.trim() === '范围外') {
                        const checkbox = node.querySelector('.el-checkbox');
                        const isChecked = checkbox?.classList.contains('is-checked');
                        const isIndet = checkbox?.classList.contains('is-indeterminate');
                        return {
                            className: checkbox?.className,
                            isChecked,
                            isIndet,
                            innerHTML: checkbox?.outerHTML.substring(0, 300)
                        };
                    }
                }
                return null;
            }
        """)
        print(f"  dom: {dom_state}")

        cli.screenshot(path='d:/filework/excel-to-diagram/screenshots/relation_state.png')

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
