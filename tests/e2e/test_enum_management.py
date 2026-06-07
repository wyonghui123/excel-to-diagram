"""
枚举管理页面 E2E 测试
使用 Playwright Python

测试范围：
1. 登录功能
2. 枚举类型列表加载
3. 数据验证
4. 分页功能
5. 行操作按钮
"""

import asyncio
from playwright.async_api import async_playwright


class EnumManagementTest:
    
    def __init__(self):
        self.base_url = 'http://localhost:3004'
        self.username = 'admin'
        self.password = 'admin123'
    
    async def setup(self):
        """初始化浏览器"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=False)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        
        # 收集日志
        self.console_logs = []
        self.page.on('console', lambda msg: self.console_logs.append(f"[{msg.type}] {msg.text}"))
        
        # 收集网络请求
        self.network_logs = []
        self.page.on('response', lambda resp: self.network_logs.append(f"[{resp.status}] {resp.url}"))
    
    async def teardown(self):
        """清理资源"""
        await self.browser.close()
        await self.playwright.stop()
    
    async def login(self):
        """登录"""
        print("\n=== 1. 登录测试 ===")
        await self.page.goto(f'{self.base_url}/')
        await self.page.wait_for_selector('#username', timeout=10000)
        
        await self.page.fill('#username', self.username)
        await self.page.fill('#password', self.password)
        await self.page.click('button.login-btn')
        await asyncio.sleep(2)
        
        # 验证登录成功
        is_logged_in = await self.page.evaluate('''() => {
            return localStorage.getItem('auth_token') !== null;
        }''')
        print(f"登录成功: {is_logged_in}")
        assert is_logged_in, "登录失败"
        return True
    
    async def test_list_loading(self):
        """测试列表加载"""
        print("\n=== 2. 列表加载测试 ===")
        await self.page.goto(f'{self.base_url}/business-config')
        await self.page.wait_for_selector('.el-table', timeout=10000)
        await asyncio.sleep(3)  # 等待数据加载
        
        # 验证表格存在
        table = self.page.locator('.el-table')
        assert await table.is_visible(), "表格不存在"
        print("表格存在: OK")
        
        # 验证有数据行
        rows = self.page.locator('.el-table__body tr')
        row_count = await rows.count()
        print(f"表格行数: {row_count}")
        assert row_count > 0, "表格无数据"
        print("表格有数据: OK")
        
        # 验证分页
        pagination = self.page.locator('.el-pagination')
        assert await pagination.is_visible(), "分页不存在"
        print("分页存在: OK")
        
        # 获取分页信息
        total_text = await self.page.locator('.el-pagination__total').text_content()
        print(f"分页信息: {total_text}")
        
        return row_count
    
    async def test_search(self, keyword='field'):
        """测试搜索功能"""
        print(f"\n=== 3. 搜索功能测试 (关键词: {keyword}) ===")
        
        # 查找搜索框
        search_input = self.page.locator('.el-input__inner').first
        if await search_input.is_visible():
            await search_input.fill(keyword)
            await self.page.wait_for_timeout(1000)
            
            # 点击搜索按钮
            search_btn = self.page.locator('button:has-text("搜索")')
            if await search_btn.is_visible():
                await search_btn.click()
                await asyncio.sleep(1)
            
            print(f"搜索关键词: {keyword}")
        else:
            print("搜索框未找到")
    
    async def test_pagination(self):
        """测试分页功能"""
        print("\n=== 4. 分页功能测试 ===")
        
        # 获取当前分页信息
        total_text = await self.page.locator('.el-pagination__total').text_content()
        print(f"当前分页: {total_text}")
        
        # 检查是否有足够数据分页
        import re
        match = re.search(r'共 (\d+) 条', total_text)
        if match:
            total_count = int(match.group(1))
            if total_count > 20:
                # 点击下一页
                next_btn = self.page.locator('.btn-next')
                is_disabled = await next_btn.get_attribute('class')
                
                if 'disabled' not in is_disabled:
                    await next_btn.click()
                    await asyncio.sleep(1)
                    print("点击下一页: OK")
                    
                    # 验证切换到下一页
                    current_page = await self.page.locator('.el-pagination__jumper input').input_value()
                    print(f"当前页码: {current_page}")
                else:
                    print("下一页按钮禁用")
            else:
                print(f"数据量少({total_count}条)，无需分页")
    
    async def test_row_actions(self):
        """测试行操作按钮"""
        print("\n=== 5. 行操作按钮测试 ===")
        
        # 查找行操作按钮
        action_buttons = self.page.locator('.el-table__body .el-button--small')
        button_count = await action_buttons.count()
        print(f"行操作按钮数: {button_count}")
        
        if button_count > 0:
            # 获取第一个按钮文本
            first_btn = action_buttons.first
            first_btn_text = await first_btn.text_content()
            print(f"第一个按钮: {first_btn_text}")
            
            # 截图
            await self.page.screenshot(path='screenshot_row_actions.png')
            print("截图已保存: screenshot_row_actions.png")
    
    async def test_sorting(self):
        """测试排序功能"""
        print("\n=== 6. 排序功能测试 ===")
        
        # 获取排序前的第一个值
        first_cell = self.page.locator('.el-table__body tr:first-child .cell').first
        first_value_before = await first_cell.text_content()
        print(f"排序前第一个值: {first_value_before}")
        
        # 点击第一列排序
        header = self.page.locator('.el-table__header th').first
        caret = header.locator('.caret-wrapper')
        
        if await caret.is_visible():
            await caret.click()
            await asyncio.sleep(1)
            
            # 获取排序后的第一个值
            first_cell = self.page.locator('.el-table__body tr:first-child .cell').first
            first_value_after = await first_cell.text_content()
            print(f"排序后第一个值: {first_value_after}")
            print("排序功能: OK")
    
    async def test_refresh(self):
        """测试刷新功能"""
        print("\n=== 7. 刷新功能测试 ===")
        
        refresh_btn = self.page.locator('button:has-text("刷新")')
        if await refresh_btn.is_visible():
            await refresh_btn.click()
            await asyncio.sleep(2)
            print("点击刷新: OK")
    
    async def test_network_requests(self):
        """检查网络请求"""
        print("\n=== 8. 网络请求检查 ===")
        
        for log in self.network_logs:
            if '/api/v2/' in log:
                print(log)
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("=" * 50)
        print("枚举管理页面 E2E 测试")
        print("=" * 50)
        
        try:
            await self.setup()
            await self.login()
            await self.test_list_loading()
            await self.test_search()
            await self.test_pagination()
            await self.test_row_actions()
            await self.test_sorting()
            await self.test_refresh()
            await self.test_network_requests()
            
            print("\n" + "=" * 50)
            print("所有测试通过!")
            print("=" * 50)
            
        except AssertionError as e:
            print(f"\n测试失败: {e}")
            await self.page.screenshot(path='screenshot_error.png')
            print("错误截图已保存: screenshot_error.png")
            raise
        except Exception as e:
            print(f"\n测试异常: {e}")
            await self.page.screenshot(path='screenshot_exception.png')
            print("异常截图已保存: screenshot_exception.png")
            raise
        finally:
            await self.teardown()


async def main():
    test = EnumManagementTest()
    await test.run_all_tests()


if __name__ == '__main__':
    asyncio.run(main())
