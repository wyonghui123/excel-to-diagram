"""
监视 el-tree vnode.props.data 何时变化
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

        # 1. 找到 el-tree vnode 的 props.data 引用
        cli.evaluate("""
            () => {
                window.__history = [];
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const obj = vueComp.parent;
                const setupState = obj.setupState;

                // 持续轮询 treeData.value 的引用
                let lastRef = setupState.treeData;
                let lastSetupStateTreeDataLength = setupState.treeData?.length;

                window.__poller = setInterval(() => {
                    const curRef = setupState.treeData;
                    if (curRef !== lastRef) {
                        window.__history.push({
                            time: Date.now(),
                            event: 'treeData.value ref changed',
                            oldLength: lastRef?.length,
                            newLength: curRef?.length,
                            isSameRef: curRef === lastRef
                        });
                        lastRef = curRef;
                    }
                }, 5);
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
                  f"oldLength={h.get('oldLength', '')}, newLength={h.get('newLength', '')}")

        # 5. 停止轮询
        cli.evaluate("() => clearInterval(window.__poller)")

        # 6. 检查最终状态
        final = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;
                const obj = vueComp.parent;
                const setupState = obj.setupState;

                return {
                    domCheckedCount: trees[0].querySelectorAll('.el-checkbox.is-checked').length,
                    nodeChecked: store.nodesMap['d_5']?.checked,
                    treeDataLength: setupState.treeData?.length,
                    treeDataRef: setupState.treeData
                };
            }
        """)
        print(f"\n[最终状态]: {json.dumps(final, ensure_ascii=False, indent=2)}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
