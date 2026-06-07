"""
深度检查 el-tree 结构和可用方法
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def test_tree_structure():
    cli = PlaywrightCLI()
    results = {"success": False, "steps": [], "errors": []}

    try:
        # 认证导航
        print("[Step 1] 认证并导航...")
        cli.authenticated_navigate(
            '/system/archdata?productId=1&versionId=1',
            wait_for_selector='.multi-object-management',
            timeout=20000
        )
        cli.wait_for_timeout(3000)

        # 等待 el-tree
        print("[Step 2] 等待 el-tree...")
        max_wait = 10
        for i in range(max_wait):
            tree_count = cli.evaluate("() => document.querySelectorAll('.el-tree').length")
            if tree_count > 0:
                print(f"[OK] 找到 {tree_count} 个 el-tree")
                break
            import time
            time.sleep(1)

        # 深度检查 el-tree
        print("\n[Step 3] 深度检查 el-tree...")

        tree_info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];

                const vueComp = tree.__vueParentComponent;
                const treeRef = vueComp?.proxy;

                // 获取 tree 的内部数据
                const store = vueComp?.store;
                const storeState = store?.state;

                // 获取节点信息
                const nodesMap = storeState?.nodes || {};
                const firstNodeKey = Object.keys(nodesMap)[0];
                const firstNode = nodesMap[firstNodeKey];

                return {
                    treeUid: vueComp?.uid,
                    treeRefKeys: treeRef ? Object.keys(treeRef).filter(k => !k.startsWith('$')) : [],
                    storeExists: !!store,
                    storeStateKeys: storeState ? Object.keys(storeState) : [],
                    nodesCount: Object.keys(nodesMap).length,
                    firstNodeKey: firstNodeKey,
                    firstNode: firstNode ? {
                        key: firstNode.key,
                        id: firstNode.id,
                        data: firstNode.data,
                        checked: firstNode.checked,
                        label: firstNode.label
                    } : null,

                    // el-tree 的 props
                    nodeKey: vueComp?.props?.nodeKey,
                    showCheckbox: vueComp?.props?.showCheckbox,
                    checkStrictly: vueComp?.props?.checkStrictly,

                    // DOM 节点信息
                    domNodeId: tree.querySelector('.el-tree-node')?.getAttribute('data-key') ||
                               tree.querySelector('.el-tree-node')?.id ||
                               'no-id',
                    domNodeAttr: (() => {
                        const node = tree.querySelector('.el-tree-node');
                        if (!node) return {};
                        const attrs = {};
                        for (const attr of node.attributes) {
                            attrs[attr.name] = attr.value;
                        }
                        return attrs;
                    })()
                };
            }
        """)
        print(f"[INFO] el-tree 信息:")
        for key, value in tree_info.items():
            print(f"  {key}: {value}")

        # 尝试使用 treeRef 的方法
        print("\n[Step 4] 尝试使用 treeRef 方法...")

        test_result = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;
                const treeRef = vueComp?.proxy;

                if (!treeRef) return { error: 'No treeRef' };

                // 获取 store 中的节点
                const store = vueComp?.store;
                const nodesMap = store?.state?.nodes || {};
                const firstKey = Object.keys(nodesMap)[0];

                console.log('First key from store:', firstKey);

                // 尝试各种方法
                const methods = {
                    hasSetChecked: !!treeRef.setChecked,
                    hasSetCheckedKeys: !!treeRef.setCheckedKeys,
                    hasGetCheckedKeys: !!treeRef.getCheckedKeys,
                    hasGetCheckedNodes: !!treeRef.getCheckedNodes,
                    hasGetNode: !!treeRef.getNode,
                    hasCheckNode: !!treeRef.checkNode
                };

                console.log('Available methods:', methods);

                // 获取已选中的 key
                if (treeRef.getCheckedKeys) {
                    const checkedKeys = treeRef.getCheckedKeys();
                    console.log('Checked keys before:', checkedKeys);
                }

                // 获取第一个节点的 key
                if (firstKey && treeRef.setChecked) {
                    console.log('Setting checked for key:', firstKey);
                    treeRef.setChecked(firstKey, true);

                    setTimeout(() => {
                        const checkedKeys = treeRef.getCheckedKeys();
                        console.log('Checked keys after:', checkedKeys);
                    }, 500);
                }

                return {
                    methods,
                    firstKey,
                    error: null
                };
            }
        """)
        print(f"[结果] {test_result}")

        import time
        time.sleep(1)

        # 检查最终状态
        final_state = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;
                const treeRef = vueComp?.proxy;

                const checkedKeys = treeRef?.getCheckedKeys?.() || [];
                const checkedNodes = treeRef?.getCheckedNodes?.() || [];
                const domChecked = tree.querySelectorAll('.el-checkbox.is-checked').length;

                return {
                    checkedKeys,
                    checkedNodesCount: checkedNodes.length,
                    domCheckedCount: domChecked,
                    checkedNodeLabels: checkedNodes.map(n => n.label || n.name).slice(0, 3)
                };
            }
        """)
        print(f"\n[最终状态] {final_state}")

        # 截图
        cli.screenshot('test_tree_structure.png')

        success = final_state.get('domCheckedCount', 0) > 0
        results["success"] = success
        results["final_state"] = final_state

        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"DOM checkedCount: {final_state.get('domCheckedCount', 0)}")
        print(f"Store checkedKeys: {final_state.get('checkedKeys', [])}")
        print(f"测试成功: {success}")
        print("=" * 60)

        return results

    except Exception as e:
        error_msg = f"测试异常: {str(e)}"
        results["errors"].append(error_msg)
        print(f"[ERROR] {error_msg}")
        import traceback
        traceback.print_exc()
        return results

    finally:
        cli.close()
        print("[INFO] 浏览器已关闭")


if __name__ == "__main__":
    print("=" * 60)
    print("深度检查 el-tree 结构")
    print("=" * 60)

    import json
    results = test_tree_structure()

    print("\n最终结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    sys.exit(0 if results["success"] else 1)
