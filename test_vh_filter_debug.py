#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 value_help 过滤器 E2E - 详细调试版
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright


def test_value_help_filter_debug():
    """详细调试测试"""
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

            # 填写登录表单
            page.fill('input[type="text"]', 'admin')
            page.fill('input[type="password"]', 'admin123')
            page.click('button[type="submit"]')

            # 等待登录完成
            page.wait_for_timeout(5000)
            print("   [DECORATIVE] 登录完成")

            # 2. 导航到用户组页面
            print("\n2. 导航到用户组页面...")
            page.goto('http://localhost:3004/list/user_group', wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(8000)  # 更长的等待时间

            # 3. 获取页面 HTML 摘要
            print("\n3. 页面 HTML 摘要:")
            body_html = page.locator('body').inner_html()
            print(f"   body 长度: {len(body_html)} 字符")

            # 检查是否为空
            if len(body_html.strip()) < 100:
                print("   [WARNING]  body 内容很少，可能页面未加载")

            # 检查 #app
            app_html = page.locator('#app').inner_html()
            print(f"   #app 长度: {len(app_html)} 字符")

            # 4. 检查关键元素
            print("\n4. 检查关键元素:")

            # 检查 main
            main_count = page.locator('main').count()
            print(f"   main: {main_count} 个")

            # 检查 .el-table
            table_count = page.locator('.el-table').count()
            print(f"   .el-table: {table_count} 个")

            # 检查任意 .el- 组件
            el_count = page.locator('[class^="el-"]').count()
            print(f"   [class^='el-']: {el_count} 个")

            # 检查是否有 Vue 加载错误
            console_messages = []
            page.on('console', lambda msg: console_messages.append(msg.text) if msg.type == 'error' else None)
            page.wait_for_timeout(1000)

            errors = [m for m in console_messages if 'error' in m.lower()]
            if errors:
                print(f"\n5. 控制台错误 ({len(errors)} 个):")
                for e in errors[:5]:
                    print(f"   - {e[:100]}")

            # 5. 截图
            print("\n6. 保存截图...")
            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           'test_vh_filter_debug_screenshot.png')
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"   [DECORATIVE] 截图保存到: {screenshot_path}")

            # 6. 检查网络请求
            print("\n7. 检查网络请求:")
            response = page.request.get('http://localhost:3010/api/v1/meta/user_group/view-config')
            if response.ok:
                data = response.json()
                filters = data.get('data', {}).get('list', {}).get('filters', [])
                vh_filters = [f for f in filters if f.get('type') == 'value_help']
                print(f"   [DECORATIVE] API 返回 {len(filters)} 个过滤器，其中 {len(vh_filters)} 个是 value_help 类型")
                for f in vh_filters:
                    print(f"     - {f.get('field')}: {f.get('label')}")
                    vh = f.get('value_help', {})
                    if vh:
                        print(f"       result_type: {vh.get('presentation', {}).get('result_type')}")
                        print(f"       multiple: {vh.get('behavior', {}).get('multiple')}")
            else:
                print(f"   [DECORATIVE] API 请求失败: {response.status}")

            print("\n" + "=" * 60)
            print("测试完成")
            print("=" * 60)

        except Exception as e:
            print(f"\n[DECORATIVE] 测试失败: {e}")
            import traceback
            traceback.print_exc()

            # 截图保存
            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           'test_vh_filter_error.png')
            page.screenshot(path=screenshot_path, full_page=True)

        finally:
            browser.close()


if __name__ == '__main__':
    test_value_help_filter_debug()
