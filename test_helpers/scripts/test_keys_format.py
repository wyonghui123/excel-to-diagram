"""检查 preservedCheckedKeys 的 keys 格式"""
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

        # 检查 keys 格式
        info = cli.evaluate("""
            () => {
                const panels = document.querySelectorAll('.collapsible-panel');
                for (const panel of panels) {
                    const titleEl = panel.querySelector('.panel-title, [class*="title"]');
                    if (titleEl?.textContent?.includes('关系范围')) {
                        const section = panel.querySelector('.rss-root');
                        const vc = section.__vueParentComponent;
                        const setup = vc.setupState || {};
                        
                        const preservedKeys = setup.preservedCheckedKeys ? Array.from(setup.preservedCheckedKeys) : [];
                        
                        // 检查 classifierTreeData 的 ids
                        const treeData = setup.classifierTreeData || [];
                        const allIds = [];
                        const collectIds = (nodes) => {
                            for (const n of nodes) {
                                allIds.push(n.id);
                                if (n.children) collectIds(n.children);
                            }
                        };
                        collectIds(treeData);
                        
                        // 检查交集
                        const intersection = preservedKeys.filter(k => allIds.includes(k));
                        
                        return {
                            preservedKeysSample: preservedKeys.slice(0, 10),
                            allIdsSample: allIds.slice(0, 10),
                            intersectionCount: intersection.length,
                            preservedCount: preservedKeys.length,
                            allIdsCount: allIds.length
                        };
                    }
                }
                return { error: 'panel not found' };
            }
        """)
        print(f"Info: {info}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
