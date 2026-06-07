"""
监视 node.setChecked 是否被调用
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

        # 1. 给 node.setChecked 加 wrapper 来观察调用
        cli.evaluate("""
            () => {
                window.__setCheckedCalls = [];

                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;

                const node = store.nodesMap['d_5'];
                if (node) {
                    const origSetChecked = node.setChecked.bind(node);
                    node.setChecked = function(value, deep) {
                        window.__setCheckedCalls.push({
                            time: Date.now(),
                            value,
                            deep,
                            beforeChecked: this.checked,
                            trace: new Error('setChecked call').stack.split('\\n').slice(0, 8).join('\\n')
                        });
                        return origSetChecked(value, deep);
                    };
                }
            }
        """)

        # 2. 给 el-checkbox 的 onClick 加 wrapper
        cli.evaluate("""
            () => {
                window.__checkboxEvents = [];

                const trees = document.querySelectorAll('.el-tree');
                const checkboxes = trees[0].querySelectorAll('.el-checkbox');
                if (checkboxes.length > 0) {
                    const input = checkboxes[0].querySelector('input[type="checkbox"]');
                    if (input) {
                        input.addEventListener('change', (e) => {
                            window.__checkboxEvents.push({
                                time: Date.now(),
                                type: 'change',
                                targetChecked: e.target.checked
                            });
                        }, true);  // capture phase
                        input.addEventListener('click', (e) => {
                            window.__checkboxEvents.push({
                                time: Date.now(),
                                type: 'click',
                                targetChecked: e.target.checked
                            });
                        }, true);
                    }
                }
            }
        """)

        # 3. 找到目标节点并点击
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

        # 4. 真实点击
        cli._page.click('[data-test-target="1"]', timeout=5000)
        print("[OK] 点击成功")

        time.sleep(1)

        # 5. 收集所有事件
        result = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;
                const node = store.nodesMap['d_5'];

                return {
                    setCheckedCalls: window.__setCheckedCalls || [],
                    checkboxEvents: window.__checkboxEvents || [],
                    nodeChecked: node?.checked,
                    nodeIndeterminate: node?.indeterminate,
                    getCheckedKeys: elTreeRef.getCheckedKeys()
                };
            }
        """)
        print("\n[setChecked 调用记录]:")
        for call in result.get('setCheckedCalls', []):
            print(f"  value={call['value']}, deep={call['deep']}, before={call['beforeChecked']}")
            print(f"    {call['trace'][:200]}")
            print()

        print("\n[Checkbox 事件]:")
        for ev in result.get('checkboxEvents', []):
            print(f"  {ev}")

        print(f"\n[最终状态]: node.checked={result.get('nodeChecked')}, "
              f"node.indeterminate={result.get('nodeIndeterminate')}, "
              f"getCheckedKeys={result.get('getCheckedKeys')}")

        cli.screenshot('after_setChecked_observer.png')

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
