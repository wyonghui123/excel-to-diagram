"""
精确定位 ObjectScopeSection 组件并验证 @check 事件
通过 el-tree 的 __vueParentComponent.parent 链定位
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

        # 初始化 console 日志捕获
        cli.evaluate("""
            () => {
                window.__allLogs = [];
                const origLog = console.log;
                console.log = function(...args) {
                    window.__allLogs.push(args.map(a =>
                        typeof a === 'string' ? a :
                        typeof a === 'object' ? JSON.stringify(a) : String(a)
                    ).join(' '));
                    return origLog.apply(this, args);
                };
            }
        """)

        # 1. 验证 ObjectScopeSection 组件可访问
        print("\n" + "=" * 60)
        print("[1] 验证 ObjectScopeSection 组件 + 事件绑定")
        print("=" * 60)

        info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const vueComp = targetTree.__vueParentComponent;
                const objectScopeComp = vueComp?.parent;

                if (!objectScopeComp) return { error: 'ObjectScopeSection not found' };
                if (objectScopeComp.type?.__name !== 'ObjectScopeSection') {
                    return { error: 'Wrong component: ' + objectScopeComp.type?.__name };
                }

                const setupState = objectScopeComp.setupState || {};

                // 检查 el-tree 的 vnode 中的 onCheck prop
                const vnode = vueComp?.vnode;
                const props = vnode?.props || {};
                const onCheck = props.onCheck;

                let onCheckInfo = 'unknown';
                if (Array.isArray(onCheck)) {
                    onCheckInfo = {
                        isArray: true,
                        length: onCheck.length,
                        contains: onCheck.map(fn => {
                            const s = fn.toString();
                            return s.includes('handleBoCheck') ? 'handleBoCheck' :
                                   s.includes('checkedInfo') ? 'checkedInfo_consumer' :
                                   'other';
                        })
                    };
                } else if (typeof onCheck === 'function') {
                    const s = onCheck.toString();
                    onCheckInfo = {
                        isFunction: true,
                        contains: s.includes('handleBoCheck') ? 'handleBoCheck' : 'other',
                        first200: s.substring(0, 200)
                    };
                } else {
                    onCheckInfo = { type: typeof onCheck, value: String(onCheck).substring(0, 100) };
                }

                return {
                    componentName: objectScopeComp.type.__name,
                    uid: objectScopeComp.uid,
                    setupStateKeys: Object.keys(setupState),
                    handleBoCheckType: typeof setupState.handleBoCheck,
                    treeDataType: setupState.treeData?.__v_isRef ? 'ref' :
                                  Array.isArray(setupState.treeData) ? 'array' :
                                  typeof setupState.treeData,
                    treeDataLength: setupState.treeData?.__v_isRef ?
                        setupState.treeData.value?.length : setupState.treeData?.length,
                    treeRefExists: !!setupState.treeRef?.value,
                    onCheckInfo,
                    settingFromPropValue: setupState.settingFromProp?.value
                };
            }
        """)
        print(json.dumps(info, ensure_ascii=False, indent=2))

        # 2. 直接调用 handleBoCheck
        print("\n" + "=" * 60)
        print("[2] 直接调用 handleBoCheck")
        print("=" * 60)

        # 获取第一个 domain 节点信息
        node_info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const obj = vueComp.parent;
                const td = obj.setupState.treeData;
                const data = td?.__v_isRef ? td.value : td;
                if (!data || data.length === 0) return { error: 'No data' };
                const first = data[0];
                return {
                    id: first.id, originalId: first.originalId,
                    name: first.name, type: first.type
                };
            }
        """)
        print(f"[节点] {node_info}")

        call_result = cli.evaluate(f"""
            () => {{
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const obj = vueComp.parent;
                const setupState = obj.setupState;
                const handleBoCheck = setupState.handleBoCheck;

                const nodeData = {{
                    id: '{node_info['id']}',
                    originalId: {node_info['originalId']},
                    name: '{node_info['name']}',
                    type: '{node_info['type']}'
                }};
                const checkedInfo = {{
                    checkedKeys: ['{node_info['id']}'],
                    checkedNodes: [nodeData],
                    halfCheckedKeys: [],
                    halfCheckedNodes: []
                }};

                const before = {{
                    checkedBoIds: setupState.checkedBoIds?.__v_isRef ?
                        setupState.checkedBoIds.value : setupState.checkedBoIds,
                    settingFromProp: setupState.settingFromProp?.value
                }};

                try {{
                    handleBoCheck(nodeData, checkedInfo);
                    return {{
                        called: true,
                        before,
                        after: {{
                            checkedBoIds: setupState.checkedBoIds?.__v_isRef ?
                                setupState.checkedBoIds.value : setupState.checkedBoIds,
                            settingFromProp: setupState.settingFromProp?.value
                        }}
                    }};
                }} catch (e) {{
                    return {{ error: e.message }};
                }}
            }}
        """)
        print(f"[调用结果] {json.dumps(call_result, ensure_ascii=False, indent=2)}")

        time.sleep(0.5)

        # 3. 检查调用后状态
        print("\n[3] 等待 nextTick 后状态")
        after_state = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const obj = vueComp.parent;
                const setupState = obj.setupState;
                return {
                    checkedBoIds: setupState.checkedBoIds?.__v_isRef ?
                        setupState.checkedBoIds.value : setupState.checkedBoIds,
                    treeRefCheckedKeys: setupState.treeRef?.value?.getCheckedKeys?.() || [],
                    domCheckedCount: trees[0].querySelectorAll('.el-checkbox.is-checked').length,
                    settingFromProp: setupState.settingFromProp?.value
                };
            }
        """)
        print(json.dumps(after_state, ensure_ascii=False, indent=2))

        # 4. 模拟真实点击
        print("\n" + "=" * 60)
        print("[4] 模拟真实点击 checkbox")
        print("=" * 60)

        # 先清除所有已选状态
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const vueComp = trees[0].__vueParentComponent;
                const obj = vueComp.parent;
                const setupState = obj.setupState;
                setupState.treeRef?.value?.setCheckedKeys([]);
            }
        """)
        time.sleep(0.3)

        click_info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const checkboxes = targetTree.querySelectorAll('.el-checkbox');

                // 找到第一个可见的 checkbox
                let targetCheckbox = null;
                for (let i = 0; i < checkboxes.length; i++) {
                    const node = checkboxes[i].closest('.el-tree-node');
                    if (node) {
                        const rect = node.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            targetCheckbox = checkboxes[i];
                            break;
                        }
                    }
                }

                if (!targetCheckbox) return { error: 'No visible checkbox', totalCheckboxes: checkboxes.length };

                const node = targetCheckbox.closest('.el-tree-node');
                const label = node?.querySelector('.oss-node-label')?.textContent?.trim();
                const beforeClass = targetCheckbox.className;

                targetCheckbox.click();

                return {
                    clicked: true,
                    label,
                    beforeClass,
                    hasIsChecked: targetCheckbox.classList.contains('is-checked')
                };
            }
        """)
        print(f"[点击] {json.dumps(click_info, ensure_ascii=False, indent=2)}")

        time.sleep(1.5)

        # 5. 检查点击后状态
        print("\n[5] 真实点击后状态")
        click_state = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const vueComp = targetTree.__vueParentComponent;
                const obj = vueComp.parent;
                const setupState = obj.setupState;
                return {
                    domCheckedCount: targetTree.querySelectorAll('.el-checkbox.is-checked').length,
                    domCheckedLabels: Array.from(targetTree.querySelectorAll('.el-checkbox.is-checked')).map(cb => {
                        return cb.closest('.el-tree-node')?.querySelector('.oss-node-label')?.textContent?.trim();
                    }),
                    treeRefCheckedKeys: setupState.treeRef?.value?.getCheckedKeys?.() || [],
                    setupStateCheckedBoIds: setupState.checkedBoIds?.__v_isRef ?
                        setupState.checkedBoIds.value : setupState.checkedBoIds
                };
            }
        """)
        print(json.dumps(click_state, ensure_ascii=False, indent=2))

        # 6. 完整控制台日志
        print("\n[6] 控制台日志")
        all_logs = cli.evaluate("() => window.__allLogs || []")
        relevant = [l for l in all_logs if 'ObjectScope' in l or 'handleBoCheck' in l or 'emit' in l]
        print(f"[总日志] {len(all_logs)} 条")
        print(f"[相关日志] {len(relevant)} 条")
        for log in relevant[-10:]:
            print(f"  - {log[:200]}")

        # 截图
        cli.screenshot('deep_diag_final.png')

        # 7. 总结
        print("\n" + "=" * 60)
        print("[最终结论]")
        print("=" * 60)

        # 直接调用是否成功
        direct_ok = call_result.get('called') and len(after_state.get('checkedBoIds', [])) > 0
        real_click_ok = click_state.get('domCheckedCount', 0) > 0

        print(f"  [直接调用 handleBoCheck]: {'[OK] 成功' if direct_ok else '[FAIL] 失败'}")
        print(f"    - 调用前 checkedBoIds: {call_result.get('before', {}).get('checkedBoIds', [])}")
        print(f"    - 调用后 checkedBoIds: {after_state.get('checkedBoIds', [])}")

        print(f"  [真实点击 checkbox]: {'[OK] 成功' if real_click_ok else '[FAIL] 失败'}")
        print(f"    - 点击前 DOM checked: 0 (已清空)")
        print(f"    - 点击后 DOM checked: {click_state.get('domCheckedCount', 0)}")
        print(f"    - treeRef checkedKeys: {click_state.get('treeRefCheckedKeys', [])}")

        # onCheck 绑定
        on_check_ok = info.get('onCheckInfo', {})
        if isinstance(on_check_ok, dict):
            contains = on_check_ok.get('contains')
            print(f"  [onCheck 绑定]: {contains}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
