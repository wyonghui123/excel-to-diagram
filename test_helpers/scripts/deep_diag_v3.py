"""
深入排查: 为什么 handleBoCheck 触发后 DOM 不更新
关键检查:
  1. setupState.treeRef.value 是否真的是 el-tree 实例
  2. el-tree 的内部 store.nodesMap 状态
  3. 真实点击 vs setChecked 的差异
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

        # 1. 检查 treeRef 的真实结构
        print("\n[1] 检查 setupState.treeRef 结构")
        result = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const obj = vueComp.parent;
                const setupState = obj.setupState;
                const treeRef = setupState.treeRef;

                return {
                    treeRefType: typeof treeRef,
                    treeRefIsRef: treeRef?.__v_isRef === true,
                    treeRefIsShallow: treeRef?.__v_isShallow === true,
                    treeRefValueType: typeof treeRef?.value,
                    treeRefValueIsNull: treeRef?.value === null,
                    treeRefValueIsUndefined: treeRef?.value === undefined,
                    treeRefValueKeys: treeRef?.value ? Object.keys(treeRef.value).slice(0, 20) : null,
                    treeRefValueHasGetCheckedKeys: typeof treeRef?.value?.getCheckedKeys,
                    treeRefValueHasSetChecked: typeof treeRef?.value?.setChecked,
                    treeRefValueHasSetCheckedKeys: typeof treeRef?.value?.setCheckedKeys
                };
            }
        """)
        print(json.dumps(result, ensure_ascii=False, indent=2))

        # 2. 检查 el-tree 内部 store 状态
        print("\n[2] 检查 el-tree 内部 store.nodesMap")
        result2 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const elTreeRef = vueComp?.proxy;
                const store = elTreeRef?.store;

                if (!store) return { error: 'No store' };

                const nodesMap = store.nodesMap || {};
                const nodeKeys = Object.keys(nodesMap);
                const sampleNodes = nodeKeys.slice(0, 5).map(key => {
                    const node = nodesMap[key];
                    return {
                        key,
                        id: node.data?.id,
                        name: node.data?.name,
                        type: node.data?.type,
                        checked: node.checked,
                        indeterminate: node.indeterminate
                    };
                });

                return {
                    nodeCount: nodeKeys.length,
                    sampleNodes,
                    storeKeys: Object.keys(store)
                };
            }
        """)
        print(json.dumps(result2, ensure_ascii=False, indent=2))

        # 3. 直接用 el-tree 的 setChecked 验证
        print("\n[3] el-tree.setChecked 直接调用")
        result3 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const elTreeRef = vueComp?.proxy;
                const store = elTreeRef?.store;

                if (!store) return { error: 'No store' };
                const nodesMap = store.nodesMap || {};
                const firstKey = Object.keys(nodesMap)[0];
                if (!firstKey) return { error: 'No node' };

                elTreeRef.setChecked(firstKey, true);

                return {
                    called: true,
                    nodeKey: firstKey,
                    nodeData: nodesMap[firstKey].data,
                    afterChecked: nodesMap[firstKey].checked,
                    getCheckedKeys: elTreeRef.getCheckedKeys(),
                    getCheckedNodes: elTreeRef.getCheckedNodes().map(n => ({
                        id: n.id, name: n.name, type: n.type
                    }))
                };
            }
        """)
        print(json.dumps(result3, ensure_ascii=False, indent=2))

        time.sleep(0.5)

        # 4. 检查 DOM
        print("\n[4] setChecked 后 DOM 状态")
        result4 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const checkedBoxes = targetTree.querySelectorAll('.el-checkbox.is-checked');
                return {
                    domCheckedCount: checkedBoxes.length,
                    labels: Array.from(checkedBoxes).map(cb => {
                        return cb.closest('.el-tree-node')?.querySelector('.oss-node-label')?.textContent?.trim();
                    })
                };
            }
        """)
        print(json.dumps(result4, ensure_ascii=False, indent=2))

        # 5. 现在测试真实点击 - 用 dispatchEvent 模拟
        print("\n[5] 真实点击 (dispatchEvent)")
        result5 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];

                // 先清空
                const vueComp = targetTree.__vueParentComponent;
                vueComp.proxy.setCheckedKeys([]);

                // 找到第一个 checkbox
                const checkboxes = targetTree.querySelectorAll('.el-checkbox');
                let targetCheckbox = null;
                for (let i = 0; i < checkboxes.length; i++) {
                    const node = checkboxes[i].closest('.el-tree-node');
                    const rect = node?.getBoundingClientRect();
                    if (rect && rect.width > 0 && rect.height > 0) {
                        targetCheckbox = checkboxes[i];
                        break;
                    }
                }

                if (!targetCheckbox) return { error: 'No checkbox' };

                // 获取 checkbox 内的 input
                const input = targetCheckbox.querySelector('input[type="checkbox"]');
                const label = targetCheckbox.closest('.el-tree-node')?.querySelector('.oss-node-label')?.textContent?.trim();

                // 派发 click 事件 (更接近用户行为)
                if (input) {
                    input.click();
                } else {
                    targetCheckbox.click();
                }

                return {
                    clicked: true,
                    label,
                    hasInput: !!input,
                    checkboxClass: targetCheckbox.className
                };
            }
        """)
        print(json.dumps(result5, ensure_ascii=False, indent=2))

        time.sleep(1)

        # 6. 检查点击后状态
        print("\n[6] 真实点击后状态")
        result6 = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const vueComp = targetTree.__vueParentComponent;
                const obj = vueComp.parent;
                const setupState = obj.setupState;
                const elTreeRef = vueComp.proxy;

                return {
                    domCheckedCount: targetTree.querySelectorAll('.el-checkbox.is-checked').length,
                    domCheckedLabels: Array.from(targetTree.querySelectorAll('.el-checkbox.is-checked')).map(cb => {
                        return cb.closest('.el-tree-node')?.querySelector('.oss-node-label')?.textContent?.trim();
                    }),
                    treeRefCheckedKeys: elTreeRef.getCheckedKeys(),
                    treeRefCheckedNodes: elTreeRef.getCheckedNodes().map(n => ({
                        id: n.id, name: n.name, type: n.type
                    })),
                    setupStateCheckedBoIds: setupState.checkedBoIds?.__v_isRef ?
                        setupState.checkedBoIds.value : setupState.checkedBoIds
                };
            }
        """)
        print(json.dumps(result6, ensure_ascii=False, indent=2))

        cli.screenshot('deep_diag_v3_final.png')

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
