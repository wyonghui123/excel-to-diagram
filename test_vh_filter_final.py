#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 value_help 过滤器 E2E - 最终版
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright


def test_value_help_filter_final():
    """最终测试"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True
        )
        page = context.new_page()

        try:
            # 1. 登录
            print("\n1. 登录...")
            page.goto('http://localhost:3004/login', wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(3000)

            page.fill('input[type="text"]', 'admin')
            page.fill('input[type="password"]', 'admin123')
            page.click('button[type="submit"]')
            page.wait_for_timeout(5000)
            print("   [DECORATIVE] 登录完成")

            # 2. 导航到用户组页面
            print("\n2. 导航到用户组页面...")
            page.goto('http://localhost:3004/list/user_group', wait_until='networkidle', timeout=60000)
            page.wait_for_timeout(5000)

            # 3. 检查页面结构
            print("\n3. 检查页面结构:")

            # 检查是否有多个 #app，取第一个
            app_count = page.locator('#app').count()
            print(f"   #app 元素数量: {app_count}")

            # 获取第一个 #app 的内容
            app_html = page.locator('#app').first.inner_html()
            print(f"   #app 内容长度: {len(app_html)} 字符")

            # 检查关键组件
            components = {
                'main': page.locator('main').count(),
                '.el-table': page.locator('.el-table').count(),
                '.el-table__header th': page.locator('.el-table__header th').count(),
                '.filter-trigger': page.locator('.filter-trigger').count(),
                '.el-popover': page.locator('.el-popover').count(),
            }

            print("\n4. 关键组件:")
            for name, count in components.items():
                status = "[DECORATIVE]" if count > 0 else "[DECORATIVE]"
                print(f"   {status} {name}: {count}")

            # 5. 如果有表头，检查第一列是否有过滤器
            if components['.el-table__header th'] > 0:
                print("\n5. 检查表头过滤器:")

                # 获取第一列的类名
                first_th_class = page.locator('.el-table__header th').first.get_attribute('class')
                print(f"   第一列表头类名: {first_th_class}")

                # 检查第一列是否有过滤器触发器
                first_th_filter = page.locator('.el-table__header th').first.locator('.filter-trigger')
                print(f"   第一列表头过滤器触发器: {first_th_filter.count()}")

            # 6. 检查网络请求
            print("\n6. 检查 API:")
            response = page.request.get('http://localhost:3010/api/v1/meta/user_group/view-config')
            if response.ok:
                data = response.json()
                columns = data.get('data', {}).get('list', {}).get('columns', [])
                vh_columns = [c for c in columns if c.get('filter_type') == 'value_help']
                print(f"   [DECORATIVE] API 返回 {len(columns)} 列，其中 {len(vh_columns)} 列是 value_help 类型")
                for c in vh_columns:
                    print(f"     - {c.get('key')}: {c.get('title')}")
                    vhc = c.get('value_help_config', {})
                    if vhc:
                        print(f"       result_type: {vhc.get('presentation', {}).get('result_type')}")
                        print(f"       multiple: {vhc.get('behavior', {}).get('multiple')}")
            else:
                print(f"   [DECORATIVE] API 请求失败: {response.status}")

            # 7. 截图
            print("\n7. 保存截图...")
            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           'test_vh_filter_final_screenshot.png')
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"   [DECORATIVE] 截图保存到: {screenshot_path}")

            print("\n" + "=" * 60)
            print("测试完成 [DECORATIVE]")
            print("=" * 60)

        except Exception as e:
            print(f"\n[DECORATIVE] 测试失败: {e}")
            import traceback
            traceback.print_exc()

            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           'test_vh_filter_error.png')
            page.screenshot(path=screenshot_path, full_page=True)

        finally:
            browser.close()


if __name__ == '__main__':
    test_value_help_filter_final()
