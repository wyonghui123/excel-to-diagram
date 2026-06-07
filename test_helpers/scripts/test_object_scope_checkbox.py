"""
精确测试 ObjectScopeSection 的 checkbox 功能
只点击 ObjectScopeSection 组件中的 el-tree
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def test_object_scope_checkbox():
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

        # 查找 MultiObjectManagementPage 组件和它的 el-tree
        print("[Step 3] 查找 MultiObjectManagementPage 组件...")

        component_info = cli.evaluate("""
            () => {
                const result = { trees: [], objectScopeTree: null, allComponents: [] };

                // 递归查找组件
                const findComponent = (comp, depth = 0, path = '') => {
                    if (depth > 30 || !comp) return null;

                    const type = comp.type;
                    const name = type && type.__name ? type.__name : (type && type.name ? type.name : '');

                    // 记录找到的组件
                    if (['MultiObjectManagementPage', 'MultiObjectPage', 'ObjectScopeSection', 'RelationScopeTree'].includes(name)) {
                        result.allComponents.push({ name, depth, path, uid: comp.uid });
                    }

                    if (name === 'MultiObjectManagementPage' || name === 'MultiObjectPage') {
                        return comp;
                    }

                    if (comp.subTree) {
                        const r = findComponent(comp.subTree, depth + 1, path + '>subTree');
                        if (r) return r;
                    }

                    const children = comp.componentTree || [];
                    for (const child of children) {
                        const r = findComponent(child, depth + 1, path + '>child');
                        if (r) return r;
                    }

                    return null;
                };

                const app = document.querySelector('#app')?.__vue_app__;
                if (!app) {
                    result.error = 'No Vue app';
                    return result;
                }

                const root = app._instance;
                const pageComp = findComponent(root);

                if (pageComp) {
                    result.pageFound = true;
                    result.pageUid = pageComp.uid;
                    result.exposedKeys = pageComp.exposed ? Object.keys(pageComp.exposed) : [];
                    result.setupKeys = pageComp.setupState ? Object.keys(pageComp.setupState) : [];

                    // 查找页面中的所有 el-tree
                    const allTrees = document.querySelectorAll('.el-tree');
                    result.trees = Array.from(allTrees).map((tree, i) => {
                        const vueComp = tree.__vueParentComponent;
                        return {
                            index: i,
                            uid: vueComp?.uid,
                            parentUid: vueComp?.parent?.uid,
                            parentName: vueComp?.parent?.type?.__name || vueComp?.parent?.type?.name || 'unknown'
                        };
                    });
                } else {
                    result.pageFound = false;
                }

                return result;
            }
        """)
        print(f"[INFO] 组件信息: {component_info}")

        # 找到 ObjectScopeSection 的 el-tree
        print("[Step 4] 找到目标 el-tree...")

        target_tree = cli.evaluate("""
            () => {
                const result = { found: false, treeIndex: -1 };

                // 递归查找组件
                const findComponent = (comp, depth = 0, parent = null) => {
                    if (depth > 30 || !comp) return null;
                    const type = comp.type;
                    const name = type && type.__name ? type.__name : (type && type.name ? type.name : '');

                    if (name === 'ObjectScopeSection') {
                        return { comp, parentName: parent?.type?.__name || parent?.type?.name || 'unknown' };
                    }

                    if (comp.subTree) {
                        const r = findComponent(comp.subTree, depth + 1, comp);
                        if (r) return r;
                    }

                    const children = comp.componentTree || [];
                    for (const child of children) {
                        const r = findComponent(child, depth + 1, comp);
                        if (r) return r;
                    }
                    return null;
                };

                const app = document.querySelector('#app')?.__vue_app__;
                if (!app) return result;

                const objectScopeInfo = findComponent(app._instance);
                if (!objectScopeInfo) return result;

                const objectScopeComp = objectScopeInfo.comp;
                console.log('Found ObjectScopeSection, uid:', objectScopeComp.uid);

                // 查找 ObjectScopeSection 的 el-tree
                const allTrees = document.querySelectorAll('.el-tree');
                for (let i = 0; i < allTrees.length; i++) {
                    const tree = allTrees[i];
                    const vueComp = tree.__vueParentComponent;
                    console.log('Tree', i, 'parent uid:', vueComp?.parent?.uid, 'target uid:', objectScopeComp.uid);

                    if (vueComp?.parent?.uid === objectScopeComp.uid) {
                        result.found = true;
                        result.treeIndex = i;
                        result.treeUid = vueComp.uid;
                        result.parentUid = objectScopeComp.uid;
                        console.log('Found target tree at index', i);
                        break;
                    }
                }

                return result;
            }
        """)
        print(f"[INFO] 目标 el-tree: {target_tree}")

        if not target_tree.get('found'):
            print("[ERROR] 未找到 ObjectScopeSection 的 el-tree")
            results["errors"].append("未找到 ObjectScopeSection 的 el-tree")
            return results

        # 点击目标 el-tree 的 checkbox
        print("[Step 5] 点击目标 el-tree 的 checkbox...")

        # 先获取初始状态
        initial_count = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[?];
                if (!targetTree) return 0;
                return targetTree.querySelectorAll('.is-checked').length;
            }
        """.replace("?", str(target_tree.get('treeIndex', 0))))
        print(f"[INFO] 初始 checkedCount: {initial_count}")

        # 点击 checkbox
        click_result = cli.evaluate(f"""
            () => {{
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[{target_tree.get('treeIndex', 0)}];
                if (!targetTree) return {{ error: 'No tree' }};

                const checkbox = targetTree.querySelector('.el-tree-node .el-checkbox');
                if (!checkbox) return {{ error: 'No checkbox' }};

                const node = checkbox.closest('.el-tree-node');
                const label = node?.querySelector('.oss-node-label')?.textContent?.trim();

                console.log('=== Clicking checkbox ===');
                console.log('Label:', label);
                console.log('Before class:', checkbox.className);

                checkbox.click();

                setTimeout(() => {{
                    console.log('After class:', checkbox.className);
                    console.log('Has is-checked:', checkbox.classList.contains('is-checked'));
                }}, 100);

                return {{
                    clicked: true,
                    label: label?.substring(0, 30)
                }};
            }}
        """)
        print(f"[INFO] 点击结果: {click_result}")

        # 等待事件处理
        cli.wait_for_timeout(2000)

        # 检查选中状态
        print("[Step 6] 检查选中状态...")

        after_state = cli.evaluate(f"""
            () => {{
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[{target_tree.get('treeIndex', 0)}];
                if (!targetTree) return {{ error: 'No tree' }};

                const checkboxes = targetTree.querySelectorAll('.el-checkbox.is-checked');
                const checkedLabels = [];

                checkboxes.forEach(cb => {{
                    const label = cb.closest('.el-tree-node')?.querySelector('.oss-node-label')?.textContent?.trim();
                    checkedLabels.push(label?.substring(0, 30));
                }});

                return {{
                    checkedCount: checkboxes.length,
                    checkedLabels
                }};
            }}
        """)
        print(f"[INFO] 点击后状态: {after_state}")

        # 检查控制台日志
        console_logs = cli.evaluate("() => window.__consoleLogs || []")
        relevant_logs = [l for l in console_logs if 'ObjectScopeSection' in str(l) or 'handleBoCheck' in str(l)]
        print(f"[INFO] 相关控制台日志数量: {len(relevant_logs)}")
        if relevant_logs:
            print(f"[INFO] 日志内容: {relevant_logs[-5:]}")

        # 截图
        cli.screenshot('test_object_scope_checkbox.png')

        # 判断结果
        success = after_state.get('checkedCount', 0) > initial_count
        results["success"] = success
        results["final_state"] = {
            "target_tree_index": target_tree.get('treeIndex'),
            "initial_count": initial_count,
            "after_count": after_state.get('checkedCount', 0),
            "checked_labels": after_state.get('checkedLabels', []),
            "console_logs_count": len(relevant_logs)
        }

        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"目标 el-tree 索引: {target_tree.get('treeIndex')}")
        print(f"初始选中数: {initial_count}")
        print(f"点击后选中数: {after_state.get('checkedCount', 0)}")
        print(f"Console 日志: {len(relevant_logs)}")
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
    print("精确测试 ObjectScopeSection checkbox")
    print("=" * 60)

    import json
    results = test_object_scope_checkbox()

    print("\n最终结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    sys.exit(0 if results["success"] else 1)
