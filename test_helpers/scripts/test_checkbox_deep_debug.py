"""
深度调试 el-tree checkbox 事件绑定
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def test_checkbox_deep_debug():
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
        cli.wait_for_timeout(2000)

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

        # 深度检查 el-tree 配置
        print("[Step 3] 深度检查 el-tree...")

        tree_config = cli.evaluate("""
            () => {
                const tree = document.querySelector('.el-tree');
                if (!tree) return { error: 'No tree' };

                const vueComp = tree.__vueParentComponent;
                if (!vueComp) return { error: 'No Vue component' };

                // 检查 Vue 组件实例
                const instance = vueComp.proxy || vueComp;

                // 检查类型
                const type = vueComp.type;
                const typeName = type?.__name || type?.name || 'unknown';

                // 检查 props
                const props = vueComp.props || {};

                // 检查事件绑定
                const events = vueComp.emits || [];

                // 检查 el-tree 的内部状态
                const store = vueComp.store;
                const storeState = store?.state;

                return {
                    typeName,
                    hasCheckStrictly: props.checkStrictly !== undefined,
                    checkStrictly: props.checkStrictly,
                    showCheckbox: props.showCheckbox,
                    nodeKey: props.nodeKey,
                    storeNodes: storeState?.nodes || {},
                    storeCheckedKeys: storeState?.checkedKeys || [],
                    instanceKeys: Object.keys(instance).slice(0, 20),
                    emitsOptions: events
                };
            }
        """)
        print(f"[INFO] el-tree 配置: {tree_config}")

        # 检查所有 checkbox 和它们的事件
        print("[Step 4] 检查 checkbox 元素...")

        checkbox_info = cli.evaluate("""
            () => {
                const result = { checkboxes: [], error: '' };

                const tree = document.querySelector('.el-tree');
                if (!tree) {
                    result.error = 'No tree';
                    return result;
                }

                // 查找所有 tree-node
                const nodes = tree.querySelectorAll('.el-tree-node');
                console.log('Total nodes:', nodes.length);

                nodes.forEach((node, i) => {
                    if (i < 5) {  // 只记录前5个
                        const content = node.querySelector('.el-tree-node__content');
                        const checkbox = content?.querySelector('.el-checkbox');
                        const label = node.querySelector('.oss-node-label, .el-tree-node__label')?.textContent?.trim();

                        result.checkboxes.push({
                            index: i,
                            label: label?.substring(0, 30),
                            hasCheckbox: !!checkbox,
                            checkboxClass: checkbox?.className,
                            contentClass: content?.className
                        });
                    }
                });

                return result;
            }
        """)
        print(f"[INFO] Checkbox 信息: {checkbox_info}")

        # 尝试点击 checkbox（不是 node-content）
        print("[Step 5] 点击 checkbox 元素...")

        # 先展开一个节点（如果需要）
        expand_result = cli.evaluate("""
            () => {
                const tree = document.querySelector('.el-tree');
                if (!tree) return { error: 'No tree' };

                const vueComp = tree.__vueParentComponent;
                const instance = vueComp?.proxy || vueComp;

                // 尝试调用 tree 的 expand/collapse 方法
                if (instance && instance.expandNode) {
                    // 获取第一个节点
                    const firstNode = tree.querySelector('.el-tree-node');
                    const nodeId = firstNode?.getAttribute('node-id');

                    if (nodeId) {
                        instance.expandNode(nodeId);
                        return { expanded: true, nodeId };
                    }
                }

                return { expanded: false };
            }
        """)
        print(f"[INFO] 展开节点: {expand_result}")

        cli.wait_for_timeout(1000)

        # 点击 checkbox
        print("[Step 6] 点击 checkbox...")

        click_result = cli.evaluate("""
            () => {
                const tree = document.querySelector('.el-tree');
                if (!tree) return { error: 'No tree' };

                // 尝试找到第一个可见的 checkbox
                const checkboxes = tree.querySelectorAll('.el-tree-node .el-checkbox');
                console.log('Checkboxes found:', checkboxes.length);

                if (checkboxes.length === 0) {
                    return { error: 'No checkboxes found' };
                }

                const checkbox = checkboxes[0];
                const node = checkbox.closest('.el-tree-node');
                const label = node?.querySelector('.oss-node-label, .el-tree-node__label')?.textContent?.trim();

                // 记录点击前的状态
                const beforeState = {
                    checkboxChecked: checkbox.classList.contains('is-checked'),
                    label: label?.substring(0, 30)
                };

                console.log('Before click - checked:', beforeState.checkboxChecked, 'label:', beforeState.label);

                // 点击 checkbox
                checkbox.click();

                return {
                    clicked: true,
                    label: beforeState.label,
                    beforeChecked: beforeState.checkboxChecked
                };
            }
        """)
        print(f"[INFO] 点击 checkbox: {click_result}")

        # 等待并检查状态
        cli.wait_for_timeout(2000)

        # 检查选中状态
        print("[Step 7] 检查选中状态...")
        after_state = cli.evaluate("""
            () => {
                const tree = document.querySelector('.el-tree');
                if (!tree) return { error: 'No tree' };

                const checkboxes = tree.querySelectorAll('.el-tree-node .el-checkbox');
                let checkedCount = 0;
                const checkedLabels = [];

                checkboxes.forEach(cb => {
                    if (cb.classList.contains('is-checked')) {
                        checkedCount++;
                        const label = cb.closest('.el-tree-node')?.querySelector('.oss-node-label, .el-tree-node__label')?.textContent?.trim();
                        checkedLabels.push(label?.substring(0, 30));
                    }
                });

                // 检查 Vue store 中的状态
                const vueComp = tree.__vueParentComponent;
                const storeState = vueComp?.store?.state;

                return {
                    checkedCount,
                    checkedLabels,
                    storeCheckedKeys: storeState?.checkedKeys || [],
                    storeCheckedNodes: storeState?.checkedNodes?.length || 0
                };
            }
        """)
        print(f"[INFO] 点击后状态: {after_state}")

        # 检查控制台日志
        console_logs = cli.evaluate("() => window.__consoleLogs || []")
        relevant_logs = [l for l in console_logs if 'ObjectScopeSection' in str(l) or 'handleBoCheck' in str(l) or 'el-tree' in str(l).lower()]
        print(f"[INFO] 相关控制台日志: {relevant_logs[-10:]}")

        # 截图
        cli.screenshot('test_deep_debug.png')

        success = after_state.get('checkedCount', 0) > 0
        results["success"] = success
        results["final_state"] = after_state

        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"点击后选中数: {after_state.get('checkedCount', 0)}")
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
    print("深度调试 el-tree checkbox 事件")
    print("=" * 60)

    import json
    results = test_checkbox_deep_debug()

    print("\n最终结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    sys.exit(0 if results["success"] else 1)
