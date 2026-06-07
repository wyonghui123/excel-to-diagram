"""
通过监视 setupState 拦截 loadTreeData 调用并记录 treeData.value
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import time
import json


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
                print(f"[OK] 找到 {tree_count} 个 el-tree")
                break
            time.sleep(1)

        # 1. 拦截 loadTreeData
        cli.evaluate("""
            () => {
                window.__history = [];
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const obj = vueComp.parent;
                const setupState = obj.setupState;

                const origLoad = setupState.loadTreeData;
                setupState.loadTreeData = function(opts) {
                    const startTime = Date.now();
                    window.__history.push({
                        time: startTime,
                        event: 'loadTreeData start',
                        opts: JSON.stringify(opts || {}),
                        treeDataBefore: setupState.treeData?.length
                    });
                    const result = origLoad.call(this, opts);
                    // 在 result 之后，treeData 可能已经被设置
                    return result;
                };

                // 监视 initialBoIds prop 变化
                let lastBoIds = setupState.props?.initialBoIds;
                if (lastBoIds) {
                    window.__initialBoIdsSnapshot = JSON.stringify(lastBoIds);
                }
            }
        """)

        # 2. 找到目标节点
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const checkboxes = trees[0].querySelectorAll('.el-checkbox');
                for (let i = 0; i < checkboxes.length; i++) {
                    const node = checkboxes[i].closest('.el-tree-node');
                    if (!node) continue;
                    const rect = node.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        checkboxes[i].setAttribute('data-test-target', '1');
                        return;
                    }
                }
            }
        """)

        # 3. 点击
        cli._page.click('[data-test-target="1"]', timeout=5000)
        print("[OK] 点击成功")

        time.sleep(2)

        # 4. 收集历史
        history = cli.evaluate("() => window.__history || []")
        print(f"\n[历史 (共 {len(history)} 条)]:")
        for i, h in enumerate(history):
            print(f"  [{i}] t={h['time']}, event={h['event']}, "
                  f"opts={h.get('opts', '')}, treeDataBefore={h.get('treeDataBefore', '')}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
