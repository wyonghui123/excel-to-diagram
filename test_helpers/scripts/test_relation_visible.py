"""简单测试：检查面板状态和可见节点"""
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
        print("[Step 2] 展开关系范围面板")
        cli.evaluate("""
            () => {
                const panels = document.querySelectorAll('.collapsible-panel');
                for (const panel of panels) {
                    const titleEl = panel.querySelector('.panel-title, [class*="title"]');
                    if (titleEl?.textContent?.includes('关系范围')) {
                        // 如果折叠，展开
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

        # 3. 检查所有可见的 el-tree 节点
        info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                return Array.from(trees).map((t, i) => ({
                    idx: i,
                    totalNodes: t.querySelectorAll('.el-tree-node').length,
                    visibleNodes: Array.from(t.querySelectorAll('.el-tree-node')).filter(n => n.offsetParent !== null).length,
                    sampleTexts: Array.from(t.querySelectorAll('.el-tree-node')).filter(n => n.offsetParent !== null).slice(0, 5).map(n => n.querySelector('.rss-node-label, .oss-node-label')?.textContent?.trim())
                }));
            }
        """)
        print(f"[Step 3] 树状态:")
        for i in info:
            print(f"  tree[{i['idx']}]: total={i['totalNodes']}, visible={i['visibleNodes']}, sample={i['sampleTexts']}")

        # 4. 检查 toolbar
        toolbar = cli.evaluate("""
            () => {
                const rssToolbar = document.querySelector('.rss-toolbar');
                if (!rssToolbar) return null;
                const buttons = rssToolbar.querySelectorAll('.app-btn');
                return {
                    visible: rssToolbar.offsetParent !== null,
                    buttonCount: buttons.length,
                    buttonTexts: Array.from(buttons).map(b => b.textContent?.trim())
                };
            }
        """)
        print(f"[Step 4] toolbar: {toolbar}")

        # 5. 现在展开 范围内
        print("\n[Step 5] 展开 范围内 节点")
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.rss-node-label');
                    if (labelEl?.textContent?.trim() === '范围内') {
                        const expandIcon = node.querySelector('.el-tree-node__expand-icon');
                        console.log('expandIcon:', expandIcon?.className);
                        if (expandIcon && !expandIcon.classList.contains('is-leaf')) {
                            expandIcon.click();
                        }
                        return;
                    }
                }
            }
        """)
        time.sleep(2)

        info2 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                return {
                    totalNodes: relTree.querySelectorAll('.el-tree-node').length,
                    visibleNodes: Array.from(relTree.querySelectorAll('.el-tree-node')).filter(n => n.offsetParent !== null).length,
                    sampleTexts: Array.from(relTree.querySelectorAll('.el-tree-node')).filter(n => n.offsetParent !== null).slice(0, 10).map(n => n.querySelector('.rss-node-label')?.textContent?.trim())
                };
            }
        """)
        print(f"[Step 5] 展开 范围内 后: {info2}")

        # 6. 在 范围内 上点击 checkbox (应该会父子联动)
        print("\n[Step 6] 点击 范围内 节点 checkbox")
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const nodes = relTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.rss-node-label');
                    if (labelEl?.textContent?.trim() === '范围内') {
                        const checkbox = node.querySelector('.el-checkbox');
                        if (checkbox) checkbox.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(2)

        info3 = cli.evaluate("""
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
        print(f"[Step 6] 点击后: {info3}")

        cli.screenshot(path='d:/filework/excel-to-diagram/screenshots/relation_scope_state.png')

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
