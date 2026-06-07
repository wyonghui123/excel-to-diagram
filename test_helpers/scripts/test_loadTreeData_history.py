"""
通过 shallowRef 的 value 拦截器监视 treeData 何时被赋值
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

        # 1. 通过 setTimeout 在异步上下文中记录 click 前后的 treeData
        cli.evaluate("""
            () => {
                window.__history = [];
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const obj = vueComp.parent;
                const setupState = obj.setupState;

                // 保存 treeData 的引用
                window.__savedTreeData = setupState.treeData;
                window.__savedRef = setupState.treeData;

                // 修改 loadTreeData 来在调用前后记录
                const origLoad = setupState.loadTreeData;
                setupState.loadTreeData = function(opts) {
                    const callTime = Date.now();
                    window.__history.push({
                        time: callTime,
                        event: 'loadTreeData called',
                        opts: JSON.stringify(opts),
                        treeDataRefBefore: setupState.treeData === window.__savedRef ? 'same' : 'changed',
                        treeDataLength: setupState.treeData?.length
                    });
                    return origLoad.call(this, opts).then(result => {
                        window.__history.push({
                            time: Date.now(),
                            event: 'loadTreeData completed',
                            treeDataRefAfter: setupState.treeData === window.__savedRef ? 'same' : 'changed'
                        });
                        return result;
                    });
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
                  f"opts={h.get('opts', '')}, refBefore={h.get('treeDataRefBefore', '')}, "
                  f"refAfter={h.get('treeDataRefAfter', '')}, length={h.get('treeDataLength', '')}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
