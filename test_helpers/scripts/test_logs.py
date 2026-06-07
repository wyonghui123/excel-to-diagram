"""
捕获 browser console，看 restoration log
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

        # 装 console log 捕获
        cli.evaluate("""
            () => {
                window.__logs = [];
                const origLog = console.log;
                console.log = function(...args) {
                    window.__logs.push(args.join(' ').substring(0, 200));
                    return origLog.apply(this, args);
                };
            }
        """)

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

        # 清空 logs
        cli.evaluate("() => { window.__logs = [] }")

        # 3. 点击 范围外
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

        # 获取所有 logs
        logs = cli.evaluate("() => window.__logs || []")
        print("[Browser Console Logs]:")
        for log in logs:
            if 'RelationScope' in log or 'silent' in log or 'setCheckedKeys' in log or 'restoration' in log or 'unchanged' in log or 'coordinator' in log:
                print(f"  >>> {log}")
            else:
                print(f"  {log[:150]}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
