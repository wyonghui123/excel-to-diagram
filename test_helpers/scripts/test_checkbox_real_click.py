"""
架构数据管理页面 checkbox 真实交互测试
模拟用户实际点击 checkbox，观察 @check 事件
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def test_checkbox_real_interaction():
    cli = PlaywrightCLI()
    results = {"success": False, "steps": [], "errors": []}

    try:
        # Step 1: 认证导航
        print("[Step 1] 认证并导航...")
        cli.authenticated_navigate(
            '/system/archdata?productId=1&versionId=1',
            wait_for_selector='.multi-object-management',
            timeout=20000
        )
        print("[OK] 页面加载成功")
        cli.wait_for_timeout(2000)

        # Step 2: 等待 el-tree 渲染
        print("[Step 2] 等待 el-tree 渲染...")
        max_wait = 10
        waited = 0
        while waited < max_wait:
            tree_count = cli.evaluate("() => document.querySelectorAll('.el-tree').length")
            if tree_count > 0:
                print(f"[OK] 找到 {tree_count} 个 el-tree")
                break
            import time
            time.sleep(1)
            waited += 1

        # Step 3: 记录初始状态
        print("[Step 3] 记录初始状态...")
        initial_count = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                let count = 0;
                trees.forEach(t => { count += t.querySelectorAll('.is-checked').length; });
                return count;
            }
        """)
        print(f"[INFO] 初始 checkedCount: {initial_count}")

        # Step 4: 真实用户交互 - 点击 checkbox 元素
        print("[Step 4] 执行真实用户交互 - 点击 checkbox...")

        # 方法: 找到 el-tree-node 的第一个 checkbox，模拟真实用户点击
        click_result = cli.evaluate("""
            () => {
                const result = { clicked: false, method: '', error: '' };

                // 查找 el-tree
                const tree = document.querySelector('.el-tree');
                if (!tree) {
                    result.error = 'No el-tree found';
                    return result;
                }

                // 查找第一个带 checkbox 的 tree-node
                const treeNodes = tree.querySelectorAll('.el-tree-node');
                console.log('Total tree nodes:', treeNodes.length);

                // 查找 node-content 下的 checkbox
                const firstNodeWithCheckbox = Array.from(treeNodes).find(node => {
                    return node.querySelector('.el-tree-node__content .el-checkbox');
                });

                if (!firstNodeWithCheckbox) {
                    result.error = 'No checkbox found in tree nodes';
                    return result;
                }

                const checkbox = firstNodeWithCheckbox.querySelector('.el-tree-node__content .el-checkbox');
                const nodeContent = firstNodeWithCheckbox.querySelector('.el-tree-node__content');

                // 记录节点信息
                result.nodeId = firstNodeWithCheckbox.getAttribute('node-id');
                result.nodeLabel = firstNodeWithCheckbox.querySelector('.oss-node-label, .el-tree-node__label')?.textContent?.trim() || 'unknown';

                // 获取 el-tree 的 Vue 实例
                const treeComponent = tree.__vueParentComponent;
                result.treeUid = treeComponent?.uid;
                result.hasProxy = !!treeComponent?.proxy;
                result.proxyKeys = treeComponent?.proxy ? Object.keys(treeComponent.proxy).slice(0, 10) : [];

                // 尝试获取组件暴露的方法
                result.exposedKeys = treeComponent?.exposed ? Object.keys(treeComponent.exposed) : [];

                // 模拟用户点击 node-content（el-tree 的标准交互方式）
                // 这应该触发 el-tree 的 check 事件
                console.log('=== Simulating user click on node-content ===');
                console.log('Node ID:', result.nodeId);
                console.log('Node Label:', result.nodeLabel);

                // 方法1: 点击整个 node-content
                if (nodeContent) {
                    nodeContent.click();
                    result.clicked = true;
                    result.method = 'click-node-content';
                    console.log('Clicked node-content successfully');
                }

                return result;
            }
        """)

        print(f"[INFO] 点击结果: {click_result}")

        # Step 5: 等待事件处理完成
        print("[Step 5] 等待事件处理...")
        cli.wait_for_timeout(2000)

        # Step 6: 检查选中状态
        print("[Step 6] 检查选中状态...")
        after_click_count = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                let count = 0;
                let checkedNodes = [];
                trees.forEach(t => {
                    const checked = t.querySelectorAll('.is-checked');
                    count += checked.length;
                    checked.forEach(n => {
                        const label = n.closest('.el-tree-node')?.querySelector('.oss-node-label, .el-tree-node__label')?.textContent?.trim() || '';
                        checkedNodes.push(label);
                    });
                });
                return { count, checkedNodes };
            }
        """)
        print(f"[INFO] 点击后 checkedCount: {after_click_count}")

        # Step 7: 检查控制台日志
        print("[Step 7] 检查控制台日志...")
        console_logs = cli.evaluate("""
            () => {
                const logs = window.__consoleLogs || [];
                const relevantLogs = logs.filter(l =>
                    l.includes('ObjectScopeSection') ||
                    l.includes('handleBoCheck') ||
                    l.includes('emitTypedScopeChange') ||
                    l.includes('el-tree') ||
                    l.includes('scope-change')
                );
                return relevantLogs.slice(-20);
            }
        """)
        print(f"[INFO] 控制台日志: {console_logs}")

        # Step 8: 检查 store
        print("[Step 8] 检查 Pinia store...")
        store_info = cli.evaluate("""
            () => {
                const app = document.querySelector('#app')?.__vue_app__;
                if (!app) return { error: 'No Vue app' };

                const pinia = app.config.globalProperties.$pinia;
                const stores = {};

                if (pinia && pinia._s) {
                    pinia._s.forEach((store, name) => {
                        stores[name] = {
                            checkedBoIds: store.checkedBoIds,
                            scopeIds: store.scopeIds,
                            hasBoCrud: name === 'boCrud'
                        };
                    });
                }

                return stores;
            }
        """)
        print(f"[INFO] Store 信息: {store_info}")

        # Step 9: 截图
        cli.screenshot('test_checkbox_real_click.png')
        print("[OK] 截图: test_checkbox_real_click.png")

        # Step 10: 判断结果
        success = after_click_count.get('count', 0) > initial_count

        results["success"] = success
        results["final_state"] = {
            "initial_count": initial_count,
            "after_click_count": after_click_count.get('count', 0),
            "checkedNodes": after_click_count.get('checkedNodes', []),
            "click_result": click_result,
            "console_logs": console_logs
        }

        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"初始选中数: {initial_count}")
        print(f"点击后选中数: {after_click_count.get('count', 0)}")
        print(f"Console 日志数量: {len(console_logs)}")
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
    print("真实用户交互测试: 点击 checkbox")
    print("=" * 60)

    import json
    results = test_checkbox_real_interaction()

    print("\n最终结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    sys.exit(0 if results["success"] else 1)
