"""
详细检查 el-tree 的 parent 组件
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def test_parent_component():
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

        # 详细检查 el-tree 的 parent
        print("\n[Step 3] 详细检查 el-tree 的 parent...")

        parent_info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;
                const parent = vueComp?.parent;

                const result = {
                    treeUid: vueComp?.uid,
                    treeType: vueComp?.type?.__name || vueComp?.type?.name,
                    parentUid: parent?.uid,
                    parentType: parent?.type?.__name || parent?.type?.name,
                    parentKeys: parent ? Object.keys(parent).filter(k => !k.startsWith('$')).slice(0, 20) : [],

                    // 检查 parent 的 setupState
                    parentHasSetupState: !!parent?.setupState,
                    parentSetupStateKeys: parent?.setupState ? Object.keys(parent.setupState) : [],

                    // 检查 parent 的 type
                    parentTypeProps: parent?.type ? Object.keys(parent.type).filter(k => !k.startsWith('$')) : []
                };

                // 获取 parent 的完整信息
                if (parent) {
                    // 检查 setupState 中的关键属性
                    const setupState = parent.setupState || {};

                    result.keyValues = {
                        treeRef: setupState.treeRef ? 'exists' : 'missing',
                        treeData: setupState.treeData ? 'exists' : 'missing',
                        treeDataValue: setupState.treeData?.value ? 'has value' : 'no value',
                        loading: setupState.loading?.value,
                        settingFromProp: setupState.settingFromProp?.value,
                        checkedBoIds: setupState.checkedBoIds?.value
                    };

                    // 检查 type 中的 setup 函数
                    if (parent.type?.setup) {
                        result.hasSetup = true;
                    }
                }

                return result;
            }
        """)
        print(f"[INFO] Parent 信息:")
        for key, value in parent_info.items():
            if isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")

        # 尝试从 DOM 结构找到正确的组件
        print("\n[Step 4] 从 DOM 结构查找组件...")

        dom_tree_info = cli.evaluate("""
            () => {
                const result = { containers: [] };

                // 查找包含 el-tree 的容器
                const trees = document.querySelectorAll('.el-tree');
                trees.forEach((tree, i) => {
                    // 向上查找容器
                    let container = tree.parentElement;
                    let depth = 0;
                    while (container && depth < 10) {
                        const className = container.className || '';
                        const id = container.id || '';

                        if (className.includes('oss-tree') ||
                            className.includes('object-scope') ||
                            id.includes('object-scope') ||
                            id.includes('oss-tree')) {
                            result.containers.push({
                                treeIndex: i,
                                className,
                                id,
                                childCount: container.children?.length
                            });
                            break;
                        }
                        container = container.parentElement;
                        depth++;
                    }
                });

                // 查找 oss-tree 或 object-scope-section
                const ossTree = document.querySelector('.oss-tree, .object-scope-section');
                result.ossTreeExists = !!ossTree;
                result.ossTreeClass = ossTree?.className || '';

                return result;
            }
        """)
        print(f"[INFO] DOM 结构: {dom_tree_info}")

        # 截图
        cli.screenshot('test_parent_component.png')

        success = parent_info.get('keyValues', {}).get('treeData') == 'exists'
        results["success"] = success
        results["final_state"] = parent_info

        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"parentName: {parent_info.get('parentType')}")
        print(f"treeData: {parent_info.get('keyValues', {}).get('treeData')}")
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
    print("详细检查 parent 组件")
    print("=" * 60)

    import json
    results = test_parent_component()

    print("\n最终结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    sys.exit(0 if results["success"] else 1)
