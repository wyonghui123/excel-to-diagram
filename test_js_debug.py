#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 value_help 过滤器 - 检查 JS 错误
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright


def test_check_js():
    """检查 JS 错误"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True
        )
        page = context.new_page()

        js_messages = []
        page.on('console', lambda msg: js_messages.append(f"[{msg.type}] {msg.text}"))

        try:
            # 1. 登录
            print("\n1. 登录...")
            page.goto('http://localhost:3004/login', wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(2000)

            page.fill('input[type="text"]', 'admin')
            page.fill('input[type="password"]', 'admin123')
            page.click('button[type="submit"]')
            page.wait_for_timeout(5000)
            print("   [DECORATIVE] 登录完成")

            # 2. 导航到用户组页面
            print("\n2. 导航到用户组页面...")
            page.goto('http://localhost:3004/list/user_group', wait_until='networkidle', timeout=60000)
            page.wait_for_timeout(8000)

            # 3. 打印所有 JS 消息
            print("\n3. JS 消息:")
            for msg in js_messages[-30:]:  # 只打印最后 30 条
                print(f"   {msg[:200]}")

            # 4. 检查页面 URL
            print(f"\n4. 当前 URL: {page.url}")

            # 5. 检查页面内容
            print(f"\n5. 页面标题: {page.title()}")

            # 6. 检查 body 内容
            body_text = page.locator('body').text_content()
            print(f"   body 文本长度: {len(body_text)} 字符")
            print(f"   body 文本预览: {body_text[:500]}...")

            # 7. 截图
            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           'test_js_debug_screenshot.png')
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"\n6. 截图保存到: {screenshot_path}")

        except Exception as e:
            print(f"\n[DECORATIVE] 错误: {e}")
            import traceback
            traceback.print_exc()

        finally:
            browser.close()


if __name__ == '__main__':
    test_check_js()
