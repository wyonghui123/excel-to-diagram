"""
E2E 测试：验证角色权限配置页面中的"管理维度范围"区域

测试流程：
1. 打开浏览器，访问 http://localhost:3004/system/roles
2. 登录（使用 dev-login）
3. 找到角色 ID=1397 的角色，点击进入权限配置页面
4. 在"管理维度范围"区域，检查：
   - 是否显示了"版本"维度行
   - 如果显示了版本行，检查是否显示了"v1.0"标签
   - 检查浏览器控制台是否有错误（Error 级别）
5. 截图保存到 `d:\filework\excel-to-diagram\test_dim_scope.png`

使用 test_helpers/browser_auth.py 的 authenticated_page 方法进行认证。
"""
import asyncio
import os
import sys

# 添加项目路径
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth import authenticated_page, go_to


async def test_role_dimension_scope():
    """测试角色维度范围配置页面"""
    print("=" * 70)
    print("E2E 测试：角色权限配置页面的管理维度范围")
    print("=" * 70)

    screenshot_path = 'd:/filework/excel-to-diagram/test_dim_scope.png'

    try:
        # Step 1: 使用 authenticated_page 打开浏览器并登录
        print("\n[Step 1] 打开浏览器，访问角色列表页...")
        async with authenticated_page(target_url='/system/roles') as page:
            await page.wait_for_load_state('domcontentloaded')
            await page.wait_for_timeout(2000)  # 等待 Vue 渲染

            # 截图：角色列表页
            print("[INFO] 截图保存: role_list.png")
            await page.screenshot(path='d:/filework/excel-to-diagram/role_list.png', full_page=True)

            # Step 2: 在角色列表中找到 ID=1397 的行并点击
            print("\n[Step 2] 查找角色 ID=1397...")

            # 尝试多种方式找到角色行
            # 方式1: 通过表格行查找
            found = False
            try:
                # 查找包含 "1397" 的表格行
                rows = await page.query_selector_all('table tbody tr')
                for row in rows:
                    row_text = await row.text_content()
                    if '1397' in row_text:
                        print(f"[INFO] 找到包含 1397 的行: {row_text[:100]}...")
                        # 点击该行的链接或按钮进入详情
                        link = await row.query_selector('a, .el-button, [role="button"]')
                        if link:
                            await link.click()
                            found = True
                            print("[INFO] 已点击进入角色详情页")
                            break
                        else:
                            # 直接点击整行
                            await row.click()
                            found = True
                            print("[INFO] 已点击整行进入角色详情页")
                            break
            except Exception as e:
                print(f"[WARN] 表格方式查找失败: {e}")

            if not found:
                # 方式2: 直接导航到角色详情页
                print("[INFO] 尝试直接导航到角色详情页...")
                await go_to(page, '/system/roles/1397')
                await page.wait_for_timeout(2000)

            # 截图：角色详情页
            print("[INFO] 截图保存: role_detail.png")
            await page.screenshot(path='d:/filework/excel-to-diagram/role_detail.png', full_page=True)

            # Step 3: 查找"管理维度范围"区域
            print("\n[Step 3] 查找'管理维度范围'区域...")

            # 等待页面加载
            await page.wait_for_timeout(1000)

            # 尝试查找维度范围相关内容
            dim_scope_found = False
            version_row_found = False
            version_tag_found = False

            # 检查页面文本
            page_text = await page.text_content('body')

            # 检查是否有"维度范围"或"维度"相关文字
            if '维度' in page_text or 'dimension' in page_text.lower():
                print("[INFO] 页面中包含维度相关内容")
                dim_scope_found = True
            else:
                print("[WARN] 页面中未找到'维度'相关内容")

            # 查找"版本"或"version"相关文字
            if '版本' in page_text or 'version' in page_text.lower():
                print("[INFO] 页面中包含版本相关内容")
                version_row_found = True
            else:
                print("[WARN] 页面中未找到'版本'相关内容")

            # 查找"v1.0"标签
            if 'v1.0' in page_text or 'V1.0' in page_text:
                print("[INFO] 页面中包含 v1.0 标签")
                version_tag_found = True
            else:
                print("[WARN] 页面中未找到 v1.0 标签")

            # Step 4: 收集控制台错误
            print("\n[Step 4] 检查浏览器控制台错误...")

            # 通过 evaluate 获取控制台日志
            console_logs = await page.evaluate("""
                () => {
                    const logs = [];
                    // 获取 Vue 错误
                    if (window.__appErrors) {
                        window.__appErrors.forEach(e => logs.push({ type: 'vue_error', message: e.message }));
                    }
                    // 获取控制台错误
                    if (window.__consoleErrors) {
                        window.__consoleErrors.forEach(e => logs.push({ type: 'console_error', message: e.message }));
                    }
                    return logs;
                }
            """)

            print(f"[INFO] 检测到 {len(console_logs)} 个控制台错误:")
            for log in console_logs[:10]:  # 最多显示10个
                print(f"  - [{log['type']}] {log['message'][:100]}")

            # Step 5: 最终截图
            print("\n[Step 5] 保存最终截图...")
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"[INFO] 截图保存到: {screenshot_path}")

            # 输出测试结果摘要
            print("\n" + "=" * 70)
            print("测试结果摘要")
            print("=" * 70)
            print(f"[{'OK' if dim_scope_found else 'X'}] 维度相关区域: {'已找到' if dim_scope_found else '未找到'}")
            print(f"[{'OK' if version_row_found else 'X'}] 版本维度行: {'已找到' if version_row_found else '未找到'}")
            print(f"[{'OK' if version_tag_found else 'X'}] v1.0 标签: {'已找到' if version_tag_found else '未找到'}")
            print(f"[{'X' if len(console_logs) > 0 else 'OK'}] 控制台错误: {'有错误' if len(console_logs) > 0 else '无错误'} (共 {len(console_logs)} 个)")
            print(f"[OK] 截图已保存: {screenshot_path}")
            print("=" * 70)

            return {
                'dim_scope_found': dim_scope_found,
                'version_row_found': version_row_found,
                'version_tag_found': version_tag_found,
                'console_errors': len(console_logs),
                'screenshot_path': screenshot_path
            }

    except Exception as e:
        print(f"\n[ERROR] 测试过程中发生异常: {e}")
        import traceback
        traceback.print_exc()
        return {
            'error': str(e),
            'screenshot_path': screenshot_path
        }


