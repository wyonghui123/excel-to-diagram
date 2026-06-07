"""
架构数据管理页面 checkbox 测试
使用 PlaywrightCLI - 每个 Agent 独立浏览器进程天然隔离
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def test_archdata_checkbox():
    cli = PlaywrightCLI()
    results = {"success": False, "steps": [], "errors": []}

    try:
        # Step 1: 获取产品和版本列表
        print("[Step 1] 获取产品和版本信息...")

        import urllib.request
        import json

        # 获取产品列表
        try:
            req = urllib.request.Request('http://localhost:3010/api/v1/products?pageSize=10')
            with urllib.request.urlopen(req, timeout=10) as response:
                products_data = json.loads(response.read().decode('utf-8'))
                if products_data.get('success') and products_data.get('data', {}).get('list'):
                    first_product = products_data['data']['list'][0]
                    product_id = first_product['id']
                    product_name = first_product.get('name', 'Unknown')
                    print(f"[INFO] 第一个产品: {product_name} (ID: {product_id})")
                else:
                    product_id = None
                    print(f"[WARN] 无法获取产品列表: {products_data}")
        except Exception as e:
            product_id = None
            print(f"[WARN] 获取产品失败: {e}")

        # 获取版本列表
        version_id = None
        if product_id:
            try:
                req = urllib.request.Request(f'http://localhost:3010/api/v1/products/{product_id}/versions?pageSize=10')
                with urllib.request.urlopen(req, timeout=10) as response:
                    versions_data = json.loads(response.read().decode('utf-8'))
                    if versions_data.get('success') and versions_data.get('data', {}).get('list'):
                        first_version = versions_data['data']['list'][0]
                        version_id = first_version['id']
                        version_name = first_version.get('name', 'Unknown')
                        print(f"[INFO] 第一个版本: {version_name} (ID: {version_id})")
                    else:
                        print(f"[WARN] 无法获取版本列表: {versions_data}")
            except Exception as e:
                print(f"[WARN] 获取版本失败: {e}")

        # Step 1.5: 认证导航（使用版本1.0）
        print("[Step 1.5] 认证并导航到架构数据管理...")

        # 使用产品ID=1, 版本ID=1
        target_path = '/system/archdata?productId=1&versionId=1'
        print(f"[INFO] 带参数导航: {target_path}")

        cli.authenticated_navigate(
            target_path,
            wait_for_selector='.multi-object-management',
            timeout=20000
        )
        print("[OK] 页面加载成功")

        # 等待数据加载
        cli.wait_for_timeout(2000)

        # Step 1.6: 使用 Vue 组件方法选择产品和版本
        print("[Step 1.6] 使用 Vue 组件选择产品和版本...")

        select_result = cli.evaluate("""
            () => {
                const results = { success: false, message: '' };

                // 查找 MultiObjectManagement 组件
                const app = document.querySelector('#app')?.__vue_app__;
                if (!app) {
                    results.message = 'No Vue app';
                    return results;
                }

                // 递归查找组件
                const findComponent = (comp, depth = 0) => {
                    if (depth > 20 || !comp) return null;
                    const type = comp.type;
                    const name = type && type.__name ? type.__name : (type && type.name ? type.name : '');

                    if (name === 'MultiObjectManagement' || name === 'MultiObjectPage') {
                        return comp;
                    }

                    if (comp.subTree) {
                        const result = findComponent(comp.subTree, depth + 1);
                        if (result) return result;
                    }

                    const children = comp.componentTree || [];
                    for (const child of children) {
                        const result = findComponent(child, depth + 1);
                        if (result) return result;
                    }

                    return null;
                };

                const root = app._instance;
                const multiObjComp = findComponent(root);

                if (multiObjComp && multiObjComp.exposed) {
                    const exposed = multiObjComp.exposed;
                    if (exposed.selectProduct) {
                        exposed.selectProduct(1);
                        results.calledSelectProduct = true;
                    }
                    if (exposed.selectVersion) {
                        setTimeout(() => {
                            exposed.selectVersion(1);
                            results.calledSelectVersion = true;
                        }, 500);
                    }
                    results.success = true;
                    results.componentFound = true;
                    results.exposedKeys = Object.keys(exposed);
                } else if (multiObjComp) {
                    results.componentFound = true;
                    results.uid = multiObjComp.uid;
                    results.hasExposed = !!multiObjComp.exposed;
                } else {
                    results.message = 'Component not found';
                }

                return results;
            }
        """)
        print(f"[INFO] Vue 组件选择结果: {select_result}")

        # 等待数据加载
        cli.wait_for_timeout(3000)

        # Step 2: 截图初始状态
        cli.screenshot('test_archdata_01_initial.png')
        print("[OK] 截图: test_archdata_01_initial.png")

        # Step 3: 检查页面元素
        print("[Step 2] 检查页面元素...")

        page_info = cli.evaluate("""
            () => {
                const main = document.querySelector('main');
                const multiObj = document.querySelector('.multi-object-management');
                const elTrees = document.querySelectorAll('.el-tree');
                const versionSelector = document.querySelector('.el-select');

                return {
                    hasMain: !!main,
                    hasMultiObjectMgmt: !!multiObj,
                    treeCount: elTrees.length,
                    hasVersionSelector: !!versionSelector,
                    url: window.location.href
                };
            }
        """)
        print(f"[INFO] 页面信息: {page_info}")
        results["steps"].append(f"页面信息: {page_info}")

        # Step 3.5: 等待 el-tree 渲染
        print("[Step 2.5] 等待 el-tree 渲染...")

        max_wait = 15
        waited = 0
        tree_found = False
        while waited < max_wait:
            tree_count = cli.evaluate("() => document.querySelectorAll('.el-tree').length")
            print(f"[INFO] 等待 el-tree... {waited}s, treeCount={tree_count}")

            if tree_count > 0:
                tree_found = True
                print(f"[OK] 找到 {tree_count} 个 el-tree")
                break

            import time
            time.sleep(1)
            waited += 1

        if not tree_found:
            print("[WARN] 未找到 el-tree，尝试获取更多页面信息...")
            # 获取更详细的页面结构
            page_structure = cli.evaluate("""
                () => {
                    const body = document.body;
                    const main = document.querySelector('main');

                    // 递归获取页面文本
                    const getText = (el) => {
                        if (!el) return '';
                        return Array.from(el.childNodes)
                            .filter(n => n.nodeType === Node.TEXT_NODE || n.nodeType === Node.ELEMENT_NODE)
                            .map(n => {
                                if (n.nodeType === Node.TEXT_NODE) {
                                    const text = n.textContent.trim();
                                    return text.length > 0 ? text : '';
                                }
                                return getText(n);
                            })
                            .filter(t => t)
                            .join(' ');
                    };

                    return {
                        mainText: main ? getText(main).substring(0, 1000) : 'no main',
                        mainChildCount: main ? main.children.length : 0,
                        mainClasses: main ? Array.from(main.classList).join(', ') : ''
                    };
                }
            """)
            print(f"[INFO] 页面结构: {page_structure}")
            results["steps"].append(f"页面结构: {page_structure}")

        # Step 4: 检查 el-tree 中的 checkbox
        print("[Step 3] 检查 el-tree checkbox...")

        tree_info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const result = [];
                trees.forEach((t, i) => {
                    if (i < 3) {
                        result.push({
                            id: t.id || 'no-id',
                            class: t.className.substring(0, 50),
                            nodeCount: t.querySelectorAll('.el-tree-node').length,
                            checkboxCount: t.querySelectorAll('.el-tree-node__content .el-checkbox').length,
                            checkedCount: t.querySelectorAll('.is-checked').length
                        });
                    }
                });
                return result;
            }
        """)
        print(f"[INFO] El-tree 信息: {tree_info}")
        results["steps"].append(f"El-tree: {tree_info}")

        # Step 4: 点击 checkbox
        print("[Step 4] 点击 checkbox...")

        clicked = False
        clicked_selector = None

        # 方法1: 使用 PlaywrightCLI 的 click 方法
        checkbox_selectors = [
            '.el-tree-node__content .el-checkbox',
            '.el-tree .el-checkbox:first-of-type',
            '[class*="tree-node"] .el-checkbox'
        ]

        for selector in checkbox_selectors:
            if cli.is_visible(selector, timeout=2000):
                if cli.click(selector):
                    clicked = True
                    clicked_selector = selector
                    print(f"[OK] 点击成功: {selector}")
                    break

        if not clicked:
            # 方法2: 使用 el-tree 的方法触发 check
            clicked = cli.evaluate("""
                () => {
                    const tree = document.querySelector('.el-tree');
                    if (!tree) return false;

                    // 尝试通过 treeRef 调用 setChecked
                    const treeInstance = tree.__vueParentComponent;

                    // 方法1: 模拟 click 事件
                    const nodeContent = tree.querySelector('.el-tree-node__content');
                    if (nodeContent) {
                        nodeContent.click();
                        return 'clicked-node-content';
                    }
                    return false;
                }
            """)
            if clicked:
                print(f"[OK] 通过 tree node content 点击: {clicked}")

        # 方法3: 直接使用 el-tree 的 setChecked 方法
        tree_check_result = cli.evaluate("""
            () => {
                const tree = document.querySelector('.el-tree');
                if (!tree) return { error: 'no tree' };

                // 获取 el-tree 的 Vue 实例
                const treeComponent = tree.__vueParentComponent;
                if (!treeComponent) return { error: 'no vue component' };

                // 尝试调用 tree 实例的方法
                const treeRef = treeComponent.proxy;

                if (treeRef && treeRef.setChecked) {
                    // 获取第一个节点的数据
                    const treeData = treeComponent.props?.data || [];
                    if (treeData.length > 0) {
                        const firstNodeId = treeData[0].id;
                        treeRef.setChecked(firstNodeId, true);
                        return { method: 'setChecked', nodeId: firstNodeId };
                    }
                }

                return { error: 'cannot call setChecked' };
            }
        """)
        print(f"[INFO] treeRef.setChecked 结果: {tree_check_result}")

        if tree_check_result.get('method') == 'setChecked':
            clicked = True

        if not clicked:
            # 方法4: 模拟完整的事件链
            clicked = cli.evaluate("""
                () => {
                    const tree = document.querySelector('.el-tree');
                    const node = tree.querySelector('.el-tree-node');
                    if (!node) return false;

                    // 获取节点数据和key
                    const nodeKey = node.getAttribute('aria-label') ||
                                   node.querySelector('.el-tree-node__content')?.getAttribute('node-id');

                    // 尝试直接操作 tree 的内部状态
                    const treeComponent = tree.__vueParentComponent;
                    if (treeComponent && treeComponent.props) {
                        console.log('Tree props:', JSON.stringify({
                            data: treeComponent.props.data?.slice(0, 2),
                            checkedKeys: treeComponent.props.defaultCheckedKeys
                        }));
                    }

                    // 点击节点内容
                    const content = node.querySelector('.el-tree-node__content');
                    if (content) {
                        content.click();
                        return 'clicked-content';
                    }
                    return false;
                }
            """)
            if clicked:
                print(f"[OK] 模拟事件链: {clicked}")

        # 验证 checkbox 元素确实存在且可见
        checkbox_info = cli.evaluate("""
            () => {
                const tree = document.querySelector('.el-tree');
                const checkbox = tree?.querySelector('.el-tree-node__content .el-checkbox');
                if (!checkbox) return { exists: false };

                const rect = checkbox.getBoundingClientRect();
                return {
                    exists: true,
                    rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height },
                    isChecked: checkbox.checked,
                    hasIsChecked: checkbox.classList.contains('is-checked'),
                    ariaChecked: checkbox.getAttribute('aria-checked'),
                    parentClass: checkbox.parentElement?.className
                };
            }
        """)
        print(f"[INFO] Checkbox 详情: {checkbox_info}")

        # 获取点击前后的组件实例ID
        instance_before = cli.evaluate("""
            () => {
                const tree = document.querySelector('.el-tree');
                return tree?.__vueParentComponent?.uid || 'no-component';
            }
        """)
        print(f"[INFO] 点击前组件实例ID: {instance_before}")

        cli.wait_for_timeout(1000)

        # 获取点击后状态
        instance_after = cli.evaluate("""
            () => {
                const tree = document.querySelector('.el-tree');
                return tree?.__vueParentComponent?.uid || 'no-component';
            }
        """)
        print(f"[INFO] 点击后组件实例ID: {instance_after}")

        # 检查 console.log 中是否有 handleBoCheck 输出
        console_logs = cli.evaluate("""
            () => {
                const logs = window.__consoleLogs || [];
                const handleBoCheckLogs = logs.filter(l =>
                    l.includes('handleBoCheck') ||
                    l.includes('ObjectScopeSection') ||
                    l.includes('emitTypedScopeChange')
                );
                return handleBoCheckLogs.slice(-20);
            }
        """)
        print(f"[INFO] Console 日志: {console_logs}")

        # Step 6: 验证选中状态
        print("[Step 5] 验证选中状态...")

        after_click = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                let checkedCount = 0;
                trees.forEach(t => {
                    checkedCount += t.querySelectorAll('.is-checked').length;
                });

                const checkedNodes = [];
                document.querySelectorAll('.is-checked').forEach(n => {
                    checkedNodes.push(n.textContent.trim().substring(0, 30));
                });

                // 获取 Vue 组件实例信息
                const app = document.querySelector('#app')?.__vue_app__;
                const pinia = app?.config?.globalProperties?.pinia;
                const stores = [];
                if (pinia && pinia._s) {
                    pinia._s.forEach((store, name) => {
                        stores.push({
                            name,
                            hasCheckedBoIds: !!store.checkedBoIds,
                            checkedBoIds: store.checkedBoIds
                        });
                    });
                }

                // 检查控制台日志
                const consoleLogs = window.__consoleLogs || [];

                return {
                    checkedCount,
                    checkedNodes,
                    stores,
                    consoleLogs: consoleLogs.slice(-10)
                };
            }
        """)
        print(f"[INFO] 点击后状态: {after_click}")
        results["steps"].append(f"点击后: {after_click}")

        # Step 7: 检查 store
        store_info = cli.evaluate("""
            () => {
                const app = document.querySelector('#app');
                if (!app || !app.__vue_app__) return null;
                const pinia = app.__vue_app__.config.globalProperties.$pinia;

                const allStores = {};
                if (pinia && pinia._s) {
                    pinia._s.forEach((store, name) => {
                        allStores[name] = {
                            hasCheckedBoIds: !!store.checkedBoIds,
                            checkedBoIds: store.checkedBoIds,
                            stateKeys: Object.keys(store.$state || {}).slice(0, 5)
                        };
                    });
                }

                return allStores;
            }
        """)
        print(f"[INFO] Store: {store_info}")
        results["steps"].append(f"Store: {store_info}")

        # Step 8: 截图最终状态
        cli.screenshot('test_archdata_02_after_click.png')
        print("[OK] 截图: test_archdata_02_after_click.png")

        # Step 9: 判断结果
        checked_count = after_click.get('checkedCount', 0)
        checked_bo_ids = store_info.get('checkedBoIds') if store_info else None

        success = (
            checked_count > 0 or
            (checked_bo_ids and len(checked_bo_ids) > 0)
        )

        results["success"] = success
        results["final_state"] = {
            "checkedCount": checked_count,
            "checkedBoIds": checked_bo_ids,
            "checkboxClicked": clicked
        }

        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"Checkbox 点击: {clicked}")
        print(f"选中数量: {checked_count}")
        print(f"Store checkedBoIds: {checked_bo_ids}")
        print(f"测试成功: {success}")
        print("=" * 60)

        return results

    except Exception as e:
        error_msg = f"测试异常: {str(e)}"
        results["errors"].append(error_msg)
        print(f"[ERROR] {error_msg}")
        import traceback
        traceback.print_exc()
        try:
            cli.screenshot('test_archdata_error.png')
        except:
            pass
        return results

    finally:
        cli.close()
        print("[INFO] 浏览器已关闭")


if __name__ == "__main__":
    print("=" * 60)
    print("开始测试: 架构数据管理 checkbox")
    print("=" * 60)

    import json
    results = test_archdata_checkbox()

    print("\n最终结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    sys.exit(0 if results["success"] else 1)
