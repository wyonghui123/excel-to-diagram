"""
模拟 check 事件测试
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def test_simulate_check_event():
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

        # 模拟 check 事件
        print("\n[Step 3] 模拟 check 事件...")

        simulate_result = cli.evaluate("""
            () => {
                const result = {};

                // 查找 ObjectScopeSection 组件
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
                    result.error = 'Component not found';
                    return result;
                }

                // 获取 handleBoCheck 函数
                const handleBoCheck = objectScopeComp.setupState?.handleBoCheck;
                if (!handleBoCheck) {
                    result.error = 'handleBoCheck not found';
                    return result;
                }

                // 构造 check 事件参数
                const nodeData = {
                    id: 'd_5',
                    originalId: 5,
                    name: 'TestDomainForDelete',
                    type: 'domain',
                    code: 'TDD'
                };

                const checkedInfo = {
                    checkedKeys: ['d_5'],
                    checkedNodes: [nodeData],
                    halfCheckedKeys: [],
                    halfCheckedNodes: []
                };

                console.log('=== Before calling handleBoCheck ===');
                console.log('Node data:', nodeData);
                console.log('Checked info:', checkedInfo);

                // 调用 handleBoCheck
                try {
                    handleBoCheck(nodeData, checkedInfo);
                    result.called = true;
                    console.log('handleBoCheck called successfully');
                } catch (e) {
                    result.error = e.message;
                    console.error('handleBoCheck error:', e);
                }

                // 等待 nextTick
                setTimeout(() => {
                    console.log('=== After handleBoCheck ===');
                    const checkedBoIds = objectScopeComp.setupState?.checkedBoIds?.value;
                    console.log('checkedBoIds:', checkedBoIds);
                }, 100);

                return result;
            }
        """)
        print(f"[结果] {simulate_result}")

        import time
        time.sleep(0.5)

        # 检查结果
        print("\n[Step 4] 检查结果...")

        final_state = cli.evaluate("""
            () => {
                // 查找 ObjectScopeSection 组件
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

                return {
                    componentFound: !!objectScopeComp,
                    checkedBoIds: objectScopeComp?.setupState?.checkedBoIds?.value || [],
                    checkedBoIdsLength: objectScopeComp?.setupState?.checkedBoIds?.value?.length || 0
                };
            }
        """)
        print(f"[INFO] {final_state}")

        # 检查控制台日志
        console_logs = cli.evaluate("() => window.__consoleLogs || []")
        handle_logs = [l for l in console_logs if 'ObjectScope' in str(l) or 'handleBoCheck' in str(l)]
        print(f"\n[控制台日志] 相关日志: {handle_logs}")

        # 使用 treeRef.setChecked 来验证
        print("\n[Step 5] 使用 treeRef.setChecked 验证...")

        set_result = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;
                const treeRef = vueComp?.proxy;

                // 使用 treeRef.setChecked
                if (treeRef?.setChecked) {
                    treeRef.setChecked('d_5', true);
                    return { called: true };
                }

                return { error: 'setChecked not found' };
            }
        """)
        print(f"[结果] {set_result}")

        import time
        time.sleep(0.5)

        after_set = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const tree = trees[0];
                const vueComp = tree.__vueParentComponent;
                const treeRef = vueComp?.proxy;

                return {
                    checkedKeys: treeRef?.getCheckedKeys?.() || [],
                    domCheckedCount: tree.querySelectorAll('.el-checkbox.is-checked').length
                };
            }
        """)
        print(f"[setChecked 后] {after_set}")

        # 检查控制台日志
        console_logs2 = cli.evaluate("() => window.__consoleLogs || []")
        handle_logs2 = [l for l in console_logs2 if 'ObjectScope' in str(l) or 'handleBoCheck' in str(l)]
        print(f"\n[控制台日志] 最新日志: {handle_logs2}")

        # 截图
        cli.screenshot('test_simulate_event.png')

        # 判断结果
        success = final_state.get('checkedBoIdsLength', 0) > 0 or after_set.get('domCheckedCount', 0) > 0
        results["success"] = success
        results["final_state"] = {
            "simulate_success": simulate_result.get('called', False),
            "checkedBoIds": final_state.get('checkedBoIds', []),
            "setChecked_domCheckedCount": after_set.get('domCheckedCount', 0)
        }

        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"直接调用 handleBoCheck: {simulate_result}")
        print(f"checkedBoIds: {final_state.get('checkedBoIds', [])}")
        print(f"setChecked DOM checkedCount: {after_set.get('domCheckedCount', 0)}")
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
    print("模拟 check 事件")
    print("=" * 60)

    import json
    results = test_simulate_check_event()

    print("\n最终结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    sys.exit(0 if results["success"] else 1)