def main():
    """主函数"""
    # 检查截图文件是否存在
    screenshot_path = 'd:/filework/excel-to-diagram/test_dim_scope.png'

    result = asyncio.run(test_role_dimension_scope())

    # 验证截图文件
    print("\n" + "=" * 70)
    print("验证截图文件")
    print("=" * 70)

    if os.path.exists(screenshot_path):
        file_size = os.path.getsize(screenshot_path)
        print(f"[OK] 截图文件存在: {screenshot_path}")
        print(f"[OK] 文件大小: {file_size} bytes ({file_size / 1024:.1f} KB)")
        if file_size > 0:
            print("[OK] 文件大小 > 0，截图有效")
        else:
            print("[WARN] 文件大小为 0，可能截图失败")
    else:
        print(f"[ERROR] 截图文件不存在: {screenshot_path}")

    # 检查控制台错误
    print("\n" + "=" * 70)
    print("控制台错误检查")
    print("=" * 70)

    if 'error' not in result:
        if result.get('console_errors', 0) > 0:
            print(f"[WARN] 检测到 {result['console_errors']} 个控制台错误")
        else:
            print("[OK] 无控制台错误")
    else:
        print(f"[ERROR] 测试异常: {result['error']}")

    print("\n测试完成!")


if __name__ == '__main__':
    main()
