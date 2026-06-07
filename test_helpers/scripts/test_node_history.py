"""
最终诊断: setChecked 后 node.checked=true 立刻被重置
跟踪所有 watch 触发, 找到重置源头
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

        # 1. 添加对象身份追踪
        cli.evaluate("""
            () => {
                window.__nodeHistory = [];

                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;

                // 拦截 store.nodesMap 的访问
                const origNodesMap = store.nodesMap;
                let prevNode = origNodesMap['d_5'];

                window.__checkStore = () => {
                    const cur = store.nodesMap['d_5'];
                    window.__nodeHistory.push({
                        time: Date.now(),
                        isNewNode: cur !== prevNode,
                        curChecked: cur?.checked,
                        curIndeterminate: cur?.indeterminate,
                        dataChanged: cur?.data !== prevNode?.data
                    });
                    prevNode = cur;
                };

                // 监听 initialBoIds
                const objComp = vueComp.parent;
                const setupState = objComp.setupState;

                // 拦截 setCheckedKeys
                const origSetCheckedKeys = elTreeRef.setCheckedKeys.bind(elTreeRef);
                elTreeRef.setCheckedKeys = function(...args) {
                    window.__nodeHistory.push({
                        time: Date.now(),
                        event: 'setCheckedKeys',
                        args: JSON.stringify(args).substring(0, 200)
                    });
                    return origSetCheckedKeys(...args);
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

        # 3. 多个时间点采样
        cli.evaluate("() => { window.__checkStore(); }")

        # 4. 点击
        cli._page.click('[data-test-target="1"]', timeout=5000)
        print("[OK] 点击成功")

        for ms in [10, 50, 100, 200, 500, 1000, 2000]:
            time.sleep(ms / 1000.0)
            cli.evaluate("() => { window.__checkStore(); }")

        # 5. 收集历史
        history = cli.evaluate("() => window.__nodeHistory || []")
        print(f"\n[节点历史 (共 {len(history)} 条)]:")
        for i, h in enumerate(history):
            print(f"  [{i}] t={h['time']}, isNew={h.get('isNewNode')}, "
                  f"checked={h.get('curChecked')}, indet={h.get('curIndeterminate')}, "
                  f"dataChanged={h.get('dataChanged')}, event={h.get('event')}, args={h.get('args', '')[:100]}")

        # 6. 最后状态
        print("\n[最终状态]:")
        final = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;
                return {
                    domCheckedCount: trees[0].querySelectorAll('.el-checkbox.is-checked').length,
                    nodeChecked: store.nodesMap['d_5']?.checked,
                    getCheckedKeys: elTreeRef.getCheckedKeys()
                };
            }
        """)
        print(json.dumps(final, ensure_ascii=False, indent=2))

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
