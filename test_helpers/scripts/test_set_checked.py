"""简化测试 - 直接调用 handleCheck"""
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

        # 找到 范围外 节点
        node_info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vc = relTree.__vueParentComponent;
                const proxy = vc.proxy;
                const store = proxy.store;
                
                for (const [key, node] of Object.entries(store.nodesMap)) {
                    if (node.label === '范围外' || node.data?.name === '范围外') {
                        return {
                            id: node.id,
                            label: node.label,
                            checked: node.checked,
                            indeterminate: node.indeterminate,
                            childCount: node.childNodes?.length || 0
                        };
                    }
                }
                return null;
            }
        """)
        print(f"Node: {node_info}")

        if node_info:
            # 直接调用 setChecked
            cli.evaluate(f"""
                () => {{
                    const trees = document.querySelectorAll('.el-tree');
                    const relTree = trees[1];
                    const vc = relTree.__vueParentComponent;
                    const proxy = vc.proxy;
                    proxy.setChecked('{node_info['id']}', true);
                }}
            """)
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
            print(f"State after setChecked: {state}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
