#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
排查 value_help 过滤器 - 检查前端传递的值类型
通过拦截网络请求检查实际发送的参数
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright


def test_value_help_value_type():
    """检查 value_help 过滤器传递的值类型"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True
        )
        page = context.new_page()

        # 收集 API 请求详情
        api_details = []

        def handle_request(request):
            if '/api/v1/user-group' in request.url:
                api_details.append({
                    'url': request.url,
                    'method': request.method,
                    'post_data': request.post_data,
                })

        page.on('request', handle_request)

        # 收集 console 日志
        console_logs = []
        page.on('console', lambda msg: console_logs.append(f'[{msg.type}] {msg.text}'))

        try:
            print("\n" + "=" * 60)
            print("检查 value_help 过滤器传递的值类型")
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
            page.goto('http://localhost:3004/user-permission?tab=user-groups', wait_until='networkidle', timeout=60000)
            page.wait_for_timeout(5000)

            # 3. 打开父组过滤器
            print("\n[步骤3] 打开父组过滤器...")
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

            # 4. 注入 JS 来监听 emit 的值
            print("\n[步骤4] 注入 JS 监听器...")
            page.evaluate("""() => {
                // 监听 headerFilterValues 的变化
                const origFetch = window.fetch;
                window._capturedRequests = [];
                window.fetch = function(...args) {
                    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url;
                    if (url && url.includes('user-group')) {
                        window._capturedRequests.push({
                            url: url,
                            method: args[1]?.method || 'GET',
                        });
                    }
                    return origFetch.apply(this, args);
                };

                // 监听 XMLHttpRequest
                const origXHROpen = XMLHttpRequest.prototype.open;
                const origXHRSend = XMLHttpRequest.prototype.send;
                XMLHttpRequest.prototype.open = function(method, url, ...rest) {
                    this._url = url;
                    this._method = method;
                    return origXHROpen.call(this, method, url, ...rest);
                };
                XMLHttpRequest.prototype.send = function(body) {
                    if (this._url && this._url.includes('user-group')) {
                        window._capturedRequests = window._capturedRequests || [];
                        window._capturedRequests.push({
                            url: this._url,
                            method: this._method,
                        });
                    }
                    return origXHRSend.call(this, body);
                };
            }""")

            # 5. 选择选项
            print("\n[步骤5] 选择选项...")
            el_select = page.locator('.filter-panel:visible .el-select')
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

            # 6. 检查 ValueHelpField 的值
            print("\n[步骤6] 检查 ValueHelpField 的值...")
            vh_value = page.evaluate("""() => {
                // 找到 value-help-field 组件
                const vhEl = document.querySelector('.filter-panel .value-help-field');
                if (!vhEl) return 'No value-help-field found';
                
                // 尝试获取 Vue 组件实例
                const vueInst = vhEl.__vue_parent_component || vhEl.__vue__;
                if (!vueInst) return 'No Vue instance';
                
                // 尝试获取 modelValue
                const props = vueInst.props || vueInst.$props;
                if (props) {
                    return {
                        modelValue: props.modelValue,
                        modelValueType: typeof props.modelValue,
                        isArray: Array.isArray(props.modelValue),
                    };
                }
                return 'No props found';
            }""")
            print(f"   ValueHelpField 值: {vh_value}")

            # 7. 点击确认按钮
            print("\n[步骤7] 点击确认按钮...")
            api_details.clear()

            confirm_btn = page.locator('.filter-panel:visible .el-button--primary')
            if confirm_btn.count() > 0 and confirm_btn.first.is_visible():
                confirm_btn.first.click()
                page.wait_for_timeout(3000)
                print("   [DECORATIVE] 点击了确认按钮")
            else:
                filter_panel = page.locator('.filter-panel:visible')
                if filter_panel.count() > 0:
                    filter_panel.first.click(position={'x': 10, 'y': 10})
                    page.wait_for_timeout(500)
                    if confirm_btn.count() > 0 and confirm_btn.first.is_visible():
                        confirm_btn.first.click()
                        page.wait_for_timeout(3000)

            # 8. 检查 API 请求
            print(f"\n[步骤8] API 请求详情: {len(api_details)} 个")
            for req in api_details:
                print(f"   - {req['method']} {req['url']}")

            # 9. 检查 headerFilterValues
            print("\n[步骤9] 检查 headerFilterValues...")
            hf_values = page.evaluate("""() => {
                // 尝试从 Vue 组件树获取 headerFilterValues
                const app = document.querySelector('#app');
                if (!app || !app.__vue_app__) return 'No Vue app';
                
                // 遍历 DOM 找到 MetaListPage 组件
                const table = document.querySelector('.el-table');
                if (!table) return 'No table found';
                
                // 尝试通过 __vue_parent_component 向上遍历
                let comp = table.__vue_parent_component;
                let depth = 0;
                let found = null;
                while (comp && depth < 20) {
                    const setupState = comp.setupState;
                    if (setupState && 'headerFilterValues' in setupState) {
                        found = {
                            headerFilterValues: setupState.headerFilterValues,
                            depth: depth,
                            componentName: comp.type?.name || comp.type?.__name || 'unknown',
                        };
                        break;
                    }
                    comp = comp.parent;
                    depth++;
                }
                
                if (!found) return 'headerFilterValues not found in component tree';
                
                const hfv = found.headerFilterValues;
                if (typeof hfv === 'object' && hfv !== null) {
                    const result = {};
                    for (const [key, val] of Object.entries(hfv)) {
                        if (key.startsWith('__')) continue;
                        result[key] = {
                            value: val,
                            type: typeof val,
                            isArray: Array.isArray(val),
                            length: Array.isArray(val) ? val.length : undefined,
                        };
                    }
                    return result;
                }
                return { raw: String(hfv) };
            }""")
            print(f"   headerFilterValues: {hf_values}")

            # 10. 截图
            print("\n[步骤10] 保存截图...")
            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           'test_vh_value_type_screenshot.png')
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"   [DECORATIVE] 截图保存到: {screenshot_path}")

        except Exception as e:
            print(f"\n[DECORATIVE] 测试失败: {e}")
            import traceback
            traceback.print_exc()

        finally:
            browser.close()


if __name__ == '__main__':
    test_value_help_value_type()
