"""
调试：检查为什么点击 范围外 不工作
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

        # 3. 装 hook
        print("[Setup] 装 @check 监听")
        cli.evaluate("""
            () => {
                window.__checks = [];
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                // 监听 el-tree 的 @check
                const origEmit = elTreeRef.$emit;
                elTreeRef.$emit = function(event, ...args) {
                    if (event === 'check') {
                        window.__checks.push({
                            event: 'check_emitted',
                            args: args.length,
                            checkedKeys: elTreeRef.getCheckedKeys()
                        });
                    }
                    return origEmit.apply(this, [event, ...args]);
                };
            }
        """)

        # 4. 找 范围外 节点 (with extra info)
        info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                const result = [];
                for (const node of nodes) {
                    const labelEl = node.querySelector('.rss-node-label');
                    if (labelEl?.textContent?.trim() === '范围外') {
                        const checkbox = node.querySelector('.el-checkbox');
                        const isVisible = node.offsetParent !== null;
                        const bbox = node.getBoundingClientRect();
                        return {
                            label: labelEl.textContent.trim(),
                            hasCheckbox: !!checkbox,
                            isVisible,
                            bbox: { x: bbox.x, y: bbox.y, width: bbox.width, height: bbox.height },
                            checkboxHTML: checkbox?.outerHTML.substring(0, 500)
                        };
                    }
                }
                return { notFound: true, totalNodes: nodes.length, nodeTexts: Array.from(nodes).map(n => n.querySelector('.rss-node-label')?.textContent?.trim()) };
            }
        """)
        print(f"[Setup] 范围外 节点信息: {info}")

        # 5. 真实点击
        print("\n[Click] 真实点击 checkbox")
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.rss-node-label');
                    if (labelEl?.textContent?.trim() === '范围外') {
                        const checkbox = node.querySelector('.el-checkbox');
                        if (checkbox) {
                            console.log('clicking checkbox...');
                            checkbox.click();
                            console.log('clicked');
                        }
                        return;
                    }
                }
            }
        """)
        time.sleep(2)

        # 6. 检查状态
        state = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const store = vueComp.proxy.store;
                const total = Object.keys(store.nodesMap).length;
                const checked = Object.values(store.nodesMap).filter(n => n.checked).length;
                const indet = Object.values(store.nodesMap).filter(n => n.indeterminate).length;
                return { total, checked, indet };
            }
        """)
        print(f"[Click] store 状态: {state}")

        checks = cli.evaluate("() => window.__checks || []")
        print(f"[Click] @check 事件: {checks}")

        # 7. 看看 DOM 状态变化
        dom = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.rss-node-label');
                    if (labelEl?.textContent?.trim() === '范围外') {
                        const checkbox = node.querySelector('.el-checkbox');
                        return {
                            className: checkbox?.className,
                            isChecked: checkbox?.classList.contains('is-checked'),
                            isIndet: checkbox?.classList.contains('is-indeterminate')
                        };
                    }
                }
                return null;
            }
        """)
        print(f"[Click] DOM 状态: {dom}")

        cli.screenshot(path='d:/filework/excel-to-diagram/screenshots/click_debug.png')

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
