"""
深入分析: el-tree @check 事件触发后 DOM 状态被重置
可能原因:
  1. el-tree store 内部状态被重置
  2. 节点重新渲染导致 checkbox state 丢失
  3. settingFromProp 在中途被重置
  4. watch 监听重新触发了 loadTreeData
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

        cli.evaluate("""
            () => {
                window.__logs = [];
                const origLog = console.log;
                console.log = function(...args) {
                    window.__logs.push(args.map(a =>
                        typeof a === 'string' ? a :
                        typeof a === 'object' ? JSON.stringify(a) : String(a)
                    ).join(' '));
                    return origLog.apply(this, args);
                };
            }
        """)

        # 1. 找到目标节点
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

        # 2. 实时跟踪状态变化 - 在多个时间点采样
        cli.evaluate("""
            () => {
                window.__stateSnapshots = [];
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const vueComp = targetTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const obj = vueComp.parent;
                const setupState = obj.setupState;

                const snapshot = (label) => {
                    window.__stateSnapshots.push({
                        label,
                        time: Date.now(),
                        domCheckedCount: targetTree.querySelectorAll('.el-checkbox.is-checked').length,
                        treeRefCheckedKeys: elTreeRef.getCheckedKeys(),
                        settingFromProp: setupState.settingFromProp,
                        treeDataLength: setupState.treeData?.length,
                        treeKey: setupState.treeKey
                    });
                };

                snapshot('before_click');
                window.__snapshot = snapshot;
            }
        """)

        # 3. 真实点击
        page = cli._page
        page.click('[data-test-target="1"]', timeout=5000)
        print("[OK] 点击成功")

        # 4. 在多个时间点采样
        for ms in [50, 100, 200, 500, 1000, 2000]:
            time.sleep(ms / 1000.0)
            cli.evaluate(f"() => window.__snapshot && window.__snapshot('after_{ms}ms')")

        # 5. 获取所有快照
        snapshots = cli.evaluate("() => window.__stateSnapshots || []")
        print(f"\n[共 {len(snapshots)} 个快照]:")
        for s in snapshots:
            print(f"  {s['label']:20s} | dom={s['domCheckedCount']:2d} | keys={s['treeRefCheckedKeys']} | setting={s['settingFromProp']} | dataLen={s['treeDataLength']} | treeKey={s['treeKey']}")

        # 6. 检查 store 内部状态
        print("\n[4] 当前 store 内部状态")
        store_state = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const store = vueComp.proxy.store;
                const nodesMap = store.nodesMap || {};
                return {
                    d_5_checked: nodesMap['d_5']?.checked,
                    d_5_indeterminate: nodesMap['d_5']?.indeterminate,
                    d_5_data_id: nodesMap['d_5']?.data?.id
                };
            }
        """)
        print(json.dumps(store_state, ensure_ascii=False, indent=2))

        # 7. 控制台日志
        logs = cli.evaluate("() => window.__logs || []")
        relevant = [l for l in logs if 'ObjectScope' in l or 'handleBoCheck' in l or 'emit' in l or 'Watcher' in l or 'load' in l]
        print(f"\n[5] 控制台日志 (相关: {len(relevant)})")
        for log in relevant[-15:]:
            print(f"  - {log[:250]}")

        cli.screenshot('after_snapshots.png')

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
