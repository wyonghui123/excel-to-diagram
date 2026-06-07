"""
检查 el-tree 的 onCheck prop
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def test_oncheck_prop():
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

        # 检查 el-tree 的 vnode 和 props
        print("\n[Step 3] 检查 el-tree vnode 和 props...")

        vnode_info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;

                const vnode = vueComp?.vnode;
                const props = vnode?.props || {};

                // 检查 onCheck
                const onCheck = props['onCheck'];
                const onCheckOn = vnode?.on?.['check'];

                // 检查 vnode 的其他属性
                return {
                    vnodeType: vnode?.type?.name || vnode?.type,
                    propsKeys: Object.keys(props),
                    onCheck: onCheck ? 'exists' : 'missing',
                    onCheckType: onCheck ? typeof onCheck : null,
                    onCheckOn: onCheckOn ? 'exists' : 'missing',
                    vnodeOnKeys: vnode?.on ? Object.keys(vnode.on) : [],

                    // 尝试从 props 获取更多信息
                    onCheckFromProps: onCheck ? onCheck.toString().substring(0, 100) : null
                };
            }
        """)
        print(f"[INFO] VNode 信息:")
        for key, value in vnode_info.items():
            print(f"  {key}: {value}")

        # 尝试获取组件树的更多信息
        print("\n[Step 4] 检查组件树...")

        tree_info = cli.evaluate("""
            () => {
                const result = { components: [] };

                // 递归遍历组件树
                const traverse = (comp, depth = 0, path = '') => {
                    if (depth > 20 || !comp) return;

                    const name = comp.type?.__name || comp.type?.name || 'unknown';
                    const uid = comp.uid;

                    // 只记录相关组件
                    if (['ObjectScopeSection', 'ElTree', 'ElTreeNode', 'MultiObjectManagementPage'].includes(name)) {
                        result.components.push({
                            name,
                            depth,
                            path,
                            uid
                        });
                    }

                    if (comp.subTree) {
                        traverse(comp.subTree, depth + 1, path + '>subTree');
                    }

                    for (const child of comp.componentTree || []) {
                        traverse(child, depth + 1, path + '>child');
                    }
                };

                const app = document.querySelector('#app')?.__vue_app__;
                traverse(app?._instance, 0, 'root');

                return result;
            }
        """)
        print(f"[INFO] 组件树:")
        for comp in tree_info.get('components', []):
            print(f"  {comp}")

        # 检查 el-tree 父组件
        print("\n[Step 5] 检查 el-tree 父组件...")

        parent_info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;
                const parent = vueComp?.parent;

                if (!parent) return { error: 'No parent' };

                return {
                    parentUid: parent.uid,
                    parentName: parent.type?.__name || parent.type?.name || 'unknown',
                    parentSetupStateKeys: parent.setupState ? Object.keys(parent.setupState) : []
                };
            }
        """)
        print(f"[INFO] 父组件信息:")
        for key, value in parent_info.items():
            print(f"  {key}: {value}")

        # 截图
        cli.screenshot('test_oncheck_prop.png')

        # 判断结果
        success = vnode_info.get('onCheck') == 'exists'
        results["success"] = success
        results["final_state"] = vnode_info

        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"onCheck prop 存在: {vnode_info.get('onCheck')}")
        print(f"onCheck 类型: {vnode_info.get('onCheckType')}")
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
    print("检查 onCheck prop")
    print("=" * 60)

    import json
    results = test_oncheck_prop()

    print("\n最终结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    sys.exit(0 if results["success"] else 1)
