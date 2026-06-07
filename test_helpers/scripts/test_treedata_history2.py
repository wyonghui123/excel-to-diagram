"""
最终定位: treeData 何时被重新赋值
简化版, 只监视 store.setData
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

        # 1. 监视 store.setData 和 loadTreeData
        cli.evaluate("""
            () => {
                window.__history = [];

                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const obj = vueComp.parent;
                const setupState = obj.setupState;
                const elTreeRef = vueComp.proxy;

                // 监视 el-tree store.setData 调用
                const origSetData = elTreeRef.store.setData.bind(elTreeRef.store);
                elTreeRef.store.setData = function(data) {
                    window.__history.push({
                        time: Date.now(),
                        event: 'store.setData',
                        dataLength: data?.length
                    });
                    return origSetData(data);
                };

                // 监视 loadTreeData 调用
                const origLoadTreeData = setupState.loadTreeData;
                setupState.loadTreeData = function(...args) {
                    window.__history.push({
                        time: Date.now(),
                        event: 'loadTreeData',
                        args: JSON.stringify(args).substring(0, 100)
                    });
                    return origLoadTreeData.apply(this, args);
                };

                // 监视 setCheckedKeys
                const origSetCheckedKeys = elTreeRef.setCheckedKeys.bind(elTreeRef);
                elTreeRef.setCheckedKeys = function(...args) {
                    window.__history.push({
                        time: Date.now(),
                        event: 'setCheckedKeys',
                        args: JSON.stringify(args).substring(0, 100)
                    });
                    return origSetCheckedKeys(...args);
                };

                // 监视 setChecked
                const origSetChecked = elTreeRef.setChecked.bind(elTreeRef);
                elTreeRef.setChecked = function(...args) {
                    window.__history.push({
                        time: Date.now(),
                        event: 'setChecked',
                        args: JSON.stringify(args).substring(0, 100)
                    });
                    return origSetChecked(...args);
                };
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
                  f"dataLength={h.get('dataLength', '')}, args={h.get('args', '')[:80]}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
