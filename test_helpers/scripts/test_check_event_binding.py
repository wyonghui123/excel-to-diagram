"""
测试 el-tree @check 事件是否正确绑定
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def test_check_event():
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

        # 检查 el-tree 的事件绑定
        print("\n[Step 3] 检查 el-tree 事件绑定...")

        event_info = cli.evaluate("""
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

                if (objectScopeComp) {
                    result.componentFound = true;
                    result.componentUid = objectScopeComp.uid;

                    // 检查 emits
                    const emits = objectScopeComp.type?.emits || [];
                    result.emits = emits;

                    // 检查组件的 ctx
                    const ctx = objectScopeComp.ctx;
                    if (ctx) {
                        result.ctxKeys = Object.keys(ctx).filter(k => !k.startsWith('$'));
                    }

                    // 检查 setupState 中的 handleBoCheck
                    const setupState = objectScopeComp.setupState || {};
                    if (setupState.handleBoCheck) {
                        result.handleBoCheckExists = true;
                        result.handleBoCheckType = typeof setupState.handleBoCheck;
                    }
                } else {
                    result.componentFound = false;
                }

                // 检查 el-tree 组件的事件处理
                const tree = document.querySelectorAll('.el-tree')[0];
                const vueComp = tree.__vueParentComponent;

                // 检查 el-tree 实例的事件
                const treeRef = vueComp?.proxy;
                result.treeRefExists = !!treeRef;

                // 检查 el-tree 的 vnode
                const vnode = vueComp?.vnode;
                if (vnode) {
                    result.vnodeProps = vnode.props ? Object.keys(vnode.props) : [];
                    result.vnodeOn = vnode.props?.on || {};
                }

                return result;
            }
        """)
        print(f"[INFO] 事件绑定信息:")
        for key, value in event_info.items():
            print(f"  {key}: {value}")

        # 直接调用 handleBoCheck 测试
        print("\n[Step 4] 直接调用 handleBoCheck...")

        call_result = cli.evaluate("""
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

                if (objectScopeComp && objectScopeComp.setupState?.handleBoCheck) {
                    const handleBoCheck = objectScopeComp.setupState.handleBoCheck;

                    // 构造假的 checkedInfo
                    const fakeData = {
                        id: 'd_5',
                        originalId: 5,
                        name: 'TestDomainForDelete',
                        type: 'domain'
                    };

                    const fakeCheckedInfo = {
                        checkedKeys: ['d_5'],
                        checkedNodes: [fakeData],
                        halfCheckedKeys: [],
                        halfCheckedNodes: []
                    };

                    console.log('Calling handleBoCheck directly...');
                    try {
                        handleBoCheck(fakeData, fakeCheckedInfo);
                        result.called = true;
                        console.log('handleBoCheck called successfully');
                    } catch (e) {
                        result.error = e.message;
                        console.error('handleBoCheck error:', e);
                    }
                } else {
                    result.error = 'handleBoCheck not found';
                }

                return result;
            }
        """)
        print(f"[结果] {call_result}")

        import time
        time.sleep(1)

        # 检查结果
        final_state = cli.evaluate("""
            () => {
                // 检查 ObjectScopeSection 的 checkedBoIds
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
                    checkedBoIds: objectScopeComp?.setupState?.checkedBoIds?.value || []
                };
            }
        """)
        print(f"\n[最终状态] {final_state}")

        # 检查控制台日志
        console_logs = cli.evaluate("() => window.__consoleLogs || []")
        handle_logs = [l for l in console_logs if 'handleBoCheck' in str(l) or 'ObjectScope' in str(l)]
        print(f"\n[控制台日志] handleBoCheck 相关: {handle_logs[-5:]}")

        # 截图
        cli.screenshot('test_check_event.png')

        success = len(final_state.get('checkedBoIds', [])) > 0
        results["success"] = success
        results["final_state"] = final_state

        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"handleBoCheck 可调用: {call_result.get('called', False)}")
        print(f"checkedBoIds: {final_state.get('checkedBoIds', [])}")
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
    print("测试 @check 事件绑定")
    print("=" * 60)

    import json
    results = test_check_event()

    print("\n最终结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    sys.exit(0 if results["success"] else 1)
