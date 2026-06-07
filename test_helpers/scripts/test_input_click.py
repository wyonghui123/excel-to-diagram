"""检查 el-tree 内部状态"""
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

        # 检查 el-tree 内部状态
        info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vc = relTree.__vueParentComponent;
                const proxy = vc.proxy;
                
                // 检查是否有 showCheckbox
                const props = proxy.$props;
                
                // 检查节点 DOM
                const nodes = relTree.querySelectorAll('.el-tree-node');
                let firstNodeInfo = null;
                for (const node of nodes) {
                    const labelEl = node.querySelector('.rss-node-label');
                    if (labelEl?.textContent?.trim() === '范围外') {
                        const checkbox = node.querySelector('.el-checkbox');
                        const input = checkbox?.querySelector('input');
                        firstNodeInfo = {
                            hasCheckbox: !!checkbox,
                            hasInput: !!input,
                            inputChecked: input?.checked,
                            inputIndeterminate: input?.indeterminate,
                            inputDisabled: input?.disabled,
                            checkboxClass: checkbox?.className
                        };
                        break;
                    }
                }
                
                return {
                    showCheckbox: props.showCheckbox,
                    checkStrictly: props.checkStrictly,
                    firstNode: firstNodeInfo
                };
            }
        """)
        print(f"Info: {info}")

        # 手动触发 input click
        result = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.rss-node-label');
                    if (labelEl?.textContent?.trim() === '范围外') {
                        const input = node.querySelector('.el-checkbox__original');
                        if (input) {
                            console.log('Clicking input, checked before:', input.checked);
                            input.click();
                            console.log('Clicking input, checked after:', input.checked);
                            return { clicked: true };
                        }
                        return { clicked: false, reason: 'no input' };
                    }
                }
                return { clicked: false, reason: 'node not found' };
            }
        """)
        print(f"Click result: {result}")
        time.sleep(1)

        # 检查状态
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
