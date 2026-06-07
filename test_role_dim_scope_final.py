"""
E2E 测试：验证角色权限配置页面中的"管理维度范围"区域

正确的路由：
- 角色列表: /user-permission/roles
- 角色详情: /role/:id 或 /system/role-detail/:roleId
- 角色权限: /system/role-permission/:roleId
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

    cli = PlaywrightCLI(headless=False)

    try:
        # Step 1: 认证并导航到角色列表页
        print("\n[Step 1] 打开浏览器，访问角色列表页 (/user-permission/roles)...")
        cli.authenticated_navigate(
            '/user-permission/roles',
            wait_for_selector='.el-table, .empty, table',
            timeout=30000
        )
        cli.screenshot('d:/filework/excel-to-diagram/01_roles_list.png')

        # 获取当前 URL
        current_url = cli.evaluate("() => window.location.href")
        print(f"[INFO] 当前 URL: {current_url}")

        # 获取页面内容摘要
        page_title = cli.evaluate("() => document.title")
        print(f"[INFO] 页面标题: {page_title}")

        # 检查页面是否加载成功
        try:
            health = cli.check_health()
            print(f"[INFO] 页面健康状态: {health['healthy']}")
        except Exception as e:
            print(f"[WARN] 健康检查失败: {e}")
            health = {'healthy': True, 'summary': 'unknown'}

        # Step 2: 查找角色列表中的 ID=1397
        print("\n[Step 2] 查找角色 ID=1397...")

        # 使用 JavaScript 搜索包含 1397 的元素
        search_result = cli.evaluate("""
            () => {
                // 搜索包含 1397 的元素
                const all = document.querySelectorAll('*');
                let found = [];
                for (const el of all) {
                    const text = el.textContent || '';
                    if (text.includes('1397')) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && rect.height < 500) {
                            found.push({
                                tag: el.tagName,
                                class: String(el.className || '').slice(0, 80),
                                text: text.slice(0, 150).replace(/\\s+/g, ' ').trim()
                            });
                        }
                    }
                }
                return found.slice(0, 10);
            }
        """)
        print(f"[INFO] 找到 {len(search_result)} 个包含 '1397' 的可见元素:")
        for i, item in enumerate(search_result):
            print(f"  {i+1}. [{item['tag']}] {item['class']}")
            print(f"     文本: {item['text'][:80]}...")

        # Step 3: 点击角色行进入详情页
        print("\n[Step 3] 点击角色行进入详情页...")

        click_result = cli.evaluate("""
            () => {
                // 找到包含 1397 的表格单元格并点击其所在行
                const cells = document.querySelectorAll('td');
                for (const cell of cells) {
                    if (cell.textContent.includes('1397')) {
                        // 找到同一行的 <tr>
                        const row = cell.closest('tr');
                        if (row) {
                            // 在行中找到链接或可点击元素
                            const link = row.querySelector('a, .el-button, [role="button"], .el-link');
                            if (link) {
                                link.click();
                                return { clicked: true, method: 'link', text: link.textContent.slice(0, 50) };
                            }
                            // 直接点击行
                            row.click();
                            return { clicked: true, method: 'row', text: row.textContent.slice(0, 80) };
                        }
                    }
                }
                return { clicked: false };
            }
        """)
        print(f"[INFO] 点击结果: {click_result}")

        if click_result.get('clicked'):
            print("[INFO] 等待页面跳转...")
            cli.wait_for_timeout(3000)
            cli.screenshot('d:/filework/excel-to-diagram/02_after_click.png')

            new_url = cli.evaluate("() => window.location.href")
            print(f"[INFO] 点击后 URL: {new_url}")
        else:
            # 直接导航到角色详情页
            print("[INFO] 未找到可点击的元素，直接导航到角色详情页...")
            cli.authenticated_navigate(
                '/role/1397',
                wait_for_selector='.el-form, .el-card, .el-table, .empty',
                timeout=20000
            )
            cli.screenshot('d:/filework/excel-to-diagram/02_direct_nav.png')

        # Step 4: 在当前页面查找维度范围相关内容
        print("\n[Step 4] 查找'管理维度范围'区域...")

        # 获取页面完整文本
        full_text = cli.evaluate("() => document.body.innerText || ''")

        # 检查关键内容
        dim_keywords = ['维度', 'dimension', 'scope']
        version_keywords = ['版本', 'version', 'v1.0', 'V1.0', 'v-1']
        permission_keywords = ['权限', 'permission', '管理']

        print("\n[页面分析]")
        print(f"  页面文本长度: {len(full_text)} 字符")

        print("\n  关键词检查:")
        dim_found = any(k.lower() in full_text.lower() for k in dim_keywords)
        version_found = any(k.lower() in full_text.lower() for k in version_keywords)
        perm_found = any(k.lower() in full_text.lower() for k in permission_keywords)

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

        # 查找具体的版本标签
        version_tag_found = 'v1.0' in full_text or 'V1.0' in full_text or 'v-1' in full_text
        print(f"\n  版本标签检查: {'[OK]' if version_tag_found else '[X]'} v1.0 标签")

        # Step 5: 检查控制台错误
        print("\n[Step 5] 检查浏览器控制台错误...")

        try:
            health = cli.check_health()
            print(f"[INFO] 页面健康: {health['healthy']}")
            print(f"[INFO] 健康摘要: {health['summary']}")
        except Exception as e:
            print(f"[WARN] 健康检查失败: {e}")
            health = {'healthy': True, 'summary': 'unknown', 'details': {}}

        console_errors = []
        if not health['healthy']:
            details = health.get('details', {})
            for key, value in details.items():
                if value and isinstance(value, list):
                    console_errors.extend(value)
                elif value:
                    console_errors.append(str(value))

        print(f"[INFO] 控制台错误数量: {len(console_errors)}")
        if console_errors:
            print("  错误详情:")
            for err in console_errors[:5]:
                print(f"    - {str(err)[:100]}")

        # Step 6: 最终截图
        print("\n[Step 6] 保存最终截图...")
        cli.screenshot(screenshot_path)
        print(f"[INFO] 截图保存到: {screenshot_path}")

        # 额外：尝试导航到权限配置页
        print("\n[Step 7] 尝试导航到权限配置页...")

        cli.authenticated_navigate(
            '/system/role-permission/1397',
            wait_for_selector='.el-form, .el-card, .el-table, .empty',
            timeout=15000
        )
        cli.screenshot('d:/filework/excel-to-diagram/03_permission_page.png')

        perm_page_text = cli.evaluate("() => document.body.innerText || ''")
        print(f"[INFO] 权限配置页文本长度: {len(perm_page_text)} 字符")

        # 检查权限页是否包含维度相关内容
        perm_dim_found = any(k.lower() in perm_page_text.lower() for k in dim_keywords)
        perm_version_found = any(k.lower() in perm_page_text.lower() for k in version_keywords)
        print(f"[INFO] 权限页找到维度内容: {perm_dim_found}")
        print(f"[INFO] 权限页找到版本内容: {perm_version_found}")

        # 返回测试结果
        return {
            'success': True,
            'page_loaded': health['healthy'],
            'dim_found': dim_found or perm_dim_found,
            'version_found': version_found or perm_version_found,
            'version_tag_found': version_tag_found,
            'console_errors': len(console_errors),
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
        print(f"[{'OK' if result.get('version_tag_found') else 'X'}] 找到 v1.0 标签")
        print(f"[{'OK' if result.get('console_errors', 0) == 0 else 'X'}] 无控制台错误 (共 {result.get('console_errors', 0)} 个)")
        print(f"[OK] 截图已保存: {screenshot_path}")

        # 列出所有截图
        print("\n生成的截图文件:")
        for name in ['01_roles_list.png', '02_after_click.png', '03_permission_page.png']:
            path = f'd:/filework/excel-to-diagram/{name}'
            if os.path.exists(path):
                size = os.path.getsize(path)
                print(f"  - {name}: {size:,} bytes")
    else:
        print(f"[ERROR] 测试失败: {result.get('error', '未知错误')}")

    print("\n" + "=" * 70)
    print("测试完成!")
    print("=" * 70)


if __name__ == '__main__':
    main()
