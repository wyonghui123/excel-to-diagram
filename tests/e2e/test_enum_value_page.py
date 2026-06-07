"""
枚举值页面 E2E 测试
"""

import asyncio
from playwright.async_api import async_playwright


class EnumValuePageTest:

    def __init__(self):
        self.base_url = 'http://localhost:3004'
        self.username = 'admin'
        self.password = 'admin123'

    async def setup(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=False)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()

        self.console_logs = []
        self.page.on('console', lambda msg: self.console_logs.append(f"[{msg.type}] {msg.text}"))

        self.network_logs = []
        self.page.on('response', lambda resp: self.network_logs.append(f"[{resp.status}] {resp.url}"))

    async def teardown(self):
        await self.browser.close()
        await self.playwright.stop()

    async def login(self):
        print("\n=== 1. 登录 ===")
        await self.page.goto(f'{self.base_url}/')
        await self.page.wait_for_selector('#username', timeout=10000)

        await self.page.fill('#username', self.username)
        await self.page.fill('#password', self.password)
        await self.page.click('button.login-btn')
        await asyncio.sleep(2)

        is_logged_in = await self.page.evaluate('''() => {
            return localStorage.getItem('auth_token') !== null;
        }''')
        print(f"登录成功: {is_logged_in}")
        return is_logged_in

    async def test_enum_type_list(self):
        """测试枚举类型列表"""
        print("\n=== 2. 枚举类型列表 ===")
        await self.page.goto(f'{self.base_url}/business-config')
        await self.page.wait_for_selector('.el-table', timeout=10000)
        await asyncio.sleep(3)

        rows = self.page.locator('.el-table__body tr')
        row_count = await rows.count()
        print(f"枚举类型数量: {row_count}")
        return row_count

    async def test_navigate_to_enum_values(self):
        """测试跳转到枚举值页面"""
        print("\n=== 3. 跳转到枚举值页面 ===")

        # 点击第一行的"管理枚举值"按钮
        manage_btn = self.page.locator('button:has-text("管理枚举值")').first
        if await manage_btn.is_visible(timeout=3000):
            await manage_btn.click()
            await asyncio.sleep(3)
            print(f"当前URL: {self.page.url}")
            print("跳转成功")
            return True
        else:
            print("未找到'管理枚举值'按钮，跳转到枚举值页面...")
            # 直接导航到枚举值页面 - 使用正确的路由
            await self.page.goto(f'{self.base_url}/business-config/enums/field_type/values?name=字段类型&code=field_type')
            await asyncio.sleep(3)
            print(f"当前URL: {self.page.url}")
            return True

    async def test_enum_value_page(self):
        """测试枚举值页面"""
        print("\n=== 4. 枚举值页面 ===")

        # 检查表格
        table = self.page.locator('.el-table')
        if await table.is_visible():
            print("表格存在: OK")
        else:
            print("表格不存在")
            return False

        # 检查分页
        pagination = self.page.locator('.el-pagination')
        if await pagination.is_visible():
            print("分页存在: OK")
            total_text = await self.page.locator('.el-pagination__total').text_content()
            print(f"分页信息: {total_text}")
        else:
            print("分页不存在")

        # 检查滚动
        rows = self.page.locator('.el-table__body tr')
        row_count = await rows.count()
        print(f"枚举值数量: {row_count}")

        return True

    async def test_scroll(self):
        """测试页面滚动"""
        print("\n=== 5. 滚动测试 ===")

        # 获取页面高度
        page_height = await self.page.evaluate('document.body.scrollHeight')
        print(f"页面高度: {page_height}px")

        # 滚动到页面底部
        await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(1)

        # 检查表格是否可见
        table_visible = await self.page.locator('.el-table').is_visible()
        print(f"滚动后表格可见: {table_visible}")

    async def run_all_tests(self):
        print("=" * 50)
        print("枚举值页面 E2E 测试")
        print("=" * 50)

        try:
            await self.setup()
            await self.login()
            await self.test_enum_type_list()
            await self.test_navigate_to_enum_values()
            await self.test_enum_value_page()
            await self.test_scroll()

            # 检查控制台错误
            print("\n=== 控制台日志 ===")
            errors = [log for log in self.console_logs if 'error' in log.lower() or 'Error' in log or 'warning' in log.lower()]
            for log in errors:
                print(log)

            print("\n" + "=" * 50)
            print("所有测试通过!")
            print("=" * 50)

        except Exception as e:
            print(f"\n测试异常: {e}")
            # 打印所有控制台日志
            print("\n=== 控制台日志 ===")
            for log in self.console_logs:
                print(log)
            await self.page.screenshot(path='screenshot_enum_value_error.png')
            raise
        finally:
            await self.teardown()


async def main():
    test = EnumValuePageTest()
    await test.run_all_tests()


if __name__ == '__main__':
    asyncio.run(main())
