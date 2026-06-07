"""
E2E 测试：验证角色权限配置页面中的"管理维度范围"区域（详细诊断版）

使用 PlaywrightCLI 进行更详细的诊断
"""
import sys
import os

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI


def test_role_dimension_scope():
    """测试角色维度范围配置页面"""
    print("=" * 70)
    print("E2E 测试：角色权限配置页面的管理维度范围")
    print("=" * 70)

    screenshot_path = 'd:/filework/excel-to-diagram/test_dim_scope.png'

    cli = PlaywrightCLI(headless=False)  # 使用非无头模式以便调试

    try:
        # Step 1: 认证并导航到角色列表页
        print("\n[Step 1] 打开浏览器，访问角色列表页...")
        cli.authenticated_navigate(
            '/system/roles',
            wait_for_selector='table, .el-table, .el-card, .empty, [class*="role"]',
            timeout=20000
        )
        cli.screenshot('d:/filework/excel-to-diagram/01_roles_list.png')

        # 获取当前 URL
        current_url = cli.evaluate("() => window.location.href")
        print(f"[INFO] 当前 URL: {current_url}")

        # 获取页面内容摘要
        page_title = cli.evaluate("() => document.title")
        print(f"[INFO] 页面标题: {page_title}")

        # 检查页面是否加载成功
        health = cli.check_health()
        print(f"[INFO] 页面健康状态: {health['healthy']}")

        # Step 2: 查找角色列表中的角色
        print("\n[Step 2] 查找角色列表...")

        # 检查表格是否存在
        table_exists = cli.is_visible('table')
        print(f"[INFO] 表格存在: {table_exists}")

        # 检查是否有 el-table 类
        el_table_exists = cli.is_visible('.el-table')
        print(f"[INFO] el-table 存在: {el_table_exists}")

        # 尝试查找 ID=1397 的行
        # 使用 JavaScript 在页面中搜索
        search_result = cli.evaluate("""
            () => {
                // 搜索包含 1397 的元素
                const all = document.querySelectorAll('*');
                let found = [];
                for (const el of all) {
                    const text = el.textContent || '';
                    if (text.includes('1397')) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            found.push({
                                tag: el.tagName,
                                class: el.className?.slice?.(0, 50) || '',
                                text: text.slice(0, 100)
                            });
                        }
                    }
                }
                return found.slice(0, 5); // 最多返回5个
            }
        """)
        print(f"[INFO] 找到 {len(search_result)} 个包含 '1397' 的可见元素:")
        for item in search_result:
            print(f"  - {item['tag']}: {item['text'][:60]}...")

        # Step 3: 导航到角色详情页
        print("\n[Step 3] 导航到角色详情页...")

        # 尝试多个可能的路径
        possible_paths = [
            '/system/roles/1397',
            '/system/roles/1397/permissions',
            '/system/role/1397',
            '/system/role/1397/permissions',
            '/role/1397',
            '/permission/1397',
        ]

        role_detail_found = False
        for path in possible_paths:
            print(f"[INFO] 尝试路径: {path}")
            cli.authenticated_navigate(
                path,
                wait_for_selector='.el-form, .el-card, .el-table, .empty, [class*="permission"]',
                timeout=10000
            )
            cli.screenshot(f'd:/filework/excel-to-diagram/02_{path.replace("/", "_")}.png')

            # 检查页面内容
            body_text = cli.evaluate("() => document.body.textContent || ''")
            if '权限' in body_text or 'permission' in body_text.lower() or '维度' in body_text:
                print(f"[INFO] 找到包含权限/维度内容的页面: {path}")
                role_detail_found = True
                break
            elif '404' in body_text or 'not found' in body_text.lower():
                print(f"[WARN] 页面不存在: {path}")
            else:
                print(f"[INFO] 页面加载但内容不明确: {path}")

        # Step 4: 如果直接导航失败，尝试在列表页点击
        if not role_detail_found:
            print("\n[Step 4] 尝试在角色列表页点击角色...")

            # 返回角色列表
            cli.authenticated_navigate(
                '/system/roles',
                wait_for_selector='table, .el-table, .empty',
                timeout=15000
            )
            cli.screenshot('d:/filework/excel-to-diagram/03_roles_list_retry.png')

            # 尝试点击包含 1397 的行
            click_result = cli.evaluate("""
                () => {
                    // 找到包含 1397 的表格单元格
                    const cells = document.querySelectorAll('td');
                    for (const cell of cells) {
                        if (cell.textContent.includes('1397')) {
                            // 尝试找到同一行的链接或按钮
                            const row = cell.closest('tr');
                            if (row) {
                                // 尝试点击行
                                row.click();
                                return { clicked: true, rowText: row.textContent.slice(0, 100) };
                            }
                        }
                    }
                    // 如果没找到单元格，尝试找其他包含 1397 的可点击元素
                    const links = document.querySelectorAll('a, button, [role="button"]');
                    for (const link of links) {
                        if (link.textContent.includes('1397') || link.href?.includes('1397')) {
                            link.click();
                            return { clicked: true, element: link.tagName, text: link.textContent.slice(0, 50) };
                        }
                    }
                    return { clicked: false };
                }
            """)
            print(f"[INFO] 点击结果: {click_result}")

            if click_result.get('clicked'):
                cli.wait_for_timeout(2000)
                cli.screenshot('d:/filework/excel-to-diagram/04_after_click.png')

                # 获取新 URL
                new_url = cli.evaluate("() => window.location.href")
                print(f"[INFO] 点击后 URL: {new_url}")

        # Step 5: 在当前页面查找维度范围相关内容
        print("\n[Step 5] 查找'管理维度范围'区域...")

        # 获取页面完整文本
        full_text = cli.evaluate("() => document.body.innerText || ''")

        # 检查关键内容
        dim_keywords = ['维度', 'dimension', 'scope']
        version_keywords = ['版本', 'version', 'v1.0', 'V1.0']
        permission_keywords = ['权限', 'permission', '管理']

        print("\n[分析结果]")
        print(f"  页面文本长度: {len(full_text)} 字符")

        print("\n  关键词检查:")
        for keyword in dim_keywords:
            found = keyword.lower() in full_text.lower()
            status = "[OK]" if found else "[X]"
            print(f"    - '{keyword}': {status}")
        for keyword in version_keywords:
            found = keyword.lower() in full_text.lower()
            status = "[OK]" if found else "[X]"
            print(f"    - '{keyword}': {status}")
        for keyword in permission_keywords:
            found = keyword.lower() in full_text.lower()
            status = "[OK]" if found else "[X]"
            print(f"    - '{keyword}': {status}")

        # Step 6: 检查控制台错误
        print("\n[Step 6] 检查浏览器控制台错误...")

        health = cli.check_health()
        print(f"[INFO] 页面健康: {health['healthy']}")
        print(f"[INFO] 健康摘要: {health['summary']}")

        if not health['healthy']:
            print(f"[WARN] 页面存在问题:")
            for key, value in health['details'].items():
                if value:
                    print(f"    - {key}: {value}")

        # Step 7: 最终截图
        print("\n[Step 7] 保存最终截图...")
        cli.screenshot(screenshot_path)
        print(f"[INFO] 截图保存到: {screenshot_path}")

        # 返回测试结果
        return {
            'success': True,
            'page_loaded': health['healthy'],
            'dim_found': any(k.lower() in full_text.lower() for k in dim_keywords),
            'version_found': any(k.lower() in full_text.lower() for k in version_keywords),
            'health': health,
            'screenshot': screenshot_path
        }

    except Exception as e:
        print(f"\n[ERROR] 测试异常: {e}")
        import traceback
        traceback.print_exc()

        # 尝试截图
        try:
            cli.screenshot('d:/filework/excel-to-diagram/error_state.png')
        except:
            pass

        return {'success': False, 'error': str(e)}

    finally:
        cli.close()


