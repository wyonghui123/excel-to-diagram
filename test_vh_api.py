#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
排查 value_help 过滤器 - 监听所有 API 请求
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright


def test_value_help_all_requests():
    """验证 value_help 过滤器 - 监听所有 API 请求"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True
        )
        page = context.new_page()

        # 收集所有 API 请求
        all_requests = []

        def handle_request(request):
            if '/api/v1/' in request.url:
                all_requests.append({
                    'url': request.url,
                    'method': request.method,
                })

        page.on('request', handle_request)

        try:
            print("\n" + "=" * 60)
            print("验证 value_help 过滤器 - 所有 API 请求")
            print("=" * 60)

            # 1. 登录
            print("\n[步骤1] 登录...")
            page.goto('http://localhost:3004/login', wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(2000)
            page.fill('input[type="text"]', 'admin')
            page.fill('input[type="password"]', 'admin123')
            page.click('button[type="submit"]')
            page.wait_for_timeout(5000)
            print("   [DECORATIVE] 登录完成")

            # 2. 导航到用户组页面
            print("\n[步骤2] 导航到用户组页面...")
            all_requests.clear()
            page.goto('http://localhost:3004/user-permission?tab=user-groups', wait_until='networkidle', timeout=60000)
            page.wait_for_timeout(5000)
            print(f"   初始 API 请求: {len(all_requests)} 个")
            for req in all_requests:
                print(f"   - {req['method']} {req['url'][:150]}")

            # 3. 打开父组过滤器并选择
            print("\n[步骤3] 打开父组过滤器并选择选项...")
            headers = page.locator('.el-table__header th')
            parent_col_idx = -1
            for i in range(headers.count()):
                text = headers.nth(i).text_content().strip()
                if '父组' in text:
                    parent_col_idx = i
                    break

            if parent_col_idx < 0:
                print("   [DECORATIVE] 没有找到父组列")
                return

            trigger = headers.nth(parent_col_idx).locator('.filter-trigger')
            trigger.first.click()
            page.wait_for_timeout(1500)

            el_select = page.locator('.filter-panel:visible .el-select')
            if el_select.count() == 0:
                print("   [DECORATIVE] 没有找到 el-select")
                return

            el_select.first.click()
            page.wait_for_timeout(2000)

            options = page.locator('.el-select-dropdown:visible .el-select-dropdown__item')
            for j in range(options.count()):
                opt_text = options.nth(j).text_content().strip()
                if '条/页' not in opt_text:
                    print(f"   选择: {opt_text}")
                    options.nth(j).click()
                    page.wait_for_timeout(500)
                    break

            # 4. 点击确认按钮
            print("\n[步骤4] 点击确认按钮...")
            all_requests.clear()

            confirm_btn = page.locator('.filter-panel:visible .el-button--primary')
            if confirm_btn.count() > 0 and confirm_btn.first.is_visible():
                confirm_btn.first.click()
                page.wait_for_timeout(3000)
                print("   [DECORATIVE] 点击了确认按钮")
            else:
                print("   [WARNING]  确认按钮不可见")
                # 尝试点击空白区域关闭下拉
                filter_panel = page.locator('.filter-panel:visible')
                if filter_panel.count() > 0:
                    filter_panel.first.click(position={'x': 10, 'y': 10})
                    page.wait_for_timeout(500)
                    if confirm_btn.count() > 0 and confirm_btn.first.is_visible():
                        confirm_btn.first.click()
                        page.wait_for_timeout(3000)
                        print("   [DECORATIVE] 点击了确认按钮（第二次尝试）")

            # 5. 检查 API 请求
            print(f"\n[步骤5] 确认后的 API 请求: {len(all_requests)} 个")
            for req in all_requests:
                print(f"   - {req['method']} {req['url'][:200]}")

            # 6. 检查过滤结果
            print("\n[步骤6] 检查过滤结果...")
            rows = page.locator('.el-table__body tr')
            row_count = rows.count()
            print(f"   表格行数: {row_count}")

            active_filters = page.locator('.filter-trigger.is-active')
            print(f"   活跃过滤器: {active_filters.count()}")

            # 7. 检查 Vue 组件状态
            print("\n[步骤7] 检查 Vue 组件状态...")
            result = page.evaluate("""() => {
                // 查找所有 filter-trigger 元素
                const triggers = document.querySelectorAll('.filter-trigger');
                const info = [];
                triggers.forEach((t, i) => {
                    const isActive = t.classList.contains('is-active');
                    const badge = t.querySelector('.filter-badge');
                    const badgeText = badge ? badge.textContent : '';
                    info.push(`trigger[${i}]: active=${isActive}, badge="${badgeText}"`);
                });
                return info.join('\\n');
            }""")
            print(f"   {result}")

            # 8. 截图
            print("\n[步骤8] 保存截图...")
            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           'test_vh_all_api_screenshot.png')
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"   [DECORATIVE] 截图保存到: {screenshot_path}")

        except Exception as e:
            print(f"\n[DECORATIVE] 测试失败: {e}")
            import traceback
            traceback.print_exc()

        finally:
            browser.close()


if __name__ == '__main__':
    test_value_help_all_requests()
