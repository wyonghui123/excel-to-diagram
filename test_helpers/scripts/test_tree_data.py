"""
检查 el-tree 的 data 属性和组件状态
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def test_tree_data():
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

        # 检查 el-tree 的 data
        print("\n[Step 3] 检查 el-tree data...")

        data_info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;

                // 获取 props.data
                const propsData = vueComp?.props?.data || [];
                const setupState = vueComp?.setupState || {};

                // 获取 treeRef
                const treeRef = vueComp?.proxy;
                const treeData = treeRef?.data || [];

                // 检查 DOM 中的节点
                const domNodes = tree.querySelectorAll('.el-tree-node');
                const domNodeKeys = Array.from(domNodes).map(n => n.getAttribute('data-key'));

                return {
                    propsDataLength: propsData.length,
                    propsDataFirst: propsData[0] || null,
                    setupStateKeys: Object.keys(setupState).filter(k => !k.startsWith('__')),
                    treeDataLength: treeData.length,
                    treeDataFirst: treeData[0] || null,
                    domNodesCount: domNodes.length,
                    domNodeKeys: domNodeKeys.slice(0, 5)
                };
            }
        """)
        print(f"[INFO] Data 信息:")
        for key, value in data_info.items():
            print(f"  {key}: {value}")

        # 检查 ObjectScopeSection 组件的 data
        print("\n[Step 4] 检查 ObjectScopeSection 组件...")

        component_info = cli.evaluate("""
            () => {
                const result = {};

                // 递归查找组件
                const findComponent = (comp, depth = 0) => {
                    if (depth > 30 || !comp) return null;
                    const name = comp.type?.__name || comp.type?.name || '';
                    if (name === 'ObjectScopeSection') return comp;
                    if (comp.subTree) {
                        const r = findComponent(comp.subTree, depth + 1);
                        if (r) return r;
                    }
                    for (const child of comp.componentTree || []) {
                        const r = findComponent(child, depth + 1);
                        if (r) return r;
                    }
                    return null;
                };

                const app = document.querySelector('#app')?.__vue_app__;
                const objectScopeComp = findComponent(app?._instance);

                if (objectScopeComp) {
                    result.componentFound = true;
                    result.componentUid = objectScopeComp.uid;

                    // 检查 setupState
                    const setupState = objectScopeComp.setupState || {};
                    result.setupStateKeys = Object.keys(setupState);

                    // 检查 treeData
                    if (setupState.treeData) {
                        result.treeDataLength = setupState.treeData.value?.length || 0;
                        result.treeDataFirst = setupState.treeData.value?.[0] || null;
                    }

                    // 检查 treeRef
                    if (setupState.treeRef) {
                        result.treeRefExists = true;
                        result.treeRefValue = setupState.treeRef.value ? 'exists' : 'null';
                    }

                    // 检查 checkedBoIds
                    if (setupState.checkedBoIds) {
                        result.checkedBoIds = setupState.checkedBoIds.value;
                    }

                    // 检查 loading
                    if (setupState.loading !== undefined) {
                        result.loading = setupState.loading.value;
                    }
                } else {
                    result.componentFound = false;
                }

                return result;
            }
        """)
        print(f"[INFO] ObjectScopeSection 组件:")
        for key, value in component_info.items():
            print(f"  {key}: {value}")

        # 尝试使用 treeRef.setChecked 直接设置
        print("\n[Step 5] 尝试使用 setChecked 设置节点...")

        # 使用 DOM 中的 data-key
        set_result = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;
                const treeRef = vueComp?.proxy;

                // 获取 DOM 中的第一个节点 key
                const domNode = tree.querySelector('.el-tree-node');
                const dataKey = domNode?.getAttribute('data-key');
                console.log('DOM data-key:', dataKey);

                // 获取节点的 id
                const nodeId = domNode?.querySelector('.oss-node-label')?.getAttribute('title') ||
                              domNode?.querySelector('[class*="id"]')?.textContent;
                console.log('Node id from DOM:', nodeId);

                // 尝试使用 data-key 作为 key
                if (dataKey && treeRef?.setChecked) {
                    console.log('Calling setChecked with dataKey:', dataKey);
                    treeRef.setChecked(dataKey, true);

                    // 等待状态更新
                    setTimeout(() => {
                        const checkedKeys = treeRef.getCheckedKeys();
                        const domChecked = tree.querySelectorAll('.el-checkbox.is-checked').length;
                        console.log('After setChecked - checkedKeys:', checkedKeys);
                        console.log('After setChecked - domChecked:', domChecked);
                    }, 500);
                }

                return { dataKey, treeRefExists: !!treeRef };
            }
        """)
        print(f"[结果] {set_result}")

        import time
        time.sleep(1)

        # 检查最终状态
        final_state = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;
                const treeRef = vueComp?.proxy;

                return {
                    checkedKeys: treeRef?.getCheckedKeys?.() || [],
                    domCheckedCount: tree.querySelectorAll('.el-checkbox.is-checked').length,
                    firstNodeChecked: tree.querySelector('.el-tree-node .el-checkbox.is-checked') !== null
                };
            }
        """)
        print(f"\n[最终状态] {final_state}")

        # 截图
        cli.screenshot('test_tree_data.png')

        success = final_state.get('domCheckedCount', 0) > 0
        results["success"] = success
        results["final_state"] = final_state

        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"DOM checkedCount: {final_state.get('domCheckedCount', 0)}")
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
    print("检查 el-tree data")
    print("=" * 60)

    import json
    results = test_tree_data()

    print("\n最终结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    sys.exit(0 if results["success"] else 1)
