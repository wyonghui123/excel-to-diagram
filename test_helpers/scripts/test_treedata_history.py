"""
最终定位: treeData 何时被重新赋值
通过 Proxy 拦截 shallowRef 内部值变化
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

        # 1. 监视 treeData 的 setter
        cli.evaluate("""
            () => {
                window.__treeDataHistory = [];

                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const obj = vueComp.parent;
                const setupState = obj.setupState;
                const treeData = setupState.treeData;
                const treeKey = setupState.treeKey;

                // 找到 el-tree 的 props
                const elTreeProps = vueComp.vnode.props;

                // 监视 el-tree store.setData 调用
                const elTreeRef = vueComp.proxy;
                const origSetData = elTreeRef.store.setData.bind(elTreeRef.store);
                elTreeRef.store.setData = function(data) {
                    window.__treeDataHistory.push({
                        time: Date.now(),
                        event: 'store.setData',
                        dataLength: data?.length
                    });
                    return origSetData(data);
                };

                // 监视 loadTreeData 调用
                const origLoadTreeData = setupState.loadTreeData;
                setupState.loadTreeData = function(...args) {
                    window.__treeDataHistory.push({
                        time: Date.now(),
                        event: 'loadTreeData',
                        args: JSON.stringify(args).substring(0, 100)
                    });
                    return origLoadTreeData(...args);
                };

                // 监视 settingFromProp
                const settingFromProp = setupState.settingFromProp;
                Object.defineProperty(settingFromProp, 'value', {
                    get() { return settingFromProp._value; },
                    set(v) {
                        window.__treeDataHistory.push({
                            time: Date.now(),
                            event: 'settingFromProp change',
                            newValue: v
                        });
                        settingFromProp._value = v;
                    }
                });
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
        history = cli.evaluate("() => window.__treeDataHistory || []")
        print(f"\n[历史 (共 {len(history)} 条)]:")
        for i, h in enumerate(history):
            print(f"  [{i}] t={h['time']}, event={h['event']}, "
                  f"dataLength={h.get('dataLength', '')}, args={h.get('args', '')[:80]}, "
                  f"newValue={h.get('newValue', '')}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
