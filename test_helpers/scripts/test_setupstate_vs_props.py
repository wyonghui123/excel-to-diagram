"""
比较 setupState 和 props 中的 treeData
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def test_setupstate_vs_props():
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

        # 比较 setupState 和 props 中的 treeData
        print("\n[Step 3] 比较 setupState 和 props...")

        compare_result = cli.evaluate("""
            () => {
                const result = {};

                // 获取 el-tree 的 props.data
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;

                // props.data
                result.propsData = vueComp?.props?.data || [];
                result.propsDataLength = result.propsData.length;
                result.propsDataFirst = result.propsData[0] || null;

                // el-tree 的 treeRef.data
                const treeRef = vueComp?.proxy;
                result.treeRefDataLength = treeRef?.data?.length || 0;
                result.treeRefDataFirst = treeRef?.data?.[0] || null;

                // parent 的 setupState.treeData
                const parent = vueComp?.parent;
                const setupState = parent?.setupState || {};

                result.setupStateTreeDataExists = !!setupState.treeData;
                result.setupStateTreeDataValue = setupState.treeData?.value || null;
                result.setupStateTreeDataLength = setupState.treeData?.value?.length || 0;

                // 检查 DOM 中的节点
                result.domNodesCount = tree.querySelectorAll('.el-tree-node').length;

                return result;
            }
        """)
        print(f"[INFO] 比较结果:")
        for key, value in compare_result.items():
            if isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")

        # 检查 setupState.treeData 的具体值
        print("\n[Step 4] 检查 setupState.treeData...")

        setupstate_result = cli.evaluate("""
            () => {
                const result = {};

                // 获取 el-tree
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;
                const parent = vueComp?.parent;

                // 获取 setupState 中的 treeData
                const setupState = parent?.setupState || {};
                const treeDataRef = setupState.treeData;

                result.treeDataRefType = typeof treeDataRef;
                result.treeDataRefValue = treeDataRef ? JSON.stringify(treeDataRef) : 'null';

                if (treeDataRef) {
                    // 检查 ref 结构
                    result.treeDataRefKeys = Object.keys(treeDataRef);
                    result.treeDataRefValueKeys = Object.keys(treeDataRef.value || {});
                    result.treeDataValue = treeDataRef.value;
                    result.treeDataValueType = typeof treeDataRef.value;
                    result.treeDataValueIsArray = Array.isArray(treeDataRef.value);
                    result.treeDataValueLength = treeDataRef.value?.length;
                }

                return result;
            }
        """)
        print(f"[INFO] setupState.treeData 详情:")
        for key, value in setupstate_result.items():
            print(f"  {key}: {value}")

        # 检查 setupState 和 el-tree 组件的差异
        print("\n[Step 5] 深入检查组件...")

        deep_result = cli.evaluate("""
            () => {
                const result = {};

                // 获取 el-tree
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;
                const parent = vueComp?.parent;

                // parent 是组件实例，检查它的 vnode
                if (parent) {
                    const parentVnode = parent.vnode;
                    result.parentVnodeExists = !!parentVnode;

                    // parent 的 vnode 指向 el-tree
                    if (parentVnode?.el === tree) {
                        result.parentVnodePointsToTree = true;
                    }

                    // 检查 parent 的 props
                    result.parentProps = parent.props || {};
                }

                // 检查 el-tree 的 vnode
                const treeVnode = vueComp?.vnode;
                result.treeVnodeProps = treeVnode?.props || {};

                // 比较 setupState.treeData 和 el-tree props.data
                const setupState = parent?.setupState || {};
                const treeDataRef = setupState.treeData;
                const treeDataValue = treeDataRef?.value;
                const elTreeData = vueComp?.props?.data;

                result.treeDataValue === elTreeData = treeDataValue === elTreeData;
                result.treeDataValue == elTreeData = treeDataValue == elTreeData;

                return result;
            }
        """)
        print(f"[INFO] 深度检查: {deep_result}")

        # 截图
        cli.screenshot('test_setupstate_vs_props.png')

        success = compare_result.get('domNodesCount', 0) > 0
        results["success"] = success
        results["final_state"] = compare_result

        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"DOM 节点数: {compare_result.get('domNodesCount', 0)}")
        print(f"propsData 长度: {compare_result.get('propsDataLength', 0)}")
        print(f"treeRefData 长度: {compare_result.get('treeRefDataLength', 0)}")
        print(f"setupState.treeData 长度: {compare_result.get('setupStateTreeDataLength', 0)}")
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
    print("比较 setupState 和 props 中的 treeData")
    print("=" * 60)

    import json
    results = test_setupstate_vs_props()

    print("\n最终结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    sys.exit(0 if results["success"] else 1)
