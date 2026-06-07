"""
综合诊断脚本: 对象范围树 checkbox 不显示状态
通过四个维度诊断问题根因:
  1. el-tree 事件绑定是否正确 (onCheck prop)
  2. setupState 中的 handleBoCheck 函数是否可访问
  3. 直接调用 handleBoCheck 是否能更新状态
  4. 模拟真实点击是否能触发 @check 事件
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import time
import json


def find_object_scope_comp_js():
    """JS 代码片段: 递归查找 ObjectScopeSection 组件"""
    return """
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
    """


def diag_1_event_binding(cli):
    """诊断 1: 检查 el-tree 的事件绑定"""
    print("\n" + "=" * 60)
    print("诊断 1: el-tree 事件绑定检查")
    print("=" * 60)

    js = f"""
        () => {{
            const result = {{}};
            {find_object_scope_comp_js()}

            const app = document.querySelector('#app')?.__vue_app__;
            const objectScopeComp = findComponent(app?._instance);

            if (!objectScopeComp) {{
                result.error = 'ObjectScopeSection 组件未找到';
                return result;
            }}

            // 1.1 检查 setupState 中的 handleBoCheck
            const setupState = objectScopeComp.setupState || {{}};
            result.handleBoCheckExists = typeof setupState.handleBoCheck === 'function';
            result.handleBoCheckSource = setupState.handleBoCheck?.toString().substring(0, 100);

            // 1.2 检查 setupState 中的 treeRef
            result.treeRefExists = !!setupState.treeRef;
            result.treeRefHasValue = !!setupState.treeRef?.value;

            // 1.3 检查 setupState 中的 treeData
            result.treeDataType = Array.isArray(setupState.treeData) ? 'array' : typeof setupState.treeData;
            result.treeDataIsRef = setupState.treeData?.__v_isRef === true;
            if (setupState.treeData?.__v_isRef) {{
                result.treeDataValue = setupState.treeData.value?.length;
            }} else {{
                result.treeDataLength = setupState.treeData?.length;
            }}

            // 1.4 找到 el-tree 实例
            const trees = document.querySelectorAll('.el-tree');
            result.treeCount = trees.length;

            for (let i = 0; i < trees.length; i++) {{
                const tree = trees[i];
                const vueComp = tree.__vueParentComponent;
                if (vueComp?.parent?.uid === objectScopeComp.uid) {{
                    result.targetTreeIndex = i;
                    result.targetTreeUid = vueComp.uid;

                    // 检查 el-tree 的 vnode 中的 onCheck prop
                    const vnode = vueComp?.vnode;
                    if (vnode?.props) {{
                        const onCheck = vnode.props.onCheck;
                        result.onCheckExists = !!onCheck;
                        result.onCheckFns = Array.isArray(onCheck) ? onCheck.length : 1;

                        // 关键检查: onCheck 是否绑定了 handleBoCheck
                        if (Array.isArray(onCheck)) {{
                            result.onCheckBindings = onCheck.map(fn => {{
                                const fnStr = fn.toString().substring(0, 200);
                                return fnStr.includes('handleBoCheck') ? 'contains_handleBoCheck' : fnStr;
                            }});
                        }} else if (typeof onCheck === 'function') {{
                            const fnStr = onCheck.toString();
                            result.onCheckBinding = fnStr.includes('handleBoCheck') ? 'contains_handleBoCheck' : fnStr.substring(0, 200);
                        }}
                    }}
                    break;
                }}
            }}

            return result;
        }}
    """
    result = cli.evaluate(js)
    print(f"[结果] {json.dumps(result, ensure_ascii=False, indent=2)}")
    return result


def diag_2_call_handle_bo_check(cli):
    """诊断 2: 直接调用 handleBoCheck 测试"""
    print("\n" + "=" * 60)
    print("诊断 2: 直接调用 handleBoCheck")
    print("=" * 60)

    # 1. 找一个真实的 domain 节点
    js_get_node = f"""
        () => {{
            {find_object_scope_comp_js()}

            const app = document.querySelector('#app')?.__vue_app__;
            const objectScopeComp = findComponent(app?._instance);
            if (!objectScopeComp) return {{ error: 'Component not found' }};

            const treeData = objectScopeComp.setupState?.treeData;
            const data = treeData?.__v_isRef ? treeData.value : treeData;
            if (!data || data.length === 0) return {{ error: 'No tree data' }};

            // 找第一个 domain 节点
            const firstDomain = data[0];
            return {{
                nodeId: firstDomain.id,
                nodeOriginalId: firstDomain.originalId,
                nodeName: firstDomain.name,
                nodeType: firstDomain.type,
                childCount: firstDomain.children?.length || 0
            }};
        }}
    """
    node_info = cli.evaluate(js_get_node)
    print(f"[目标节点] {node_info}")

    if 'error' in node_info:
        return {"error": node_info['error']}

    node_id = node_info.get('nodeId')
    node_original_id = node_info.get('nodeOriginalId')
    node_name = node_info.get('nodeName')
    node_type = node_info.get('nodeType')

    # 2. 直接调用 handleBoCheck
    js_call = f"""
        () => {{
            {find_object_scope_comp_js()}

            const app = document.querySelector('#app')?.__vue_app__;
            const objectScopeComp = findComponent(app?._instance);
            if (!objectScopeComp) return {{ error: 'Component not found' }};

            const handleBoCheck = objectScopeComp.setupState?.handleBoCheck;
            if (!handleBoCheck) return {{ error: 'handleBoCheck not found' }};

            // 记录 before
            const beforeState = {{
                checkedBoIds: objectScopeComp.setupState.checkedBoIds?.__v_isRef ?
                    objectScopeComp.setupState.checkedBoIds.value : objectScopeComp.setupState.checkedBoIds
            }};

            // 构造调用参数
            const nodeData = {{
                id: '{node_id}',
                originalId: {node_original_id},
                name: '{node_name}',
                type: '{node_type}'
            }};
            const checkedInfo = {{
                checkedKeys: ['{node_id}'],
                checkedNodes: [nodeData],
                halfCheckedKeys: [],
                halfCheckedNodes: []
            }};

            try {{
                handleBoCheck(nodeData, checkedInfo);
                return {{
                    called: true,
                    before: beforeState,
                    after_call: {{
                        checkedBoIds: objectScopeComp.setupState.checkedBoIds?.__v_isRef ?
                            objectScopeComp.setupState.checkedBoIds.value : objectScopeComp.setupState.checkedBoIds,
                        settingFromProp: objectScopeComp.setupState.settingFromProp?.value
                    }}
                }};
            }} catch (e) {{
                return {{ error: e.message, stack: e.stack }};
            }}
        }}
    """
    result = cli.evaluate(js_call)
    print(f"[调用结果] {json.dumps(result, ensure_ascii=False, indent=2)}")

    time.sleep(0.5)

    # 3. 等待 nextTick 后再检查
    js_check = f"""
        () => {{
            {find_object_scope_comp_js()}

            const app = document.querySelector('#app')?.__vue_app__;
            const objectScopeComp = findComponent(app?._instance);
            if (!objectScopeComp) return {{ error: 'Component not found' }};

            return {{
                checkedBoIds: objectScopeComp.setupState.checkedBoIds?.__v_isRef ?
                    objectScopeComp.setupState.checkedBoIds.value : objectScopeComp.setupState.checkedBoIds,
                treeRefCheckedKeys: objectScopeComp.setupState.treeRef?.value?.getCheckedKeys?.() || []
            }};
        }}
    """
    after_state = cli.evaluate(js_check)
    print(f"[nextTick 后状态] {json.dumps(after_state, ensure_ascii=False, indent=2)}")

    return {"call_result": result, "after_state": after_state}


def diag_3_real_click(cli):
    """诊断 3: 模拟真实点击 checkbox，验证 @check 事件"""
    print("\n" + "=" * 60)
    print("诊断 3: 模拟真实点击 checkbox")
    print("=" * 60)

    # 1. 监听 console.log
    cli.evaluate("""
        () => {
            window.__clickLogs = [];
            const origLog = console.log;
            console.log = function(...args) {
                window.__clickLogs.push({
                    type: 'log',
                    args: args.map(a => typeof a === 'string' ? a : JSON.stringify(a))
                });
                return origLog.apply(this, args);
            };
        }
    """)

    # 2. 找一个真实的 checkbox 并点击
    click_js = f"""
        () => {{
            {find_object_scope_comp_js()}

            const app = document.querySelector('#app')?.__vue_app__;
            const objectScopeComp = findComponent(app?._instance);
            if (!objectScopeComp) return {{ error: 'Component not found' }};

            // 找到目标 el-tree
            const trees = document.querySelectorAll('.el-tree');
            let targetTree = null;
            let targetIndex = -1;
            for (let i = 0; i < trees.length; i++) {{
                if (trees[i].__vueParentComponent?.parent?.uid === objectScopeComp.uid) {{
                    targetTree = trees[i];
                    targetIndex = i;
                    break;
                }}
            }}

            if (!targetTree) return {{ error: 'Target tree not found' }};

            // 找到第一个可见的 checkbox
            const checkboxes = targetTree.querySelectorAll('.el-checkbox');
            if (checkboxes.length === 0) return {{ error: 'No checkboxes' }};

            // 找到第一个非全选区域的 checkbox
            let targetCheckbox = null;
            for (let i = 0; i < checkboxes.length; i++) {{
                const node = checkboxes[i].closest('.el-tree-node');
                if (node && !node.classList.contains('is-hidden')) {{
                    targetCheckbox = checkboxes[i];
                    break;
                }}
            }}

            if (!targetCheckbox) return {{ error: 'No visible checkbox' }};

            const node = targetCheckbox.closest('.el-tree-node');
            const label = node?.querySelector('.oss-node-label')?.textContent?.trim();
            const beforeClass = targetCheckbox.className;

            // 模拟用户点击
            targetCheckbox.click();

            return {{
                clicked: true,
                label: label?.substring(0, 30),
                beforeClass,
                treeIndex: targetIndex,
                treeNodeCount: checkboxes.length
            }};
        }}
    """
    click_result = cli.evaluate(click_js)
    print(f"[点击] {json.dumps(click_result, ensure_ascii=False, indent=2)}")

    time.sleep(1.5)

    # 3. 检查 DOM 状态和控制台
    state_js = f"""
        () => {{
            {find_object_scope_comp_js()}

            const app = document.querySelector('#app')?.__vue_app__;
            const objectScopeComp = findComponent(app?._instance);

            // 找到目标 el-tree
            const trees = document.querySelectorAll('.el-tree');
            let targetTree = null;
            for (let i = 0; i < trees.length; i++) {{
                if (trees[i].__vueParentComponent?.parent?.uid === objectScopeComp.uid) {{
                    targetTree = trees[i];
                    break;
                }}
            }}

            const checkedCount = targetTree ? targetTree.querySelectorAll('.el-checkbox.is-checked').length : 0;
            const treeRefCheckedKeys = objectScopeComp?.setupState?.treeRef?.value?.getCheckedKeys?.() || [];

            return {{
                domCheckedCount: checkedCount,
                treeRefCheckedKeys,
                setupStateCheckedBoIds: objectScopeComp?.setupState?.checkedBoIds?.__v_isRef ?
                    objectScopeComp.setupState.checkedBoIds.value : objectScopeComp?.setupState?.checkedBoIds,
                setupStateSettingFromProp: objectScopeComp?.setupState?.settingFromProp?.value,
            }};
        }}
    """
    state_result = cli.evaluate(state_js)
    print(f"[状态] {json.dumps(state_result, ensure_ascii=False, indent=2)}")

    # 4. 检查控制台日志
    logs = cli.evaluate("() => window.__clickLogs || []")
    relevant_logs = [l for l in logs if 'handleBoCheck' in str(l) or 'ObjectScope' in str(l)]
    print(f"\n[控制台日志] 相关日志: {len(relevant_logs)} 条")
    for log in relevant_logs[-5:]:
        print(f"  - {log}")

    return {
        "click_result": click_result,
        "state": state_result,
        "logs_count": len(relevant_logs)
    }


def diag_4_set_checked_directly(cli):
    """诊断 4: 直接用 treeRef.setChecked 验证 UI 更新"""
    print("\n" + "=" * 60)
    print("诊断 4: treeRef.setChecked 直接调用")
    print("=" * 60)

    set_js = f"""
        () => {{
            {find_object_scope_comp_js()}

            const app = document.querySelector('#app')?.__vue_app__;
            const objectScopeComp = findComponent(app?._instance);
            if (!objectScopeComp) return {{ error: 'Component not found' }};

            const treeData = objectScopeComp.setupState?.treeData;
            const data = treeData?.__v_isRef ? treeData.value : treeData;
            if (!data || data.length === 0) return {{ error: 'No tree data' }};

            const treeRef = objectScopeComp.setupState?.treeRef?.value;
            if (!treeRef) return {{ error: 'treeRef not found' }};

            // 找到第一个 domain 节点
            const firstNode = data[0];

            // 先清除所有选择
            treeRef.setCheckedKeys([]);

            // 设置第一个节点为 checked
            treeRef.setChecked(firstNode.id, true);

            return {{
                called: true,
                nodeId: firstNode.id,
                checkedKeys: treeRef.getCheckedKeys(),
                checkedNodes: treeRef.getCheckedNodes().map(n => ({{
                    id: n.id, name: n.name, type: n.type
                }}))
            }};
        }}
    """
    set_result = cli.evaluate(set_js)
    print(f"[setChecked 结果] {json.dumps(set_result, ensure_ascii=False, indent=2)}")

    time.sleep(0.5)

    # 检查 DOM
    dom_js = f"""
        () => {{
            {find_object_scope_comp_js()}

            const app = document.querySelector('#app')?.__vue_app__;
            const objectScopeComp = findComponent(app?._instance);

            const trees = document.querySelectorAll('.el-tree');
            let targetTree = null;
            for (let i = 0; i < trees.length; i++) {{
                if (trees[i].__vueParentComponent?.parent?.uid === objectScopeComp.uid) {{
                    targetTree = trees[i];
                    break;
                }}
            }}

            return {{
                domCheckedCount: targetTree ? targetTree.querySelectorAll('.el-checkbox.is-checked').length : 0,
                checkedLabels: targetTree ? Array.from(targetTree.querySelectorAll('.el-checkbox.is-checked')).map(cb => {{
                    return cb.closest('.el-tree-node')?.querySelector('.oss-node-label')?.textContent?.trim();
                }}) : []
            }};
        }}
    """
    dom_result = cli.evaluate(dom_js)
    print(f"[DOM 状态] {json.dumps(dom_result, ensure_ascii=False, indent=2)}")

    return {
        "set_result": set_result,
        "dom": dom_result
    }


def main():
    cli = PlaywrightCLI()
    try:
        # 1. 认证导航
        print("[Step 1] 认证并导航到 /system/archdata?productId=1&versionId=1")
        cli.authenticated_navigate(
            '/system/archdata?productId=1&versionId=1',
            wait_for_selector='.multi-object-management',
            timeout=20000
        )
        cli.wait_for_timeout(3000)

        # 2. 等待 el-tree 加载
        print("\n[Step 2] 等待 el-tree 加载...")
        for i in range(15):
            tree_count = cli.evaluate("() => document.querySelectorAll('.el-tree').length")
            if tree_count > 0:
                print(f"[OK] 找到 {tree_count} 个 el-tree")
                break
            time.sleep(1)
        else:
            print("[ERROR] 未找到 el-tree")
            return

        # 截图初始状态
        cli.screenshot('diag_initial.png')

        # 诊断 1: 事件绑定
        diag1 = diag_1_event_binding(cli)

        # 诊断 2: 直接调用 handleBoCheck
        diag2 = diag_2_call_handle_bo_check(cli)
        cli.screenshot('diag_after_call.png')

        # 诊断 3: 真实点击
        diag3 = diag_3_real_click(cli)
        cli.screenshot('diag_after_real_click.png')

        # 诊断 4: 直接 setChecked
        diag4 = diag_4_set_checked_directly(cli)
        cli.screenshot('diag_after_setChecked.png')

        # 总结
        print("\n" + "=" * 60)
        print("诊断总结")
        print("=" * 60)

        # 评估 1: 事件是否绑定
        print("\n[1] 事件绑定:")
        if diag1.get('onCheckBinding') == 'contains_handleBoCheck' or \
           any('contains_handleBoCheck' in str(b) for b in diag1.get('onCheckBindings', [])):
            print("  [OK] onCheck 事件已正确绑定到 handleBoCheck")
        else:
            print(f"  [FAIL] onCheck 事件绑定异常: {diag1.get('onCheckBinding') or diag1.get('onCheckBindings')}")
            print(f"  handleBoCheck 存在: {diag1.get('handleBoCheckExists')}")

        # 评估 2: 直接调用
        print("\n[2] 直接调用 handleBoCheck:")
        if diag2.get('call_result', {}).get('called'):
            checked = diag2.get('after_state', {}).get('checkedBoIds', [])
            print(f"  [OK] handleBoCheck 可调用，checkedBoIds = {checked}")
        else:
            print(f"  [FAIL] {diag2.get('call_result', {}).get('error')}")

        # 评估 3: 真实点击
        print("\n[3] 真实点击 checkbox:")
        clicked = diag3.get('click_result', {}).get('clicked')
        if clicked:
            dom_checked = diag3.get('state', {}).get('domCheckedCount', 0)
            logs = diag3.get('logs_count', 0)
            if logs > 0:
                print(f"  [OK] 点击触发 handleBoCheck, DOM checkedCount = {dom_checked}")
            else:
                print(f"  [FAIL] 点击未触发 handleBoCheck (logs={logs}), DOM checkedCount = {dom_checked}")
        else:
            print(f"  [FAIL] 点击失败: {diag3.get('click_result', {}).get('error')}")

        # 评估 4: setChecked
        print("\n[4] treeRef.setChecked:")
        if diag4.get('set_result', {}).get('called'):
            dom_checked = diag4.get('dom', {}).get('domCheckedCount', 0)
            print(f"  [OK] setChecked 可用, DOM checkedCount = {dom_checked}")
            print(f"  checkedLabels = {diag4.get('dom', {}).get('checkedLabels', [])}")
        else:
            print(f"  [FAIL] {diag4.get('set_result', {}).get('error')}")

    except Exception as e:
        print(f"\n[ERROR] 异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()
        print("\n[INFO] 浏览器已关闭")


if __name__ == "__main__":
    main()
