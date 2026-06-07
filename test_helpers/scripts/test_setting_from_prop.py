"""
检查 settingFromProp 值
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def test_setting_from_prop():
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

        # 多次尝试查找组件
        print("\n[Step 3] 多次尝试查找组件...")

        for i in range(5):
            import time
            time.sleep(0.5)

            find_result = cli.evaluate("""
                () => {
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

                    if (!objectScopeComp) {
                        return { found: false };
                    }

                    const setupState = objectScopeComp.setupState || {};

                    return {
                        found: true,
                        uid: objectScopeComp.uid,
                        settingFromProp: setupState.settingFromProp?.value,
                        checkedBoIds: setupState.checkedBoIds?.value || [],
                        treeDataLength: setupState.treeData?.value?.length || 0
                    };
                }
            """)
            print(f"[尝试 {i+1}] {find_result}")

        # 检查 treeRef 和 settingFromProp
        print("\n[Step 4] 检查 treeRef 和 settingFromProp...")

        tree_ref_info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;
                const parent = vueComp?.parent;

                // 获取父组件的 setupState
                const setupState = parent?.setupState || {};

                // 检查 settingFromProp
                const settingFromProp = setupState.settingFromProp;
                const settingFromPropValue = settingFromProp?.value;

                return {
                    parentName: parent?.type?.__name || parent?.type?.name || 'unknown',
                    parentUid: parent?.uid,
                    settingFromPropExists: !!settingFromProp,
                    settingFromPropValue: settingFromPropValue,
                    settingFromPropType: settingFromProp ? typeof settingFromProp.value : null,
                    checkedBoIds: setupState.checkedBoIds?.value || [],
                    treeDataLength: setupState.treeData?.value?.length || 0
                };
            }
        """)
        print(f"[INFO] {tree_ref_info}")

        # 直接设置 settingFromProp = false，然后调用 handleBoCheck
        print("\n[Step 5] 设置 settingFromProp = false，然后调用 handleBoCheck...")

        call_result = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;
                const parent = vueComp?.parent;

                if (!parent) return { error: 'No parent' };

                const setupState = parent.setupState || {};

                // 保存原始值
                const originalValue = setupState.settingFromProp?.value;

                // 设置为 false
                if (setupState.settingFromProp) {
                    setupState.settingFromProp.value = false;
                    console.log('settingFromProp set to false');
                }

                // 获取 handleBoCheck
                const handleBoCheck = setupState.handleBoCheck;
                if (!handleBoCheck) {
                    return { error: 'handleBoCheck not found' };
                }

                // 构造参数
                const nodeData = {
                    id: 'd_5',
                    originalId: 5,
                    name: 'TestDomainForDelete',
                    type: 'domain'
                };

                const checkedInfo = {
                    checkedKeys: ['d_5'],
                    checkedNodes: [nodeData],
                    halfCheckedKeys: [],
                    halfCheckedNodes: []
                };

                console.log('Calling handleBoCheck...');

                // 调用 handleBoCheck
                try {
                    handleBoCheck(nodeData, checkedInfo);
                    console.log('handleBoCheck called successfully');
                } catch (e) {
                    console.error('handleBoCheck error:', e);
                    return { error: e.message };
                }

                // 恢复原始值
                if (setupState.settingFromProp) {
                    setupState.settingFromProp.value = originalValue;
                }

                return { called: true };
            }
        """)
        print(f"[结果] {call_result}")

        import time
        time.sleep(0.5)

        # 检查 checkedBoIds
        after_check = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;
                const parent = vueComp?.parent;

                const setupState = parent?.setupState || {};

                return {
                    checkedBoIds: setupState.checkedBoIds?.value || [],
                    checkedBoIdsLength: setupState.checkedBoIds?.value?.length || 0
                };
            }
        """)
        print(f"\n[handleBoCheck 后] checkedBoIds: {after_check}")

        # 检查控制台日志
        console_logs = cli.evaluate("() => window.__consoleLogs || []")
        handle_logs = [l for l in console_logs if 'ObjectScope' in str(l) or 'handleBoCheck' in str(l)]
        print(f"\n[控制台日志] {handle_logs}")

        # 截图
        cli.screenshot('test_setting_from_prop.png')

        success = after_check.get('checkedBoIdsLength', 0) > 0
        results["success"] = success
        results["final_state"] = after_check

        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"settingFromProp: {tree_ref_info.get('settingFromPropValue')}")
        print(f"checkedBoIds: {after_check.get('checkedBoIds', [])}")
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
    print("检查 settingFromProp")
    print("=" * 60)

    import json
    results = test_setting_from_prop()

    print("\n最终结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    sys.exit(0 if results["success"] else 1)