def main():
    """主函数"""
    print("\n开始测试...\n")

    result = test_role_dimension_scope()

    # 验证截图
    print("\n" + "=" * 70)
    print("截图文件验证")
    print("=" * 70)

    screenshot_path = 'd:/filework/excel-to-diagram/test_dim_scope.png'
    if os.path.exists(screenshot_path):
        size = os.path.getsize(screenshot_path)
        print(f"[OK] 截图存在: {screenshot_path}")
        print(f"[OK] 文件大小: {size:,} bytes ({size / 1024:.1f} KB)")
        if size > 0:
            print("[OK] 截图有效 (大小 > 0)")
        else:
            print("[WARN] 截图大小为 0")
    else:
        print(f"[ERROR] 截图不存在: {screenshot_path}")

    # 诊断摘要
    print("\n" + "=" * 70)
    print("测试结果摘要")
    print("=" * 70)

    if result.get('success'):
        health = result.get('health', {})
        print(f"[{'OK' if result.get('page_loaded') else 'X'}] 页面加载成功")
        print(f"[{'OK' if result.get('dim_found') else 'X'}] 找到维度相关内容")
        print(f"[{'OK' if result.get('version_found') else 'X'}] 找到版本相关内容")
        print(f"[{'OK' if health.get('healthy', False) else 'X'}] 页面健康检查")

        # 列出所有截图
        print("\n生成的截图文件:")
        for i in range(1, 5):
            path = f'd:/filework/excel-to-diagram/01_roles_list.png' if i == 1 else \
                   f'd:/filework/excel-to-diagram/02__system__roles__1397.png' if i == 2 else \
                   f'd:/filework/excel-to-diagram/03_roles_list_retry.png' if i == 3 else \
                   f'd:/filework/excel-to-diagram/04_after_click.png'
            if os.path.exists(path):
                size = os.path.getsize(path)
                print(f"  - {os.path.basename(path)}: {size:,} bytes")
    else:
        print(f"[ERROR] 测试失败: {result.get('error', '未知错误')}")

    print("\n" + "=" * 70)
    print("测试完成!")
    print("=" * 70)


if __name__ == '__main__':
    main()
